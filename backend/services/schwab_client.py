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

    _store_tokens(token_data, db)
    logger.info("Schwab tokens exchanged and stored")


# ── Token storage ─────────────────────────────────────────────────────────────

def _store_tokens(token_data: dict, db: Session) -> None:
    """
    Encrypt and upsert tokens into schwab_tokens table.
    Accepts both direct OAuth responses (expires_in seconds) and schwab-py
    token dicts (expires_at as Unix float timestamp).
    """
    access_token  = _encrypt(token_data["access_token"])
    refresh_token = _encrypt(token_data["refresh_token"])

    # Compute expires_at ISO string
    if "expires_at" in token_data and isinstance(token_data["expires_at"], (int, float)):
        expires_dt = datetime.fromtimestamp(float(token_data["expires_at"]), tz=_ET)
    elif "expires_in" in token_data:
        expires_dt = datetime.now(_ET) + timedelta(seconds=int(token_data["expires_in"]))
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
    """
    row = db.query(SchwabToken).first()
    if not row:
        logger.debug("Schwab token refresh skipped — no tokens stored")
        return False

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
        return False


# ── Status ────────────────────────────────────────────────────────────────────

def get_status(db: Session) -> dict:
    """
    Return token status for the SCHWAB header indicator.
    States: 'connected' (green), 'aging' (amber), 'disconnected' (red).
    """
    row = db.query(SchwabToken).first()
    if not row:
        return {"connected": False, "state": "disconnected"}

    try:
        _decrypt(row.access_token)  # verify decryptable
        expires_at = datetime.fromisoformat(row.expires_at)
        now_et = datetime.now(_ET)

        # Access token expired?
        if expires_at < now_et:
            return {"connected": False, "state": "expired"}

        # Refresh token aging? (Schwab refresh tokens expire after 7 days)
        updated_utc = datetime.strptime(row.updated_at, "%Y-%m-%d %H:%M:%S").replace(
            tzinfo=timezone.utc
        )
        age_days = (datetime.now(timezone.utc) - updated_utc).days

        if age_days >= 6:
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
        return {
            "access_token":  _decrypt(r.access_token),
            "refresh_token": _decrypt(r.refresh_token),
            "token_type":    "Bearer",
            "expires_at":    expires_ts,
        }

    def _write(token_dict: dict):
        _store_tokens(token_dict, db)

    return schwab.auth.client_from_access_functions(
        SCHWAB_CLIENT_ID,
        SCHWAB_CLIENT_SECRET,
        token_read_func=_read,
        token_write_func=_write,
    )
