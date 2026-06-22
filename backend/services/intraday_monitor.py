"""
intraday_monitor.py — Lightweight intraday price monitor.

Runs every 15 minutes during NYSE trading hours (9:30 AM–3:45 PM ET).
Does NOT recalculate pivots, Hurst, or full conviction engine.
Reads EOD-calculated signal state and watches current price against it.

Two triggers (each fires at most once per ticker per day):

  PROXIMITY      — prox >= 0.85 toward entry zone
                   Bullish: prox = 1 - (close - lrr) / (hrr - lrr)   peaks at LRR
                   Bearish: prox =     (close - lrr) / (hrr - lrr)   peaks at HRR
                   Not clamped — price below LRR (Bullish) reports as 110%+ etc.

  RETRACEMENT_50 — price retraces 50% from D back toward C (pullback entry)
                   Uptrend:   level = pivot_c + 0.50 × (d_eff - pivot_c)
                              fires when close <= level
                   Downtrend: level = d_eff  + 0.50 × (pivot_c - d_eff)
                              fires when close >= level
                   d_eff = max/min(stored pivot_d, current close) — intraday D may be higher/lower
                   Gate:  structural_state must be UPTREND_VALID or DOWNTREND_VALID
                   Dedup key includes pivot_c — new C = new setup, resets the alert

Entry point: run_intraday_check(db)
"""

import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from models.price_cache import PriceCache
from models.signal_output import SignalOutput
from models.signal_pivots import SignalPivots
from models.intraday_alert_log import IntradayAlertLog
from models.user import User
from models.user_alert_subscription import UserAlertSubscription
from services.schwab_market_data import schwab_fetch_intraday_quotes, yahoo_fetch_intraday_quotes
from services.sms import send_sms_to
from services.email_alert import send_email_to

logger = logging.getLogger(__name__)
_ET = ZoneInfo("America/New_York")

_PROX_THRESHOLD      = 0.85
_VALID_STATES        = {"UPTREND_VALID", "DOWNTREND_VALID"}


def _load_alert_recipients(db: Session) -> dict:
    """Build per-alert-type delivery lists from user subscriptions + channel prefs.

    Returns { alert_type: {"emails": [...], "phones": [...]} }. An alert with no
    subscribers (or with subscribers who have no channel enabled) simply won't
    appear / will have empty lists — nothing sends. This is the per-user
    replacement for the old hardcoded delivery flags: opt-in via the Alert
    Settings page, default off.
    """
    recipients: dict = {}
    rows = (
        db.query(UserAlertSubscription, User)
        .join(User, User.id == UserAlertSubscription.user_id)
        .filter(
            UserAlertSubscription.enabled.is_(True),
            User.status == "active",
        )
        .all()
    )
    for sub, user in rows:
        bucket = recipients.setdefault(sub.alert_type, {"emails": [], "phones": []})
        if user.alert_email_enabled and user.email:
            bucket["emails"].append(user.email)
        if user.alert_sms_enabled and user.phone:
            bucket["phones"].append(user.phone)
    return recipients


def _dispatch(bucket: dict, subject: str, message: str) -> bool:
    """Send a fired alert to all resolved recipients. Returns True if any channel
    had recipients (SMS may still no-op while globally disabled)."""
    if not bucket:
        return False
    sent = False
    for email in bucket.get("emails", []):
        send_email_to(email, subject, message)
        sent = True
    phones = bucket.get("phones", [])
    if phones:
        send_sms_to(phones, message)
        sent = True
    return sent


# ── Proximity ─────────────────────────────────────────────────────────────────

def _compute_prox(close: float, lrr: float, hrr: float, viewpoint: str) -> float | None:
    """
    Direction-aware proximity. Not clamped — reports >1.0 when price passes through
    the entry level (e.g. close below LRR on a Bullish ticker = 110%+).
    Returns None if range is invalid.
    """
    rng = hrr - lrr
    if rng <= 0:
        return None
    if viewpoint == "Bullish":
        return 1.0 - (close - lrr) / rng
    else:  # Bearish
        return (close - lrr) / rng


# ── Retracement ───────────────────────────────────────────────────────────────

def _compute_retrace(
    close: float,
    pivot_c: float,
    pivot_d: float | None,
    structural_state: str,
) -> tuple[float | None, float | None]:
    """
    Compute the 50% retracement level and current retrace %.
    Uses intraday close to extend D if price is making new highs/lows today.
    Returns (level_50, retrace_pct) — both None if conditions not met.
    """
    if structural_state not in _VALID_STATES or pivot_d is None or pivot_c is None:
        return None, None

    if structural_state == "UPTREND_VALID":
        d_eff   = max(pivot_d, close)          # intraday high may exceed stored D
        dc_range = d_eff - pivot_c
        if dc_range <= 0:
            return None, None
        level_50   = pivot_c + 0.50 * dc_range
        retrace_pct = (d_eff - close) / dc_range   # 0 at D, 1.0 at C
        return level_50, retrace_pct

    else:  # DOWNTREND_VALID
        d_eff   = min(pivot_d, close)          # intraday low may exceed stored D
        dc_range = pivot_c - d_eff
        if dc_range <= 0:
            return None, None
        level_50   = d_eff + 0.50 * dc_range
        retrace_pct = (close - d_eff) / dc_range   # 0 at D, 1.0 at C
        return level_50, retrace_pct


