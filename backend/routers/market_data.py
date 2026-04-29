from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session, load_only
from database import get_db
from models.price_cache import PriceCache
from models.ticker import Ticker
from services.yahoo_finance import fetch_ticker_data, RateLimitError, compute_ma20_regime
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo
import numpy as np
import json
import logging

_ET = ZoneInfo("America/New_York")

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/market-data", tags=["market-data"])


def get_active_tickers(db: Session) -> list:
    rows = db.query(Ticker).filter(Ticker.active == True).order_by(Ticker.tier, Ticker.display_order).all()
    return [r.ticker for r in rows]


def compute_vov_with_rank(vix_history_json: str) -> tuple:
    """
    Returns (vov_30d, vov_rank) from VIX price history.

    vov_30d:   30-day realized vol of VIX log returns, annualized.
    vov_rank:  percentile of vov_30d within its own trailing 252-day VoV history (0-100).
               Requires 252 + 30 bars (~282 total log returns). With 5 years of history
               (~1,260 bars) this is always available.

    Returns (None, None) if insufficient data.
    Returns (vov_30d, None) if enough for current VoV but not rank (< 282 log returns).
    """
    prices = np.array(json.loads(vix_history_json))
    if len(prices) < 32:
        return None, None

    log_returns = np.diff(np.log(prices))

    if len(log_returns) < 30:
        return None, None

    vov_current = float(np.std(log_returns[-30:], ddof=0) * np.sqrt(252))

    # Rolling 252-day history of 30d VoV values — computable from stored price history
    if len(log_returns) < 30 + 251:
        return vov_current, None

    vov_history = np.array([
        float(np.std(log_returns[i:i+30], ddof=0) * np.sqrt(252))
        for i in range(len(log_returns) - 30 - 251, len(log_returns) - 30 + 1)
    ])

    rank = float(np.sum(vov_history <= vov_current) / len(vov_history) * 100)
    return vov_current, round(rank, 1)


