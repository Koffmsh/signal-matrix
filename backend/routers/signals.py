from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session
from database import get_db
from services.auth_service import require_admin_user
from models.signal_hurst import SignalHurst
from models.signal_pivots import SignalPivots
from models.signal_output import SignalOutput
from models.signal_history import SignalHistory
from models.ticker import Ticker
from models.quad_settings import QuadSettings
from services.signal_engine import (compute_hurst, compute_h_trade_delta,
                                    compute_asymmetric_h, get_prices_from_cache,
                                    WINDOW_TREND)
from services.pivot_engine import compute_pivots
from services.conviction_engine import compute_output
from datetime import datetime
from zoneinfo import ZoneInfo
from typing import Optional
import json
import logging

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/signals", tags=["signals"])


def _compute_emerging_direction(closes: list) -> str | None:
    """
    Returns "Bullish", "Bearish", or None.
    Only called when trade_direction == "Neutral" (NO_STRUCTURE or BREAK_CONFIRMED).

    Emerging Bullish — all four must be true:
      1. close[-1] > MA50 today
      2. MA50 today > MA50[5 bars ago]   (slope positive)
      3. Last 3 closes each above their respective MA50  (persistence)
      4. close[-1] >= max(closes[-22:])  (22-day closing high breakout)

    Mirror conditions for Emerging Bearish.
    Requires at least 55 bars (50 for MA50 + 5 for slope lookback).
    """
    if len(closes) < 55:
        return None

    import numpy as np

    def ma50(offset=0):
        end = len(closes) - offset
        return float(np.mean(closes[end - 50: end]))

    ma50_today = ma50(0)
    ma50_5ago  = ma50(5)
    ma50_1ago  = ma50(1)   # MA50 as of 2 bars ago (for close[-2] check)
    ma50_2ago  = ma50(2)   # MA50 as of 3 bars ago (for close[-3] check)

    c0 = closes[-1]
    c1 = closes[-2]
    c2 = closes[-3]

    high_22 = max(closes[-22:])
    low_22  = min(closes[-22:])

    # Emerging Bullish
    if (c0 > ma50_today
            and ma50_today > ma50_5ago
            and c1 > ma50_1ago
            and c2 > ma50_2ago
            and max(closes[-3:]) >= high_22):
        return "Bullish"

    # Emerging Bearish
    if (c0 < ma50_today
            and ma50_today < ma50_5ago
            and c1 < ma50_1ago
            and c2 < ma50_2ago
            and min(closes[-3:]) <= low_22):
        return "Bearish"

    return None


def get_active_tickers(db: Session) -> list:
    rows = db.query(Ticker).filter(Ticker.active == True).order_by(Ticker.tier, Ticker.display_order).all()
    return [r.ticker for r in rows]


# ── Callable functions (used by scheduler and HTTP endpoints) ─────────────────

ASYMMETRIC_H_ASSET_CLASSES = {"Commodities", "Foreign Exchange"}
ASYMMETRIC_H_EXCLUDED      = {"/ZN"}   # Fixed Income behavior despite Commodities classification


