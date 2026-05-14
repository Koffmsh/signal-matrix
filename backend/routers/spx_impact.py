import json
from datetime import datetime
from zoneinfo import ZoneInfo
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from database import SessionLocal
from models.spx_impact_cache import SpxImpactCache

router = APIRouter()
_ET = ZoneInfo("America/New_York")


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _serialize(row) -> dict | None:
    if not row:
        return None
    return {
        "computed_date":  row.computed_date,
        "snapshot_label": row.snapshot_label,
        "contributors":   json.loads(row.contributors_json),
        "detractors":     json.loads(row.detractors_json),
        "spx_return_pct": row.spx_return_pct,
        "tickers_priced": row.tickers_priced,
        "updated_at":     row.updated_at.strftime("%m/%d/%y %H:%M") if row.updated_at else None,
    }


@router.get("/api/spx-impact")
def get_spx_impact(db: Session = Depends(get_db)):
    """
    Returns the most recent EOD snapshot plus any intraday snapshots for today.
    Frontend receives { eod, "11am", "1pm" } — null when not yet computed.
    """
    today_et = datetime.now(_ET).strftime("%Y-%m-%d")

    eod_row = db.query(SpxImpactCache).filter(
        SpxImpactCache.snapshot_label == "eod"
    ).order_by(SpxImpactCache.computed_date.desc()).first()

    intraday_rows = db.query(SpxImpactCache).filter(
        SpxImpactCache.snapshot_label.in_(["11am", "1pm"]),
        SpxImpactCache.computed_date == today_et,
    ).all()

    intraday = {row.snapshot_label: row for row in intraday_rows}

    return {
        "eod":  _serialize(eod_row),
        "11am": _serialize(intraday.get("11am")),
        "1pm":  _serialize(intraday.get("1pm")),
    }
