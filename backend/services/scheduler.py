import asyncio
import logging
import time
from datetime import datetime, date
from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
import pandas_market_calendars as mcal

from database import SessionLocal
from routers.market_data import refresh_data
from routers.signals import calculate_signals
from models.scheduler_log import SchedulerLog
import services.schwab_client as schwab_client
from services.schwab_market_data import schwab_fetch_all
from services.schwab_options import schwab_fetch_iv, accumulate_hv_only
from services.intraday_monitor import run_intraday_check
from services.spx_constituents import compute_and_cache_spx_impact, compute_and_cache_spx_impact_intraday

logger = logging.getLogger(__name__)

# Cache NYSE calendar at module level — never reinstantiate on job runs
_nyse = mcal.get_calendar("NYSE")

scheduler = AsyncIOScheduler(timezone="America/New_York")


def _is_trading_day(check_date: date) -> bool:
    schedule = _nyse.schedule(
        start_date=check_date.strftime("%Y-%m-%d"),
        end_date=check_date.strftime("%Y-%m-%d"),
    )
    return not schedule.empty


def run_eod_job(trigger: str = "scheduled") -> None:
    """
    Core EOD job — sync, safe to run in APScheduler thread pool.
    1. Confirm today is a NYSE trading day
    2. Run refresh_data (REFRESH DATA equivalent)
    3. Run calculate_signals (CALCULATE SIGNALS equivalent)
    4. Write result to scheduler_log
    """
    # Use ET date throughout — NYSE trading days are ET-based
    et_date = datetime.now(ZoneInfo("America/New_York")).date()

    if not _is_trading_day(et_date):
        logger.info(f"Scheduler: {et_date} is not a trading day — skipping")
        return

    logger.info(f"Scheduler: starting EOD job (trigger={trigger})")
    t0 = time.monotonic()

    db         = SessionLocal()
    refresh_ok = False
    signals_ok = False
    error_msg  = None
    status     = "failure"

    try:
        result     = refresh_data(db)
        refresh_ok = not result.get("rate_limited", False)
        logger.info(f"Scheduler: refresh complete — {result['count']} tickers")

        sig        = calculate_signals(db, trigger=trigger)
        signals_ok = sig["output"]["errors"] == 0
        logger.info(f"Scheduler: signals complete — {sig['output']['calculated']} tickers")

        status = "success"

    except Exception as e:
        error_msg = str(e)
        logger.error(f"Scheduler: EOD job failed — {e}")

    finally:
        duration = round(time.monotonic() - t0, 2)
        db.add(SchedulerLog(
            run_date   = et_date.strftime("%Y-%m-%d"),
            trigger    = trigger,
            status     = status,
            refresh_ok = refresh_ok,
            signals_ok = signals_ok,
            error_msg  = error_msg,
            duration_s = duration,
            created_at = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
        ))
        db.commit()
        db.close()
        logger.info(f"Scheduler: job complete — status={status}, duration={duration}s")


async def run_catchup_on_startup() -> None:
    """
    On startup, check if today's EOD job was missed and run it if so.
    Only fires if: trading day + past 4:15 PM ET + no successful run today.
    """
    et        = ZoneInfo("America/New_York")
    now_et    = datetime.now(et)
    today_et  = now_et.date()   # ET date — consistent with run_date storage

    if not _is_trading_day(today_et):
        logger.info("Scheduler: startup catchup — not a trading day")
        return

    cutoff_et = now_et.replace(hour=16, minute=0, second=0, microsecond=0)

    if now_et < cutoff_et:
        logger.info("Scheduler: startup catchup — before 4:00 PM ET, scheduler will fire normally")
        return

    # Past cutoff — check if already ran successfully today
    db = SessionLocal()
    try:
        already_ran = db.query(SchedulerLog).filter(
            SchedulerLog.run_date == today_et.strftime("%Y-%m-%d"),
            SchedulerLog.status   == "success",
        ).first()
    finally:
        db.close()

    if already_ran:
        logger.info(f"Scheduler: startup catchup — already ran today at {already_ran.created_at}")
        return

    logger.info("Scheduler: startup catchup — running missed EOD job")
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, schwab_data_job)


def _refresh_schwab_tokens_job() -> None:
    """Proactive Schwab token refresh — runs every 25 minutes."""
    db = SessionLocal()
    try:
        schwab_client.refresh_access_token(db)
    finally:
        db.close()


