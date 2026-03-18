"""
Signal Engine — Task 3.1
Hurst Exponent + Fractal Dimension via DFA (Detrended Fluctuation Analysis)

Price history is read from the SQLite price_cache table (populated by REFRESH DATA).
Never calls yfinance directly — CALCULATE SIGNALS always runs after REFRESH DATA.
"""
import json
import logging
import numpy as np
from models.price_cache import PriceCache

logger = logging.getLogger(__name__)

# DFA lookback windows (trading days)
WINDOW_TRADE = 63
WINDOW_TREND = 252
WINDOW_LT    = 756


def get_prices_from_cache(ticker: str, db) -> list | None:
    """
    Read full price history from the SQLite price_cache table.
    Returns list of floats (oldest → newest), or None if not cached.
    REFRESH DATA must be run first to populate the cache.
    """
    row = db.query(PriceCache).filter(PriceCache.ticker == ticker).first()
    if row is None or not row.history_json:
        logger.warning(f"No cached price history for {ticker} — run REFRESH DATA first")
        return None
    return json.loads(row.history_json)


def dfa(prices: list, window: int) -> float | None:
    """
    Detrended Fluctuation Analysis — computes Hurst Exponent H.

    Algorithm:
    1. Convert prices to log returns
    2. Compute cumulative sum of mean-centred returns (integration)
    3. Generate ~20 log-spaced scales from 10 to window//4
    4. For each scale n: divide series into non-overlapping segments,
       detrend each segment (linear fit), compute RMS of residuals F(n)
    5. H = slope of log(F(n)) vs log(n) via linear regression

    Returns H in [0, 1], or None if insufficient data.
      H > 0.5 → trending (persistent)
      H < 0.5 → mean-reverting
      H = 0.5 → random walk
    """
    if len(prices) < window:
        return None

    # Use exactly the last `window` prices
    arr = np.array(prices[-window:], dtype=float)

    # Step 1: log returns (window-1 values)
    log_returns = np.log(arr[1:] / arr[:-1])

    # Step 2: cumulative sum of mean-centred returns
    cumsum = np.cumsum(log_returns - np.mean(log_returns))
    N = len(cumsum)

    # Step 3: log-spaced scales
    min_scale = 10
    max_scale = N // 4
    if max_scale < min_scale:
        return None

    scales = np.unique(
        np.round(
            np.logspace(np.log10(min_scale), np.log10(max_scale), 20)
        ).astype(int)
    )

    # Step 4: compute F(n) for each scale
    log_scales = []
    log_f_vals = []

    for n in scales:
        if n < 4:
            continue
        n_segments = N // n
        if n_segments < 2:
            continue

        rms_sum = 0.0
        x = np.arange(n, dtype=float)
        for seg in range(n_segments):
            segment = cumsum[seg * n:(seg + 1) * n]
            coeffs  = np.polyfit(x, segment, 1)
            trend   = np.polyval(coeffs, x)
            rms_sum += np.mean((segment - trend) ** 2)

        F_n = np.sqrt(rms_sum / n_segments)
        if F_n > 0:
            log_scales.append(np.log(float(n)))
            log_f_vals.append(np.log(F_n))

    # Step 5: H = slope of log(F(n)) vs log(n)
    if len(log_scales) < 4:
        return None

    coeffs = np.polyfit(log_scales, log_f_vals, 1)
    H = float(np.clip(coeffs[0], 0.0, 1.0))
    return H


def compute_hurst(ticker: str, db) -> dict:
    """
    Read price history from cache and compute H + D for all three timeframes.

    Returns dict with keys:
      ticker, h_trade, h_trend, h_lt, d_trade, d_trend, d_lt
    Fields are None when insufficient data or cache miss.
    """
    prices = get_prices_from_cache(ticker, db)

    if prices is None:
        return {
            "ticker":  ticker,
            "h_trade": None, "h_trend": None, "h_lt": None,
            "d_trade": None, "d_trend": None, "d_lt": None,
        }

    def h_and_d(window):
        h = dfa(prices, window)
        d = round(2.0 - h, 4) if h is not None else None
        h = round(h, 4)       if h is not None else None
        return h, d

    h_trade, d_trade = h_and_d(WINDOW_TRADE)
    h_trend, d_trend = h_and_d(WINDOW_TREND)
    h_lt,    d_lt    = h_and_d(WINDOW_LT)

    logger.info(
        f"{ticker}: H(trade)={h_trade} H(trend)={h_trend} H(lt)={h_lt}"
    )

    return {
        "ticker":  ticker,
        "h_trade": h_trade,
        "h_trend": h_trend,
        "h_lt":    h_lt,
        "d_trade": d_trade,
        "d_trend": d_trend,
        "d_lt":    d_lt,
    }