def run_hurst(db: Session) -> dict:
    """Compute Hurst Exponent + Fractal Dimension for all active tickers."""
    results = []
    errors  = []

    # Fetch asset_class for all active tickers in one query — needed for asymmetric H eligibility
    ticker_rows = db.query(Ticker).filter(Ticker.active == True).all()
    asset_class_map = {t.ticker: (t.asset_class or "") for t in ticker_rows}

    # Pre-load all existing hurst rows to avoid per-ticker queries
    all_hurst_rows = db.query(SignalHurst).all()
    hurst_map_calc = {r.ticker: r for r in all_hurst_rows}

    for ticker in get_active_tickers(db):
        try:
            data = compute_hurst(ticker, db)

            # Task 6.3 — Asymmetric H for Commodities and FX
            h_trend_up   = None
            h_trend_down = None
            ac = asset_class_map.get(ticker, "")
            if ac in ASYMMETRIC_H_ASSET_CLASSES and ticker not in ASYMMETRIC_H_EXCLUDED:
                prices = get_prices_from_cache(ticker, db)
                if prices:
                    h_trend_up, h_trend_down = compute_asymmetric_h(prices, window=WINDOW_TREND)

            existing = hurst_map_calc.get(ticker)

            now = datetime.utcnow()

            if existing:
                existing.h_trade       = data["h_trade"]
                existing.h_trend       = data["h_trend"]
                existing.h_lt          = data["h_lt"]
                existing.d_trade       = data["d_trade"]
                existing.d_trend       = data["d_trend"]
                existing.d_lt          = data["d_lt"]
                existing.h_trend_up    = h_trend_up
                existing.h_trend_down  = h_trend_down
                existing.calculated_at = now
            else:
                db.add(SignalHurst(
                    ticker        = ticker,
                    h_trade       = data["h_trade"],
                    h_trend       = data["h_trend"],
                    h_lt          = data["h_lt"],
                    d_trade       = data["d_trade"],
                    d_trend       = data["d_trend"],
                    d_lt          = data["d_lt"],
                    h_trend_up    = h_trend_up,
                    h_trend_down  = h_trend_down,
                    calculated_at = now,
                ))

            results.append(data)

        except Exception as e:
            logger.error(f"Hurst calculation failed for {ticker}: {e}")
            errors.append({"ticker": ticker, "error": str(e)})

    db.commit()
    return {"calculated": len(results), "errors": len(errors), "error_list": errors, "results": results}


def run_pivots(db: Session) -> dict:
    """Compute ABC pivot structure for all active tickers."""
    results = []
    errors  = []

    # Pre-load all existing pivot rows to avoid per-ticker queries
    all_pivot_rows = db.query(SignalPivots).all()
    pivot_map = {(r.ticker, r.timeframe): r for r in all_pivot_rows}

    for ticker in get_active_tickers(db):
        try:
            data = compute_pivots(ticker, db)
            now  = datetime.utcnow()

            for tf in ("trade", "trend", "lt"):
                tf_data = data[tf]

                existing = pivot_map.get((ticker, tf))

                fields = dict(
                    bar_window       = tf_data.get("bar_window"),
                    pivot_a          = tf_data.get("pivot_a"),
                    pivot_b          = tf_data.get("pivot_b"),
                    pivot_c          = tf_data.get("pivot_c"),
                    pivot_d          = tf_data.get("pivot_d"),
                    pivot_a_date     = tf_data.get("pivot_a_date"),
                    pivot_b_date     = tf_data.get("pivot_b_date"),
                    pivot_c_date     = tf_data.get("pivot_c_date"),
                    pivot_d_date     = tf_data.get("pivot_d_date"),
                    structural_state = tf_data.get("structural_state"),
                    d_extended       = bool(tf_data.get("d_extended") or False),
                    calculated_at    = now,
                )

                if existing:
                    for k, v in fields.items():
                        setattr(existing, k, v)
                else:
                    db.add(SignalPivots(ticker=ticker, timeframe=tf, **fields))

            results.append(data)

        except Exception as e:
            logger.error(f"Pivot calculation failed for {ticker}: {e}")
            errors.append({"ticker": ticker, "error": str(e)})

    db.commit()
    return {"calculated": len(results), "errors": len(errors), "error_list": errors, "results": results}


