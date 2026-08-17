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
    "trend": 120,
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
    "trend": 10,
    "lt":    50,
}

# Max bars to look back when selecting A (the origin pivot of the structure).
# Prevents the engine from anchoring to a pivot that is too old to be relevant.
# None = no limit (LT structures are inherently long-dated).
_MAX_A_LOOKBACK = {
    "trade":  90,
    "trend": 200,
    "lt":    None,
}


# —— Price fetch from cache ————————————————————————————————————————————

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


# —— Pivot detection ———————————————————————————————————————————————————

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


# —— ABC structure builder —————————————————————————————————————————————

def _find_uptrend_abc(pivot_highs: list, pivot_lows: list):
    """
    Uptrend: A = lowest confirmed pivot low in the lookback window.
             B = first confirmed pivot high after A.
             C = first confirmed pivot low after B with C > A.

    Iterates A candidates from most extreme (lowest) to least extreme.
    When the most extreme A has no confirmed B or C yet (e.g. a very recent
    low with no follow-through), falls back to the next candidate rather than
    returning None.  This allows a prior valid structure to be found and the
    trend to heal as soon as D re-establishes above the old C.
    """
    if not pivot_lows or not pivot_highs:
        return None

    # Try A candidates from most extreme (lowest price) to least extreme
    for a_idx, a_price in sorted(pivot_lows, key=lambda x: x[1]):
        b_candidates = [(i, p) for i, p in pivot_highs if i > a_idx]
        if not b_candidates:
            continue
        b_idx, b_price = b_candidates[0]

        c_candidates = [(i, p) for i, p in pivot_lows if i > b_idx and p > a_price]
        if not c_candidates:
            continue
        c_idx, c_price = c_candidates[0]

        return dict(
            direction="uptrend",
            a=a_price, b=b_price, c=c_price,
            a_idx=a_idx, b_idx=b_idx, c_idx=c_idx,
        )

    return None


def _find_downtrend_abc(pivot_highs: list, pivot_lows: list):
    """
    Downtrend: A = highest confirmed pivot high in the lookback window.
               B = first confirmed pivot low after A.
               C = first confirmed pivot high after B with C < A.

    Iterates A candidates from most extreme (highest) to least extreme.
    When the most extreme A has no confirmed B or C yet (e.g. a very recent
    high with no follow-through), falls back to the next candidate rather than
    returning None.
    """
    if not pivot_highs or not pivot_lows:
        return None

    # Try A candidates from most extreme (highest price) to least extreme
    for a_idx, a_price in sorted(pivot_highs, key=lambda x: x[1], reverse=True):
        b_candidates = [(i, p) for i, p in pivot_lows if i > a_idx]
        if not b_candidates:
            continue
        b_idx, b_price = b_candidates[0]

        c_candidates = [(i, p) for i, p in pivot_highs if i > b_idx and p < a_price]
        if not c_candidates:
            continue
        c_idx, c_price = c_candidates[0]

        return dict(
            direction="downtrend",
            a=a_price, b=b_price, c=c_price,
            a_idx=a_idx, b_idx=b_idx, c_idx=c_idx,
        )

    return None


def _compute_d_extended(abc: dict, prices: list) -> bool:
    """Quick check: has D extended beyond B + 0.5*|B-A|?"""
    direction = abc["direction"]
    b_idx = abc["b_idx"]
    b_price = abc["b"]
    a_price = abc["a"]

    if direction == "uptrend":
        d_prices = [p for p in prices[b_idx + 1:] if p > b_price]
        if d_prices:
            return max(d_prices) > b_price + 0.5 * abs(b_price - a_price)
    else:
        d_prices = [p for p in prices[b_idx + 1:] if p < b_price]
        if d_prices:
            return min(d_prices) < b_price - 0.5 * abs(b_price - a_price)
    return False


def _price_on_correct_side(abc: dict, current_price: float, prices: list) -> bool:
    """
    Returns True if current_price is on the valid side of the break level:
      uptrend:   price > break_level  (structure intact)
      downtrend: price < break_level  (structure intact)

    Break level = C normally; B when d_extended (D > B + 0.5*|B-A|).
    """
    d_extended = _compute_d_extended(abc, prices)
    break_level = abc["b"] if d_extended else abc["c"]

    if abc["direction"] == "uptrend":
        return current_price > break_level
    else:
        return current_price < break_level


def _d_has_established(abc: dict, prices: list) -> bool:
    """
    Returns True if D has established — price has at some point closed through B.
      uptrend:   any close above B
      downtrend: any close below B

    A newer ABC structure that has never established D should not override
    an older intact structure in the opposite direction. D is the confirmation
    event: it simultaneously breaks the prior structure's C and proves the new
    trend via two higher highs (B and D) and a higher low (C).
    """
    b_idx   = abc["b_idx"]
    b_price = abc["b"]
    if abc["direction"] == "uptrend":
        return any(p > b_price for p in prices[b_idx + 1:])
    else:
        return any(p < b_price for p in prices[b_idx + 1:])


