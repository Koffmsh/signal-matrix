"""
Pivot Engine — Task 3.2
ABC Pivot Detector: finds A, B, C, D price levels and structural state
for three timeframes (trade, trend, long-term).

Price history is read from the SQLite price_cache table (populated by REFRESH DATA).
Never calls yfinance directly — CALCULATE SIGNALS always runs after REFRESH DATA.
"""
import json
import logging
from models.price_cache import PriceCache

logger = logging.getLogger(__name__)

# Bar windows per timeframe (trading days)
TIMEFRAMES = {
    "trade": 3,
    "trend": 20,
    "lt":    90,
}


# ── Price fetch from cache ────────────────────────────────────────────────────

def get_prices_and_dates_from_cache(ticker: str, db):
    """
    Read full price history and dates from the SQLite price_cache table.
    Returns (prices: list[float], dates: list[str]) oldest → newest,
    or (None, None) if not cached.
    REFRESH DATA must be run first to populate the cache.
    """
    row = db.query(PriceCache).filter(PriceCache.ticker == ticker).first()
    if row is None or not row.history_json or not row.history_dates_json:
        logger.warning(f"No cached price history for {ticker} — run REFRESH DATA first")
        return None, None
    prices = json.loads(row.history_json)
    dates  = json.loads(row.history_dates_json)
    return prices, dates


# ── Pivot detection ───────────────────────────────────────────────────────────

def find_pivot_highs_lows(prices: list, bar_window: int):
    """
    Scan prices for pivot highs and pivot lows.

    Pivot high at index i: prices[i] == max(prices[i - bar_window : i + bar_window + 1])
    Pivot low  at index i: prices[i] == min(prices[i - bar_window : i + bar_window + 1])

    Returns:
        pivot_highs: list of (index, price)  — oldest to newest
        pivot_lows:  list of (index, price)  — oldest to newest
    """
    n = len(prices)
    pivot_highs = []
    pivot_lows  = []

    for i in range(bar_window, n - bar_window):
        window = prices[i - bar_window : i + bar_window + 1]
        if prices[i] == max(window):
            pivot_highs.append((i, prices[i]))
        if prices[i] == min(window):
            pivot_lows.append((i, prices[i]))

    return pivot_highs, pivot_lows


# ── ABC structure builder ─────────────────────────────────────────────────────

def _find_uptrend_abc(pivot_highs: list, pivot_lows: list):
    """
    Uptrend: A = pivot low, B = pivot high, C = pivot low (C > A).
    Walk backwards from the most recent pivot low as C candidate.
    Returns dict or None.
    """
    if len(pivot_lows) < 2 or len(pivot_highs) < 1:
        return None

    for c_pos in range(len(pivot_lows) - 1, 0, -1):
        c_idx, c_price = pivot_lows[c_pos]

        # Most recent pivot high before C
        b_candidates = [(i, p) for i, p in pivot_highs if i < c_idx]
        if not b_candidates:
            continue
        b_idx, b_price = b_candidates[-1]

        # Most recent pivot low before B
        a_candidates = [(i, p) for i, p in pivot_lows if i < b_idx]
        if not a_candidates:
            continue
        a_idx, a_price = a_candidates[-1]

        if c_price > a_price:   # uptrend confirmed: C higher than A
            return dict(
                direction="uptrend",
                a=a_price, b=b_price, c=c_price,
                a_idx=a_idx, b_idx=b_idx, c_idx=c_idx,
            )

    return None


def _find_downtrend_abc(pivot_highs: list, pivot_lows: list):
    """
    Downtrend: A = pivot high, B = pivot low, C = pivot high (C < A).
    Walk backwards from the most recent pivot high as C candidate.
    Returns dict or None.
    """
    if len(pivot_highs) < 2 or len(pivot_lows) < 1:
        return None

    for c_pos in range(len(pivot_highs) - 1, 0, -1):
        c_idx, c_price = pivot_highs[c_pos]

        # Most recent pivot low before C
        b_candidates = [(i, p) for i, p in pivot_lows if i < c_idx]
        if not b_candidates:
            continue
        b_idx, b_price = b_candidates[-1]

        # Most recent pivot high before B
        a_candidates = [(i, p) for i, p in pivot_highs if i < b_idx]
        if not a_candidates:
            continue
        a_idx, a_price = a_candidates[-1]

        if c_price < a_price:   # downtrend confirmed: C lower than A
            return dict(
                direction="downtrend",
                a=a_price, b=b_price, c=c_price,
                a_idx=a_idx, b_idx=b_idx, c_idx=c_idx,
            )

    return None


def find_abc_structure(pivot_highs: list, pivot_lows: list):
    """
    Find the most recent valid ABC structure (uptrend or downtrend).
    When both are valid, the one with the more recent C wins.
    Returns dict or None.
    """
    uptrend   = _find_uptrend_abc(pivot_highs, pivot_lows)
    downtrend = _find_downtrend_abc(pivot_highs, pivot_lows)

    if uptrend and downtrend:
        return uptrend if uptrend["c_idx"] >= downtrend["c_idx"] else downtrend

    return uptrend or downtrend


# ── D + structural state ──────────────────────────────────────────────────────