# ── Deduplication ─────────────────────────────────────────────────────────────

def _already_fired(
    db: Session,
    today: str,
    ticker: str,
    alert_type: str,
    pivot_c: float | None,
) -> bool:
    """Return True if this alert already fired today for this ticker/type/C combo."""
    q = db.query(IntradayAlertLog).filter(
        IntradayAlertLog.ticker     == ticker,
        IntradayAlertLog.alert_date == today,
        IntradayAlertLog.alert_type == alert_type,
    )
    if pivot_c is not None:
        q = q.filter(IntradayAlertLog.pivot_c == pivot_c)
    return q.first() is not None


def _log_alert(
    db: Session,
    today: str,
    now_str: str,
    ticker: str,
    alert_type: str,
    price: float,
    metric: float | None,
    conviction: float | None,
    pivot_c: float | None,
) -> None:
    """Write fired alert to log. Uses merge to handle any race condition."""
    try:
        db.add(IntradayAlertLog(
            ticker     = ticker,
            alert_date = today,
            alert_type = alert_type,
            pivot_c    = pivot_c,
            fired_at   = now_str,
            price      = price,
            metric     = metric,
            conviction = conviction,
            created_at = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
        ))
        db.flush()
    except Exception:
        db.rollback()
        logger.debug(f"Alert log already exists for {ticker}/{alert_type} — skipping duplicate")


# ── SMS formatting ─────────────────────────────────────────────────────────────

def _fmt_price(p: float) -> str:
    return f"${p:,.2f}"


def _proximity_message(
    ticker: str, viewpoint: str, close: float,
    lrr: float, hrr: float, prox: float, conviction: float | None,
) -> str:
    entry_level = lrr if viewpoint == "Bullish" else hrr
    conv_str    = f" | Conv {int(conviction)}%" if conviction else ""
    return (
        f"⚡ {ticker} — ENTRY ZONE ({viewpoint})\n"
        f"{_fmt_price(close)} near {_fmt_price(entry_level)} | Prox {prox * 100:.0f}%{conv_str}\n"
        f"Range: {_fmt_price(lrr)} – {_fmt_price(hrr)}\n"
        f"[Trade tf — EOD structure]"
    )


def _retrace_message(
    ticker: str, viewpoint: str, close: float,
    pivot_c: float, pivot_d: float, level_50: float, retrace_pct: float,
    conviction: float | None,
) -> str:
    conv_str  = f" | Conv {int(conviction)}%" if conviction else ""
    move_word = "pullback" if viewpoint == "Bullish" else "bounce"
    return (
        f"📐 {ticker} — 50% RETRACE ({viewpoint})\n"
        f"{_fmt_price(close)} at 50% {move_word} from D {_fmt_price(pivot_d)}\n"
        f"C: {_fmt_price(pivot_c)} | 50% level: {_fmt_price(level_50)}{conv_str}\n"
        f"[Trade tf — EOD structure]"
    )


# ── Main entry point ───────────────────────────────────────────────────────────

