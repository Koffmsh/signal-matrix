import json
import numpy as np
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from database import SessionLocal
from models.price_cache import PriceCache

router = APIRouter()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.get("/api/vol/spx-history")
def spx_vol_history(db: Session = Depends(get_db)):
    """
    Returns rolling HV30, HV90, and daily % change for SPX over the full price history.
    Computed on demand from price_cache.history_json — no vol_history dependency.
    """
    row = db.query(PriceCache).filter(PriceCache.ticker == "SPX").first()
    if not row or not row.history_json or not row.history_dates_json:
        return {"dates": [], "hv30": [], "hv90": [], "pct_change": [], "updated": None}

    closes = np.array(json.loads(row.history_json), dtype=float)
    dates  = json.loads(row.history_dates_json)

    if len(closes) != len(dates) or len(closes) < 2:
        return {"dates": [], "hv30": [], "hv90": [], "pct_change": [], "updated": None}

    # Daily log returns (one shorter than closes)
    log_rets = np.log(closes[1:] / closes[:-1])

    # Daily % change (arithmetic, shown as bars) — aligned to dates[1:]
    pct_change = ((closes[1:] - closes[:-1]) / closes[:-1] * 100).tolist()

    # Rolling HV30 — 21-day window × √252, annualised
    # Rolling HV90 — 63-day window × √252, annualised
    n = len(log_rets)
    hv30_series = [None] * n
    hv90_series = [None] * n

    for i in range(n):
        if i >= 20:   # need 21 returns (indices i-20 .. i)
            hv30_series[i] = round(float(np.std(log_rets[i-20:i+1], ddof=0) * (252**0.5) * 100), 2)
        if i >= 62:   # need 63 returns
            hv90_series[i] = round(float(np.std(log_rets[i-62:i+1], ddof=0) * (252**0.5) * 100), 2)

    # Dates align to closes[1:] (same as returns)
    chart_dates = dates[1:]

    return {
        "dates":      chart_dates,
        "hv30":       hv30_series,
        "hv90":       hv90_series,
        "pct_change": [round(p, 2) for p in pct_change],
        "updated":    row.updated_at.strftime("%m/%d/%y %H:%M") if row.updated_at else None,
    }
