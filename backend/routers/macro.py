import json
import logging

import numpy as np
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session, load_only
from database import SessionLocal
from datetime import datetime
from zoneinfo import ZoneInfo

from models.price_cache import PriceCache
from models.signal_output import SignalOutput
from models.quad_settings import QuadSettings
from models.ticker import Ticker

_ET = ZoneInfo("America/New_York")

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
def macro_correlations(live: bool = Query(False), db: Session = Depends(get_db)):
    all_tickers = [_CORRELATION_BASE] + [t["ticker"] for t in _CORRELATION_TICKERS]

    rows = (
        db.query(PriceCache)
        .filter(PriceCache.ticker.in_(all_tickers))
        .options(load_only(
            PriceCache.ticker,
            PriceCache.history_json,
            PriceCache.history_dates_json,
            PriceCache.updated_at,
            PriceCache.close,
        ))
        .all()
    )

    live_prices = {}
    if live:
        try:
            from services.schwab_client import get_schwab_client
            from services.schwab_market_data import get_schwab_symbol
            client = get_schwab_client(db)
            schwab_syms = [get_schwab_symbol(t) for t in all_tickers]
            resp = client.get_quotes(schwab_syms)
            assert resp.status_code == 200
            quotes = resp.json()
            for tk in all_tickers:
                ss = get_schwab_symbol(tk)
                q = quotes.get(ss, {}).get("quote", {})
                price = q.get("lastPrice")
                if price:
                    live_prices[tk] = price
        except Exception as e:
            logger.warning(f"Correlation live quotes failed: {e} — falling back to cached")

        # Yahoo fallback for SCHWAB_UNSUPPORTED tickers (DXY, SPX, /CL, /GC, etc.)
        missing = [t for t in all_tickers if t not in live_prices]
        if missing:
            try:
                import yfinance as yf
                from services.yahoo_finance import get_yahoo_symbol
                for tk in missing:
                    try:
                        ysym = get_yahoo_symbol(tk)
                        info = yf.Ticker(ysym).fast_info
                        price = getattr(info, "last_price", None)
                        if price:
                            live_prices[tk] = price
                    except Exception:
                        pass
            except Exception as e:
                logger.warning(f"Yahoo correlation fallback failed: {e}")

    now_et = datetime.now(_ET)
    today_str = now_et.strftime("%Y-%m-%d")

    cache = {}
    updated = None
    for row in rows:
        if not row.history_json or not row.history_dates_json:
            continue
        closes = json.loads(row.history_json)
        dates = json.loads(row.history_dates_json)
        if len(closes) != len(dates) or len(closes) < 20:
            continue
        if live and row.ticker in live_prices:
            if dates and dates[-1] == today_str:
                closes[-1] = live_prices[row.ticker]
            else:
                dates.append(today_str)
                closes.append(live_prices[row.ticker])
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

    # DXY context: chart data + signal summary
    dxy_ctx = None
    dxy_price = (
        db.query(PriceCache)
        .filter(PriceCache.ticker == _CORRELATION_BASE)
        .options(load_only(
            PriceCache.ticker, PriceCache.close,
            PriceCache.history_json, PriceCache.history_dates_json,
            PriceCache.spark_json,
        ))
        .first()
    )
    if dxy_price and dxy_price.history_json and dxy_price.history_dates_json:
        dxy_dates = json.loads(dxy_price.history_dates_json)
        dxy_closes = json.loads(dxy_price.history_json)
        # last 1 year (~252 trading days)
        n = min(252, len(dxy_dates))
        dxy_ctx = {
            "close": dxy_price.close,
            "chart_dates": dxy_dates[-n:],
            "chart_closes": dxy_closes[-n:],
        }
        # Signal data
        sigs = (
            db.query(SignalOutput)
            .filter(SignalOutput.ticker == _CORRELATION_BASE)
            .options(load_only(
                SignalOutput.timeframe, SignalOutput.viewpoint,
                SignalOutput.conviction, SignalOutput.trade_direction,
                SignalOutput.quad_alignment, SignalOutput.quad_score,
                SignalOutput.lrr, SignalOutput.hrr,
            ))
            .all()
        )
        sig_map = {s.timeframe: s for s in sigs}
        trade = sig_map.get("trade")
        trend = sig_map.get("trend")
        if trade:
            dxy_ctx["viewpoint"] = trade.viewpoint
            dxy_ctx["conviction"] = trade.conviction
            dxy_ctx["trade_dir"] = trade.trade_direction
            dxy_ctx["quad_alignment"] = trade.quad_alignment
            dxy_ctx["quad_score"] = trade.quad_score
            dxy_ctx["lrr"] = trade.lrr
            dxy_ctx["hrr"] = trade.hrr
        if trend:
            dxy_ctx["trend_dir"] = trend.trade_direction

        # Ticker metadata for quad text
        tk_row = db.query(Ticker).filter(Ticker.ticker == _CORRELATION_BASE).first()
        if tk_row:
            dxy_ctx["sector"] = tk_row.sector
            dxy_ctx["asset_class"] = tk_row.asset_class

        # Current US monthly quad
        now_et = datetime.now(_ET)
        cur_month = now_et.strftime("%Y-%m")
        quad_row = db.query(QuadSettings).filter(
            QuadSettings.country == "US",
            QuadSettings.forecast_month == cur_month,
            QuadSettings.quad_type == "monthly",
        ).first()
        if quad_row:
            dxy_ctx["quad"] = quad_row.quad
            dxy_ctx["quad_prob"] = quad_row.probability

    result = {"base": _CORRELATION_BASE, "rows": result_rows, "updated": updated, "dxy": dxy_ctx}
    if live:
        result["mode"] = "live"
        result["refreshed_at"] = now_et.strftime("%I:%M %p ET").lstrip("0")
    else:
        result["mode"] = "eod"
        result["refreshed_at"] = None
    return result
