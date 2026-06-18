"""
schwab_client.py — Schwab OAuth token management and client factory.

Handles:
  - OAuth authorization URL generation
  - Auth code → token exchange (initial login)
  - Proactive access token refresh via refresh token
  - Fernet-encrypted token storage in Supabase (schwab_tokens table)
  - schwab-py client construction for Tasks 5.4+
  - Status reporting for SCHWAB header indicator
"""

import os
import base64
import logging
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from urllib.parse import urlencode

import httpx
import schwab
from cryptography.fernet import Fernet
from sqlalchemy.orm import Session

from models.schwab_tokens import SchwabToken

logger = logging.getLogger(__name__)
_ET = ZoneInfo("America/New_York")

SCHWAB_CLIENT_ID     = os.environ.get("SCHWAB_CLIENT_ID", "")
SCHWAB_CLIENT_SECRET = os.environ.get("SCHWAB_CLIENT_SECRET", "")
SCHWAB_CALLBACK_URL  = os.environ.get("SCHWAB_CALLBACK_URL", "")
_ENCRYPTION_KEY      = os.environ.get("SCHWAB_TOKEN_ENCRYPTION_KEY", "")

_AUTH_URL  = "https://api.schwabapi.com/v1/oauth/authorize"
_TOKEN_URL = "https://api.schwabapi.com/v1/oauth/token"


# ── Encryption helpers ────────────────────────────────────────────────────────

def _fernet() -> Fernet:
    key = _ENCRYPTION_KEY
    if isinstance(key, str):
        key = key.encode()
    return Fernet(key)


def _encrypt(text: str) -> str:
    return _fernet().encrypt(text.encode()).decode()


def _decrypt(text: str) -> str:
    return _fernet().decrypt(text.encode()).decode()


# ── OAuth flow ────────────────────────────────────────────────────────────────

def get_auth_url() -> str:
    """Return the Schwab OAuth authorization URL to redirect the browser to."""
    params = {
        "client_id":     SCHWAB_CLIENT_ID,
        "redirect_uri":  SCHWAB_CALLBACK_URL,
        "response_type": "code",
    }
    return f"{_AUTH_URL}?{urlencode(params)}"


def exchange_code_for_tokens(auth_code: str, db: Session) -> None:
    """
    Exchange the authorization code received in the callback for access +
    refresh tokens.  Stores them encrypted in Supabase.
    """
    credentials = base64.b64encode(
        f"{SCHWAB_CLIENT_ID}:{SCHWAB_CLIENT_SECRET}".encode()
    ).decode()

    with httpx.Client() as client:
        response = client.post(
            _TOKEN_URL,
            headers={
                "Authorization":  f"Basic {credentials}",
                "Content-Type":   "application/x-www-form-urlencoded",
            },
            data={
                "grant_type":   "authorization_code",
                "code":         auth_code,
                "redirect_uri": SCHWAB_CALLBACK_URL,
            },
        )
        response.raise_for_status()
        token_data = response.json()

    _store_tokens(token_data, db, is_full_oauth=True)
    logger.info("Schwab tokens exchanged and stored")


# ── Token storage ─────────────────────────────────────────────────────────────