def run_intraday_check(db: Session) -> dict:
    """
    Lightweight intraday monitor — called every 15 minutes during market hours.
    1. Refresh prices (fast — skip/append path, no history API calls)
    2. Read signal_output (EOD state, read-only)
    3. Read signal_pivots (D and structural_state, read-only)
    4. Evaluate PROXIMITY and RETRACEMENT_50 triggers
    5. Send SMS + log for any new alerts
    Returns summary dict for scheduler logging.
    """
    now_et  = datetime.now(_ET)
    today   = now_et.strftime("%Y-%m-%d")
    now_str = now_et.strftime("%H:%M")

    alerts_sent = 0
    tickers_checked = 0

    # ── Step 1: Refresh prices ────────────────────────────────────────────────
    # Two passes:
    #   a) schwab_fetch_intraday_quotes() — Schwab-supported equities/ETFs (~70 tickers)
    #      Always calls get_quotes(), uses lastPrice only, no cache_date update.
    #   b) yahoo_fetch_intraday_quotes()  — Yahoo-only tickers (indices, FX, futures, ~11 tickers)
    #      Uses fetch_ticker_close() (5-day yfinance), no cache_date update.
    try:
        schwab_fetch_intraday_quotes(db)
    except Exception as e:
        logger.error(f"Intraday monitor: Schwab price refresh failed — {e}")
        return {"alerts_sent": 0, "error": str(e)}

    try:
        yahoo_fetch_intraday_quotes(db)
    except Exception as e:
        logger.warning(f"Intraday monitor: Yahoo price refresh failed — {e} (continuing)")

    # ── Step 2: Load signal_output (trade tf, non-Neutral viewpoints only) ───
    outputs = {
        r.ticker: r
        for r in db.query(SignalOutput).filter(
            SignalOutput.timeframe == "trade",
            SignalOutput.viewpoint.in_(["Bullish", "Bearish"]),
        ).all()
    }

    if not outputs:
        logger.info("Intraday monitor: no non-Neutral tickers — skipping")
        return {"alerts_sent": 0}

    # ── Delivery recipients (per-user subscriptions) ─────────────────────────
    alert_recipients = _load_alert_recipients(db)
    if not alert_recipients:
        logger.info("Intraday monitor: no alert subscribers — evaluating skipped")
        return {"alerts_sent": 0}

    # ── Step 3: Load signal_pivots (trade tf) ────────────────────────────────
    pivots = {
        r.ticker: r
        for r in db.query(SignalPivots).filter(
            SignalPivots.timeframe == "trade",
            SignalPivots.ticker.in_(list(outputs.keys())),
        ).all()
    }

    # ── Step 4: Load current prices ──────────────────────────────────────────
    prices = {
        r.ticker: r
        for r in db.query(PriceCache).filter(
            PriceCache.ticker.in_(list(outputs.keys()))
        ).all()
    }

    # ── Step 5: Evaluate triggers ─────────────────────────────────────────────
    for ticker, sig in outputs.items():
        pc  = prices.get(ticker)
        piv = pivots.get(ticker)
        if not pc or not sig.lrr or not sig.hrr:
            continue

        close     = pc.close
        viewpoint = sig.viewpoint
        tickers_checked += 1

        # ── PROXIMITY ────────────────────────────────────────────────────────
        prox_bucket = alert_recipients.get("PROXIMITY")
        if prox_bucket:
            prox = _compute_prox(close, sig.lrr, sig.hrr, viewpoint)
            if prox is not None and prox >= _PROX_THRESHOLD:
                if not _already_fired(db, today, ticker, "PROXIMITY", None):
                    msg = _proximity_message(
                        ticker, viewpoint, close,
                        sig.lrr, sig.hrr, prox, sig.conviction,
                    )
                    _dispatch(prox_bucket, f"⚡ {ticker} — ENTRY ZONE ({viewpoint})", msg)
                    _log_alert(db, today, now_str, ticker, "PROXIMITY",
                               close, prox, sig.conviction, None)
                    alerts_sent += 1
                    logger.info(f"Intraday alert PROXIMITY: {ticker} prox={prox:.2f}")

        # ── RETRACEMENT_50 ───────────────────────────────────────────────────
        retrace_bucket = alert_recipients.get("RETRACEMENT_50")
        if retrace_bucket and piv and piv.pivot_c is not None and piv.pivot_d is not None:
            level_50, retrace_pct = _compute_retrace(
                close, piv.pivot_c, piv.pivot_d, piv.structural_state or "",
            )

            if level_50 is not None:
                triggered = (
                    (piv.structural_state == "UPTREND_VALID"   and viewpoint == "Bullish" and close <= level_50) or
                    (piv.structural_state == "DOWNTREND_VALID" and viewpoint == "Bearish" and close >= level_50)
                )
                conviction_ok = sig.conviction is not None and sig.conviction >= 85.0
                if triggered and conviction_ok and not _already_fired(db, today, ticker, "RETRACEMENT_50", piv.pivot_c):
                    # Use stored D for display (clean EOD reference)
                    msg = _retrace_message(
                        ticker, viewpoint, close,
                        piv.pivot_c, piv.pivot_d, level_50, retrace_pct or 0.0,
                        sig.conviction,
                    )
                    _dispatch(retrace_bucket, f"📐 {ticker} — 50% RETRACE ({viewpoint})", msg)
                    _log_alert(db, today, now_str, ticker, "RETRACEMENT_50",
                               close, retrace_pct, sig.conviction, piv.pivot_c)
                    alerts_sent += 1
                    logger.info(
                        f"Intraday alert RETRACEMENT_50: "
                        f"{ticker} close={close} level_50={level_50:.2f}"
                    )

    db.commit()
    logger.info(
        f"Intraday check complete: {tickers_checked} tickers checked, "
        f"{alerts_sent} alerts sent ({now_str} ET)"
    )
    return {"alerts_sent": alerts_sent, "tickers_checked": tickers_checked}