def run_output(db: Session) -> dict:
    """Compute LRR/HRR + Conviction for all active tickers."""
    results = []
    errors  = []

    # Fetch asset_class + sector for all active tickers
    ticker_rows_out = db.query(Ticker).filter(Ticker.active == True).all()
    asset_class_map_out = {t.ticker: (t.asset_class or "") for t in ticker_rows_out}
    sector_map_out      = {t.ticker: (t.sector      or "") for t in ticker_rows_out}

    # Fetch US monthly quad for current ET month
    from zoneinfo import ZoneInfo
    _ET = ZoneInfo("America/New_York")
    now_et        = datetime.now(_ET)
    current_month = now_et.strftime("%Y-%m")
    quad_row = db.query(QuadSettings).filter(
        QuadSettings.country        == "US",
        QuadSettings.forecast_month == current_month,
        QuadSettings.quad_type      == "monthly",
    ).first()
    quad_current = quad_row.quad        if quad_row else None
    quad_prob    = quad_row.probability if quad_row else 0.0

    # Fetch country quarterly quads for current quarter (International Equities routing)
    current_q_num    = (now_et.month - 1) // 3 + 1
    current_quarter  = f"{now_et.year}-Q{current_q_num}"
    quarterly_rows   = db.query(QuadSettings).filter(
        QuadSettings.quad_type      == "quarterly",
        QuadSettings.forecast_month == current_quarter,
    ).all()
    # country_code → quad  (probability is always 1.0 for quarterly rows)
    quarterly_quads  = {r.country: r.quad for r in quarterly_rows}

    # Sector label → ISO country code (matches COUNTRY_CODE in QuadSetup.js)
    _SECTOR_TO_CODE = {
        "Japan": "JP", "China": "CN", "Mexico": "MX", "Turkey": "TR", "UAE": "AE",
        "Germany": "DE", "France": "FR", "United Kingdom": "GB", "Spain": "ES",
        "South Korea": "KR", "India": "IN", "Brazil": "BR", "Canada": "CA",
        "Australia": "AU", "Eurozone": "EU", "United States": "US",
    }

    # Pre-load price history for emerging_direction computation (trade tf only)
    from models.price_cache import PriceCache
    from sqlalchemy.orm import load_only as _load_only
    pc_rows = (
        db.query(PriceCache)
        .options(_load_only(PriceCache.ticker, PriceCache.history_json))
        .filter(PriceCache.history_json.isnot(None))
        .all()
    )
    price_history_map = {}
    for pc in pc_rows:
        try:
            price_history_map[pc.ticker] = json.loads(pc.history_json)
        except Exception:
            pass

    # Pre-load all existing signal_output rows to avoid per-ticker queries
    all_output_rows = db.query(SignalOutput).all()
    prior_ranges_map = {}
    for row in all_output_rows:
        t, tf = row.ticker, row.timeframe
        if t not in prior_ranges_map:
            prior_ranges_map[t] = {}
        prior_ranges_map[t][tf] = {"prior_hrr": row.hrr, "prior_lrr": row.lrr}

    # Pre-load all existing signal_output trade rows for viewpoint_since tracking
    existing_trade_map = {row.ticker: row for row in all_output_rows if row.timeframe == "trade"}

    for ticker in get_active_tickers(db):
        try:
            prior_ranges = prior_ranges_map.get(ticker, {})

            # Route International Equities to their country quarterly quad;
            # everything else uses the US monthly quad.
            ticker_ac     = asset_class_map_out.get(ticker, "")
            ticker_sector = sector_map_out.get(ticker, "")
            if ticker_ac == "International Equities":
                country_code  = _SECTOR_TO_CODE.get(ticker_sector)
                ticker_quad   = quarterly_quads.get(country_code) if country_code else None
                ticker_prob   = 1.0 if ticker_quad is not None else 0.0
            else:
                ticker_quad   = quad_current
                ticker_prob   = quad_prob

            data = compute_output(
                ticker, db,
                prior_ranges  = prior_ranges,
                asset_class   = ticker_ac,
                sector        = ticker_sector,
                quad_current  = ticker_quad,
                quad_prob     = ticker_prob,
            )
            now  = datetime.utcnow()

            # Task 6.1 — h_trade_delta: change in H_trade over ~20 trading days
            h_trade_val   = data["trade"].get("h_value") if data.get("trade") else None
            h_trade_delta = None
            if h_trade_val is not None:
                h_trade_delta = compute_h_trade_delta(db, ticker, h_trade_val)

            # ── viewpoint_since — track when current aligned viewpoint began ──
            new_viewpoint = data["viewpoint"]
            now_et        = datetime.now(ZoneInfo("America/New_York")).isoformat()
            existing_ref  = existing_trade_map.get(ticker)

            if existing_ref is None:
                viewpoint_since = now_et if new_viewpoint in ("Bullish", "Bearish") else None
            elif new_viewpoint in ("Bullish", "Bearish") and new_viewpoint != existing_ref.viewpoint:
                viewpoint_since = now_et                        # transition to aligned state
            elif new_viewpoint in ("Bullish", "Bearish") and new_viewpoint == existing_ref.viewpoint:
                viewpoint_since = existing_ref.viewpoint_since  # preserve existing timestamp
            else:
                viewpoint_since = None                          # Neutral — clear

            # Emerging direction — only when trade direction is Neutral
            trade_dir_val = data["trade"].get("direction") if data.get("trade") else None
            emerging_dir  = None
            if trade_dir_val == "Neutral":
                closes = price_history_map.get(ticker, [])
                emerging_dir = _compute_emerging_direction(closes)

            for tf in ("trade", "trend", "lt"):
                tf_data  = data[tf]
                row_id   = f"{ticker}_{tf}"

                conviction = data["conviction"] if new_viewpoint != "Neutral" else None

                fields = dict(
                    ticker           = ticker,
                    timeframe        = tf,
                    lrr              = tf_data.get("lrr"),
                    hrr              = tf_data.get("hrr"),
                    structural_state = tf_data.get("structural_state"),
                    trade_direction  = tf_data.get("direction"),
                    conviction       = conviction,
                    h_value          = tf_data.get("h_value"),
                    viewpoint        = new_viewpoint,
                    viewpoint_since  = viewpoint_since,
                    alert            = data["alert"],
                    vol_signal       = data["vol_signal"],
                    warning          = tf_data.get("warning"),
                    lrr_warn         = tf_data.get("lrr_warn"),
                    hrr_warn         = tf_data.get("hrr_warn"),
                    pivot_b          = tf_data.get("pivot_b"),
                    pivot_c          = tf_data.get("pivot_c"),
                    lrr_extended     = tf_data.get("lrr_extended", False),
                    hrr_extended     = tf_data.get("hrr_extended", False),
                    hrr_snapped      = bool(tf_data.get("hrr_snapped") or False),
                    lrr_snapped      = bool(tf_data.get("lrr_snapped") or False),
                    d_extended       = bool(tf_data.get("d_extended") or False),
                    obv_direction    = data.get("obv_direction"),
                    obv_confirming   = data.get("obv_confirming"),
                    h_trade_delta    = h_trade_delta if tf == "trade" else None,
                    vix_regime       = data.get("vix_regime"),
                    quad_alignment      = data.get("quad_alignment"),
                    quad_mult           = data.get("quad_mult"),
                    quad_score          = data.get("quad_score"),
                    emerging_direction  = emerging_dir if tf == "trade" else None,
                    calculated_at       = now,
                )

                existing = next(
                    (r for r in all_output_rows if r.id == row_id), None
                )

                if existing:
                    for k, v in fields.items():
                        setattr(existing, k, v)
                else:
                    db.add(SignalOutput(id=row_id, **fields))

            results.append(data)

        except Exception as e:
            logger.error(f"Output calculation failed for {ticker}: {e}")
            errors.append({"ticker": ticker, "error": str(e)})

    db.commit()
    return {"calculated": len(results), "errors": len(errors), "error_list": errors, "results": results}


