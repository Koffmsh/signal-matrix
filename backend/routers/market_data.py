from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from database import get_db
from models.price_cache import PriceCache
from models.ticker import Ticker
from services.yahoo_finance import fetch_ticker_data, RateLimitError
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

_ET = ZoneInfo("America/New_York")
import json
import logging

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/market-data", tags=["market-data"])


def get_active_tickers(db: Session) -> list:
    rows = db.query(Ticker).filter(Ticker.active == True).order_by(Ticker.tier, Ticker.display_order).all()
    return [r.ticker for r in rows]


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
        "data_source":  row.data_source or "yahoo",
        "iv_source":    row.iv_source,
        "updated":      row.updated_at.replace(tzinfo=timezone.utc).astimezone(_ET).strftime("%m/%d/%y %H:%M") if row.updated_at else None,
    }


def get_stale(ticker: str, db: Session) -> dict | None:
    """Return any cached row for ticker, regardless of date."""
    row = db.query(PriceCache).filter(PriceCache.ticker == ticker).first()
    if row and row.close is not None:
        logger.info(f"Stale cache fallback: {ticker} (cached {row.cache_date})")
        return serialize_cache_row(row)
    return None


def get_or_fetch(ticker: str, today: str, db: Session) -> dict | None:
    """Return cached data if fresh for today, otherwise fetch from Yahoo and cache."""
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
        return get_stale(ticker, db)

    # Upsert: update existing row or insert new
    existing = db.query(PriceCache).filter(
        PriceCache.ticker == ticker
    ).first()

    if existing:
        existing.close               = data["close"]
        existing.volume              = data["volume"]
        existing.ma20                = data["ma20"]
        existing.ma50                = data["ma50"]
        existing.ma100               = data["ma100"]
        existing.rel_iv              = data["rel_iv"]
        existing.spark_json          = json.dumps(data["spark_prices"])
        existing.history_json        = json.dumps(data["history_prices"])
        existing.history_dates_json  = json.dumps(data["history_dates"])
        existing.volume_history_json = json.dumps(data["volume_history"])
        existing.cache_date          = today
        existing.updated_at          = datetime.utcnow()
        existing.data_source         = "yahoo"
    else:
        db.add(PriceCache(
            ticker               = data["ticker"],
            yahoo_symbol         = data["yahoo_symbol"],
            close                = data["close"],
            volume               = data["volume"],
            ma20                 = data["ma20"],
            ma50                 = data["ma50"],
            ma100                = data["ma100"],
            rel_iv               = data["rel_iv"],
            spark_json           = json.dumps(data["spark_prices"]),
            history_json         = json.dumps(data["history_prices"]),
            history_dates_json   = json.dumps(data["history_dates"]),
            volume_history_json  = json.dumps(data["volume_history"]),
            cache_date           = today,
            data_source          = "yahoo",
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
        "data_source":  "yahoo",
        "updated":      data["updated"],
    }


def refresh_data(db: Session) -> dict:
    """
    Core refresh logic — callable by scheduler or REFRESH DATA button.
    Tries Schwab first (via schwab_fetch_all); falls back to Yahoo Finance.
    After fetch, reads all tickers from cache and returns serialized data.
    """
    from services.schwab_market_data import schwab_fetch_all

    today = datetime.now(_ET).strftime("%Y-%m-%d")

    # Attempt Schwab fetch (handles its own Yahoo fallback internally)
    fetch_result = schwab_fetch_all(db)
    data_source  = fetch_result.get("data_source", "yahoo")
    rate_limited = fetch_result.get("rate_limited", False)

    # Read all active tickers from cache (now populated by fetch above)
    results = []
    for ticker in get_active_tickers(db):
        row = db.query(PriceCache).filter(PriceCache.ticker == ticker).first()
        if row and row.close is not None:
            results.append(serialize_cache_row(row))
        else:
            logger.warning(f"No cache row for {ticker} after fetch")

    return {
        "data":         results,
        "count":        len(results),
        "date":         today,
        "rate_limited": rate_limited,
        "data_source":  data_source,
    }


@router.get("/batch")
def get_batch(db: Session = Depends(get_db)):
    """
    Fetch market data for all active tickers.
    Tries Schwab first; falls back to Yahoo Finance.
    Subsequent calls same day are served from cache (fast).
    """
    return refresh_data(db)


@router.get("/quote/{ticker}")
def get_quote(ticker: str, db: Session = Depends(get_db)):
    """
    Single ticker quote — reads cache or fetches from Yahoo.
    Use for debugging: http://localhost:8000/api/market-data/quote/AAPL
    """
    today = datetime.now(_ET).strftime("%Y-%m-%d")  # ET date
    data  = get_or_fetch(ticker.upper(), today, db)
    if data is None:
        return {"error": f"No data available for {ticker}"}
    return data
