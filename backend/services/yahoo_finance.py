import time
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, date
from zoneinfo import ZoneInfo
import logging

_ET = ZoneInfo("America/New_York")

logger = logging.getLogger(__name__)


def compute_ma20_regime(prices: list) -> str:
    """
    Compute the terminal MA20 price regime using the 2-consecutive-close rule.

    regime = 'uptrend'   when the 2 most-recent closes are BOTH above the rolling MA20
    regime = 'downtrend' when the 2 most-recent closes are BOTH below the rolling MA20
    Forgiveness: 1 close on the wrong side does not flip the regime (mirrors BREAK_OF_TRADE logic).

    Scans backward from the most recent bar — O(1) in the common case.
    Returns 'uptrend' or 'downtrend'.
    """
    n = len(prices)
    if n < 21:
        return "downtrend"

    arr  = np.array(prices, dtype=float)
    cs   = np.cumsum(np.insert(arr, 0, 0.0))
    ma20 = (cs[20:] - cs[:-20]) / 20.0   # ma20[k] = SMA at arr[k + 19]
    above = arr[19:] > ma20               # above[k] = True if arr[k+19] > MA20[k]

    # Scan backward: find the most recent 2 consecutive closes on the same side
    for j in range(len(above) - 1, 0, -1):
        if above[j] and above[j - 1]:
            return "uptrend"
        if not above[j] and not above[j - 1]:
            return "downtrend"

    # Fallback — fewer than 2 valid MA20 observations
    return "uptrend" if above[-1] else "downtrend"


class RateLimitError(Exception):
    """Raised when Yahoo Finance returns a 429 Too Many Requests."""
    pass

# Symbol mapping — dashboard ticker -> Yahoo Finance symbol
YAHOO_SYMBOL_MAP = {
    "SPX":  "^GSPC",
    "NDX":  "^NDX",
    "$DJI": "^DJI",
    "VIX":  "^VIX",
    "USD":  "DX-Y.NYB",
    "JPY":  "JPY=X",
    "/CL":  "CL=F",    # WTI Crude Oil front-month futures
    "/ZN":  "ZN=F",    # 10-Year Treasury Note futures
    "/GC":  "GC=F",    # Gold futures
}

def get_yahoo_symbol(ticker: str) -> str:
    return YAHOO_SYMBOL_MAP.get(ticker, ticker)


def fetch_ticker_data(ticker: str) -> dict | None:
    """
    Fetch 4 years of history for a ticker.
    Returns dict with close, volume, ma20/50/100, rel_iv, spark_prices,
    history_prices (full 4-year list), and history_dates (corresponding YYYY-MM-DD list).
    Returns None if fetch fails.
    """
    yahoo_symbol = get_yahoo_symbol(ticker)

    try:
        yf_ticker = yf.Ticker(yahoo_symbol)
        hist = yf_ticker.history(period="4y")

        if hist.empty or len(hist) < 20:
            logger.warning(f"Insufficient data for {ticker} ({yahoo_symbol})")
            return None

        closes  = hist["Close"].dropna()
        volumes = hist["Volume"].dropna()

        # Latest values
        close  = round(float(closes.iloc[-1]), 2)
        volume = int(volumes.iloc[-1]) if not volumes.empty else 0

        # Moving averages — computed from close history
        ma20  = round(float(closes.tail(20).mean()),  2) if len(closes) >= 20  else None
        ma50  = round(float(closes.tail(50).mean()),  2) if len(closes) >= 50  else None
        ma100 = round(float(closes.tail(100).mean()), 2) if len(closes) >= 100 else None
        ma200 = round(float(closes.tail(200).mean()), 2) if len(closes) >= 200 else None

        # Realized volatility percentile (proxy for Rel IV until Schwab Phase 5)
        rel_iv = compute_realized_vol_percentile(closes)

        # Sparkline — last 60 closes, last point anchored to current close
        spark_window = closes.tail(60).tolist()
        spark_prices = [round(p, 2) for p in spark_window]
        if spark_prices:
            spark_prices[-1] = close  # Ensure last point = exact close

        # Full price history — include today's bar when fetched after market close (EOD).
        # Scheduler runs at 4:00 PM ET so today's close IS the confirmed EOD price.
        # Use <= so the 5th post-pivot bar counts on the day data is fetched.
        history_closes = closes[closes.index.date <= date.today()]
        history_prices = [round(float(p), 4) for p in history_closes.tolist()]
        history_dates  = [str(d.date()) for d in history_closes.index]

        # Volume history — aligned to history_closes dates so OBV series stays in sync
        # PHASE 5 SWAP COMPLETE: Schwab path populates volume_history_json from
        # candles[].volume in schwab_market_data._schwab_fetch() — Task 5.6.
        # This block is kept as the Yahoo fallback path only.
        # conviction_engine.py OBV engine reads volume_history_json regardless of source.
        # PHASE 6 TODO: swap to Schwab streaming volume for real-time OBV accuracy.
        volume_series  = hist["Volume"].reindex(history_closes.index).fillna(0)
        volume_history = [int(v) for v in volume_series.tolist()]

        # STD20 — 21-day realized vol in dollar terms (BB formula input, matches _sigma() in conviction_engine)
        if len(history_prices) >= 22:
            arr      = np.array(history_prices[-22:], dtype=float)
            log_rets = np.log(arr[1:] / arr[:-1])
            std20    = round(float(np.std(log_rets) * close), 4)
        else:
            std20 = None

        # MA20 price regime — 2-consecutive-close rule (separate from ABC pivot direction)
        ma20_regime = compute_ma20_regime(history_prices)

        updated = datetime.now(_ET).strftime("%m/%d/%y %H:%M")

        time.sleep(0.5)  # Rate limit: pause between Yahoo Finance fetches

        return {
            "ticker":          ticker,
            "yahoo_symbol":    yahoo_symbol,
            "close":           close,
            "volume":          volume,
            "ma20":            ma20,
            "ma50":            ma50,
            "ma100":           ma100,
            "ma200":           ma200,
            "std20":           std20,
            "ma20_regime":     ma20_regime,
            "rel_iv":          rel_iv,
            "spark_prices":    spark_prices,
            "history_prices":  history_prices,
            "history_dates":   history_dates,
            "volume_history":  volume_history,
            "updated":         updated,
        }

    except Exception as e:
        err = str(e)
        if "429" in err or "too many requests" in err.lower() or "rate limit" in err.lower():
            logger.error(f"Rate limit (429) hit on {ticker} ({yahoo_symbol}) — stopping batch")
            raise RateLimitError(f"429 on {ticker}")
        logger.error(f"Failed to fetch {ticker} ({yahoo_symbol}): {e}")
        return None


def compute_realized_vol_percentile(closes: pd.Series) -> int:
    """
    Realized volatility percentile (0-100) as Rel IV proxy.
    Method: 21-day rolling annualized realized vol, percentile rank
    within its own 252-day history.
    Replaced by Schwab IV Percentile in Phase 5.
    """
    try:
        if len(closes) < 42:
            return 50  # Insufficient data — default to midpoint

        log_returns  = closes.pct_change().dropna()
        rolling_vol  = log_returns.rolling(21).std() * (252 ** 0.5)
        rolling_vol  = rolling_vol.dropna()

        if len(rolling_vol) < 2:
            return 50

        current_vol  = rolling_vol.iloc[-1]
        hist_vol     = rolling_vol.tail(252)
        percentile   = int((hist_vol < current_vol).sum() / len(hist_vol) * 100)

        return max(0, min(100, percentile))

    except Exception:
        return 50  # Safe default