def _store_tokens(token_data: dict, db: Session, is_full_oauth: bool = False) -> None:
    """
    Encrypt and upsert tokens into schwab_tokens table.
    Accepts both direct OAuth responses (expires_in seconds) and schwab-py
    token dicts (expires_at as Unix float timestamp).

    is_full_oauth=True: called after a new authorization_code exchange — resets
    created_at so the aging clock restarts from now.
    is_full_oauth=False (default): access-token refresh only — created_at unchanged,
    preserving the original refresh-token issue time for accurate age tracking.
    """
    # Handle new schwab-py token format: {"creation_timestamp": ..., "token": {...}}
    inner = token_data.get("token", token_data)

    access_token  = _encrypt(inner["access_token"])
    refresh_token = _encrypt(inner["refresh_token"])

    # Compute expires_at ISO string
    if "expires_at" in inner and isinstance(inner["expires_at"], (int, float)):
        expires_dt = datetime.fromtimestamp(float(inner["expires_at"]), tz=_ET)
    elif "expires_in" in inner:
        expires_dt = datetime.now(_ET) + timedelta(seconds=int(inner["expires_in"]))
    else:
        expires_dt = datetime.now(_ET) + timedelta(seconds=1800)  # 30-min default

    expires_at_str = expires_dt.isoformat()
    now_utc        = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")

    row = db.query(SchwabToken).first()
    if row:
        row.access_token  = access_token
        row.refresh_token = refresh_token
        row.expires_at    = expires_at_str
        row.updated_at    = now_utc
        if is_full_oauth:
            # Reset aging clock — a new refresh token was issued
            row.created_at = now_utc
            logger.info(f"OAuth exchange: created_at reset to {now_utc}")
    else:
        row = SchwabToken(
            access_token  = access_token,
            refresh_token = refresh_token,
            expires_at    = expires_at_str,
            created_at    = now_utc,
            updated_at    = now_utc,
        )
        db.add(row)
    db.commit()


def clear_tokens(db: Session) -> None:
    """Delete all stored tokens (logout)."""
    db.query(SchwabToken).delete()
    db.commit()
    logger.info("Schwab tokens cleared")


# ── Proactive refresh ─────────────────────────────────────────────────────────

def refresh_access_token(db: Session) -> bool:
    """
    Proactively refresh the access token using the stored refresh token.
    Called every 25 minutes by APScheduler.
    Returns True on success, False on failure (caller should log/alert).

    Idempotency guard: skips the Schwab call if the token was already refreshed
    within the last 10 minutes. Prevents the race condition where two concurrent
    scheduler instances (e.g., during a Fly.io rolling deploy) both use the same
    refresh token simultaneously — Schwab invalidates it after first use.
    """
    row = db.query(SchwabToken).first()
    if not row:
        logger.debug("Schwab token refresh skipped — no tokens stored")
        return False

    # Idempotency: skip if another instance refreshed recently
    try:
        last_refresh = datetime.strptime(row.updated_at, "%Y-%m-%d %H:%M:%S").replace(
            tzinfo=timezone.utc
        )
        seconds_since_refresh = (datetime.now(timezone.utc) - last_refresh).total_seconds()
        if seconds_since_refresh < 600:  # refreshed within the last 10 minutes
            logger.debug(
                f"Schwab token refresh skipped — refreshed {seconds_since_refresh:.0f}s ago"
            )
            return True
    except Exception:
        pass  # if updated_at can't be parsed, proceed with refresh attempt

    # Also skip if the access token is still valid with > 6 minutes to spare
    try:
        expires_at = datetime.fromisoformat(row.expires_at)
        time_left_s = (expires_at - datetime.now(_ET)).total_seconds()
        if time_left_s > 360:
            logger.debug(
                f"Schwab token refresh skipped — token valid for {time_left_s:.0f}s more"
            )
            return True
    except Exception:
        pass  # if expires_at can't be parsed, proceed with refresh attempt

    try:
        refresh_token = _decrypt(row.refresh_token)
    except Exception:
        logger.error("Schwab token refresh failed — decryption error")
        return False

    credentials = base64.b64encode(
        f"{SCHWAB_CLIENT_ID}:{SCHWAB_CLIENT_SECRET}".encode()
    ).decode()

    try:
        with httpx.Client() as client:
            response = client.post(
                _TOKEN_URL,
                headers={
                    "Authorization": f"Basic {credentials}",
                    "Content-Type":  "application/x-www-form-urlencoded",
                },
                data={
                    "grant_type":    "refresh_token",
                    "refresh_token": refresh_token,
                },
            )
            response.raise_for_status()
            token_data = response.json()

        _store_tokens(token_data, db)
        logger.info("Schwab access token refreshed successfully")
        return True

    except Exception as e:
        logger.error(f"Schwab token refresh failed: {e}")
        # Send immediate email if refresh token is definitively expired
        if "invalid_grant" in str(e).lower() or "invalid_grant" in str(getattr(e, 'response', '')):
            try:
                from services.email_alert import send_email
                send_email(
                    "Signal Matrix: Schwab data connection lost",
                    "The Schwab API connection has been interrupted (invalid_grant).\n\n"
                    "Signal Matrix is falling back to Yahoo Finance until you reconnect.\n\n"
                    "Reconnect here: https://api.signal.suttonmc.com/api/auth/schwab/login"
                )
                logger.info("Email sent: Schwab token expired")
            except Exception as email_err:
                logger.warning(f"Failed to send Schwab expiry email: {email_err}")
        return False


