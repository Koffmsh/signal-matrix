"""
schwab_market_data.py — Schwab EOD quote + price history fetch.

Entry point: schwab_fetch_all(db)
  - Tries Schwab first (batch quotes + per-ticker history)
  - Falls back to Yahoo Finance on any Schwab error or missing tokens
  - Writes to price_cache with data_source = 'schwab' or 'yahoo_fallback'
  - Skips re-fetch if Schwab data already cached for today (idempotent)

Called by:
  - scheduler.py at 4:00 PM ET (schwab_data_job)
  - market_data.py refresh_data() (REFRESH DATA button)
"""

import json
import time
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session
import schwab.client

from models.price_cache import PriceCache
from models.ticker import Ticker
import services.schwab_client as schwab_client_svc
from services.yahoo_finance import (
    fetch_ticker_data,
    RateLimitError,
    compute_realized_vol_percentile,
)

logger = logging.getLogger(__name__)
_ET = ZoneInfo("America/New_York")

# Schwab symbol overrides — app ticker → Schwab API symbol
SCHWAB_SYMBOL_MAP = {
    "SPX":  "$SPX.X",
    "NDX":  "$NDX.X",
    "$DJI": "$DJI.X",
    "VIX":  "$VIX.X",
}

# Tickers always routed through Yahoo Finance — Schwab cannot quote these:
#   Indices (SPX, NDX, $DJI, VIX): Schwab batch quotes API returns no data for these
#   FX (USD, JPY): non-equity instruments not available in Schwab equity quotes
#   Futures (/CL, /ZN, /GC): continuous front-month symbols Schwab doesn't serve
# Without this routing, Schwab errors leave updated_at stale → REFRESH DATA stays amber
SCHWAB_UNSUPPORTED = {"USD", "JPY", "/CL", "/ZN", "/GC", "SPX", "NDX", "$DJI", "VIX"}


def get_schwab_symbol(ticker: str) -> str:
    return SCHWAB_SYMBOL_MAP.get(ticker, ticker)


def _get_active_tickers(db: Session) -> list:
    rows = (
        db.query(Ticker)
        .filter(Ticker.active == True)
        .order_by(Ticker.tier, Ticker.display_order)
        .all()
    )
    return [r.ticker for r in rows]


def _upsert(db: Session, data: dict, data_source: str) -> None:
    """Write fetched ticker data into price_cache (no commit — caller commits).

    History merge: if existing history is longer than the new Schwab data
    (which only fetches 3 months), preserve the existing history and only
    update the recent portion. This prevents overwriting 4-year Yahoo history
    with 3 months of Schwab data.
    """
    today  = datetime.now(_ET).strftime("%Y-%m-%d")
    ticker = data["ticker"]

    existing = db.query(PriceCache).filter(PriceCache.ticker == ticker).first()
    if existing:
        old_prices = json.loads(existing.history_json)        if existing.history_json        else []
        old_dates  = json.loads(existing.history_dates_json)  if existing.history_dates_json  else []
        old_vols   = json.loads(existing.volume_history_json) if existing.volume_history_json else []
        new_p, new_d, new_v = data["history_prices"], data["history_dates"], data["volume_history"]

        if old_prices and new_d and len(new_p) < len(old_prices):
            # Schwab data is shorter — prepend old history up to where new data starts
            cut = sum(1 for d in old_dates if d < new_d[0])
            new_p = old_prices[:cut] + new_p
            new_d = old_dates[:cut]  + new_d
            new_v = old_vols[:cut]   + new_v

        existing.close               = data["close"]
        existing.volume              = data["volume"]
        existing.ma20                = data["ma20"]
        existing.ma50                = data["ma50"]
        existing.ma100               = data["ma100"]
        existing.rel_iv              = data["rel_iv"]
        existing.spark_json          = json.dumps(data["spark_prices"])
        existing.history_json        = json.dumps(new_p)
        existing.history_dates_json  = json.dumps(new_d)
        existing.volume_history_json = json.dumps(new_v)
        existing.cache_date          = today
        existing.updated_at          = datetime.utcnow()
        existing.data_source         = data_source
    else:
        db.add(PriceCache(
            ticker               = ticker,
            yahoo_symbol         = data.get("schwab_symbol", ticker),
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
            data_source          = data_source,
        ))


# ── Public entry point ────────────────────────────────────────────────────────

