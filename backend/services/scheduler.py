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

    cutoff_et = now_et.replace(hour=16, minute=15, second=0, microsecond=0)

    if now_et < cutoff_et:
        logger.info("Scheduler: startup catchup — before 4:15 PM ET, scheduler will fire normally")
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
    await loop.run_in_executor(None, lambda: run_eod_job("catchup"))


def start() -> None:
    scheduler.add_job(
        run_eod_job,
        CronTrigger(hour=16, minute=15, timezone="America/New_York"),
        id="eod_job",
        replace_existing=True,
    )
    scheduler.start()
    logger.info("Scheduler: started — EOD job registered for 4:15 PM ET")


def shutdown() -> None:
    scheduler.shutdown(wait=False)
    logger.info("Scheduler: stopped")