def snapshot_signals(trigger: str, db: Session) -> dict:
    """
    Snapshot current signal_output rows to signal_history for today's ET date.
    Idempotent — skips any ticker/timeframe that already has a row for today.
    Called inside calculate_signals; failure never blocks signal calculation.
    """
    _ET         = ZoneInfo("America/New_York")
    today_str   = datetime.now(_ET).strftime("%Y-%m-%d")
    now_utc_str = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")

    rows      = db.query(SignalOutput).all()
    inserted  = 0
    skipped   = 0

    for row in rows:
        already = db.query(SignalHistory).filter(
            SignalHistory.snapshot_date == today_str,
            SignalHistory.ticker        == row.ticker,
            SignalHistory.timeframe     == row.timeframe,
        ).first()

        if already:
            skipped += 1
            continue

        db.add(SignalHistory(
            snapshot_date    = today_str,
            trigger          = trigger,
            ticker           = row.ticker,
            timeframe        = row.timeframe,
            lrr              = row.lrr,
            hrr              = row.hrr,
            structural_state = row.structural_state,
            trade_direction  = row.trade_direction,
            conviction       = row.conviction,
            h_value          = row.h_value,
            viewpoint        = row.viewpoint,
            alert            = row.alert,
            vol_signal       = row.vol_signal,
            warning          = row.warning,
            lrr_warn         = row.lrr_warn,
            hrr_warn         = row.hrr_warn,
            pivot_b          = row.pivot_b,
            pivot_c          = row.pivot_c,
            hrr_snapped         = bool(row.hrr_snapped or False),
            lrr_snapped         = bool(row.lrr_snapped or False),
            emerging_direction  = row.emerging_direction,
            calculated_at       = str(row.calculated_at) if row.calculated_at else None,
            created_at          = now_utc_str,
        ))
        inserted += 1

    db.commit()
    logger.info(f"Snapshot: {inserted} inserted, {skipped} skipped for {today_str} (trigger={trigger})")
    return {"snapshot_date": today_str, "trigger": trigger, "inserted": inserted, "skipped": skipped}