# ── Status ────────────────────────────────────────────────────────────────────

def get_status(db: Session) -> dict:
    """
    Return token status for the SCHWAB header indicator.
    States: 'connected' (green), 'aging' (amber), 'expired'/'disconnected' (red).

    RED means the refresh token is genuinely dead — re-auth required.
    GREEN/AMBER means the system will auto-recover on the next API call even if
    the access token has expired overnight (30-min lifetime).

    Clock source: updated_at — stamped on every successful token write (OAuth
    exchange or schwab-py auto-refresh during an API call). If updated_at is
    < 7 days ago the refresh token is still valid; >= 7 days → broken.
    The access token's expires_at is intentionally NOT checked here — an expired
    access token that will auto-recover via schwab-py should not show as red.
    """
    row = db.query(SchwabToken).first()
    if not row:
        return {"connected": False, "state": "disconnected"}

    try:
        _decrypt(row.access_token)  # verify decryptable / not corrupted

        last_write = datetime.strptime(row.updated_at, "%Y-%m-%d %H:%M:%S").replace(
            tzinfo=timezone.utc
        )
        days_since_write = (datetime.now(timezone.utc) - last_write).total_seconds() / 86400

        # Truly broken — refresh token has expired (7-day Schwab limit)
        if days_since_write >= 7:
            return {"connected": False, "state": "expired"}

        # Aging — approaching the 7-day limit, re-auth soon
        age_days = int(days_since_write)
        if days_since_write >= 6:
            return {"connected": True, "state": "aging", "age_days": age_days}

        return {"connected": True, "state": "connected", "age_days": age_days}

    except Exception:
        return {"connected": False, "state": "disconnected"}


# ── schwab-py client factory (used by Tasks 5.4+) ────────────────────────────

def get_schwab_client(db: Session) -> schwab.client.Client:
    """
    Build and return a configured schwab-py client using tokens from Supabase.
    The client auto-refreshes the access token via the write callback.
    Raises RuntimeError if no tokens are stored.
    """
    row = db.query(SchwabToken).first()
    if not row:
        raise RuntimeError("No Schwab tokens stored — OAuth required")

    def _read():
        r = db.query(SchwabToken).first()
        if not r:
            raise RuntimeError("No Schwab tokens")
        expires_ts = datetime.fromisoformat(r.expires_at).timestamp()
        # schwab-py now expects {"creation_timestamp": ..., "token": {...}}
        creation_ts = datetime.fromisoformat(r.updated_at).timestamp() if r.updated_at else expires_ts - 1800
        return {
            "creation_timestamp": creation_ts,
            "token": {
                "access_token":  _decrypt(r.access_token),
                "refresh_token": _decrypt(r.refresh_token),
                "token_type":    "Bearer",
                "expires_at":    expires_ts,
            },
        }

    def _write(token_dict: dict):
        _store_tokens(token_dict, db)

    return schwab.auth.client_from_access_functions(
        SCHWAB_CLIENT_ID,
        SCHWAB_CLIENT_SECRET,
        token_read_func=_read,
        token_write_func=_write,
    )