def schwab_fetch_all(db: Session) -> dict:
    """
    Fetch all active tickers. Tries Schwab first; falls back to Yahoo Finance.
    Returns summary: {"fetched": N, "errors": N, "data_source": "schwab"|"yahoo_fallback"}.

    Idempotent within a trading day — if Schwab data is already cached for today,
    returns immediately without re-fetching.
    """
    today   = datetime.now(_ET).strftime("%Y-%m-%d")
    tickers = _get_active_tickers(db)

    if not tickers:
        return {"fetched": 0, "errors": 0, "data_source": "yahoo"}

    # Idempotency check — skip if already fetched from Schwab today.
    # Use a Schwab-supported ticker (exclude SCHWAB_UNSUPPORTED) to avoid
    # perpetual cache miss when the first ticker is a Yahoo-only symbol.
    schwab_tickers = [t for t in tickers if t not in SCHWAB_UNSUPPORTED]
    check_ticker   = schwab_tickers[0] if schwab_tickers else None
    if check_ticker:
        sample = (
            db.query(PriceCache)
            .filter(
                PriceCache.ticker      == check_ticker,
                PriceCache.cache_date  == today,
                PriceCache.data_source == "schwab",
            )
            .first()
        )
        if sample:
            logger.info("Schwab: cache already fresh for today — skipping Schwab re-fetch")
            # Still refresh Yahoo-only tickers — they have no Schwab idempotency guard
            # and their updated_at must be stamped so the header timestamp stays current
            unsupported = [t for t in tickers if t in SCHWAB_UNSUPPORTED]
            if unsupported:
                _yahoo_fetch_subset(db, unsupported, data_source="yahoo")
            return {"fetched": len(tickers), "errors": 0, "data_source": "schwab"}

    # Try to build a Schwab client
    try:
        client = schwab_client_svc.get_schwab_client(db)
    except (RuntimeError, ValueError) as e:
        logger.warning(f"Schwab: client unavailable ({e}) — falling back to Yahoo Finance")
        return _yahoo_fallback(db, tickers)

    # Attempt full Schwab fetch
    try:
        return _schwab_fetch(db, client, tickers)
    except Exception as e:
        logger.error(f"Schwab fetch failed: {e} — falling back to Yahoo Finance")
        return _yahoo_fallback(db, tickers)


# ── Schwab fetch ──────────────────────────────────────────────────────────────

