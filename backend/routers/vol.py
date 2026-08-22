import json
import bisect
import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import numpy as np
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from database import SessionLocal
from models.price_cache import PriceCache
from services.fred import fetch_fred_series

logger = logging.getLogger(__name__)

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
        ticker_data[row.ticker] = (dates, closes, row.close)
        if row.updated_at and (updated_at is None or row.updated_at > updated_at):
            updated_at = row.updated_at

    if not ticker_data:
        return {"dates": [], "series": {}, "stats": {}, "updated": None}

    # Union all date arrays — each ticker fills None for dates it lacks.
    # Avoids one stale ticker dragging the entire chart back to its last date.
    common_dates = sorted(set().union(*[set(d) for d, _, _c in ticker_data.values()]))

    if not common_dates:
        return {"dates": [], "series": {}, "stats": {}, "updated": None}

    # Build aligned series — None where a ticker has no data for that date
    series: dict[str, list] = {}
    for ticker, (dates, closes, _cur) in ticker_data.items():
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
    for ticker, (dates, closes, cur_close) in ticker_data.items():
        # Use price_cache.close as the canonical "last" — same source as the dashboard gauge.
        last = round(cur_close, 2) if cur_close is not None else (round(closes[-1], 2) if closes else None)
        # Prior Day = the bar before "last" in the series the user sees.
        # Discriminate by VALUE, not wall-clock date: when history already contains the
        # "last" bar (EOD — cur_close == closes[-1]), prior day is closes[-2]; when cur_close
        # is a newer intraday bar not yet appended to history, prior day is closes[-1].
        # The old `dates[-1] >= today_et` check collapsed prev→last whenever the page was
        # viewed on any calendar day after the last bar (weekend/holiday/next morning),
        # zeroing out every ticker's DoD.
        last_hist = round(closes[-1], 2) if closes else None
        if last is not None and last_hist is not None and last == last_hist:
            prev = round(closes[-2], 2) if len(closes) >= 2 else None
        else:
            prev = last_hist
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


@router.get("/api/vol/bond-history")
def bond_vol_history(db: Session = Depends(get_db)):
    """
    Returns close price history + stats for the MOVE index (ICE BofA MOVE —
    Treasury implied volatility).  Same response shape as macro-history but
    with a single ticker so the frontend can render it on a dedicated chart.
    """
    row = (
        db.query(PriceCache)
        .filter(PriceCache.ticker == "MOVE")
        .first()
    )
    if not row or not row.history_json or not row.history_dates_json:
        return {"dates": [], "series": {}, "stats": {}, "updated": None}

    closes = json.loads(row.history_json)
    dates  = json.loads(row.history_dates_json)
    if len(closes) != len(dates) or len(closes) < 2:
        return {"dates": [], "series": {}, "stats": {}, "updated": None}

    cur_close = row.close

    series_aligned = [round(c, 2) for c in closes]

    # ── Stats ────────────────────────────────────────────────────────────────
    def _find_price_n_days_ago(d_list, c_list, n_calendar_days):
        today = datetime.now(_ET).date()
        target = (today - timedelta(days=n_calendar_days)).isoformat()
        idx = bisect.bisect_right(d_list, target) - 1
        return round(c_list[idx], 2) if idx >= 0 else None

    last = round(cur_close, 2) if cur_close is not None else round(closes[-1], 2)
    last_hist = round(closes[-1], 2)
    if last == last_hist:
        prev = round(closes[-2], 2) if len(closes) >= 2 else None
    else:
        prev = last_hist

    wk1 = _find_price_n_days_ago(dates, closes, 7)
    mo1 = _find_price_n_days_ago(dates, closes, 30)
    mo3 = _find_price_n_days_ago(dates, closes, 91)

    def _delta(ref):
        if last is None or ref is None or ref == 0:
            return None, None
        d = round(last - ref, 2)
        p = round(d / ref * 100, 2)
        return d, p

    dod_d, dod_p = _delta(prev)
    wow_d, wow_p = _delta(wk1)
    mom_d, mom_p = _delta(mo1)

    stats = {
        "MOVE": {
            "last": last, "day1": prev, "wk1": wk1, "mo1": mo1, "mo3": mo3,
            "dod_delta": dod_d, "dod_pct": dod_p,
            "wow_delta": wow_d, "wow_pct": wow_p,
            "mom_delta": mom_d, "mom_pct": mom_p,
        },
    }

    updated_str = row.updated_at.strftime("%m/%d/%y %H:%M") if row.updated_at else None

    return {
        "dates":   dates,
        "series":  {"MOVE": series_aligned},
        "stats":   stats,
        "updated": updated_str,
    }


