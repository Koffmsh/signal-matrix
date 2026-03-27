"""
Pivot Engine — Task 3.2
ABC Pivot Detector: finds A, B, C, D price levels and structural state
for three timeframes (trade, trend, long-term).

Price history is read from the SQLite price_cache table (populated by REFRESH DATA).
Never calls yfinance directly — CALCULATE SIGNALS always runs after REFRESH DATA.
"""
import json
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

import pandas_market_calendars as mcal

from models.price_cache import PriceCache

_ET = ZoneInfo("America/New_York")
_NYSE = mcal.get_calendar("NYSE")
# Max trading days since pivot_c before the structure is considered stale.
# None = no cutoff (long-term structures are expected to be old).
_STALE_C_DAYS = {
    "trade": 60,
    "trend": 100,
    "lt":    None,
}

logger = logging.getLogger(__name__)


def _trading_days_since(date_str: str) -> int:
    """
    Count NYSE trading days elapsed since date_str (exclusive) through today ET (inclusive).
    Returns 0 on any parse or calendar error.
    """
    try:
        today_et = datetime.now(_ET).date()
        schedule = _NYSE.schedule(start_date=date_str, end_date=str(today_et))
        return max(0, len(schedule) - 1)  # subtract 1 to exclude the C date itself
    except Exception:
        return 0


