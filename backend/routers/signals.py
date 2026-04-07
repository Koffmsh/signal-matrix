from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from database import get_db
from models.signal_hurst import SignalHurst
from models.signal_pivots import SignalPivots
from models.signal_output import SignalOutput
from models.signal_history import SignalHistory
from models.ticker import Ticker
from services.signal_engine import compute_hurst
from services.pivot_engine import compute_pivots
from services.conviction_engine import compute_output
from datetime import datetime
from zoneinfo import ZoneInfo
from typing import Optional
import logging

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/signals", tags=["signals"])


def get_active_tickers(db: Session) -> list:
    rows = db.query(Ticker).filter(Ticker.active == True).order_by(Ticker.tier, Ticker.display_order).all()
    return [r.ticker for r in rows]


# ── Callable functions (used by scheduler and HTTP endpoints) ─────────────────

def run_hurst(db: Session) -> dict:
    """Compute Hurst Exponent + Fractal Dimension for all active tickers."""
    results = []
    errors  = []

    for ticker in get_active_tickers(db):
        try:
            data = compute_hurst(ticker, db)

            existing = db.query(SignalHurst).filter(
                SignalHurst.ticker == ticker
            ).first()

            now = datetime.utcnow()

            if existing:
                existing.h_trade       = data["h_trade"]
                existing.h_trend       = data["h_trend"]
                existing.h_lt          = data["h_lt"]
                existing.d_trade       = data["d_trade"]
                existing.d_trend       = data["d_trend"]
                existing.d_lt          = data["d_lt"]
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
                    calculated_at = now,
                ))

            db.commit()
            results.append(data)

        except Exception as e:
            logger.error(f"Hurst calculation failed for {ticker}: {e}")
            errors.append({"ticker": ticker, "error": str(e)})

    return {"calculated": len(results), "errors": len(errors), "error_list": errors, "results": results}


def run_pivots(db: Session) -> dict:
    """Compute ABC pivot structure for all active tickers."""
    results = []
    errors  = []

    for ticker in get_active_tickers(db):
        try:
            data = compute_pivots(ticker, db)
            now  = datetime.utcnow()

            for tf in ("trade", "trend", "lt"):
                tf_data = data[tf]

                existing = db.query(SignalPivots).filter(
                    SignalPivots.ticker    == ticker,
                    SignalPivots.timeframe == tf,
                ).first()

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
                    calculated_at    = now,
                )

                if existing:
                    for k, v in fields.items():
                        setattr(existing, k, v)
                else:
                    db.add(SignalPivots(ticker=ticker, timeframe=tf, **fields))

            db.commit()
            results.append(data)

        except Exception as e:
            logger.error(f"Pivot calculation failed for {ticker}: {e}")
            errors.append({"ticker": ticker, "error": str(e)})

    return {"calculated": len(results), "errors": len(errors), "error_list": errors, "results": results}


def run_output(db: Session) -> dict:
    """Compute LRR/HRR + Conviction for all active tickers."""
    results = []
    errors  = []

    for ticker in get_active_tickers(db):
        try:
            # Read yesterday's HRR/LRR before they get overwritten.
            # conviction_engine uses these as the EXTENDED threshold:
            # if today's close > prior_hrr (bullish) or < prior_lrr (bearish) → EXTENDED.
            prior_ranges = {}
            for tf in ("trade", "trend", "lt"):
                row = db.query(SignalOutput).filter(
                    SignalOutput.id == f"{ticker}_{tf}"
                ).first()
                prior_ranges[tf] = {
                    "prior_hrr": row.hrr if row else None,
                    "prior_lrr": row.lrr if row else None,
                }

            data = compute_output(ticker, db, prior_ranges=prior_ranges)
            now  = datetime.utcnow()

            # ── viewpoint_since — track when current aligned viewpoint began ──
            new_viewpoint = data["viewpoint"]
            now_et        = datetime.now(ZoneInfo("America/New_York")).isoformat()
            existing_ref  = db.query(SignalOutput).filter(
                SignalOutput.id == f"{ticker}_trade"
            ).first()

            if existing_ref is None:
                viewpoint_since = now_et if new_viewpoint in ("Bullish", "Bearish") else None
            elif new_viewpoint in ("Bullish", "Bearish") and new_viewpoint != existing_ref.viewpoint:
                viewpoint_since = now_et                        # transition to aligned state
            elif new_viewpoint in ("Bullish", "Bearish") and new_viewpoint == existing_ref.viewpoint:
                viewpoint_since = existing_ref.viewpoint_since  # preserve existing timestamp
            else:
                viewpoint_since = None                          # Neutral — clear

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
                    obv_direction    = data.get("obv_direction"),
                    obv_confirming   = data.get("obv_confirming"),
                    calculated_at    = now,
                )

                existing = db.query(SignalOutput).filter(
                    SignalOutput.id == row_id
                ).first()

                if existing:
                    for k, v in fields.items():
                        setattr(existing, k, v)
                else:
                    db.add(SignalOutput(id=row_id, **fields))

            db.commit()
            results.append(data)

        except Exception as e:
            logger.error(f"Output calculation failed for {ticker}: {e}")
            errors.append({"ticker": ticker, "error": str(e)})

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
            calculated_at    = str(row.calculated_at) if row.calculated_at else None,
            created_at       = now_utc_str,
        ))
        inserted += 1

    db.commit()
    logger.info(f"Snapshot: {inserted} inserted, {skipped} skipped for {today_str} (trigger={trigger})")
    return {"snapshot_date": today_str, "trigger": trigger, "inserted": inserted, "skipped": skipped}


def calculate_signals(db: Session, trigger: str = "manual") -> dict:
    """Run full signal pipeline: hurst → pivots → output. Called by scheduler."""
    hurst_result  = run_hurst(db)
    pivots_result = run_pivots(db)
    output_result = run_output(db)

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
def run_calculate_signals(db: Session = Depends(get_db)):
    """
    Task 4.3 — Full signal pipeline + snapshot in one call.
    Called by CALCULATE SIGNALS button: hurst → pivots → output → snapshot.
    Returns output results in the same shape the frontend expects.
    """
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

    # Check whether any lt rows exist — if not, only require trade + trend
    has_lt = any(r.timeframe == "lt" for r in rows)

    by_ticker: dict = {}
    for row in rows:
        t = row.ticker
        if t not in by_ticker:
            by_ticker[t] = {
                "ticker":          t,
                "viewpoint":       row.viewpoint,
                "viewpoint_since": row.viewpoint_since,
                "conviction":      None,
                "vol_signal":      row.vol_signal,
                "obv_direction":   row.obv_direction,
                "obv_confirming":  bool(row.obv_confirming) if row.obv_confirming is not None else False,
                "alert":           bool(row.alert) if row.alert is not None else False,
                "trade": None, "trend": None, "lt": None,
            }
        by_ticker[t][row.timeframe] = {
            "lrr":              row.lrr,
            "hrr":              row.hrr,
            "structural_state": row.structural_state,
            "direction":        row.trade_direction,
            "h_value":          row.h_value,
            "warning":          bool(row.warning)   if row.warning   is not None else False,
            "lrr_warn":         bool(row.lrr_warn)  if row.lrr_warn  is not None else False,
            "hrr_warn":         bool(row.hrr_warn)  if row.hrr_warn  is not None else False,
            "pivot_b":          row.pivot_b,
            "pivot_c":          row.pivot_c,
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
