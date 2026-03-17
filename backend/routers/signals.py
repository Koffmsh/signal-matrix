from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from database import get_db
from models.signal_hurst import SignalHurst
from services.signal_engine import compute_hurst
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
            data = compute_hurst(ticker)

            # Upsert — merge by primary key (ticker)
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