# Bar windows per timeframe (trading days)
TIMEFRAMES = {
    "trade": 5,
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
    For each (C, B) pair, try all A candidates (not just the most recent)
    so that a valid C > A match is found even when the nearest A is above C.
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

        # Try all pivot lows before B as A — newest first — stop at first C > A
        a_candidates = [(i, p) for i, p in pivot_lows if i < b_idx]
        if not a_candidates:
            continue
        for a_idx, a_price in reversed(a_candidates):
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
    For each (C, B) pair, try all A candidates (not just the most recent)
    so that a valid C < A match is found even when the nearest A is below C.
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

        # Try all pivot highs before B as A — newest first — stop at first C < A
        a_candidates = [(i, p) for i, p in pivot_highs if i < b_idx]
        if not a_candidates:
            continue
        for a_idx, a_price in reversed(a_candidates):
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


def update_c_dynamically(abc: dict, pivot_highs: list, pivot_lows: list) -> dict:
    """
    After the initial ABC is confirmed, scan all subsequent pivots for a
    dynamic C update:

    Uptrend:   any pivot low AFTER current C that is HIGHER than current C
               → update C upward (higher low = structural improvement)
    Downtrend: any pivot high AFTER current C that is LOWER than current C
               → update C downward (lower high = structural deterioration)

    C only moves in the direction that strengthens the trend.
    C never moves against the trend (that would be a break, not an update).

    Returns updated abc dict (or original if no update occurred).
    """
    direction = abc["direction"]
    c_idx     = abc["c_idx"]
    c_price   = abc["c"]

    if direction == "uptrend":
        # Scan all pivot lows after initial C — take every higher low found
        for i, p in pivot_lows:
            if i > c_idx and p > c_price:
                c_idx   = i
                c_price = p

    else:  # downtrend
        # Scan all pivot highs after initial C — take every lower high found
        for i, p in pivot_highs:
            if i > c_idx and p < c_price:
                c_idx   = i
                c_price = p

    return {**abc, "c": c_price, "c_idx": c_idx}


# ── Confirmed break detection ─────────────────────────────────────────────────

def _check_break_confirmed(prices: list, c_idx: int, c_price: float,
                           b_price: float, direction: str,
                           threshold: int = 2) -> bool:
    """
    Returns True if a BREAK_CONFIRMED condition exists:
      - A streak of >= threshold consecutive closes on the wrong side of C
        has occurred since C was established (prices after c_idx)
      - Price has NOT since recovered above B (uptrend) / below B (downtrend)

    Catches both active breaks (current price still on wrong side) and
    post-break price recoveries above C that have not yet cleared B.
    """
    prices_since_c = prices[c_idx + 1:]
    if len(prices_since_c) < threshold:
        return False

    if direction == "uptrend":
        on_wrong_side = lambda p: p < c_price
        recovered_b   = lambda p: p > b_price
    else:
        on_wrong_side = lambda p: p > c_price
        recovered_b   = lambda p: p < b_price

    n = len(prices_since_c)

    # Find the last close on the wrong side of C since C was established
    last_wrong_idx = None
    for j in range(n - 1, -1, -1):
        if on_wrong_side(prices_since_c[j]):
            last_wrong_idx = j
            break

    if last_wrong_idx is None:
        return False  # C was never broken since it was established

    # Count consecutive wrong-side closes ending at last_wrong_idx
    streak = 0
    for j in range(last_wrong_idx, -1, -1):
        if on_wrong_side(prices_since_c[j]):
            streak += 1
        else:
            break

    if streak < threshold:
        return False  # single-day break — forgiveness still allowed

    # Check if price recovered above B since the streak ended
    for j in range(last_wrong_idx + 1, n):
        if recovered_b(prices_since_c[j]):
            return False  # recovery above B clears the confirmed break

    return True  # confirmed break with no B recovery → BREAK_CONFIRMED


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
        # C is the line in the sand — break fires when price closes below current C
        if current_price < c_price:
            if _check_break_confirmed(prices, abc["c_idx"], c_price, b_price, "uptrend"):
                return None, None, "BREAK_CONFIRMED"
            return None, None, break_state

        # Price above C — check if an unresolved confirmed break still applies
        # (recovered above C but never cleared B)
        if _check_break_confirmed(prices, abc["c_idx"], c_price, b_price, "uptrend"):
            return None, None, "BREAK_CONFIRMED"

        # D is established the moment price closes above B.
        # Scan from b_idx+1 (not c_idx+1) so a breach that occurred before a
        # dynamic C update is never missed.
        b_idx        = abc["b_idx"]
        first_breach = None
        for i in range(b_idx + 1, len(prices)):
            if prices[i] > b_price:
                first_breach = i
                break

        if first_breach is None:
            # B never breached — ABC valid, awaiting extension
            return None, None, "UPTREND_VALID"

        # D = running high from first breach to end (inclusive)
        d_slice     = prices[first_breach:]
        d_price     = max(d_slice)
        d_local_idx = max(i for i, p in enumerate(d_slice) if p == d_price)
        d_idx       = first_breach + d_local_idx

        # EXTENDED if current bar is at the running high, FORMING if pulled back
        state = "EXTENDED" if prices[-1] == d_price else "FORMING"
        return round(d_price, 4), d_idx, state

    else:  # downtrend
        # C is the line in the sand — break fires when price closes above current C
        if current_price > c_price:
            if _check_break_confirmed(prices, abc["c_idx"], c_price, b_price, "downtrend"):
                return None, None, "BREAK_CONFIRMED"
            return None, None, break_state

        # Price below C — check if an unresolved confirmed break still applies
        if _check_break_confirmed(prices, abc["c_idx"], c_price, b_price, "downtrend"):
            return None, None, "BREAK_CONFIRMED"

        # Scan from b_idx+1 so a breach before a dynamic C update is not missed
        b_idx        = abc["b_idx"]
        first_breach = None
        for i in range(b_idx + 1, len(prices)):
            if prices[i] < b_price:
                first_breach = i
                break

        if first_breach is None:
            return None, None, "DOWNTREND_VALID"

        # D = running low from first breach to end (inclusive)
        d_slice     = prices[first_breach:]
        d_price     = min(d_slice)
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

    # Update C to the most recent confirmed structural level
    abc = update_c_dynamically(abc, pivot_highs, pivot_lows)

    d_price, d_idx, state = compute_d_and_state(abc, prices, timeframe)

    # Stale C check — if pivot_c exceeds the timeframe cutoff, treat as NO_STRUCTURE
    max_c_age = _STALE_C_DAYS.get(timeframe)
    c_date_str = dates[abc["c_idx"]] if dates else None
    if max_c_age is not None and c_date_str and _trading_days_since(c_date_str) > max_c_age:
        logger.info(
            f"[{timeframe}] pivot_c_date {c_date_str} is stale "
            f"(>{max_c_age} trading days) — overriding to NO_STRUCTURE"
        )
        return {"structural_state": "NO_STRUCTURE", "bar_window": bar_window}

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