def serialize_cache_row(row: PriceCache) -> dict:
    return {
        "ticker":          row.ticker,
        "close":           row.close,
        "volume":          row.volume,
        "ma20":            row.ma20,
        "ma50":            row.ma50,
        "ma100":           row.ma100,
        "rel_iv":          row.rel_iv,
        "spark_prices":    json.loads(row.spark_json),
        "data_source":     row.data_source or "yahoo",
        "iv_source":       row.iv_source,
        "vov_30d":         row.vov_30d,
        "vov_rank":        row.vov_rank,
        # Volatility metrics
        "hv30":            row.hv30,
        "hv90":            row.hv90,
        "iv30":            row.iv30,
        "risk_reversal":   row.risk_reversal,
        "skew_rank":       row.skew_rank,
        "put_call_ratio":  row.put_call_ratio,
        "vrp_rank":        row.vrp_rank,
        "vrp_1d_chg":      row.vrp_1d_chg,
        "vrp_1w_chg":      row.vrp_1w_chg,
        "vrp_1m_chg":      row.vrp_1m_chg,
        "updated":         row.updated_at.replace(tzinfo=timezone.utc).astimezone(_ET).strftime("%m/%d/%y %H:%M") if row.updated_at else None,
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
        existing.ma200               = data["ma200"]
        existing.std20               = data["std20"]
        existing.ma20_regime         = data["ma20_regime"]
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
            ma200                = data["ma200"],
            std20                = data["std20"],
            ma20_regime          = data["ma20_regime"],
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
    Also refreshes IV (force=True so intraday manual refreshes get fresh IV).
    After fetch, reads all tickers from cache and returns serialized data.
    """
    from services.schwab_market_data import schwab_fetch_all
    from services.schwab_options import schwab_fetch_iv

    today = datetime.now(_ET).strftime("%Y-%m-%d")

    # Attempt Schwab fetch (handles its own Yahoo fallback internally)
    fetch_result = schwab_fetch_all(db)
    data_source  = fetch_result.get("data_source", "yahoo")
    rate_limited = fetch_result.get("rate_limited", False)

    # Refresh IV — idempotent (force=False): skips if already fetched today.
    # Scheduler always fetches fresh at 4 PM; manual REFRESH DATA skips IV if current.
    try:
        schwab_fetch_iv(db, force=False)
    except Exception as e:
        logger.warning(f"IV fetch skipped during refresh: {e}")

    # Task 6.2a — VoV: compute 30-day realized vol of VIX log returns after price fetch.
    try:
        vix_row = db.query(PriceCache).filter(PriceCache.ticker == "VIX").first()
        if vix_row and vix_row.history_json:
            vov_30d, vov_rank = compute_vov_with_rank(vix_row.history_json)
            vix_row.vov_30d = vov_30d
            vix_row.vov_rank = vov_rank
            db.commit()
    except Exception as e:
        logger.warning(f"VoV computation skipped: {e}")

    # VVIX price rank — stored in rel_iv (0-100 percentile within 252-day price history).
    # VVIX has no options chain so rel_iv is otherwise unused. Price rank is conceptually
    # identical to IV rank — where current price sits within its own rolling history.
    try:
        # expire_all forces SQLAlchemy to re-fetch from DB rather than returning the
        # partially-loaded session object (skip/append path loads VVIX without history_json)
        db.expire_all()
        vvix_row = db.query(PriceCache).filter(PriceCache.ticker == "VVIX").first()
        if vvix_row and vvix_row.history_json and vvix_row.close:
            prices = json.loads(vvix_row.history_json)
            if len(prices) >= 252:
                window = prices[-252:]
                rank = round(sum(p <= vvix_row.close for p in window) / len(window) * 100)
                vvix_row.rel_iv = rank
                vvix_row.iv_source = "price_rank"
                db.commit()
                logger.info(f"VVIX price rank: {rank}th pct ({len(prices)} bars)")
            else:
                logger.warning(f"VVIX price rank skipped: only {len(prices)} bars (need 252)")
        else:
            logger.warning(f"VVIX price rank skipped: row={vvix_row is not None}, history={vvix_row.history_json is not None if vvix_row else False}, close={vvix_row.close if vvix_row else None}")
    except Exception as e:
        logger.warning(f"VVIX price rank computation skipped: {e}")

    # Read all active tickers from cache in one query — avoids N+1 round trips to Supabase.
    # load_only skips history_json / volume_history_json blobs (not needed for page load).
    tickers = get_active_tickers(db)
    rows = (
        db.query(PriceCache)
        .filter(PriceCache.ticker.in_(tickers))
        .options(load_only(
            PriceCache.ticker, PriceCache.close, PriceCache.volume,
            PriceCache.ma20, PriceCache.ma50, PriceCache.ma100,
            PriceCache.rel_iv, PriceCache.iv_source, PriceCache.vov_30d, PriceCache.vov_rank,
            PriceCache.hv30, PriceCache.hv90, PriceCache.iv30,
            PriceCache.risk_reversal, PriceCache.skew_rank, PriceCache.put_call_ratio, PriceCache.vrp_rank,
            PriceCache.vrp_1d_chg, PriceCache.vrp_1w_chg, PriceCache.vrp_1m_chg,
            PriceCache.spark_json, PriceCache.data_source, PriceCache.updated_at,
        ))
        .all()
    )
    row_map = {r.ticker: r for r in rows}
    results = []
    for ticker in tickers:
        row = row_map.get(ticker)
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


@router.get("/cached")
def get_cached(db: Session = Depends(get_db)):
    """
    Read-only cache endpoint for page load — never triggers an external fetch.
    Returns whatever is currently stored in price_cache.
    REFRESH DATA button uses /batch instead.
    """
    today    = datetime.now(_ET).strftime("%Y-%m-%d")
    tickers  = get_active_tickers(db)
    rows = (
        db.query(PriceCache)
        .filter(PriceCache.ticker.in_(tickers))
        .options(load_only(
            PriceCache.ticker, PriceCache.close, PriceCache.volume,
            PriceCache.ma20, PriceCache.ma50, PriceCache.ma100,
            PriceCache.rel_iv, PriceCache.iv_source, PriceCache.vov_30d, PriceCache.vov_rank,
            PriceCache.hv30, PriceCache.hv90, PriceCache.iv30,
            PriceCache.risk_reversal, PriceCache.skew_rank, PriceCache.put_call_ratio, PriceCache.vrp_rank,
            PriceCache.vrp_1d_chg, PriceCache.vrp_1w_chg, PriceCache.vrp_1m_chg,
            PriceCache.spark_json, PriceCache.data_source, PriceCache.updated_at,
        ))
        .all()
    )
    row_map  = {r.ticker: r for r in rows}
    results  = []
    for ticker in tickers:
        row = row_map.get(ticker)
        if row and row.close is not None:
            results.append(serialize_cache_row(row))
    return {
        "data":        results,
        "count":       len(results),
        "date":        today,
        "data_source": "cached",
    }


@router.get("/batch")
def get_batch(db: Session = Depends(get_db)):
    """
    Fetch market data for all active tickers.
    Tries Schwab first; falls back to Yahoo Finance.
    Only called by the REFRESH DATA button — never on page load.
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