def compute_d_and_state(abc: dict, prices: list, timeframe: str):
    """
    Given an ABC structure and the full price series, compute:
      - D price (running high/low established when price closes through B)
      - D index in the prices array
      - Structural state string

    Break state naming: BREAK_OF_TRADE for 'trade' timeframe,
                        BREAK_OF_TREND for 'trend' and 'lt'.
    """
    direction     = abc["direction"]
    c_idx         = abc["c_idx"]
    b_price       = abc["b"]
    c_price       = abc["c"]
    current_price = prices[-1]
    break_state   = "BREAK_OF_TRADE" if timeframe == "trade" else "BREAK_OF_TREND"

    if direction == "uptrend":
        # C is the line in the sand
        if current_price < c_price:
            return None, None, break_state

        # Scan for first close above B after C
        first_breach = None
        for i in range(c_idx + 1, len(prices)):
            if prices[i] > b_price:
                first_breach = i
                break

        if first_breach is None:
            # B never breached — ABC valid, awaiting extension
            return None, None, "UPTREND_VALID"

        # D = running high from first breach to end (inclusive)
        d_slice = prices[first_breach:]
        d_price = max(d_slice)
        # Use last occurrence of d_price in the slice
        d_local_idx = max(i for i, p in enumerate(d_slice) if p == d_price)
        d_idx       = first_breach + d_local_idx

        # EXTENDED if current bar is at the running high, FORMING if pulled back
        state = "EXTENDED" if prices[-1] == d_price else "FORMING"
        return round(d_price, 4), d_idx, state

    else:  # downtrend
        # C is the line in the sand
        if current_price > c_price:
            return None, None, break_state

        # Scan for first close below B after C
        first_breach = None
        for i in range(c_idx + 1, len(prices)):
            if prices[i] < b_price:
                first_breach = i
                break

        if first_breach is None:
            return None, None, "DOWNTREND_VALID"

        # D = running low from first breach to end (inclusive)
        d_slice = prices[first_breach:]
        d_price = min(d_slice)
        d_local_idx = max(i for i, p in enumerate(d_slice) if p == d_price)
        d_idx       = first_breach + d_local_idx

        state = "EXTENDED" if prices[-1] == d_price else "FORMING"
        return round(d_price, 4), d_idx, state


# ── Per-timeframe computation ─────────────────────────────────────────────────

def compute_pivots_for_timeframe(prices: list, dates: list, timeframe: str, bar_window: int) -> dict:
    """
    Compute ABC pivot structure for a single timeframe.
    Returns a result dict with pivot levels, dates, and structural state.
    """
    min_bars = bar_window * 2 + 1

    if len(prices) < min_bars:
        logger.warning(f"Insufficient bars for {timeframe} timeframe (need {min_bars}, have {len(prices)})")
        return {"structural_state": "NO_STRUCTURE", "bar_window": bar_window}

    pivot_highs, pivot_lows = find_pivot_highs_lows(prices, bar_window)

    if len(pivot_highs) < 2 or len(pivot_lows) < 2:
        logger.warning(f"Not enough pivots for {timeframe}: {len(pivot_highs)} highs, {len(pivot_lows)} lows")
        return {"structural_state": "NO_STRUCTURE", "bar_window": bar_window}

    abc = find_abc_structure(pivot_highs, pivot_lows)

    if abc is None:
        return {"structural_state": "NO_STRUCTURE", "bar_window": bar_window}

    d_price, d_idx, state = compute_d_and_state(abc, prices, timeframe)

    return {
        "bar_window":       bar_window,
        "pivot_a":          round(abc["a"], 4),
        "pivot_b":          round(abc["b"], 4),
        "pivot_c":          round(abc["c"], 4),
        "pivot_d":          d_price,
        "pivot_a_date":     dates[abc["a_idx"]] if dates else None,
        "pivot_b_date":     dates[abc["b_idx"]] if dates else None,
        "pivot_c_date":     dates[abc["c_idx"]] if dates else None,
        "pivot_d_date":     dates[d_idx]         if (d_idx is not None and dates) else None,
        "structural_state": state,
        "direction":        abc["direction"],
    }


# ── Main entry point ──────────────────────────────────────────────────────────

def compute_pivots(ticker: str, db) -> dict:
    """
    Read price history from cache and compute ABC pivot structure
    for all three timeframes.

    Returns:
        {
            "ticker": str,
            "trade": { bar_window, pivot_a..d, pivot_a_date..d_date, structural_state, direction },
            "trend": { ... },
            "lt":    { ... },
        }
    All pivot fields are None when structural_state == "NO_STRUCTURE".
    """
    prices, dates = get_prices_and_dates_from_cache(ticker, db)

    if prices is None:
        return {
            "ticker": ticker,
            "trade":  {"structural_state": "NO_STRUCTURE", "bar_window": TIMEFRAMES["trade"]},
            "trend":  {"structural_state": "NO_STRUCTURE", "bar_window": TIMEFRAMES["trend"]},
            "lt":     {"structural_state": "NO_STRUCTURE", "bar_window": TIMEFRAMES["lt"]},
        }

    results = {"ticker": ticker}
    for tf, bw in TIMEFRAMES.items():
        tf_result = compute_pivots_for_timeframe(prices, dates, tf, bw)
        results[tf] = tf_result
        logger.info(
            f"{ticker} [{tf}]: state={tf_result['structural_state']}"
            + (f" A={tf_result.get('pivot_a')} B={tf_result.get('pivot_b')}"
               f" C={tf_result.get('pivot_c')} D={tf_result.get('pivot_d')}"
               if tf_result["structural_state"] != "NO_STRUCTURE" else "")
        )

    return results
