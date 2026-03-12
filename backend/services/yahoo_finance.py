import yfinance as yf
import pandas as pd
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

# Symbol mapping — dashboard ticker -> Yahoo Finance symbol
YAHOO_SYMBOL_MAP = {
    "SPX":  "^GSPC",
    "NDX":  "^NDX",
    "$DJI": "^DJI",
    "VIX":  "^VIX",
    "USD":  "DX-Y.NYB",
    "JPY":  "JPY=X",
}

def get_yahoo_symbol(ticker: str) -> str:
    return YAHOO_SYMBOL_MAP.get(ticker, ticker)


def fetch_ticker_data(ticker: str) -> dict | None:
    """
    Fetch 14 months of history for a ticker (ensures 252 trading days).
    Returns dict with close, volume, ma20/50/100, rel_iv, spark_prices.
    Returns None if fetch fails.
    """
    yahoo_symbol = get_yahoo_symbol(ticker)

    try:
        yf_ticker = yf.Ticker(yahoo_symbol)
        hist = yf_ticker.history(period="14mo")

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

        # Realized volatility percentile (proxy for Rel IV until Schwab Phase 5)
        rel_iv = compute_realized_vol_percentile(closes)

        # Sparkline — last 60 closes, last point anchored to current close
        spark_window = closes.tail(60).tolist()
        spark_prices = [round(p, 2) for p in spark_window]
        if spark_prices:
            spark_prices[-1] = close  # Ensure last point = exact close

        updated = datetime.now().strftime("%m/%d/%y %H:%M")

        return {
            "ticker":        ticker,
            "yahoo_symbol":  yahoo_symbol,
            "close":         close,
            "volume":        volume,
            "ma20":          ma20,
            "ma50":          ma50,
            "ma100":         ma100,
            "rel_iv":        rel_iv,
            "spark_prices":  spark_prices,
            "updated":       updated,
        }

    except Exception as e:
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
