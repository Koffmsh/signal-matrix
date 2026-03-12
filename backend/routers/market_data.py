from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from database import get_db
from models.price_cache import PriceCache
from services.yahoo_finance import fetch_ticker_data
from datetime import date
import json
import logging

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/market-data", tags=["market-data"])

# Full Tier 1 ticker list — must match tickers.js
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


def serialize_cache_row(row: PriceCache) -> dict:
    return {
        "ticker":       row.ticker,
        "close":        row.close,
        "volume":       row.volume,
        "ma20":         row.ma20,
        "ma50":         row.ma50,
        "ma100":        row.ma100,
        "rel_iv":       row.rel_iv,
        "spark_prices": json.loads(row.spark_json),
        "updated":      str(row.updated_at),
    }


def get_or_fetch(ticker: str, today: str, db: Session) -> dict | None:
    """Return cached data if fresh for today, otherwise fetch and cache."""
    cached = db.query(PriceCache).filter(
        PriceCache.ticker     == ticker,
        PriceCache.cache_date == today
    ).first()

    if cached:
        logger.info(f"Cache hit: {ticker}")
        return serialize_cache_row(cached)

    # Cache miss — fetch from Yahoo Finance
    logger.info(f"Cache miss: {ticker} — fetching from Yahoo Finance")
    data = fetch_ticker_data(ticker)

    if data is None:
        return None

    # Upsert: update existing row or insert new
    existing = db.query(PriceCache).filter(
        PriceCache.ticker == ticker
    ).first()

    if existing:
        existing.close       = data["close"]
        existing.volume      = data["volume"]
        existing.ma20        = data["ma20"]
        existing.ma50        = data["ma50"]
        existing.ma100       = data["ma100"]
        existing.rel_iv      = data["rel_iv"]
        existing.spark_json  = json.dumps(data["spark_prices"])
        existing.cache_date  = today
    else:
        db.add(PriceCache(
            ticker       = data["ticker"],
            yahoo_symbol = data["yahoo_symbol"],
            close        = data["close"],
            volume       = data["volume"],
            ma20         = data["ma20"],
            ma50         = data["ma50"],
            ma100        = data["ma100"],
            rel_iv       = data["rel_iv"],
            spark_json   = json.dumps(data["spark_prices"]),
            cache_date   = today,
        ))

    db.commit()

    return {
        "ticker":       data["ticker"],
        "close":        data["close"],
        "volume":       data["volume"],
        "ma20":         data["ma20"],
        "ma50":         data["ma50"],
        "ma100":        data["ma100"],
        "rel_iv":       data["rel_iv"],
        "spark_prices": data["spark_prices"],
        "updated":      data["updated"],
    }


@router.get("/batch")
def get_batch(db: Session = Depends(get_db)):
    """
    Fetch market data for all Tier 1 tickers.
    Null results are omitted — React falls back to mock for those tickers.
    First call fetches all from Yahoo Finance (~30-60 seconds).
    Subsequent calls same day are served from SQLite cache (instant).
    """
    today   = str(date.today())
    results = []

    for ticker in TIER1_TICKERS:
        data = get_or_fetch(ticker, today, db)
        if data:
            results.append(data)
        else:
            logger.warning(f"No data for {ticker} — React will use mock")

    return {"data": results, "count": len(results), "date": today}


@router.get("/quote/{ticker}")
def get_quote(ticker: str, db: Session = Depends(get_db)):
    """
    Single ticker quote.
    Use for debugging: http://localhost:8000/api/market-data/quote/AAPL
    """
    today = str(date.today())
    data  = get_or_fetch(ticker.upper(), today, db)
    if data is None:
        return {"error": f"No data available for {ticker}"}
    return data