def calculate_signals(db: Session, trigger: str = "manual") -> dict:
    """Run full signal pipeline: hurst → pivots → output. Called by scheduler."""
    import time
    t0 = time.time()

    # Skip Hurst if already computed today (manual re-runs mid-day are common;
    # Hurst is slow ~33s and changes only day-over-day at EOD resolution).
    # Scheduler always forces recompute via trigger="scheduled".
    today_et = datetime.now(ZoneInfo("America/New_York")).date().isoformat()
    latest_hurst = db.query(SignalHurst).order_by(SignalHurst.calculated_at.desc()).first()
    hurst_done_today = (
        trigger == "manual"
        and latest_hurst is not None
        and str(latest_hurst.calculated_at)[:10] == today_et
    )
    if hurst_done_today:
        logger.info("calculate_signals: hurst skipped — already computed today")
        hurst_result = {"calculated": 0, "skipped": True}
    else:
        hurst_result = run_hurst(db)
        logger.info(f"calculate_signals: hurst done in {time.time()-t0:.1f}s")

    # Skip pivots if already computed today (same EOD-only logic as Hurst).
    t1 = time.time()
    latest_pivot = db.query(SignalPivots).order_by(SignalPivots.calculated_at.desc()).first()
    pivots_done_today = (
        trigger == "manual"
        and latest_pivot is not None
        and str(latest_pivot.calculated_at)[:10] == today_et
    )
    if pivots_done_today:
        logger.info("calculate_signals: pivots skipped — already computed today")
        pivots_result = {"calculated": 0, "skipped": True}
    else:
        pivots_result = run_pivots(db)
        logger.info(f"calculate_signals: pivots done in {time.time()-t1:.1f}s")

    t2 = time.time()
    output_result = run_output(db); logger.info(f"calculate_signals: output done in {time.time()-t2:.1f}s")
    logger.info(f"calculate_signals: total {time.time()-t0:.1f}s")

    snapshot_result = None
    try:
        snapshot_result = snapshot_signals(trigger, db)
    except Exception as e:
        logger.error(f"Snapshot failed (non-fatal): {e}")

    return {
        "hurst":    hurst_result,
        "pivots":   pivots_result,
        "output":   output_result,
        "snapshot": snapshot_result,
    }


# ── HTTP endpoints ────────────────────────────────────────────────────────────

@router.get("/calculate")
def run_calculate_signals(request: Request, db: Session = Depends(get_db)):
    """
    Task 4.3 — Full signal pipeline + snapshot in one call.
    Called by CALCULATE SIGNALS button: hurst → pivots → output → snapshot.
    Admin-only — full recalc is expensive; viewers see the result via /stored.
    """
    require_admin_user(request, db)
    result = calculate_signals(db, trigger="manual")
    return result["output"]


@router.get("/hurst")
def calculate_hurst(db: Session = Depends(get_db)):
    """
    Task 3.1 — Compute Hurst Exponent + Fractal Dimension for all Tier 1 tickers.
    Debug endpoint — use /calculate for full pipeline with snapshot.
    """
    return run_hurst(db)


