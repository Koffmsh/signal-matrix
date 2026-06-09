import json
import bisect
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import numpy as np
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from database import SessionLocal
from models.price_cache import PriceCache

router = APIRouter()
_ET = ZoneInfo("America/New_York")

# Tickers shown on the Macro Volatility chart (order matters for legend)
_MACRO_VOL_TICKERS = ["VIX", "VXN", "RVX", "GVZ", "OVX", "MOVE"]


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


@router.get("/api/vol/macro-history")
def macro_vol_history(db: Session = Depends(get_db)):
    """
    Returns close price history + stats table for the Macro Volatility dashboard.
    Tickers: VIX, VXN, RVX, GVZ, OVX, MOVE.

    Response:
      dates   — shared date axis (intersection of all available dates)
      series  — {ticker: [close, ...]} aligned to dates
      stats   — {ticker: {last, day1, wk1, mo1, mo3, dod_delta, dod_pct,
                           wow_delta, wow_pct, mom_delta, mom_pct}}
      updated — ET timestamp of most recent data fetch
    """
    rows = (
        db.query(PriceCache)
        .filter(PriceCache.ticker.in_(_MACRO_VOL_TICKERS))
        .all()
    )

    # Build per-ticker {date: close} maps
    ticker_data: dict[str, tuple[list, list]] = {}  # ticker -> (dates, closes)
    updated_at = None

    for row in rows:
        if not row.history_json or not row.history_dates_json:
            continue
        closes = json.loads(row.history_json)
        dates  = json.loads(row.history_dates_json)
        if len(closes) != len(dates) or len(closes) < 2:
            continue
        ticker_data[row.ticker] = (dates, closes)
        if row.updated_at and (updated_at is None or row.updated_at > updated_at):
            updated_at = row.updated_at

    if not ticker_data:
        return {"dates": [], "series": {}, "stats": {}, "updated": None}

    # Union all date arrays — each ticker fills None for dates it lacks.
    # Avoids one stale ticker dragging the entire chart back to its last date.
    common_dates = sorted(set().union(*[set(d) for d, _ in ticker_data.values()]))

    if not common_dates:
        return {"dates": [], "series": {}, "stats": {}, "updated": None}

    # Build aligned series — None where a ticker has no data for that date
    series: dict[str, list] = {}
    for ticker, (dates, closes) in ticker_data.items():
        date_to_close = dict(zip(dates, closes))
        series[ticker] = [
            round(date_to_close[d], 2) if d in date_to_close else None
            for d in common_dates
        ]

    # ── Stats table ──────────────────────────────────────────────────────────
    def _find_price_n_days_ago(dates: list, closes: list, n_calendar_days: int) -> float | None:
        """Return the last close strictly before `n_calendar_days` ago."""
        today = datetime.now(_ET).date()
        target = (today - timedelta(days=n_calendar_days)).isoformat()
        # Find the last date <= target
        idx = bisect.bisect_right(dates, target) - 1
        return round(closes[idx], 2) if idx >= 0 else None

    stats: dict[str, dict] = {}
    for ticker, (dates, closes) in ticker_data.items():
        last = round(closes[-1], 2) if closes else None
        prev = round(closes[-2], 2) if len(closes) >= 2 else None
        wk1  = _find_price_n_days_ago(dates, closes, 7)
        mo1  = _find_price_n_days_ago(dates, closes, 30)
        mo3  = _find_price_n_days_ago(dates, closes, 91)

        def _delta(ref):
            if last is None or ref is None or ref == 0:
                return None, None
            d = round(last - ref, 2)
            p = round(d / ref * 100, 2)
            return d, p

        dod_d, dod_p = _delta(prev)
        wow_d, wow_p = _delta(wk1)
        mom_d, mom_p = _delta(mo1)

        stats[ticker] = {
            "last":      last,
            "day1":      prev,
            "wk1":       wk1,
            "mo1":       mo1,
            "mo3":       mo3,
            "dod_delta": dod_d,
            "dod_pct":   dod_p,
            "wow_delta": wow_d,
            "wow_pct":   wow_p,
            "mom_delta": mom_d,
            "mom_pct":   mom_p,
        }

    updated_str = updated_at.strftime("%m/%d/%y %H:%M") if updated_at else None

    return {
        "dates":   common_dates,
        "series":  series,
        "stats":   stats,
        "updated": updated_str,
    }
