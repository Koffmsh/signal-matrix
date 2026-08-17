"""
eod_alerts.py — End-of-day alert checks that run after calculate_signals.

Currently: TREND_DIRECTION_CHANGE — fires when the Trend timeframe direction
changes from the prior EOD value. Uses signal_output (current) vs
signal_history (prior day) for comparison.
"""

import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from models.signal_output import SignalOutput
from models.signal_history import SignalHistory
from models.user import User
from models.user_alert_subscription import UserAlertSubscription
from services.email_alert import send_email_to
from services.sms import send_sms_to

logger = logging.getLogger(__name__)
_ET = ZoneInfo("America/New_York")


def _load_alert_recipients(db: Session, alert_type: str) -> dict:
    """Load delivery targets for a single alert type."""
    bucket = {"emails": [], "phones": []}
    rows = (
        db.query(UserAlertSubscription, User)
        .join(User, User.id == UserAlertSubscription.user_id)
        .filter(
            UserAlertSubscription.alert_type == alert_type,
            UserAlertSubscription.enabled.is_(True),
            User.status == "active",
        )
        .all()
    )
    for sub, user in rows:
        if user.alert_email_enabled and user.email:
            bucket["emails"].append(user.email)
        if user.alert_sms_enabled and user.phone:
            bucket["phones"].append(user.phone)
    return bucket


def _dispatch(bucket: dict, subject: str, message: str) -> bool:
    if not bucket["emails"] and not bucket["phones"]:
        return False
    sent = False
    for email in bucket["emails"]:
        send_email_to(email, subject, message)
        sent = True
    if bucket["phones"]:
        send_sms_to(bucket["phones"], message)
        sent = True
    return sent


def _fmt_price(p: float) -> str:
    return f"${p:,.2f}"


def check_trend_direction_changes(db: Session) -> dict:
    """
    Compare current signal_output trend directions vs prior day's signal_history.
    Fires TREND_DIRECTION_CHANGE alerts for any tickers whose Trend direction changed.

    Two modes:
      - Provisional (day 1): today's trend dir differs from yesterday's
      - Confirmed (day 2): yesterday's trend dir ALSO differed from 2 days ago
        (meaning yesterday was day 1, and today confirms the change persisted)
    """
    now_et = datetime.now(_ET)
    today = now_et.strftime("%Y-%m-%d")

    bucket = _load_alert_recipients(db, "TREND_DIRECTION_CHANGE")
    if not bucket["emails"] and not bucket["phones"]:
        logger.info("EOD alerts: no TREND_DIRECTION_CHANGE subscribers — skipping")
        return {"alerts_sent": 0}

    # Current trend directions from signal_output
    current_trend = {
        r.ticker: r.trade_direction
        for r in db.query(SignalOutput).filter(
            SignalOutput.timeframe == "trend",
        ).all()
    }

    # Find the two most recent distinct snapshot dates BEFORE today
    prior_dates = (
        db.query(SignalHistory.snapshot_date)
        .filter(
            SignalHistory.snapshot_date < today,
            SignalHistory.timeframe == "trend",
        )
        .distinct()
        .order_by(SignalHistory.snapshot_date.desc())
        .limit(2)
        .all()
    )
    prior_dates = [r[0] for r in prior_dates]

    if not prior_dates:
        logger.info("EOD alerts: no prior signal_history — skipping trend direction check")
        return {"alerts_sent": 0}

    # Yesterday's trend directions
    yesterday_date = prior_dates[0]
    yesterday_trend = {
        r.ticker: r.trade_direction
        for r in db.query(SignalHistory).filter(
            SignalHistory.snapshot_date == yesterday_date,
            SignalHistory.timeframe == "trend",
        ).all()
    }

    # Day-before-yesterday's trend directions (for confirmation check)
    day_before_trend = {}
    if len(prior_dates) >= 2:
        day_before_date = prior_dates[1]
        day_before_trend = {
            r.ticker: r.trade_direction
            for r in db.query(SignalHistory).filter(
                SignalHistory.snapshot_date == day_before_date,
                SignalHistory.timeframe == "trend",
            ).all()
        }

    alerts_sent = 0

    for ticker, cur_dir in current_trend.items():
        prev_dir = yesterday_trend.get(ticker)
        if prev_dir is None or cur_dir == prev_dir:
            continue

        # Direction changed — check if this is day 1 (provisional) or day 2 (confirmed)
        db_dir = day_before_trend.get(ticker)
        if db_dir is not None and prev_dir != db_dir and cur_dir == prev_dir:
            # Yesterday was already different from day-before, and today matches yesterday
            # → this is confirmation of yesterday's change
            mode = "confirmed"
        else:
            mode = "provisional"

        if mode == "provisional":
            subject = f"📊 {ticker} — TREND DIRECTION CHANGE (provisional)"
            msg = (
                f"📊 {ticker} — TREND DIRECTION CHANGE\n"
                f"Trend direction changed: {prev_dir} → {cur_dir}\n"
                f"Provisional — watching for confirmation on next trading day.\n"
                f"[Trend tf — EOD signal]"
            )
        else:
            subject = f"📊 {ticker} — TREND DIRECTION CONFIRMED"
            msg = (
                f"📊 {ticker} — TREND DIRECTION CONFIRMED\n"
                f"Trend direction change confirmed: now {cur_dir}\n"
                f"(Changed from {db_dir} → held for 2 consecutive days)\n"
                f"[Trend tf — EOD signal]"
            )

        _dispatch(bucket, subject, msg)
        alerts_sent += 1
        logger.info(
            f"EOD alert TREND_DIRECTION_CHANGE: {ticker} "
            f"{prev_dir} → {cur_dir} ({mode})"
        )

    logger.info(f"EOD alerts: {alerts_sent} trend direction change alerts sent")
    return {"alerts_sent": alerts_sent}