def _schwab_token_age_alert_job() -> None:
    """
    Daily 9 AM ET — check Schwab refresh token age and send email if expiry is near.
    Schwab refresh tokens have a hard 7-day limit from the last full OAuth exchange.
    Alert at day 5 (warning) and day 6+ (urgent daily reminder).
    """
    from services.email_alert import send_email
    db = SessionLocal()
    try:
        status = schwab_client.get_status(db)
        age    = status.get("age_days", 0)
        state  = status.get("state", "connected")

        reauth_url = "https://api.signal.suttonmc.com/api/auth/schwab/login"

        if state in ("expired", "disconnected"):
            send_email(
                "Signal Matrix: Schwab token expired — re-auth required",
                f"The Schwab token has expired and data is falling back to Yahoo Finance.\n\n"
                f"Re-authenticate now: {reauth_url}"
            )
            logger.warning("Token age alert: token expired — email sent")
        elif age >= 6:
            send_email(
                f"Signal Matrix: Schwab token expires tomorrow (day {age})",
                f"Your Schwab token is {age} days old and expires tomorrow.\n\n"
                f"Re-authenticate now to avoid a data gap: {reauth_url}"
            )
            logger.warning(f"Token age alert: day {age} (urgent) — email sent")
        elif age >= 5:
            send_email(
                f"Signal Matrix: Schwab token aging (day {age}) — re-auth in 2 days",
                f"Your Schwab token is {age} days old. Schwab tokens expire after 7 days.\n\n"
                f"Re-authenticate within 2 days: {reauth_url}"
            )
            logger.info(f"Token age alert: day {age} (warning) — email sent")
    except Exception as e:
        logger.error(f"Token age alert job failed: {e}")
    finally:
        db.close()


def schwab_data_job() -> None:
    """
    4:00 PM ET — full EOD job: prices → IV → signals in one pass.
    Chaining signals immediately after fetch eliminates the 15-min gap
    and ensures REFRESH DATA + CALCULATE SIGNALS both go green together.
    Falls back to Yahoo Finance automatically if Schwab is unavailable.
    Only runs on NYSE trading days.
    """
    et_date = datetime.now(ZoneInfo("America/New_York")).date()
    if not _is_trading_day(et_date):
        logger.info("Schwab data job: not a trading day — skipping")
        return

    logger.info("Schwab data job: starting EOD job (prices → IV → signals)")
    db         = SessionLocal()
    refresh_ok = False
    signals_ok = False
    error_msg  = None
    status     = "failure"
    t0         = time.monotonic()

    try:
        # 1. Prices
        result     = schwab_fetch_all(db)
        refresh_ok = result.get("errors", 0) == 0
        logger.info(
            f"Schwab data job: prices complete — "
            f"fetched={result.get('fetched', 0)}, errors={result.get('errors', 0)}, "
            f"source={result.get('data_source', 'unknown')}"
        )

        # 2. IV — Schwab options chain for IV-eligible tickers
        iv_result = schwab_fetch_iv(db)
        logger.info(
            f"Schwab data job: IV complete — "
            f"fetched={iv_result.get('fetched', 0)}, errors={iv_result.get('errors', 0)}"
        )

        # 2b. HV-only — Yahoo-routed tickers (SPX, NDX, RUT, VIX, futures, FX)
        hv_result = accumulate_hv_only(db)
        logger.info(
            f"Schwab data job: HV-only complete — "
            f"written={hv_result.get('written', 0)}, updated={hv_result.get('skipped', 0)}"
        )

        # 3. Signals — immediately after prices + IV are written
        sig        = calculate_signals(db, trigger="scheduled")
        signals_ok = sig["output"]["errors"] == 0
        logger.info(f"Schwab data job: signals complete — {sig['output']['calculated']} tickers")

        # 4. SPX constituent impact — one Schwab batch call, ~2s, non-fatal
        try:
            spx_result = compute_and_cache_spx_impact(db)
            logger.info(f"Schwab data job: SPX impact complete — {spx_result}")
        except Exception as _e:
            logger.warning(f"Schwab data job: SPX impact failed (non-fatal) — {_e}")

        status = "success"

    except Exception as e:
        error_msg = str(e)
        logger.error(f"Schwab data job: EOD job failed — {e}")

    finally:
        duration = round(time.monotonic() - t0, 2)
        db.add(SchedulerLog(
            run_date   = et_date.strftime("%Y-%m-%d"),
            trigger    = "scheduled",
            status     = status,
            refresh_ok = refresh_ok,
            signals_ok = signals_ok,
            error_msg  = error_msg,
            duration_s = duration,
            created_at = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
        ))
        db.commit()
        db.close()
        logger.info(f"Schwab data job: complete — status={status}, duration={duration}s")