# ── Yield Curve ──────────────────────────────────────────────────────────────

_YIELD_TICKERS = ["TWO", "TNX"]
_FRED_DGS2 = "DGS2"


@router.get("/api/vol/yield-curve-history")
def yield_curve_history(db: Session = Depends(get_db)):
    """
    Returns close price history + computed 2-10 spread for TWO (2Y yield) and
    TNX (10Y yield).  Response shape matches macro-history: union dates, per-
    ticker series, a synthetic SPREAD series, and stats.

    TWO sourced from FRED DGS2 (Yahoo 2YY=F delivers degraded stale data).
    TNX sourced from price_cache (Yahoo ^TNX is clean daily data).
    """
    ticker_data: dict[str, tuple[list, list, float | None]] = {}
    updated_at = None

    # ── TWO + TNX from price_cache (TWO is FRED-sourced, TNX is Yahoo) ──
    rows = (
        db.query(PriceCache)
        .filter(PriceCache.ticker.in_(_YIELD_TICKERS))
        .all()
    )
    for row in rows:
        if not row.history_json or not row.history_dates_json:
            continue
        closes = json.loads(row.history_json)
        dates  = json.loads(row.history_dates_json)
        if len(closes) != len(dates) or len(closes) < 2:
            continue
        ticker_data[row.ticker] = (dates, closes, row.close)
        if row.updated_at and (updated_at is None or row.updated_at > updated_at):
            updated_at = row.updated_at

    # ── Fallback: if TWO not in price_cache (first run), fetch FRED live ─
    if "TWO" not in ticker_data:
        try:
            two_dates, two_values = fetch_fred_series(_FRED_DGS2)
            if two_dates and two_values and len(two_dates) >= 2:
                ticker_data["TWO"] = (two_dates, two_values, two_values[-1])
        except Exception:
            logger.warning("FRED DGS2 live fallback failed for yield curve TWO")

    if not ticker_data:
        return {"dates": [], "series": {}, "stats": {}, "updated": None}

    common_dates = sorted(set().union(*[set(d) for d, _, _c in ticker_data.values()]))
    if not common_dates:
        return {"dates": [], "series": {}, "stats": {}, "updated": None}

    series: dict[str, list] = {}
    for ticker, (dates, closes, _cur) in ticker_data.items():
        date_to_close = dict(zip(dates, closes))
        series[ticker] = [
            round(date_to_close[d], 4) if d in date_to_close else None
            for d in common_dates
        ]

    # Compute 2-10 spread = TNX - TWO (in percentage points)
    if "TNX" in series and "TWO" in series:
        spread = []
        for i in range(len(common_dates)):
            t10 = series["TNX"][i]
            t2  = series["TWO"][i]
            if t10 is not None and t2 is not None:
                spread.append(round(t10 - t2, 4))
            else:
                spread.append(None)
        series["SPREAD"] = spread

    # ── Stats ────────────────────────────────────────────────────────────────
    def _find_price_n_days_ago(d_list, c_list, n_calendar_days):
        today = datetime.now(_ET).date()
        target = (today - timedelta(days=n_calendar_days)).isoformat()
        idx = bisect.bisect_right(d_list, target) - 1
        return round(c_list[idx], 4) if idx >= 0 else None

    stats: dict[str, dict] = {}
    for ticker, (dates, closes, cur_close) in ticker_data.items():
        last = round(cur_close, 4) if cur_close is not None else (round(closes[-1], 4) if closes else None)
        last_hist = round(closes[-1], 4) if closes else None
        if last is not None and last_hist is not None and last == last_hist:
            prev = round(closes[-2], 4) if len(closes) >= 2 else None
        else:
            prev = last_hist
        wk1 = _find_price_n_days_ago(dates, closes, 7)
        mo1 = _find_price_n_days_ago(dates, closes, 30)
        mo3 = _find_price_n_days_ago(dates, closes, 91)

        def _delta(ref):
            if last is None or ref is None or ref == 0:
                return None, None
            d = round(last - ref, 4)
            p = round(d / ref * 100, 2)
            return d, p

        dod_d, dod_p = _delta(prev)
        wow_d, wow_p = _delta(wk1)
        mom_d, mom_p = _delta(mo1)

        stats[ticker] = {
            "last": last, "day1": prev, "wk1": wk1, "mo1": mo1, "mo3": mo3,
            "dod_delta": dod_d, "dod_pct": dod_p,
            "wow_delta": wow_d, "wow_pct": wow_p,
            "mom_delta": mom_d, "mom_pct": mom_p,
        }

    # Spread stats (synthetic — computed from TWO + TNX stats)
    if "TNX" in stats and "TWO" in stats:
        s10 = stats["TNX"]
        s2  = stats["TWO"]
        sp_last = round(s10["last"] - s2["last"], 4) if s10["last"] is not None and s2["last"] is not None else None
        sp_prev = round(s10["day1"] - s2["day1"], 4) if s10["day1"] is not None and s2["day1"] is not None else None
        sp_wk1  = round(s10["wk1"]  - s2["wk1"],  4) if s10["wk1"]  is not None and s2["wk1"]  is not None else None
        sp_mo1  = round(s10["mo1"]  - s2["mo1"],  4) if s10["mo1"]  is not None and s2["mo1"]  is not None else None
        sp_mo3  = round(s10["mo3"]  - s2["mo3"],  4) if s10["mo3"]  is not None and s2["mo3"]  is not None else None

        def _sp_delta(cur, ref):
            if cur is None or ref is None:
                return None, None
            d = round(cur - ref, 4)
            p = round(d / abs(ref) * 100, 2) if ref != 0 else None
            return d, p

        sp_dod_d, sp_dod_p = _sp_delta(sp_last, sp_prev)
        sp_wow_d, sp_wow_p = _sp_delta(sp_last, sp_wk1)
        sp_mom_d, sp_mom_p = _sp_delta(sp_last, sp_mo1)

        stats["SPREAD"] = {
            "last": sp_last, "day1": sp_prev, "wk1": sp_wk1, "mo1": sp_mo1, "mo3": sp_mo3,
            "dod_delta": sp_dod_d, "dod_pct": sp_dod_p,
            "wow_delta": sp_wow_d, "wow_pct": sp_wow_p,
            "mom_delta": sp_mom_d, "mom_pct": sp_mom_p,
        }

    yc_updated = updated_at.strftime("%m/%d/%y %H:%M") if updated_at else None

    return {
        "dates":   common_dates,
        "series":  series,
        "stats":   stats,
        "updated": yc_updated,
    }


