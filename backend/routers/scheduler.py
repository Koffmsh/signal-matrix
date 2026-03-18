from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from database import get_db
from models.scheduler_log import SchedulerLog
from datetime import datetime, date
from zoneinfo import ZoneInfo
import services.scheduler as sched_svc

router = APIRouter(prefix="/api/scheduler", tags=["scheduler"])


@router.get("/status")
def get_scheduler_status(db: Session = Depends(get_db)):
    """
    Returns last run info for dashboard display.
    Read-only — no recalculation triggered.
    """
    today_str = date.today().strftime("%Y-%m-%d")
    et        = ZoneInfo("America/New_York")

    last     = db.query(SchedulerLog).order_by(SchedulerLog.id.desc()).first()
    today_ok = db.query(SchedulerLog).filter(
        SchedulerLog.run_date == today_str,
        SchedulerLog.status   == "success",
    ).first()

    # Next scheduled run time
    next_run = None
    job = sched_svc.scheduler.get_job("eod_job")
    if job and job.next_run_time:
        next_run = job.next_run_time.astimezone(et).strftime("%Y-%m-%d %H:%M:%S ET")

    # Last run time converted from UTC to ET
    last_run_time = None
    if last:
        try:
            dt_utc        = datetime.strptime(last.created_at, "%Y-%m-%d %H:%M:%S").replace(tzinfo=ZoneInfo("UTC"))
            last_run_time = dt_utc.astimezone(et).strftime("%H:%M:%S ET")
        except Exception:
            last_run_time = last.created_at

    return {
        "last_run_date":    last.run_date    if last else None,
        "last_run_status":  last.status      if last else None,
        "last_run_trigger": last.trigger     if last else None,
        "last_run_time":    last_run_time,
        "next_run_time":    next_run,
        "today_complete":   today_ok is not None,
    }
