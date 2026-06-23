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
from datetime import datetime, date as date_cls
from zoneinfo import ZoneInfo

import numpy as np

from sqlalchemy.orm import Session
import schwab.client

from models.price_cache import PriceCache
from models.ticker import Ticker
import services.schwab_client as schwab_client_svc
from services.yahoo_finance import (
    fetch_ticker_data,
    fetch_ticker_close,
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
SCHWAB_UNSUPPORTED = {
    "USD", "JPY", "/CL", "/ZN", "/GC", "SPX", "NDX", "$DJI", "VIX", "RUT", "VVIX",
    # Macro vol indices — batch quotes don't work; history API with $ prefix does
    "VXN", "RVX", "GVZ", "OVX", "MOVE",
    # Precious metals ETFs — Schwab history returns pre-restructuring prices creating
    # a discontinuity vs current post-restructuring quotes; Yahoo history is correct.
    "PALL", "PPLT",
}

# Macro vol index tickers fetchable via Schwab get_price_history() using $ prefix.
# These are a subset of SCHWAB_UNSUPPORTED — excluded from batch quotes but served
# via per-ticker history calls. Yahoo is the fallback if Schwab is unavailable.
SCHWAB_INDEX_HISTORY_MAP = {
    "VXN":  "$VXN",   # Nasdaq 100 Volatility Index
    "RVX":  "$RVX",   # Russell 2000 Volatility Index
    "GVZ":  "$GVZ",   # CBOE Gold ETF Volatility Index
    "OVX":  "$OVX",   # CBOE Crude Oil ETF Volatility Index
    "MOVE": "$MOVE",  # ICE BofA MOVE Index (bond market vol)
}


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


def _compute_std20(prices: list, close: float = None) -> float | None:
    """Standard Bollinger Band std — std of price levels over 20 days."""
    if len(prices) < 20:
        return None
    return round(float(np.std(prices[-20:], ddof=0)), 4)



def _history_fetch_mode(existing_row, today_str: str) -> str:
    """
    Determine what history fetch is needed for this ticker.

      "bootstrap" — no history, < 252 bars, or gap > 45 days → full 5-year fetch
      "short"     — gap 6–45 calendar days → 1-month fetch to fill gap
                    also triggered on first run after OHLC deployment (history_high_json NULL)
      "append"    — gap 1–5 calendar days (normal day / weekend / holiday) → append from quote
      "skip"      — last stored date is today → update quote fields only, no history change
    """
    if not existing_row or not existing_row.history_dates_json:
        return "bootstrap"
    dates = json.loads(existing_row.history_dates_json)
    if len(dates) < 252:
        return "bootstrap"

    # First run after OHLC deployment — need at least 20 bars of high/low history
    # for MA20(TP). Force a short fetch once per ticker; normal gap detection resumes
    # on all subsequent runs once history_high_json is populated.
    if not existing_row.history_high_json:
        return "short"

    last_date    = date_cls.fromisoformat(dates[-1])
    today        = date_cls.fromisoformat(today_str)
    calendar_gap = (today - last_date).days
    if calendar_gap == 0:
        return "skip"
    elif calendar_gap <= 5:
        return "append"
    elif calendar_gap <= 45:
        return "short"
    else:
        return "bootstrap"


def _update_quote_only(existing: PriceCache, close: float, volume: int,
                       today: str, data_source: str,
                       high: float = None, low: float = None) -> None:
    """Update close/volume/timestamp only — history unchanged (today already stored)."""
    import pandas as pd
    prices   = json.loads(existing.history_json)       if existing.history_json       else []
    closes_s = pd.Series(prices)
    existing.close       = close
    existing.volume      = volume
    existing.daily_high  = high
    existing.daily_low   = low
    existing.ma20        = round(float(closes_s.tail(20).mean()),  2) if len(closes_s) >= 20  else None
    existing.ma50        = round(float(closes_s.tail(50).mean()),  2) if len(closes_s) >= 50  else None
    existing.ma100       = round(float(closes_s.tail(100).mean()), 2) if len(closes_s) >= 100 else None
    existing.cache_date  = today
    existing.updated_at  = datetime.utcnow()
    existing.data_source = data_source


def _append_bar(existing: PriceCache, close: float, volume: int,
                today: str, data_source: str,
                high: float = None, low: float = None) -> None:
    """Append today's bar to existing history — no Schwab history API call needed."""
    import pandas as pd
    prices = json.loads(existing.history_json)        if existing.history_json        else []
    dates  = json.loads(existing.history_dates_json)  if existing.history_dates_json  else []
    vols   = json.loads(existing.volume_history_json) if existing.volume_history_json else []
    highs  = json.loads(existing.history_high_json)   if existing.history_high_json   else []
    lows   = json.loads(existing.history_low_json)    if existing.history_low_json    else []

    # Use close as fallback when H/L not provided
    h = high if high is not None else close
    l = low  if low  is not None else close

    if dates and dates[-1] == today:
        # Already present — update in place (re-run same day after market close)
        prices[-1] = close
        vols[-1]   = volume
        if highs: highs[-1] = h
        if lows:  lows[-1]  = l
    else:
        prices.append(close)
        dates.append(today)
        vols.append(volume)
        highs.append(h)
        lows.append(l)

    closes_s     = pd.Series(prices)
    spark_raw    = prices[-60:] if len(prices) >= 60 else prices
    spark_prices = [round(p, 2) for p in spark_raw]
    if spark_prices:
        spark_prices[-1] = close

    std20          = _compute_std20(prices)
    ma200          = round(float(np.mean(prices[-200:])), 2) if len(prices) >= 200 else None

    existing.close               = close
    existing.volume              = volume
    existing.daily_high          = h
    existing.daily_low           = l
    existing.ma20                = round(float(closes_s.tail(20).mean()),  2) if len(closes_s) >= 20  else None
    existing.ma50                = round(float(closes_s.tail(50).mean()),  2) if len(closes_s) >= 50  else None
    existing.ma100               = round(float(closes_s.tail(100).mean()), 2) if len(closes_s) >= 100 else None
    existing.ma200               = ma200
    existing.std20               = std20
    existing.spark_json          = json.dumps(spark_prices)
    existing.history_json        = json.dumps(prices)
    existing.history_dates_json  = json.dumps(dates)
    existing.history_high_json   = json.dumps(highs)
    existing.history_low_json    = json.dumps(lows)
    existing.volume_history_json = json.dumps(vols)
    existing.ath                 = round(float(max(prices)), 4) if prices else existing.ath
    existing.cache_date          = today
    existing.updated_at          = datetime.utcnow()
    existing.data_source         = data_source


def _upsert(db: Session, data: dict, data_source: str) -> None:
    """Write fetched ticker data into price_cache (no commit — caller commits).

    History merge: if existing history is longer than the new Schwab data
    (which only fetches 3 months), preserve the existing history and only
    update the recent portion. This prevents overwriting 5-year Yahoo history
    with 3 months of Schwab data.  Same merge applied to high/low history.
    """
    today  = datetime.now(_ET).strftime("%Y-%m-%d")
    ticker = data["ticker"]

    existing = db.query(PriceCache).filter(PriceCache.ticker == ticker).first()
    if existing:
        old_prices = json.loads(existing.history_json)        if existing.history_json        else []
        old_dates  = json.loads(existing.history_dates_json)  if existing.history_dates_json  else []
        old_vols   = json.loads(existing.volume_history_json) if existing.volume_history_json else []
        old_highs  = json.loads(existing.history_high_json)   if existing.history_high_json   else []
        old_lows   = json.loads(existing.history_low_json)    if existing.history_low_json    else []
        new_p, new_d, new_v = data["history_prices"], data["history_dates"], data["volume_history"]
        new_h = data.get("history_highs", [])
        new_l = data.get("history_lows",  [])

        if old_prices and new_d and len(new_p) < len(old_prices):
            # Schwab data is shorter — prepend old history up to where new data starts
            cut = sum(1 for d in old_dates if d < new_d[0])
            new_p = old_prices[:cut] + new_p
            new_d = old_dates[:cut]  + new_d
            new_v = old_vols[:cut]   + new_v
            # Merge OHLC — old OHLC history may be shorter if newly added; pad with close
            if new_h and old_highs and len(new_h) < len(new_p):
                new_h = old_highs[:cut] + new_h
                new_l = old_lows[:cut]  + new_l

        # Compute MA200 and STD20 from merged full history — Schwab alone is only 3 months
        # so MA200 requires the prepended history to be meaningful.
        close       = data["close"]
        std20       = _compute_std20(new_p, close)
        ma200       = round(float(np.mean(new_p[-200:])), 2) if len(new_p) >= 200 else None

        existing.close               = close
        existing.volume              = data["volume"]
        existing.daily_high          = data.get("daily_high")
        existing.daily_low           = data.get("daily_low")
        existing.ma20                = data["ma20"]
        existing.ma50                = data["ma50"]
        existing.ma100               = data["ma100"]
        existing.ma200               = ma200
        existing.std20               = std20
        existing.rel_iv              = data["rel_iv"]
        existing.spark_json          = json.dumps(data["spark_prices"])
        existing.history_json        = json.dumps(new_p)
        existing.history_dates_json  = json.dumps(new_d)
        existing.history_high_json   = json.dumps(new_h) if new_h else existing.history_high_json
        existing.history_low_json    = json.dumps(new_l) if new_l else existing.history_low_json
        existing.volume_history_json = json.dumps(new_v)
        existing.ath                 = round(float(max(new_p)), 4) if new_p else existing.ath
        existing.cache_date          = today
        existing.updated_at          = datetime.utcnow()
        existing.data_source         = data_source
    else:
        new_p = data["history_prices"]
        new_h = data.get("history_highs", [])
        new_l = data.get("history_lows",  [])
        close = data["close"]
        std20       = _compute_std20(new_p, close)
        ma200       = round(float(np.mean(new_p[-200:])), 2) if len(new_p) >= 200 else None

        db.add(PriceCache(
            ticker               = ticker,
            yahoo_symbol         = data.get("schwab_symbol", ticker),
            close                = close,
            volume               = data["volume"],
            daily_high           = data.get("daily_high"),
            daily_low            = data.get("daily_low"),
            ma20                 = data["ma20"],
            ma50                 = data["ma50"],
            ma100                = data["ma100"],
            ma200                = ma200,
            std20                = std20,
            rel_iv               = data["rel_iv"],
            spark_json           = json.dumps(data["spark_prices"]),
            history_json         = json.dumps(data["history_prices"]),
            history_dates_json   = json.dumps(data["history_dates"]),
            history_high_json    = json.dumps(new_h) if new_h else None,
            history_low_json     = json.dumps(new_l) if new_l else None,
            volume_history_json  = json.dumps(data["volume_history"]),
            ath                  = round(float(max(new_p)), 4) if new_p else None,
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


# ── Intraday quote refresh (15-min monitor only) ──────────────────────────────

def schwab_fetch_intraday_quotes(db: Session) -> dict:
    """
    Lightweight intraday price refresh for the 15-min monitor.

    Intentionally different from schwab_fetch_all() in three ways:
      1. No idempotency check — runs a fresh get_quotes() call every time.
         schwab_fetch_all() skips re-fetching once cache_date == today, making
         price_cache.close stale for the rest of the day.  This function has no
         such guard — every call gets a live lastPrice.
      2. lastPrice only — never falls back to closePrice (yesterday's EOD).
         If lastPrice is absent (pre-market, halted) the ticker is skipped.
      3. No history changes — cache_date is NOT updated, so schwab_fetch_all()
         idempotency remains intact for the EOD job.

    Updates price_cache: close, volume, daily_high, daily_low, updated_at.
    Yahoo-only tickers (indices, FX, futures) are skipped — they are in
    SCHWAB_UNSUPPORTED and are nearly always Neutral viewpoint anyway.
    """
    tickers        = _get_active_tickers(db)
    schwab_tickers = [t for t in tickers if t not in SCHWAB_UNSUPPORTED]
    schwab_symbols = [get_schwab_symbol(t) for t in schwab_tickers]

    if not schwab_tickers:
        return {"fetched": 0, "errors": 0}

    try:
        client = schwab_client_svc.get_schwab_client(db)
    except (RuntimeError, ValueError) as e:
        logger.warning(f"Intraday quotes: no Schwab client ({e}) — skipping")
        return {"fetched": 0, "errors": 0, "error": str(e)}

    try:
        quote_resp = client.get_quotes(schwab_symbols)
        quote_resp.raise_for_status()
        quotes = quote_resp.json()
    except Exception as e:
        logger.error(f"Intraday quotes: batch get_quotes failed — {e}")
        return {"fetched": 0, "errors": 1, "error": str(e)}

    existing_map = {
        r.ticker: r
        for r in db.query(PriceCache).filter(PriceCache.ticker.in_(schwab_tickers)).all()
    }

    fetched = 0
    skipped = 0

    for app_ticker in schwab_tickers:
        schwab_sym = get_schwab_symbol(app_ticker)
        q          = quotes.get(schwab_sym, {}).get("quote", {})

        # lastPrice only — refuse to use closePrice (yesterday's EOD close)
        last_price = q.get("lastPrice")
        if not last_price:
            skipped += 1
            logger.debug(f"Intraday quotes: no lastPrice for {app_ticker} — skipping")
            continue

        close      = round(float(last_price), 2)
        volume     = int(q.get("totalVolume", 0))
        daily_high = round(float(q.get("highPrice", close)), 2)
        daily_low  = round(float(q.get("lowPrice",  close)), 2)

        row = existing_map.get(app_ticker)
        if row:
            row.close      = close
            row.volume     = volume
            row.daily_high = daily_high
            row.daily_low  = daily_low
            row.updated_at = datetime.utcnow()
            # NOTE: cache_date intentionally NOT updated — preserves EOD idempotency
            fetched += 1

    db.commit()
    logger.info(f"Intraday quotes: {fetched} updated, {skipped} skipped (no lastPrice)")
    return {"fetched": fetched, "skipped": skipped}


def yahoo_fetch_intraday_quotes(db: Session) -> dict:
    """
    Lightweight intraday price refresh for Yahoo-only tickers (indices, FX, futures).
    Companion to schwab_fetch_intraday_quotes() — covers the SCHWAB_UNSUPPORTED set.

    Uses fetch_ticker_close() (5-day yfinance pull) to get the latest price.
    Same rules as schwab_fetch_intraday_quotes:
      - No cache_date update (preserves EOD idempotency)
      - Updates close, volume, daily_high, daily_low, updated_at only
    """
    from services.yahoo_finance import fetch_ticker_close

    tickers          = _get_active_tickers(db)
    yahoo_tickers    = [t for t in tickers if t in SCHWAB_UNSUPPORTED]

    if not yahoo_tickers:
        return {"fetched": 0, "errors": 0}

    existing_map = {
        r.ticker: r
        for r in db.query(PriceCache).filter(PriceCache.ticker.in_(yahoo_tickers)).all()
    }

    fetched = 0
    errors  = 0

    for ticker in yahoo_tickers:
        result = fetch_ticker_close(ticker)
        if result is None:
            errors += 1
            continue
        close, volume, daily_high, daily_low = result
        row = existing_map.get(ticker)
        if row:
            row.close      = close
            row.volume     = volume
            row.daily_high = daily_high
            row.daily_low  = daily_low
            row.updated_at = datetime.utcnow()
            # NOTE: cache_date intentionally NOT updated
            fetched += 1

    db.commit()
    logger.info(f"Yahoo intraday quotes: {fetched} updated, {errors} errors")
    return {"fetched": fetched, "errors": errors}


# ── Schwab index history fetch ────────────────────────────────────────────────

def _schwab_fetch_index_histories(db: Session, tickers: list, client) -> dict:
    """
    Fetch price history for macro vol index tickers via Schwab get_price_history().

    These tickers (VXN, RVX, GVZ, OVX, MOVE) are in SCHWAB_UNSUPPORTED because
    Schwab's batch quotes API cannot quote them.  However, get_price_history() works
    when the symbol is prefixed with $ (e.g. $VXN, $RVX).

    Same gap-detection modes as the main Schwab path.  The last candle in the
    history response serves as today's quote (no separate batch quote available).
    """
    import pandas as pd

    PH    = schwab.client.Client.PriceHistory
    today = datetime.now(_ET).strftime("%Y-%m-%d")

    fetched = 0
    errors  = 0

    existing_map = {
        r.ticker: r
        for r in db.query(PriceCache).filter(PriceCache.ticker.in_(tickers)).all()
    }

    for app_ticker in tickers:
        schwab_sym = SCHWAB_INDEX_HISTORY_MAP.get(app_ticker)
        if not schwab_sym:
            logger.warning(f"Schwab index: no symbol mapping for {app_ticker} — skipping")
            errors += 1
            continue

        existing_row = existing_map.get(app_ticker)
        mode         = _history_fetch_mode(existing_row, today)

        if mode == "skip":
            logger.debug(f"Schwab index: history current for {app_ticker} — skipping")
            fetched += 1
            continue

        # Period selection:
        #   append  → 1-month DAILY fetch. Schwab REJECTS periodType=day + frequencyType=daily
        #             with HTTP 400 ("valid values for frequencyType are: minute"), so the old
        #             10-day DAY fetch always 400'd → silent Yahoo fallback (defeating ADR-010,
        #             and freezing RVX whose ^RVX Yahoo symbol is delisted). MONTH/ONE_MONTH with
        #             daily frequency is the valid combo and is NOT mis-scaled (verified incl. MOVE
        #             against stored history, 2026-06-22). ~20 candles → merge upsert fills any
        #             multi-day gap (e.g. holiday + stale), not just the latest bar.
        #   short / bootstrap → 5-year fetch (reliable; upsert merge is efficient)
        if mode == "append":
            period_type, period = PH.PeriodType.MONTH, PH.Period.ONE_MONTH
            logger.info(f"Schwab index: append (1mo daily) for {app_ticker}")
        else:
            period_type, period = PH.PeriodType.YEAR, PH.Period.FIVE_YEARS
            cached_len = len(json.loads(existing_row.history_dates_json)) if existing_row and existing_row.history_dates_json else 0
            logger.info(f"Schwab index: {'gap fill' if mode == 'short' else 'bootstrap'} (5y) for {app_ticker} ({cached_len} bars cached)")

        try:
            hist_resp = client.get_price_history(
                schwab_sym,
                period_type              = period_type,
                period                   = period,
                frequency_type           = PH.FrequencyType.DAILY,
                frequency                = PH.Frequency.DAILY,
                need_extended_hours_data = False,
            )
            hist_resp.raise_for_status()
            candles = hist_resp.json().get("candles", [])
        except Exception as e:
            logger.warning(f"Schwab index: history fetch failed for {app_ticker}: {e} — trying Yahoo fallback")
            try:
                _yahoo_fetch_subset(db, [app_ticker], data_source="yahoo_fallback")
                logger.info(f"Schwab index: Yahoo fallback succeeded for {app_ticker}")
                fetched += 1
            except Exception as ye:
                logger.warning(f"Schwab index: Yahoo fallback also failed for {app_ticker}: {ye}")
                errors += 1
            time.sleep(0.5)
            continue

        if len(candles) < 2:
            logger.warning(f"Schwab index: insufficient history ({len(candles)} candles) for {app_ticker} — trying Yahoo fallback")
            try:
                _yahoo_fetch_subset(db, [app_ticker], data_source="yahoo_fallback")
                logger.info(f"Schwab index: Yahoo fallback succeeded for {app_ticker}")
                fetched += 1
            except Exception as ye:
                logger.warning(f"Schwab index: Yahoo fallback also failed for {app_ticker}: {ye}")
                errors += 1
            time.sleep(0.5)
            continue

        # Parse candles
        history_prices = [round(float(c["close"]),            4) for c in candles]
        history_highs  = [round(float(c.get("high", c["close"])), 4) for c in candles]
        history_lows   = [round(float(c.get("low",  c["close"])), 4) for c in candles]
        history_dates  = [
            datetime.fromtimestamp(c["datetime"] / 1000, tz=_ET).strftime("%Y-%m-%d")
            for c in candles
        ]
        volume_history = [int(c.get("volume", 0)) for c in candles]

        close = history_prices[-1]
        high  = history_highs[-1]
        low   = history_lows[-1]
        vol   = volume_history[-1]

        # All modes route through the merge upsert. _upsert preserves existing history
        # before the fetched window's first date and merges the recent bars, so a
        # multi-day gap (holiday + stale ticker) fills correctly — not just the latest
        # candle (the old append-bar path only tacked on history_prices[-1], leaving
        # interior holes when >1 trading day was missing).
        #
        # MAs are computed from the MERGED series (old + new window), not the ~20-candle
        # fetch alone, so ma50/ma100 don't null out on the short append fetch.
        old_dates  = json.loads(existing_row.history_dates_json) if existing_row and existing_row.history_dates_json else []
        old_prices = json.loads(existing_row.history_json)       if existing_row and existing_row.history_json       else []
        if old_prices and history_dates and len(history_prices) < len(old_prices):
            cut          = sum(1 for d in old_dates if d < history_dates[0])
            merged_close = old_prices[:cut] + history_prices
        else:
            merged_close = history_prices

        closes_s     = pd.Series(merged_close)
        spark_raw    = merged_close[-60:] if len(merged_close) >= 60 else merged_close
        spark_prices = [round(p, 2) for p in spark_raw]

        ma20   = round(float(closes_s.tail(20).mean()),  2) if len(closes_s) >= 20  else None
        ma50   = round(float(closes_s.tail(50).mean()),  2) if len(closes_s) >= 50  else None
        ma100  = round(float(closes_s.tail(100).mean()), 2) if len(closes_s) >= 100 else None
        rel_iv = compute_realized_vol_percentile(closes_s)

        _upsert(db, {
                "ticker":         app_ticker,
                "schwab_symbol":  schwab_sym,
                "close":          close,
                "volume":         vol,
                "daily_high":     high,
                "daily_low":      low,
                "ma20":           ma20,
                "ma50":           ma50,
                "ma100":          ma100,
                "rel_iv":         rel_iv,
                "spark_prices":   spark_prices,
                "history_prices": history_prices,
                "history_dates":  history_dates,
                "history_highs":  history_highs,
                "history_lows":   history_lows,
                "volume_history": volume_history,
            }, data_source="schwab")

        fetched += 1
        time.sleep(0.5)  # rate limit guard

    db.commit()
    logger.info(f"Schwab index histories: {fetched} fetched, {errors} errors")
    return {"fetched": fetched, "errors": errors}


# ── Schwab fetch ──────────────────────────────────────────────────────────────

def _schwab_fetch(db: Session, client, tickers: list) -> dict:
    """Batch quotes + per-ticker history via schwab-py."""
    import pandas as pd

    PH    = schwab.client.Client.PriceHistory
    today = datetime.now(_ET).strftime("%Y-%m-%d")

    schwab_tickers  = [t for t in tickers if t not in SCHWAB_UNSUPPORTED]
    unsupported     = [t for t in tickers if t in SCHWAB_UNSUPPORTED]
    schwab_symbols  = [get_schwab_symbol(t) for t in schwab_tickers]

    # ── Step 1: Batch quotes ──────────────────────────────────────────────────
    logger.info(f"Schwab: fetching batch quotes for {len(schwab_symbols)} symbols")
    quote_resp = client.get_quotes(schwab_symbols)
    quote_resp.raise_for_status()
    quotes = quote_resp.json()

    # ── Step 2: Per-ticker history — gap detection decides what to fetch ─────────
    fetched = 0
    errors  = 0

    # Pre-load all existing cache rows in one query — avoids N+1 within the loop
    existing_map = {
        r.ticker: r
        for r in db.query(PriceCache).filter(PriceCache.ticker.in_(schwab_tickers)).all()
    }

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

        close      = round(float(close), 2)
        daily_high = round(float(q.get("highPrice", close)), 2)
        daily_low  = round(float(q.get("lowPrice",  close)), 2)

        existing_row = existing_map.get(app_ticker)
        mode         = _history_fetch_mode(existing_row, today)

        # ── No API call paths ────────────────────────────────────────────────
        if mode == "skip":
            logger.debug(f"Schwab: history current for {app_ticker} — updating quote only")
            _update_quote_only(existing_row, close, volume, today, "schwab",
                               high=daily_high, low=daily_low)
            fetched += 1
            continue

        if mode == "append":
            logger.debug(f"Schwab: appending today's bar for {app_ticker}")
            _append_bar(existing_row, close, volume, today, "schwab",
                        high=daily_high, low=daily_low)
            fetched += 1
            continue

        # ── Schwab history API call needed ───────────────────────────────────
        if mode == "short":
            period_type, period = PH.PeriodType.MONTH, PH.Period.ONE_MONTH
            logger.info(f"Schwab: gap fill (1m) for {app_ticker}")
        else:  # bootstrap
            cached_len = len(json.loads(existing_row.history_dates_json)) if existing_row and existing_row.history_dates_json else 0
            period_type, period = PH.PeriodType.YEAR, PH.Period.FIVE_YEARS
            logger.info(f"Schwab: bootstrap (5y) for {app_ticker} ({cached_len} bars cached)")

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
        history_highs  = [round(float(c.get("high", c["close"])), 4) for c in candles]
        history_lows   = [round(float(c.get("low",  c["close"])), 4) for c in candles]
        history_dates  = [
            datetime.fromtimestamp(c["datetime"] / 1000, tz=_ET).strftime("%Y-%m-%d")
            for c in candles
        ]
        volume_history = [int(c.get("volume", 0)) for c in candles]

        closes_s     = pd.Series(history_prices)
        spark_raw    = history_prices[-60:] if len(history_prices) >= 60 else history_prices
        spark_prices = [round(p, 2) for p in spark_raw]
        if spark_prices:
            spark_prices[-1] = close  # anchor last point to exact quote

        ma20   = round(float(closes_s.tail(20).mean()),  2) if len(closes_s) >= 20  else None
        ma50   = round(float(closes_s.tail(50).mean()),  2) if len(closes_s) >= 50  else None
        ma100  = round(float(closes_s.tail(100).mean()), 2) if len(closes_s) >= 100 else None
        rel_iv = compute_realized_vol_percentile(closes_s)

        _upsert(db, {
            "ticker":         app_ticker,
            "schwab_symbol":  schwab_sym,
            "close":          close,
            "volume":         volume,
            "daily_high":     daily_high,
            "daily_low":      daily_low,
            "ma20":           ma20,
            "ma50":           ma50,
            "ma100":          ma100,
            "rel_iv":         rel_iv,
            "spark_prices":   spark_prices,
            "history_prices": history_prices,
            "history_dates":  history_dates,
            "history_highs":  history_highs,
            "history_lows":   history_lows,
            "volume_history": volume_history,
        }, data_source="schwab")

        fetched += 1
        time.sleep(0.5)  # rate limit guard — only reached on bootstrap or gap fill

    db.commit()

    # Split unsupported: index vol tickers go to Schwab history API; rest go to Yahoo
    yahoo_only   = [t for t in unsupported if t not in SCHWAB_INDEX_HISTORY_MAP]
    schwab_index = [t for t in unsupported if t in SCHWAB_INDEX_HISTORY_MAP]

    if yahoo_only:
        _yahoo_fetch_subset(db, yahoo_only, data_source="yahoo")
    if schwab_index:
        _schwab_fetch_index_histories(db, schwab_index, client)

    logger.info(f"Schwab fetch complete: {fetched} fetched, {errors} errors")
    return {"fetched": fetched, "errors": errors, "data_source": "schwab"}


# ── Yahoo fallback ────────────────────────────────────────────────────────────

def _yahoo_fallback(db: Session, tickers: list) -> dict:
    """Full Yahoo Finance fallback when Schwab is unavailable.

    SCHWAB_INDEX_HISTORY_MAP tickers (VXN, RVX, GVZ, OVX, MOVE) are excluded —
    Yahoo Finance cannot reliably serve these vol indices (^RVX is unavailable,
    others may return stale partial data). Stale Schwab-sourced data is better
    than corrupt Yahoo data overwriting good history.
    """
    yahoo_safe = [t for t in tickers if t not in SCHWAB_INDEX_HISTORY_MAP]
    skipped    = [t for t in tickers if t in SCHWAB_INDEX_HISTORY_MAP]
    if skipped:
        logger.info(f"Yahoo fallback: skipping Schwab-index tickers (no Yahoo data): {skipped}")
    logger.info(f"Yahoo fallback: fetching {len(yahoo_safe)} tickers")
    return _yahoo_fetch_subset(db, yahoo_safe, data_source="yahoo_fallback")


def _yahoo_fetch_subset(db: Session, tickers: list, data_source: str) -> dict:
    """Fetch a subset of tickers via Yahoo Finance and write to price_cache.

    Gap detection applied — same four modes as Schwab path:
      skip:      already fetched today → no-op
      append:    gap 1-5 days → lightweight 5-day fetch, append bar only
      short:     gap 6-45 days → full fetch + upsert (merge handles history)
      bootstrap: no history / < 252 bars / gap > 45 days → full 5-year fetch
    """
    today    = datetime.now(_ET).strftime("%Y-%m-%d")
    fetched  = 0
    errors   = 0
    rate_limited = False

    # Pre-load all existing rows — one query instead of N
    existing_map = {
        r.ticker: r
        for r in db.query(PriceCache).filter(PriceCache.ticker.in_(tickers)).all()
    }

    for ticker in tickers:
        if rate_limited:
            break

        existing = existing_map.get(ticker)
        mode     = _history_fetch_mode(existing, today)

        # ── Skip — already fresh ─────────────────────────────────────────────
        if mode == "skip":
            logger.debug(f"Yahoo: cache fresh for {ticker} — skipping")
            fetched += 1
            continue

        # ── Append — lightweight close fetch, no full history pull ───────────
        if mode == "append":
            result = fetch_ticker_close(ticker)
            if result:
                close, volume, high, low = result
                _append_bar(existing, close, volume, today, data_source,
                            high=high, low=low)
                fetched += 1
            else:
                errors += 1
            continue

        # ── Short gap or bootstrap — full fetch needed ───────────────────────
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