# ── HY Credit ──────────────────────────────────────────────────────────────────

_FRED_HY_OAS = "BAMLH0A0HYM2"


@router.get("/api/vol/hy-credit-history")
def hy_credit_history(db: Session = Depends(get_db)):
    """
    Returns HY OAS (FRED) + HYG price history for the HY Credit dashboard.
    OAS = bps on left axis, HYG price on right axis.
    """
    # ── HYG from price_cache ────────────────────────────────────────────────
    hyg_row = db.query(PriceCache).filter(PriceCache.ticker == "HYG").first()

    hyg_dates, hyg_closes, hyg_cur_close = [], [], None
    updated_at = None

    if hyg_row and hyg_row.history_json and hyg_row.history_dates_json:
        hyg_closes = json.loads(hyg_row.history_json)
        hyg_dates  = json.loads(hyg_row.history_dates_json)
        hyg_cur_close = hyg_row.close
        if len(hyg_closes) != len(hyg_dates) or len(hyg_closes) < 2:
            hyg_dates, hyg_closes = [], []
        if hyg_row.updated_at:
            updated_at = hyg_row.updated_at

    # ── HY OAS from price_cache (FRED-sourced, already in bps) ──────────
    oas_dates, oas_values = [], []
    oas_row = db.query(PriceCache).filter(PriceCache.ticker == "HY_OAS").first()
    if oas_row and oas_row.history_json and oas_row.history_dates_json:
        oas_values = json.loads(oas_row.history_json)
        oas_dates  = json.loads(oas_row.history_dates_json)
        if len(oas_values) != len(oas_dates) or len(oas_values) < 2:
            oas_dates, oas_values = [], []
        if oas_row.updated_at and (updated_at is None or oas_row.updated_at > updated_at):
            updated_at = oas_row.updated_at

    # Fallback: if HY_OAS not in price_cache (first run), fetch FRED live
    if not oas_dates:
        try:
            oas_dates, oas_raw = fetch_fred_series(_FRED_HY_OAS)
            oas_values = [v * 100 for v in oas_raw]
        except Exception:
            logger.warning("FRED HY OAS live fallback failed")

    if not oas_dates and not hyg_dates:
        return {"dates": [], "series": {}, "stats": {}, "updated": None}

    # ── Union dates ─────────────────────────────────────────────────────────
    all_date_sets = []
    if oas_dates:
        all_date_sets.append(set(oas_dates))
    if hyg_dates:
        all_date_sets.append(set(hyg_dates))
    common_dates = sorted(set().union(*all_date_sets)) if all_date_sets else []

    if not common_dates:
        return {"dates": [], "series": {}, "stats": {}, "updated": None}

    # ── Build aligned series ────────────────────────────────────────────────
    series: dict[str, list] = {}

    if oas_dates:
        oas_map = dict(zip(oas_dates, oas_values))
        series["OAS"] = [
            round(oas_map[d], 2) if d in oas_map else None
            for d in common_dates
        ]

    if hyg_dates:
        hyg_map = dict(zip(hyg_dates, hyg_closes))
        series["HYG"] = [
            round(hyg_map[d], 2) if d in hyg_map else None
            for d in common_dates
        ]

    # ── Stats ───────────────────────────────────────────────────────────────
    def _find_value_n_days_ago(d_list, v_list, n_calendar_days):
        today = datetime.now(_ET).date()
        target = (today - timedelta(days=n_calendar_days)).isoformat()
        idx = bisect.bisect_right(d_list, target) - 1
        return round(v_list[idx], 2) if idx >= 0 else None

    def _build_stats(dates_list, values_list, cur_val, decimals=2):
        last = round(cur_val, decimals) if cur_val is not None else (
            round(values_list[-1], decimals) if values_list else None
        )
        last_hist = round(values_list[-1], decimals) if values_list else None
        if last is not None and last_hist is not None and last == last_hist:
            prev = round(values_list[-2], decimals) if len(values_list) >= 2 else None
        else:
            prev = last_hist

        wk1 = _find_value_n_days_ago(dates_list, values_list, 7)
        mo1 = _find_value_n_days_ago(dates_list, values_list, 30)
        mo3 = _find_value_n_days_ago(dates_list, values_list, 91)

        def _delta(ref):
            if last is None or ref is None or ref == 0:
                return None, None
            d = round(last - ref, decimals)
            p = round(d / abs(ref) * 100, 2) if ref != 0 else None
            return d, p

        dod_d, dod_p = _delta(prev)
        wow_d, wow_p = _delta(wk1)
        mom_d, mom_p = _delta(mo1)

        return {
            "last": last, "day1": prev, "wk1": wk1, "mo1": mo1, "mo3": mo3,
            "dod_delta": dod_d, "dod_pct": dod_p,
            "wow_delta": wow_d, "wow_pct": wow_p,
            "mom_delta": mom_d, "mom_pct": mom_p,
        }

    stats: dict[str, dict] = {}

    if oas_dates and oas_values:
        stats["OAS"] = _build_stats(oas_dates, oas_values, oas_values[-1])

    if hyg_dates and hyg_closes:
        stats["HYG"] = _build_stats(hyg_dates, hyg_closes, hyg_cur_close)

    hy_updated = updated_at.strftime("%m/%d/%y %H:%M") if updated_at else None

    return {
        "dates":   common_dates,
        "series":  series,
        "stats":   stats,
        "updated": hy_updated,
    }