@router.get("/pivots")
def calculate_pivots(db: Session = Depends(get_db)):
    """
    Task 3.2 — Compute ABC pivot structure for all Tier 1 tickers.
    Manual trigger only — called after /api/signals/hurst by CALCULATE SIGNALS.
    """
    return run_pivots(db)


@router.get("/output")
def calculate_output(db: Session = Depends(get_db)):
    """
    Task 3.3 — Compute LRR/HRR + Conviction for all Tier 1 tickers.
    Manual trigger only — called after /api/signals/pivots by CALCULATE SIGNALS.
    """
    return run_output(db)


@router.get("/stored")
def get_stored_signals(db: Session = Depends(get_db)):
    """
    Task 3.4 — Return last calculated signal output from DB, grouped by ticker.
    Returns the same nested shape as /output results — used by frontend on page load.
    No recalculation — pure read.
    """
    rows = db.query(SignalOutput).all()

    # Fetch asymmetric H values from signal_hurst for Commodities/FX popup display
    hurst_rows = db.query(SignalHurst).all()
    hurst_map  = {r.ticker: r for r in hurst_rows}

    # Compute quad_fit (pure asset class/sector vs current quad — no viewpoint dependency)
    from zoneinfo import ZoneInfo
    from services.conviction_engine import get_quad_alignment
    _ET = ZoneInfo("America/New_York")
    now_et = datetime.now(_ET)
    current_month   = now_et.strftime("%Y-%m")
    current_quarter = f"{now_et.year}-Q{((now_et.month - 1) // 3 + 1)}"
    _quad_row = db.query(QuadSettings).filter(
        QuadSettings.country == "US",
        QuadSettings.forecast_month == current_month,
        QuadSettings.quad_type == "monthly",
    ).first()
    _us_quad = _quad_row.quad if _quad_row else None
    _quarterly = {r.country: r.quad for r in db.query(QuadSettings).filter(
        QuadSettings.quad_type == "quarterly",
        QuadSettings.forecast_month == current_quarter,
    ).all()}
    _SECTOR_TO_CODE = {
        "Japan": "JP", "China": "CN", "Mexico": "MX", "Turkey": "TR", "UAE": "AE",
        "Germany": "DE", "France": "FR", "United Kingdom": "GB", "Spain": "ES",
        "South Korea": "KR", "India": "IN", "Brazil": "BR", "Canada": "CA",
        "Australia": "AU", "Eurozone": "EU", "United States": "US",
    }
    ticker_rows_s = db.query(Ticker).filter(Ticker.active == True).all()
    _ac_map  = {t.ticker: (t.asset_class or "") for t in ticker_rows_s}
    _sec_map = {t.ticker: (t.sector      or "") for t in ticker_rows_s}

    def _quad_fit(ticker: str) -> str:
        ac  = _ac_map.get(ticker, "")
        sec = _sec_map.get(ticker, "")
        if ac == "International Equities":
            code = _SECTOR_TO_CODE.get(sec)
            quad = _quarterly.get(code) if code else None
        else:
            quad = _us_quad
        if quad is None:
            return "Neutral"
        alignment = get_quad_alignment(ac, sec, quad)
        return "Best" if alignment > 0 else "Worst" if alignment < 0 else "Neutral"

    # Check whether any lt rows exist — if not, only require trade + trend
    has_lt = any(r.timeframe == "lt" for r in rows)

    by_ticker: dict = {}
    for row in rows:
        t = row.ticker
        if t not in by_ticker:
            h_row = hurst_map.get(t)
            by_ticker[t] = {
                "ticker":          t,
                "viewpoint":       row.viewpoint,
                "viewpoint_since": row.viewpoint_since,
                "conviction":      None,
                "vol_signal":      row.vol_signal,
                "obv_direction":   row.obv_direction,
                "obv_confirming":  bool(row.obv_confirming) if row.obv_confirming is not None else False,
                "alert":           bool(row.alert) if row.alert is not None else False,
                "vix_regime":      row.vix_regime,
                "quad_alignment":  row.quad_alignment,
                "quad_mult":       row.quad_mult,
                "quad_score":      row.quad_score,
                "quad_fit":        _quad_fit(t),
                "h_trend_up":      getattr(h_row, "h_trend_up",   None) if h_row else None,
                "h_trend_down":    getattr(h_row, "h_trend_down",  None) if h_row else None,
                "trade": None, "trend": None, "lt": None,
            }
        by_ticker[t][row.timeframe] = {
            "lrr":              row.lrr,
            "hrr":              row.hrr,
            "structural_state": row.structural_state,
            "direction":        row.trade_direction,
            "h_value":          row.h_value,
            "warning":          bool(row.warning)   if row.warning   is not None else False,
            "lrr_warn":         bool(row.lrr_warn)      if row.lrr_warn      is not None else False,
            "hrr_warn":         bool(row.hrr_warn)      if row.hrr_warn      is not None else False,
            "lrr_extended":     bool(row.lrr_extended)  if row.lrr_extended  is not None else False,
            "hrr_extended":     bool(row.hrr_extended)  if row.hrr_extended  is not None else False,
            "d_extended":       bool(row.d_extended)    if row.d_extended    is not None else False,
            "pivot_b":            row.pivot_b,
            "pivot_c":            row.pivot_c,
            "h_trade_delta":      row.h_trade_delta if row.timeframe == "trade" else None,
            "emerging_direction": row.emerging_direction if row.timeframe == "trade" else None,
        }
        if row.conviction is not None:
            by_ticker[t]["conviction"] = row.conviction

    def _complete(v):
        if v["trade"] is None or v["trend"] is None:
            return False
        if has_lt and v["lt"] is None:
            return False
        return True

    results = [v for v in by_ticker.values() if _complete(v)]

    # Most recent calculated_at across all rows — used by frontend for signals freshness check
    latest_calc = max((r.calculated_at for r in rows if r.calculated_at), default=None)

    return {"results": results, "count": len(results), "calculated_at": str(latest_calc) if latest_calc else None}


