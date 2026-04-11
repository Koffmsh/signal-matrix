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
from models.signal_history import SignalHistory

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
    3. Generate ~20 log-spaced scales from 10 to N//2
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
    # Use N//2 as max_scale (not N//4) so the trade window (N=62) gets
    # scales 10–31 (~15 points) instead of 10–15 (6 points).  The
    # n_segments < 2 guard below already prevents any scale that is too large.
    min_scale = 10
    max_scale = N // 2
    if max_scale < min_scale:
        return None

    scales = np.unique(
        np.round(
            np.geomspace(min_scale, max_scale, 20)
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


def _dfa_from_returns(returns: np.ndarray, min_scale: int = 10) -> float | None:
    """
    DFA applied directly to a pre-computed returns array.
    Used for asymmetric H — up/down filtered return subsets passed in directly.

    Skips the log-return step (returns are already log returns).
    Integrates and runs DFA from that point forward.
    Returns H in [0, 1], or None if insufficient data (< 4 valid scales).
    """
    N = len(returns)
    if N < min_scale * 2:
        return None

    # Integrate: cumulative sum of mean-centred returns
    cumsum = np.cumsum(returns - np.mean(returns))
    N_cs = len(cumsum)

    max_scale = N_cs // 2
    if max_scale < min_scale:
        return None

    scales = np.unique(
        np.round(np.geomspace(min_scale, max_scale, 20)).astype(int)
    )

    log_scales = []
    log_f_vals = []

    for n in scales:
        if n < 4:
            continue
        n_segments = N_cs // n
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

    if len(log_scales) < 4:
        return None

    coeffs = np.polyfit(log_scales, log_f_vals, 1)
    H = float(np.clip(coeffs[0], 0.0, 1.0))
    return H


def compute_asymmetric_h(prices: list, window: int = 252) -> tuple:
    """
    Compute H separately for up-move days and down-move days over the Trend lookback.
    Returns (h_up, h_down). Either may be None if fewer than 30 observations.

    h_up:   persistence on positive-return days
    h_down: persistence on negative-return days

    Used in conviction for Commodities and FX only.
    Requires at least 30 observations per direction — returns None otherwise.
    """
    if len(prices) < window + 1:
        return None, None

    log_returns = np.diff(np.log(np.array(prices[-window:], dtype=float)))

    up_returns   = log_returns[log_returns > 0]
    down_returns = log_returns[log_returns < 0]

    h_up   = _dfa_from_returns(up_returns,   min_scale=10) if len(up_returns)   >= 30 else None
    h_down = _dfa_from_returns(down_returns, min_scale=10) if len(down_returns) >= 30 else None

    h_up   = round(h_up,   4) if h_up   is not None else None
    h_down = round(h_down, 4) if h_down is not None else None

    return h_up, h_down


def compute_h_trade_delta(db, ticker: str, current_h_trade: float) -> float | None:
    """
    Returns current_h_trade minus h_value from the trade-timeframe snapshot ~20 trading days ago.
    Positive = H improving (trend strengthening).
    Negative = H deteriorating (trend weakening — early warning).
    Returns None if insufficient history.
    """
    from datetime import datetime, timedelta
    from zoneinfo import ZoneInfo
    _ET = ZoneInfo("America/New_York")
    cutoff = (datetime.now(_ET) - timedelta(days=28)).strftime("%Y-%m-%d")  # ~20 trading days

    row = db.query(SignalHistory)\
        .filter(SignalHistory.ticker == ticker,
                SignalHistory.timeframe == "trade",
                SignalHistory.snapshot_date >= cutoff)\
        .order_by(SignalHistory.snapshot_date.asc())\
        .first()

    if row is None or row.h_value is None:
        return None
    return round(current_h_trade - row.h_value, 4)


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
