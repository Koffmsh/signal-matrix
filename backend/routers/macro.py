import json
import logging

import numpy as np
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session, load_only
from database import SessionLocal
from models.price_cache import PriceCache

logger = logging.getLogger(__name__)

router = APIRouter()

_CORRELATION_BASE = "DXY"

_CORRELATION_TICKERS = [
    {"ticker": "SPX",  "label": "S&P 500"},
    {"ticker": "/CL",  "label": "Crude Oil"},
    {"ticker": "DBC",  "label": "Commodities"},
    {"ticker": "/GC",  "label": "Gold"},
    {"ticker": "IBIT", "label": "Bitcoin"},
]

_WINDOWS = [15, 30, 90, 120, 180]
_ROLLING_WINDOW = 30
_ROLLING_LOOKBACK = 252


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _pearson_corr(x: np.ndarray, y: np.ndarray) -> float | None:
    if len(x) < 5 or len(x) != len(y):
        return None
    sx, sy = np.std(x, ddof=0), np.std(y, ddof=0)
    if sx == 0 or sy == 0:
        return None
    return float(np.corrcoef(x, y)[0, 1])


def _compute_correlations(base_dates, base_closes, tk_dates, tk_closes):
    base_map = dict(zip(base_dates, base_closes))
    tk_map = dict(zip(tk_dates, tk_closes))

    common = sorted(set(base_dates) & set(tk_dates))
    if len(common) < 20:
        return None

    b_arr = np.array([base_map[d] for d in common], dtype=float)
    t_arr = np.array([tk_map[d] for d in common], dtype=float)

    n = len(b_arr)

    window_corrs = {}
    for w in _WINDOWS:
        if n >= w:
            window_corrs[f"{w}D"] = round(_pearson_corr(b_arr[-w:], t_arr[-w:]), 2)
        else:
            window_corrs[f"{w}D"] = None

    rolling_high = None
    rolling_low = None
    time_pos = None
    time_neg = None

    lookback = min(_ROLLING_LOOKBACK, n - _ROLLING_WINDOW + 1)
    if lookback >= 1 and n >= _ROLLING_WINDOW:
        start = n - lookback - _ROLLING_WINDOW + 1
        if start < 0:
            start = 0
            lookback = n - _ROLLING_WINDOW + 1

        rolling_vals = []
        for i in range(start, start + lookback):
            end = i + _ROLLING_WINDOW
            if end > n:
                break
            c = _pearson_corr(b_arr[i:end], t_arr[i:end])
            if c is not None:
                rolling_vals.append(c)

        if rolling_vals:
            rolling_high = round(max(rolling_vals), 2)
            rolling_low = round(min(rolling_vals), 2)
            pos = sum(1 for v in rolling_vals if v > 0)
            total = len(rolling_vals)
            time_pos = round(pos / total * 100)
            time_neg = 100 - time_pos

    return {
        **window_corrs,
        "rolling_high": rolling_high,
        "rolling_low": rolling_low,
        "time_pos": time_pos,
        "time_neg": time_neg,
    }


@router.get("/api/macro/correlations")
def macro_correlations(db: Session = Depends(get_db)):
    all_tickers = [_CORRELATION_BASE] + [t["ticker"] for t in _CORRELATION_TICKERS]

    rows = (
        db.query(PriceCache)
        .filter(PriceCache.ticker.in_(all_tickers))
        .options(load_only(
            PriceCache.ticker,
            PriceCache.history_json,
            PriceCache.history_dates_json,
            PriceCache.updated_at,
        ))
        .all()
    )

    cache = {}
    updated = None
    for row in rows:
        if not row.history_json or not row.history_dates_json:
            continue
        closes = json.loads(row.history_json)
        dates = json.loads(row.history_dates_json)
        if len(closes) != len(dates) or len(closes) < 20:
            continue
        cache[row.ticker] = (dates, np.array(closes, dtype=float))
        if row.ticker == _CORRELATION_BASE and row.updated_at:
            updated = row.updated_at.strftime("%m/%d/%y %H:%M")

    if _CORRELATION_BASE not in cache:
        return {"base": _CORRELATION_BASE, "rows": [], "updated": None}

    base_dates, base_closes = cache[_CORRELATION_BASE]

    result_rows = []
    for t in _CORRELATION_TICKERS:
        tk = t["ticker"]
        if tk not in cache:
            result_rows.append({"ticker": tk, "label": t["label"], "data": None})
            continue

        tk_dates, tk_closes = cache[tk]
        corrs = _compute_correlations(base_dates, base_closes, tk_dates, tk_closes)
        result_rows.append({"ticker": tk, "label": t["label"], "data": corrs})

    return {"base": _CORRELATION_BASE, "rows": result_rows, "updated": updated}