@router.get("/history")
def get_signal_history(
    ticker:     Optional[str] = Query(None, description="Filter by ticker symbol"),
    timeframe:  Optional[str] = Query(None, description="Filter by timeframe: trade | trend | lt"),
    start_date: Optional[str] = Query(None, description="Start date inclusive — YYYY-MM-DD"),
    end_date:   Optional[str] = Query(None, description="End date inclusive — YYYY-MM-DD"),
    limit:      int           = Query(30,   ge=1, le=500, description="Max rows returned (default 30)"),
    db: Session = Depends(get_db),
):
    """
    Task 4.3 — Return signal history snapshots with optional filters.
    Rows are ordered newest-first.
    """
    q = db.query(SignalHistory)

    if ticker:
        q = q.filter(SignalHistory.ticker == ticker.upper())
    if timeframe:
        q = q.filter(SignalHistory.timeframe == timeframe.lower())
    if start_date:
        q = q.filter(SignalHistory.snapshot_date >= start_date)
    if end_date:
        q = q.filter(SignalHistory.snapshot_date <= end_date)

    q = q.order_by(SignalHistory.snapshot_date.desc(), SignalHistory.id.desc())
    rows = q.limit(limit).all()

    results = [
        {
            "id":               r.id,
            "snapshot_date":    r.snapshot_date,
            "trigger":          r.trigger,
            "ticker":           r.ticker,
            "timeframe":        r.timeframe,
            "lrr":              r.lrr,
            "hrr":              r.hrr,
            "structural_state": r.structural_state,
            "trade_direction":  r.trade_direction,
            "conviction":       r.conviction,
            "h_value":          r.h_value,
            "viewpoint":        r.viewpoint,
            "alert":            r.alert,
            "vol_signal":       r.vol_signal,
            "warning":          r.warning,
            "lrr_warn":         r.lrr_warn,
            "hrr_warn":         r.hrr_warn,
            "pivot_b":          r.pivot_b,
            "pivot_c":          r.pivot_c,
            "calculated_at":    r.calculated_at,
            "created_at":       r.created_at,
        }
        for r in rows
    ]

    return {"results": results, "count": len(results)}