def find_abc_structure(pivot_highs: list, pivot_lows: list, prices: list):
    """
    Find the most recent valid ABC structure (uptrend or downtrend).

    Selection priority (highest to lowest):
    1. Prefer the structure where current price is still on the correct side
       of the break level (C normally, B when d_extended).
    2. When both or neither are intact: prefer the one with the more recent C —
       UNLESS the newer structure has never established D (price never closed
       through B). Without D, a geometric ABC is not a confirmed trend reversal
       and the older unbroken structure governs.

    Returns dict or None.
    """
    uptrend   = _find_uptrend_abc(pivot_highs, pivot_lows)
    downtrend = _find_downtrend_abc(pivot_highs, pivot_lows)

    if not uptrend and not downtrend:
        return None

    if uptrend and not downtrend:
        return uptrend

    if downtrend and not uptrend:
        return downtrend

    # Both found — check which structures still have price on the correct side
    current_price = prices[-1]
    up_intact     = _price_on_correct_side(uptrend,   current_price, prices)
    down_intact   = _price_on_correct_side(downtrend, current_price, prices)

    if up_intact and not down_intact:
        return uptrend
    if down_intact and not up_intact:
        return downtrend

    # Both intact or both broken — use most recent C as tiebreak
    winner = uptrend if uptrend["c_idx"] >= downtrend["c_idx"] else downtrend
    other  = downtrend if winner is uptrend else uptrend

    # A newer ABC without D established cannot override the older structure.
    # D is the confirmation event — without it the newer ABC is geometric only.
    if not _d_has_established(winner, prices):
        return other

    return winner


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


def update_b_dynamically(abc: dict, pivot_highs: list, pivot_lows: list) -> dict:
    """
    After C is finalized, advance B to the most recent confirmed pivot between
    A and C:

    Uptrend:   most recent confirmed pivot HIGH with a_idx < idx < c_idx
    Downtrend: most recent confirmed pivot LOW  with a_idx < idx < c_idx

    B can advance to a higher OR lower price than the initial B — it always
    reflects the most recent structural reference point before the current C.
    This keeps the BC range and d_extended threshold current rather than
    anchored to the first pivot found after A.

    Returns updated abc dict (or original if no candidate is found).
    """
    direction = abc["direction"]
    a_idx     = abc["a_idx"]
    c_idx     = abc["c_idx"]

    if direction == "uptrend":
        candidates = [(i, p) for i, p in pivot_highs if a_idx < i < c_idx]
    else:
        candidates = [(i, p) for i, p in pivot_lows if a_idx < i < c_idx]

    if not candidates:
        return abc

    # Pivots are ordered oldest→newest; last entry is most recent
    new_b_idx, new_b_price = candidates[-1]
    return {**abc, "b": new_b_price, "b_idx": new_b_idx}


# —— D + structural state ——————————————————————————————————————————————

def _count_wrong_side_streak(prices: list, break_level: float, direction: str) -> int:
    """
    Count consecutive closes on the wrong side of break_level, ending at the
    last bar. Returns the streak length (0 if current bar is on the correct side).
    """
    if not prices:
        return 0

    if direction == "uptrend":
        on_wrong = lambda p: p < break_level
    else:
        on_wrong = lambda p: p > break_level

    streak = 0
    for i in range(len(prices) - 1, -1, -1):
        if on_wrong(prices[i]):
            streak += 1
        else:
            break
    return streak