def _schwab_fetch(db: Session, client, tickers: list) -> dict:
    """Batch quotes + per-ticker history via schwab-py."""
    import pandas as pd

    PH = schwab.client.Client.PriceHistory

    schwab_tickers  = [t for t in tickers if t not in SCHWAB_UNSUPPORTED]
    unsupported     = [t for t in tickers if t in SCHWAB_UNSUPPORTED]
    schwab_symbols  = [get_schwab_symbol(t) for t in schwab_tickers]

    # ── Step 1: Batch quotes ──────────────────────────────────────────────────
    logger.info(f"Schwab: fetching batch quotes for {len(schwab_symbols)} symbols")
    quote_resp = client.get_quotes(schwab_symbols)
    quote_resp.raise_for_status()
    quotes = quote_resp.json()

    # ── Step 2: Per-ticker price history ─────────────────────────────────────
    fetched = 0
    errors  = 0

    for app_ticker in schwab_tickers:
        schwab_sym = get_schwab_symbol(app_ticker)
        quote_data = quotes.get(schwab_sym, {})

        if not quote_data:
            logger.warning(f"Schwab: no quote data for {app_ticker} ({schwab_sym}) — available keys: {list(quotes.keys())[:10]}")
            errors += 1
            continue

        # Extract last price — indices use closePrice, equities use lastPrice/mark
        q      = quote_data.get("quote", {})
        close  = q.get("lastPrice") or q.get("closePrice") or q.get("mark")
        volume = int(q.get("totalVolume", 0))

        if close is None:
            logger.warning(f"Schwab: no price for {app_ticker} ({schwab_sym})")
            errors += 1
            continue

        close = round(float(close), 2)

        # Price history — 5 years on first fetch (bootstrap); 3 months on subsequent fetches
        existing_row = db.query(PriceCache).filter(PriceCache.ticker == app_ticker).first()
        existing_len = len(json.loads(existing_row.history_json)) if existing_row and existing_row.history_json else 0
        needs_bootstrap = existing_len < 252

        if needs_bootstrap:
            period_type, period = PH.PeriodType.YEAR, PH.Period.FIVE_YEARS
            logger.info(f"Schwab: bootstrap fetch (5y) for {app_ticker} ({existing_len} bars cached)")
        else:
            period_type, period = PH.PeriodType.MONTH, PH.Period.THREE_MONTHS

        logger.debug(f"Schwab: fetching history for {app_ticker} ({schwab_sym})")
        try:
            hist_resp = client.get_price_history(
                schwab_sym,
                period_type    = period_type,
                period         = period,
                frequency_type = PH.FrequencyType.DAILY,
                frequency      = PH.Frequency.DAILY,
                need_extended_hours_data = False,
            )
            hist_resp.raise_for_status()
            candles = hist_resp.json().get("candles", [])
        except Exception as e:
            logger.warning(f"Schwab: history fetch failed for {app_ticker}: {e}")
            errors += 1
            time.sleep(0.5)
            continue

        if len(candles) < 20:
            logger.warning(f"Schwab: insufficient history ({len(candles)} candles) for {app_ticker}")
            errors += 1
            time.sleep(0.5)
            continue

        history_prices = [round(float(c["close"]), 4) for c in candles]
        history_dates  = [
            datetime.fromtimestamp(c["datetime"] / 1000, tz=_ET).strftime("%Y-%m-%d")
            for c in candles
        ]
        volume_history = [int(c.get("volume", 0)) for c in candles]

        closes_s  = pd.Series(history_prices)
        spark_raw = history_prices[-60:] if len(history_prices) >= 60 else history_prices
        spark_prices = [round(p, 2) for p in spark_raw]
        if spark_prices:
            spark_prices[-1] = close  # anchor last point to exact quote

        ma20  = round(float(closes_s.tail(20).mean()),  2) if len(closes_s) >= 20  else None
        ma50  = round(float(closes_s.tail(50).mean()),  2) if len(closes_s) >= 50  else None
        ma100 = round(float(closes_s.tail(100).mean()), 2) if len(closes_s) >= 100 else None
        rel_iv = compute_realized_vol_percentile(closes_s)

        _upsert(db, {
            "ticker":         app_ticker,
            "schwab_symbol":  schwab_sym,
            "close":          close,
            "volume":         volume,
            "ma20":           ma20,
            "ma50":           ma50,
            "ma100":          ma100,
            "rel_iv":         rel_iv,
            "spark_prices":   spark_prices,
            "history_prices": history_prices,
            "history_dates":  history_dates,
            "volume_history": volume_history,
        }, data_source="schwab")

        fetched += 1
        time.sleep(0.5)  # Rate limit: 120 req/min; 51 calls @ 0.5s ≈ 26s

    db.commit()

    # Tickers Schwab doesn't carry — fetch from Yahoo tagged as 'yahoo'
    if unsupported:
        _yahoo_fetch_subset(db, unsupported, data_source="yahoo")

    logger.info(f"Schwab fetch complete: {fetched} fetched, {errors} errors")
    return {"fetched": fetched, "errors": errors, "data_source": "schwab"}


# ── Yahoo fallback ────────────────────────────────────────────────────────────

def _yahoo_fallback(db: Session, tickers: list) -> dict:
    """Full Yahoo Finance fallback when Schwab is unavailable."""
    logger.info(f"Yahoo fallback: fetching {len(tickers)} tickers")
    return _yahoo_fetch_subset(db, tickers, data_source="yahoo_fallback")


def _yahoo_fetch_subset(db: Session, tickers: list, data_source: str) -> dict:
    """Fetch a subset of tickers via Yahoo Finance and write to price_cache."""
    fetched      = 0
    errors       = 0
    rate_limited = False

    for ticker in tickers:
        if rate_limited:
            break
        try:
            data = fetch_ticker_data(ticker)
            if data:
                _upsert(db, data, data_source=data_source)
                fetched += 1
            else:
                errors += 1
        except RateLimitError:
            logger.warning(f"Yahoo Finance 429 at {ticker} — stopping")
            rate_limited = True
            errors += 1

    db.commit()
    logger.info(f"Yahoo fetch complete: {fetched} fetched, {errors} errors, source={data_source}")
    return {"fetched": fetched, "errors": errors, "data_source": data_source, "rate_limited": rate_limited}