# ── Market Volume & Breadth ─────────────────────────────────────────────────

_VOL_TICKERS    = ["TVOL", "UVOL", "DVOL"]
_BREADTH_TICKERS = ["ADD", "ADVN", "DECN"]
_MKT_VOL_LABELS = {
    "TVOL": "NYSE Total Volume",
    "UVOL": "NYSE Up Volume",
    "DVOL": "NYSE Down Volume",
    "ADD":  "NYSE Net A/D",
    "ADVN": "NYSE Advancing",
    "DECN": "NYSE Declining",
}


@router.get("/api/vol/market-volume")
def market_volume_history(db: Session = Depends(get_db)):
    """
    Returns NYSE market volume & breadth data for the MKT VOLUME dashboard.
    Sources: $TVOL/$UVOL/$DVOL (volume), $ADD/$ADVN/$DECN (breadth) — all
    from Schwab get_price_history(), stored in price_cache.
    """
    all_tickers = _VOL_TICKERS + _BREADTH_TICKERS
    rows = (
        db.query(PriceCache)
        .filter(PriceCache.ticker.in_(all_tickers))
        .all()
    )
    row_map = {r.ticker: r for r in rows}

    if not row_map:
        return {
            "volume": {}, "breadth": {},
            "volume_table": {}, "breadth_table": {},
            "ad_cumulative": [], "ad_cumulative_dates": [],
            "updated": None,
        }

    def _parse(row):
        if not row or not row.history_json or not row.history_dates_json:
            return [], []
        closes = json.loads(row.history_json)
        dates  = json.loads(row.history_dates_json)
        if len(closes) != len(dates):
            return [], []
        return dates, closes

    # Build per-ticker series
    volume = {}
    for t in _VOL_TICKERS:
        dates, closes = _parse(row_map.get(t))
        if dates:
            volume[t] = {"dates": dates, "closes": [round(c, 2) for c in closes]}

    breadth = {}
    for t in _BREADTH_TICKERS:
        dates, closes = _parse(row_map.get(t))
        if dates:
            breadth[t] = {"dates": dates, "closes": [round(c, 2) for c in closes]}

    # Volume table — % vs averages (Hedgeye-style)
    def _vol_pct_vs_avg(closes, n):
        if len(closes) < n + 1:
            return None
        avg = np.mean(closes[-(n + 1):-1])
        if avg == 0:
            return None
        return round((closes[-1] - avg) / avg * 100, 1)

    volume_table = {}
    for t in _VOL_TICKERS:
        if t not in volume:
            continue
        closes = volume[t]["closes"]
        if len(closes) < 2:
            continue
        prev = closes[-2]
        last = closes[-1]
        prior_day = round((last - prev) / prev * 100, 1) if prev != 0 else None
        volume_table[t] = {
            "label": _MKT_VOL_LABELS[t],
            "last": last,
            "prior_day": prior_day,
            "avg_1m": _vol_pct_vs_avg(closes, 21),
            "avg_3m": _vol_pct_vs_avg(closes, 63),
            "avg_1y": _vol_pct_vs_avg(closes, 252),
        }

    # Latest volume date for table header
    volume_date = None
    for t in _VOL_TICKERS:
        if t in volume and volume[t]["dates"]:
            volume_date = volume[t]["dates"][-1]
            break

    # Breadth table
    breadth_table = {}
    advn_last = None
    decn_last = None
    for t in _BREADTH_TICKERS:
        if t not in breadth:
            continue
        closes = breadth[t]["closes"]
        if not closes:
            continue
        last = closes[-1]
        breadth_table[t] = {"label": _MKT_VOL_LABELS[t], "last": last}
        if t == "ADVN":
            advn_last = last
        elif t == "DECN":
            decn_last = last

    if advn_last is not None and decn_last is not None:
        total = advn_last + decn_last
        if total > 0:
            breadth_table["ADVN"]["pct"] = round(advn_last / total * 100, 1)
            breadth_table["DECN"]["pct"] = round(decn_last / total * 100, 1)
        breadth_table["ADD"]["ratio"] = round(advn_last / decn_last, 2) if decn_last != 0 else None

    # Cumulative A/D line
    ad_cumulative = []
    ad_cumulative_dates = []
    if "ADD" in breadth:
        ad_dates = breadth["ADD"]["dates"]
        ad_closes = breadth["ADD"]["closes"]
        running = 0.0
        for i, v in enumerate(ad_closes):
            running += v
            ad_cumulative.append(round(running, 2))
            ad_cumulative_dates.append(ad_dates[i])

    # Updated timestamp
    updated_at = None
    for t in all_tickers:
        r = row_map.get(t)
        if r and r.updated_at:
            if updated_at is None or r.updated_at > updated_at:
                updated_at = r.updated_at

    updated_str = updated_at.strftime("%m/%d/%y %H:%M") if updated_at else None

    return {
        "volume":       volume,
        "breadth":      breadth,
        "volume_table": volume_table,
        "breadth_table": breadth_table,
        "ad_cumulative":       ad_cumulative,
        "ad_cumulative_dates": ad_cumulative_dates,
        "updated": updated_str,
        "volume_date": volume_date,
    }