def compute_d_and_state(abc: dict, prices: list, timeframe: str):
    """
    Given an ABC structure and the full price series, compute:
      - D price (running high/low established when price closes through B)
      - D index in the prices array
      - Structural state string
      - d_extended boolean (True when D has pushed > one BC range beyond B)

    Break logic (heal-at-break-level):
      - Price on correct side of break level → VALID immediately (no persistent breaks)
      - Price on wrong side: count consecutive wrong-side closes ending at current bar
        - 1 close → BREAK_OF_TRADE (trade tf) or BREAK_OF_TREND (trend/lt tf)
        - 2+ closes → BREAK_CONFIRMED
      - Break level = C normally; B when d_extended
    """
    direction     = abc["direction"]
    c_idx         = abc["c_idx"]
    a_price       = abc["a"]
    b_price       = abc["b"]
    c_price       = abc["c"]
    current_price = prices[-1]
    break_state   = "BREAK_OF_TRADE" if timeframe == "trade" else "BREAK_OF_TREND"

    # Scan for D establishment
    b_idx        = abc["b_idx"]
    first_breach = None
    if direction == "uptrend":
        for i in range(b_idx + 1, len(prices)):
            if prices[i] > b_price:
                first_breach = i
                break
    else:
        for i in range(b_idx + 1, len(prices)):
            if prices[i] < b_price:
                first_breach = i
                break

    d_price    = None
    d_idx      = None
    d_extended = False
    if first_breach is not None:
        d_slice = prices[first_breach:]
        if direction == "uptrend":
            d_price     = max(d_slice)
            d_local_idx = max(i for i, p in enumerate(d_slice) if p == d_price)
            d_extended  = d_price > b_price + 0.5 * abs(b_price - a_price)
        else:
            d_price     = min(d_slice)
            d_local_idx = max(i for i, p in enumerate(d_slice) if p == d_price)
            d_extended  = d_price < b_price - 0.5 * abs(b_price - a_price)
        d_idx = first_breach + d_local_idx

    # Determine break level and valid state label
    break_level = b_price if d_extended else c_price
    valid_state = "UPTREND_VALID" if direction == "uptrend" else "DOWNTREND_VALID"

    # Check current price vs break level
    if direction == "uptrend":
        on_wrong_side = current_price < break_level
    else:
        on_wrong_side = current_price > break_level

    if not on_wrong_side:
        # Price is on the correct side (or equal) — structure is valid
        if first_breach is None:
            return None, None, valid_state, False
        return round(d_price, 4), d_idx, valid_state, d_extended

    # Price on wrong side — count consecutive streak ending at current bar
    streak = _count_wrong_side_streak(prices, break_level, direction)

    if streak >= 2:
        state = "BREAK_CONFIRMED"
    else:
        state = break_state

    if d_extended:
        return round(d_price, 4), d_idx, state, True
    if first_breach is not None:
        return round(d_price, 4), d_idx, state, False
    return None, None, state, False


# —— Per-timeframe computation —————————————————————————————————————————

def compute_pivots_for_timeframe(prices: list, dates: list, timeframe: str, bar_window: int, max_a_lookback_override: int = None) -> dict:
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

    # Limit pivot candidates for A selection to the lookback window.
    max_a_lookback = max_a_lookback_override if max_a_lookback_override is not None else _MAX_A_LOOKBACK.get(timeframe)
    if max_a_lookback is not None and len(prices) > max_a_lookback:
        cutoff_idx = len(prices) - max_a_lookback
        pivot_highs_abc = [(i, p) for i, p in pivot_highs if i >= cutoff_idx]
        pivot_lows_abc  = [(i, p) for i, p in pivot_lows  if i >= cutoff_idx]
    else:
        pivot_highs_abc = pivot_highs
        pivot_lows_abc  = pivot_lows

    abc = find_abc_structure(pivot_highs_abc, pivot_lows_abc, prices)

    if abc is None:
        return {"structural_state": "NO_STRUCTURE", "bar_window": bar_window}

    # Walk C to the most recent confirmed structural level, then advance B to
    # the most recent confirmed pivot between A and the updated C.
    abc = update_c_dynamically(abc, pivot_highs, pivot_lows)
    abc = update_b_dynamically(abc, pivot_highs, pivot_lows)

    d_price, d_idx, state, d_extended = compute_d_and_state(abc, prices, timeframe)

    # On BREAK_CONFIRMED, try the opposite direction for a valid structure
    if state == "BREAK_CONFIRMED":
        if abc["direction"] == "uptrend":
            opp_abc = _find_downtrend_abc(pivot_highs_abc, pivot_lows_abc)
        else:
            opp_abc = _find_uptrend_abc(pivot_highs_abc, pivot_lows_abc)

        if opp_abc is not None:
            opp_abc = update_c_dynamically(opp_abc, pivot_highs, pivot_lows)
            opp_abc = update_b_dynamically(opp_abc, pivot_highs, pivot_lows)
            opp_d, opp_d_idx, opp_state, opp_d_ext = compute_d_and_state(
                opp_abc, prices, timeframe
            )
            if opp_state in ("UPTREND_VALID", "DOWNTREND_VALID"):
                abc = opp_abc
                d_price, d_idx, state, d_extended = opp_d, opp_d_idx, opp_state, opp_d_ext

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
        "d_extended":       d_extended,
        "direction":        abc["direction"],
    }



# NOTE: Emerging direction (frontend display only)
# When trade_direction == 'Neutral' (NO_STRUCTURE or BREAK_CONFIRMED), the
# frontend shows '~ Bullish / ~ Bearish' via _compute_emerging_direction()
# in routers/signals.py. Uses MA50 momentum + 22-day high/low breakout
# (hit within last 3 bars). Entirely independent of this pivot engine.

# —— Main entry point ——————————————————————————————————————————————————

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
