from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from database import get_db
from models.signal_hurst import SignalHurst
from models.signal_pivots import SignalPivots
from models.signal_output import SignalOutput
from services.signal_engine import compute_hurst
from services.pivot_engine import compute_pivots
from services.conviction_engine import compute_output
from datetime import datetime
import logging

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/signals", tags=["signals"])

# Full Tier 1 ticker list — must match market_data.py
TIER1_TICKERS = [
    "SPX", "NDX", "$DJI", "VIX",
    "SPY", "QQQ", "IWM",
    "XLK", "XLF", "XLE", "XLV", "XLI", "XLY", "XLP", "XLB", "XLU", "XLRE", "XLC",
    "AAPL", "MSFT", "NVDA", "AVGO", "GOOGL", "META", "NFLX", "AMZN", "TSLA",
    "SMH", "CIBR", "GRID", "QTUM", "ROBO", "SATS",
    "TLT", "IBIT", "GLD", "USD", "JPY",
    "KWEB", "EWJ", "EWW", "TUR", "UAE",
    "USO", "SLV", "PALL", "CANE", "WOOD",
]


@router.get("/hurst")
def calculate_hurst(db: Session = Depends(get_db)):
    """
    Task 3.1 — Compute Hurst Exponent + Fractal Dimension for all Tier 1 tickers.
    Fetches 4 years of price history per ticker, runs DFA at three timeframes.
    Upserts results into signal_hurst table.

    Manual trigger only — called by CALCULATE SIGNALS button.
    """
    results  = []
    errors   = []

    for ticker in TIER1_TICKERS:
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

    return {
        "calculated": len(results),
        "errors":     len(errors),
        "error_list": errors,
        "results":    results,
    }


@router.get("/pivots")
def calculate_pivots(db: Session = Depends(get_db)):
    """
    Task 3.2 — Compute ABC pivot structure for all Tier 1 tickers.
    Fetches 4 years of price history per ticker, detects pivot highs/lows,
    builds A-B-C-D structure for trade (3-bar), trend (20-bar), and LT (90-bar).
    Upserts results into signal_pivots table.

    Manual trigger only — called after /api/signals/hurst by CALCULATE SIGNALS.
    """
    results = []
    errors  = []

    for ticker in TIER1_TICKERS:
        try:
            data = compute_pivots(ticker, db)

            now = datetime.utcnow()

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

    return {
        "calculated": len(results),
        "errors":     len(errors),
        "error_list": errors,
        "results":    results,
    }


@router.get("/output")
def calculate_output(db: Session = Depends(get_db)):
    """
    Task 3.3 — Compute LRR/HRR + Conviction for all Tier 1 tickers.
    Reads from signal_hurst, signal_pivots, price_cache.
    Upserts results into signal_output table (one row per ticker per timeframe).

    Manual trigger only — called after /api/signals/pivots by CALCULATE SIGNALS.
    """
    results = []
    errors  = []

    for ticker in TIER1_TICKERS:
        try:
            data = compute_output(ticker, db)
            now  = datetime.utcnow()

            for tf in ("trade", "trend", "lt"):
                tf_data  = data[tf]
                row_id   = f"{ticker}_{tf}"

                # Conviction stored per timeframe row; None when viewpoint is Neutral
                conviction = data["conviction"] if data["viewpoint"] != "Neutral" else None

                fields = dict(
                    ticker           = ticker,
                    timeframe        = tf,
                    lrr              = tf_data.get("lrr"),
                    hrr              = tf_data.get("hrr"),
                    structural_state = tf_data.get("structural_state"),
                    trade_direction  = tf_data.get("direction"),
                    conviction       = conviction,
                    h_value          = tf_data.get("h_value"),
                    viewpoint        = data["viewpoint"],
                    alert            = data["alert"],
                    vol_signal       = data["vol_signal"],
                    warning          = tf_data.get("warning"),
                    lrr_warn         = tf_data.get("lrr_warn"),
                    hrr_warn         = tf_data.get("hrr_warn"),
                    pivot_b          = tf_data.get("pivot_b"),
                    pivot_c          = tf_data.get("pivot_c"),
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

    return {
        "calculated": len(results),
        "errors":     len(errors),
        "error_list": errors,
        "results":    results,
    }


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
                "ticker":     t,
                "viewpoint":  row.viewpoint,
                "conviction": None,
                "vol_signal": row.vol_signal,
                "alert":      bool(row.alert) if row.alert is not None else False,
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
    return {"results": results, "count": len(results)}