def _spx_impact_intraday_job(label: str) -> None:
    """Compute and cache an intraday SPX impact snapshot (11am or 1pm ET)."""
    now_et = datetime.now(ZoneInfo("America/New_York"))
    if not _is_trading_day(now_et.date()):
        return
    db = SessionLocal()
    try:
        result = compute_and_cache_spx_impact_intraday(db, label)
        logger.info(f"SPX impact {label}: {result}")
    except Exception as e:
        logger.warning(f"SPX impact {label} job failed (non-fatal): {e}")
    finally:
        db.close()


def _intraday_monitor_job() -> None:
    """
    Fires at :00/:15/:30/:45 each hour, 9:30 AM–3:45 PM ET, NYSE trading days only.
    CronTrigger aligns to clock boundaries so the first fire is exactly 9:30 AM.
    An interval trigger would fire relative to container start time and could miss open.
    """
    now_et  = datetime.now(ZoneInfo("America/New_York"))
    et_date = now_et.date()

    # NYSE trading days only — CronTrigger handles the clock, this handles holidays
    if not _is_trading_day(et_date):
        return

    # Skip the two pre-market fires (9:00 and 9:15) that the cron pattern includes
    # CronTrigger hour=9-15 minute=0,15,30,45 fires at 9:00 and 9:15 before open
    if now_et.hour == 9 and now_et.minute < 30:
        return

    db = SessionLocal()
    try:
        result = run_intraday_check(db)
        logger.info(
            f"Intraday monitor: {result.get('tickers_checked', 0)} checked, "
            f"{result.get('alerts_sent', 0)} alerts sent"
        )
    except Exception as e:
        logger.error(f"Intraday monitor job failed: {e}")
    finally:
        db.close()


def start() -> None:
    scheduler.add_job(
        schwab_data_job,
        CronTrigger(hour=16, minute=0, timezone="America/New_York"),
        id="schwab_data_job",
        replace_existing=True,
    )
    scheduler.add_job(
        _refresh_schwab_tokens_job,
        "interval",
        minutes=25,
        id="schwab_refresh",
        replace_existing=True,
    )
    scheduler.add_job(
        _intraday_monitor_job,
        # Fires at :00/:15/:30/:45 from 9 AM–3 PM, plus 9:30–9:45 via minute=30,45 at hour=9
        # Effective market-hours range: 9:30, 9:45, 10:00 … 15:30, 15:45
        # hour=9  minute=30,45  → 9:30, 9:45
        # hour=10-15 minute=0,15,30,45 → 10:00 … 15:45
        CronTrigger(
            day_of_week = "mon-fri",
            hour        = "9-15",
            minute      = "0,15,30,45",
            timezone    = "America/New_York",
        ),
        id="intraday_monitor",
        replace_existing=True,
    )
    scheduler.add_job(
        lambda: _spx_impact_intraday_job("11am"),
        CronTrigger(day_of_week="mon-fri", hour=11, minute=0, timezone="America/New_York"),
        id="spx_impact_11am",
        replace_existing=True,
    )
    scheduler.add_job(
        lambda: _spx_impact_intraday_job("1pm"),
        CronTrigger(day_of_week="mon-fri", hour=13, minute=0, timezone="America/New_York"),
        id="spx_impact_1pm",
        replace_existing=True,
    )
    scheduler.add_job(
        _schwab_token_age_alert_job,
        CronTrigger(hour=9, minute=0, timezone="America/New_York"),
        id="schwab_token_age_alert",
        replace_existing=True,
    )
    scheduler.start()
    logger.info(
        "Scheduler: started — EOD job 4:00 PM ET (prices→IV→signals), "
        "Schwab token refresh every 25 min, "
        "intraday monitor 9:30 AM–3:45 PM ET at :00/:15/:30/:45 (trading days), "
        "token age alert 9:00 AM daily"
    )


def shutdown() -> None:
    scheduler.shutdown(wait=False)
    logger.info("Scheduler: stopped")
