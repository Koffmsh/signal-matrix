"""
Conviction Engine — v1.7
LRR / HRR calculation + Conviction Score for each ticker / timeframe.

Trade timeframe:  Bollinger Band framework (MA20 ± k×STD20, k driven by Hurst).
Trend timeframe:  Single MA100 level — floor (uptrend) or ceiling (downtrend).
Tail/LT timeframe: Single MA200 level — structural floor or ceiling.

Reads from:
  - signal_hurst   (h_trade, h_trend, h_lt)
  - signal_pivots  (pivot_a/b/c/d, structural_state)
  - price_cache    (close, ma20, std20, ma20_regime, ma100, ma200, history_json,
                    volume_history_json)

Never calls yfinance directly.
"""
import json
import logging
import numpy as np
from models.signal_hurst  import SignalHurst
from models.signal_pivots import SignalPivots
from models.price_cache   import PriceCache

logger = logging.getLogger(__name__)


# ── OBV helpers ───────────────────────────────────────────────────────────────

def _build_obv(closes: list, volumes: list) -> list:
    """Compute OBV series from aligned close prices and volumes."""
    if len(closes) != len(volumes) or len(closes) < 2:
        return []
    obv = [0.0]
    for i in range(1, len(closes)):
        if closes[i] > closes[i - 1]:
            obv.append(obv[-1] + volumes[i])
        elif closes[i] < closes[i - 1]:
            obv.append(obv[-1] - volumes[i])
        else:
            obv.append(obv[-1])
    return obv


def _obv_direction(closes: list, volumes: list, bar_window: int = 9) -> str:
    """
    Determine OBV trend direction using pivot structure (bar_window = 9 each side).
    Returns: 'Bullish' | 'Bearish' | 'Neutral'
    """
    obv = _build_obv(closes, volumes)
    n   = len(obv)
    if n < bar_window * 2 + 2:
        return "Neutral"

    pivot_highs = []
    pivot_lows  = []
    for i in range(bar_window, n - bar_window):
        window = obv[i - bar_window : i + bar_window + 1]
        if obv[i] == max(window):
            pivot_highs.append((i, obv[i]))
        if obv[i] == min(window):
            pivot_lows.append((i, obv[i]))

    if len(pivot_highs) < 2 or len(pivot_lows) < 2:
        return "Neutral"

    last_high, prior_high = pivot_highs[-1][1], pivot_highs[-2][1]
    last_low,  prior_low  = pivot_lows[-1][1],  pivot_lows[-2][1]

    if last_high > prior_high and last_low > prior_low:
        return "Bullish"
    if last_high < prior_high and last_low < prior_low:
        return "Bearish"
    return "Neutral"


def _volume_multiplier(vol_signal: str) -> float:
    return {"Confirming": 1.15, "Diverging": 0.80}.get(vol_signal, 1.00)


# ── Direction inference from pivot row ────────────────────────────────────────

def _infer_pivot_direction(pivot_row) -> str | None:
    """
    Infer 'uptrend' | 'downtrend' | None from the pivot row.
    NO_STRUCTURE → None. BREAK states still infer direction so LRR/HRR
    can be computed and displayed grey.
    """
    state = pivot_row.structural_state or "NO_STRUCTURE"
    if state == "NO_STRUCTURE":
        return None
    if "UPTREND" in state:
        return "uptrend"
    if "DOWNTREND" in state:
        return "downtrend"
    # EXTENDED, WARNING, BREAK_OF_TRADE, BREAK_OF_TREND, BREAK_CONFIRMED
    # — pivot levels still exist; infer direction from A/B relationship
    if pivot_row.pivot_a is not None and pivot_row.pivot_b is not None:
        return "uptrend" if pivot_row.pivot_b > pivot_row.pivot_a else "downtrend"
    return None


# ── Trade timeframe: Bollinger Band LRR/HRR (v1.7) ───────────────────────────

def compute_trade_lrr_hrr(ma20: float | None, std20: float | None,
                           h_trade: float | None, h_trend: float | None,
                           ma20_regime: str | None) -> tuple:
    """
    BB framework for Trade timeframe (v1.7 spec §2.7).

    k_lrr      = 3 - 2 × H_trade          # regime-agnostic
    k_hrr_up   = 3 - 2 × H_trend          # uptrend regime
    k_hrr_down = max(0, H_trend - 0.5)    # downtrend regime (clamped — H<0.5 gives k=0 → HRR=MA20)

    LRR = MA20 - k_lrr × STD20
    HRR = MA20 + k_hrr × STD20   (regime-switched)

    Returns (None, None) if any required input is missing.
    """
    if ma20 is None or std20 is None or h_trade is None or h_trend is None:
        return None, None
    if std20 <= 0:
        return None, None

    k_lrr = 3.0 - 2.0 * h_trade
    lrr   = round(ma20 - k_lrr * std20, 4)

    if (ma20_regime or "uptrend") == "uptrend":
        k_hrr = 3.0 - 2.0 * h_trend
    else:
        k_hrr = max(0.0, h_trend - 0.5)   # H < 0.5 → k = 0 → HRR = MA20

    hrr = round(ma20 + k_hrr * std20, 4)

    return lrr, hrr


# ── Trend timeframe: single MA100 level (v1.7 spec §2.8) ─────────────────────

def compute_trend_level(ma100: float | None, prices: list,
                        trend_dir: str) -> tuple:
    """
    MA100 floor (uptrend) or ceiling (downtrend).
    Slope window: MA100[today] - MA100[10 trading days ago].
    Returns (level, None) when slope confirms direction, else (None, None).
    """
    if ma100 is None or trend_dir == "Neutral" or len(prices) < 110:
        return None, None

    ma100_10d_ago = sum(prices[-110:-10]) / 100.0
    slope = ma100 - ma100_10d_ago

    if slope > 0 and trend_dir == "Bullish":
        return round(ma100, 4), None
    if slope < 0 and trend_dir == "Bearish":
        return round(ma100, 4), None
    return None, None   # slope contradicts direction — hide level


# ── Tail/LT timeframe: single MA200 level (v1.7 spec §2.8) ──────────────────

def compute_tail_level(ma200: float | None, prices: list,
                       lt_dir: str) -> tuple:
    """
    MA200 structural floor (uptrend) or ceiling (downtrend).
    Slope window: MA200[today] - MA200[20 trading days ago].
    Returns (level, None) when slope confirms direction, else (None, None).
    """
    if ma200 is None or lt_dir == "Neutral" or len(prices) < 220:
        return None, None

    ma200_20d_ago = sum(prices[-220:-20]) / 200.0
    slope = ma200 - ma200_20d_ago

    if slope > 0 and lt_dir == "Bullish":
        return round(ma200, 4), None
    if slope < 0 and lt_dir == "Bearish":
        return round(ma200, 4), None
    return None, None


# ── Direction determination ───────────────────────────────────────────────────

def _compute_direction(price: float, c: float | None, state: str,
                       pivot_direction: str | None, b: float | None = None) -> str:
    """
    Derive Bullish / Bearish / Neutral for one timeframe.

    C is the invalidation level. When structurally EXTENDED (D > B + bc_range),
    the break level shifts to B — direction checks price vs B instead of C.

    Direction is determined by pivots only — H (and therefore LRR/HRR) has no role.
    """
    if state in ("BREAK_OF_TRADE", "BREAK_OF_TREND", "NO_STRUCTURE", "BREAK_CONFIRMED"):
        return "Neutral"
    if pivot_direction is None:
        return "Neutral"

    # EXTENDED: B is the new break level
    if state == "EXTENDED" and b is not None:
        if pivot_direction == "uptrend":
            return "Bullish" if price > b else "Neutral"
        if pivot_direction == "downtrend":
            return "Bearish" if price < b else "Neutral"

    if c is None:
        return "Neutral"
    if pivot_direction == "uptrend":
        return "Bullish" if price > c else "Neutral"
    if pivot_direction == "downtrend":
        return "Bearish" if price < c else "Neutral"
    return "Neutral"


# ── WARNING state check ───────────────────────────────────────────────────────

def is_warning(lrr: float | None, hrr: float | None,
               c: float | None, pivot_direction: str | None) -> bool:
    """
    Structural WARNING: LRR drifted below C (uptrend) or HRR above C (downtrend).
    Applied to Trade timeframe only — Trend/LT use single levels.
    """
    if c is None or lrr is None or hrr is None:
        return False
    if pivot_direction == "uptrend":
        return lrr < c
    if pivot_direction == "downtrend":
        return hrr > c
    return False


# ── Per-cell warn flags ───────────────────────────────────────────────────────

def _compute_warn_flags(tf: str, pivot_dir: str | None,
                        lrr: float | None, hrr: float | None,
                        b: float | None, c: float | None) -> tuple:
    """
    Price-based pivot threshold flags (⚠ indicators on LRR/HRR cells).

    Trade:  LRR ⚠ when uptrend: lrr < c  · downtrend: lrr > b
            HRR ⚠ when uptrend: hrr < b  · downtrend: hrr > c
    Trend:  LRR ⚠ when uptrend: lrr < c  · downtrend: lrr > c
            HRR = None → hrr_warn always False
    LT:     Never

    Returns (lrr_warn: bool, hrr_warn: bool).
    """
    if tf == "lt":
        return False, False

    lrr_warn = False
    hrr_warn = False

    if tf == "trade":
        if pivot_dir == "uptrend":
            lrr_warn = lrr is not None and c is not None and lrr < c
            hrr_warn = hrr is not None and b is not None and hrr < b
        elif pivot_dir == "downtrend":
            hrr_warn = hrr is not None and c is not None and hrr > c
            lrr_warn = lrr is not None and b is not None and lrr > b

    elif tf == "trend":
        # lrr holds the Trend Level (single level); hrr is always None
        if pivot_dir == "uptrend":
            lrr_warn = lrr is not None and c is not None and lrr < c
        elif pivot_dir == "downtrend":
            lrr_warn = lrr is not None and c is not None and lrr > c

    return lrr_warn, hrr_warn


# ── Conviction Score (v1.7 spec §2.9) ────────────────────────────────────────

def compute_conviction(h_trade: float | None, h_trend: float | None,
                       vol_signal: str, close: float,
                       trade_lrr: float | None, trade_hrr: float | None,
                       trade_dir: str) -> float | None:
    """
    v1.7 conviction formula:
      Base = H_trade × 0.50 + H_trend × 0.50   (equal-weight)
      Proximity boost — direction-aware, peaks at entry zone:
        Bullish: prox = 1 - (close - LRR) / (HRR - LRR)  (1.0 at LRR)
        Bearish: prox = (close - LRR) / (HRR - LRR)       (1.0 at HRR)
      conviction_raw = Base × (0.70 + 0.30 × prox)
      Final = conviction_raw × OBV_multiplier

    Returns 0–100 float, or None if either H is unavailable.
    CRITICAL: caller must blank this when Viewpoint = Neutral.
    """
    if h_trade is None or h_trend is None:
        return None

    base = (h_trade * 0.50 + h_trend * 0.50) * 100.0

    prox = 0.5   # neutral default when LRR/HRR unavailable
    if (trade_lrr is not None and trade_hrr is not None
            and trade_hrr > trade_lrr):
        band = trade_hrr - trade_lrr
        if trade_dir == "Bullish":
            prox = 1.0 - (close - trade_lrr) / band
        elif trade_dir == "Bearish":
            prox = (close - trade_lrr) / band
        prox = max(0.0, min(1.0, prox))

    conviction_raw = base * (0.70 + 0.30 * prox)
    final = conviction_raw * _volume_multiplier(vol_signal)
    return round(min(max(final, 0.0), 100.0), 2)


# ── Main entry point ──────────────────────────────────────────────────────────

def compute_output(ticker: str, db, prior_ranges: dict = None) -> dict:
    """
    Compute full signal output for all three timeframes for one ticker.

    Returns:
        {
            "ticker":        str,
            "viewpoint":     str,           # Bullish | Bearish | Neutral
            "conviction":    float | None,  # blank (None) when Neutral
            "vol_signal":    str,
            "obv_direction": str,
            "obv_confirming": bool,
            "alert":         bool,
            "trade": { lrr, hrr, structural_state, direction, h_value,
                       warning, lrr_warn, hrr_warn, lrr_extended, hrr_extended,
                       pivot_b, pivot_c },
            "trend": { lrr (=Trend Level), hrr (=None), structural_state,
                       direction, h_value, lrr_warn, hrr_warn, pivot_b, pivot_c },
            "lt":    { lrr (=Tail Level),  hrr (=None), structural_state,
                       direction, h_value, pivot_b, pivot_c },
        }
    """
    hurst_row = db.query(SignalHurst).filter(SignalHurst.ticker == ticker).first()
    cache_row = db.query(PriceCache).filter(PriceCache.ticker == ticker).first()

    price  = float(cache_row.close  or 0.0) if cache_row else 0.0
    prices = []
    volumes = []
    if cache_row and cache_row.history_json:
        prices = json.loads(cache_row.history_json)
    if cache_row and cache_row.volume_history_json:
        volumes = json.loads(cache_row.volume_history_json)

    # MA / vol inputs from price_cache (computed at fetch time — Phase A)
    ma20        = float(cache_row.ma20)        if (cache_row and cache_row.ma20  is not None) else None
    ma100       = float(cache_row.ma100)       if (cache_row and cache_row.ma100 is not None) else None
    ma200       = float(cache_row.ma200)       if (cache_row and cache_row.ma200 is not None) else None
    std20       = float(cache_row.std20)       if (cache_row and cache_row.std20 is not None) else None
    ma20_regime = cache_row.ma20_regime        if cache_row else None

    # OBV pivot direction — compared against Trade Dir for vol_signal
    if prices and volumes and len(prices) == len(volumes):
        obv_dir = _obv_direction(prices, volumes, bar_window=9)
    else:
        obv_dir = "Neutral"

    h_map = {
        "trade": getattr(hurst_row, "h_trade", None) if hurst_row else None,
        "trend": getattr(hurst_row, "h_trend", None) if hurst_row else None,
        "lt":    getattr(hurst_row, "h_lt",    None) if hurst_row else None,
    }

    h_trade = h_map["trade"]
    h_trend = h_map["trend"]

    timeframe_results = {}

    for tf in ("trade", "trend", "lt"):
        pivot_row = db.query(SignalPivots).filter(
            SignalPivots.ticker    == ticker,
            SignalPivots.timeframe == tf,
        ).first()

        if pivot_row is None:
            timeframe_results[tf] = {
                "lrr": None, "hrr": None,
                "structural_state": "NO_STRUCTURE",
                "direction": "Neutral",
                "h_value":   h_map[tf],
                "warning":   False,
                "lrr_warn":  False, "hrr_warn": False,
                "lrr_extended": False, "hrr_extended": False,
                "pivot_b": None, "pivot_c": None,
            }
            continue

        state     = pivot_row.structural_state or "NO_STRUCTURE"
        pivot_dir = _infer_pivot_direction(pivot_row)
        b = pivot_row.pivot_b
        c = pivot_row.pivot_c
        d = pivot_row.pivot_d

        # Direction — C-based (B when structurally EXTENDED)
        direction = _compute_direction(price, c, state, pivot_dir, b=b)

        # ── LRR / HRR by timeframe ───────────────────────────────────────────
        if tf == "trade":
            lrr, hrr = compute_trade_lrr_hrr(ma20, std20, h_trade, h_trend, ma20_regime)

            # WARNING: LRR drifted below C (uptrend) or HRR above C (downtrend)
            warning = is_warning(lrr, hrr, c, pivot_dir)
            if warning:
                state = "WARNING"

            # Daily overshoot flag (B5) — tactical, does NOT change structural_state
            hrr_extended = False
            lrr_extended = False
            if state not in ("BREAK_OF_TRADE", "BREAK_OF_TREND",
                             "BREAK_CONFIRMED", "NO_STRUCTURE"):
                pr        = (prior_ranges or {}).get(tf, {})
                prior_hrr = pr.get("prior_hrr")
                prior_lrr = pr.get("prior_lrr")
                if direction == "Bullish" and prior_hrr is not None and price > prior_hrr:
                    hrr_extended = True
                elif direction == "Bearish" and prior_lrr is not None and price < prior_lrr:
                    lrr_extended = True

        elif tf == "trend":
            lrr, hrr = compute_trend_level(ma100, prices, direction)
            warning      = False
            hrr_extended = False
            lrr_extended = False

        else:  # lt / tail
            lrr, hrr = compute_tail_level(ma200, prices, direction)
            warning      = False
            hrr_extended = False
            lrr_extended = False

        lrr_warn, hrr_warn = _compute_warn_flags(tf, pivot_dir, lrr, hrr, b, c)

        timeframe_results[tf] = {
            "lrr":              lrr,
            "hrr":              hrr,
            "structural_state": state,
            "direction":        direction,
            "h_value":          h_map[tf],
            "warning":          warning,
            "lrr_warn":         lrr_warn,
            "hrr_warn":         hrr_warn,
            "lrr_extended":     lrr_extended,
            "hrr_extended":     hrr_extended,
            "pivot_b":          b,
            "pivot_c":          c,
        }

    # ── Viewpoint (trade + trend alignment) ─────────────────────────────────
    trade_dir = timeframe_results["trade"]["direction"]
    trend_dir = timeframe_results["trend"]["direction"]

    if trade_dir == "Bullish" and trend_dir == "Bullish":
        viewpoint = "Bullish"
    elif trade_dir == "Bearish" and trend_dir == "Bearish":
        viewpoint = "Bearish"
    else:
        viewpoint = "Neutral"

    # ── OBV vol_signal — compared against Trade Dir ──────────────────────────
    if trade_dir in ("Bullish", "Bearish") and obv_dir == trade_dir:
        vol_signal = "Confirming"
    elif obv_dir != "Neutral" and obv_dir != trade_dir:
        vol_signal = "Diverging"
    else:
        vol_signal = "Neutral"

    obv_confirming = vol_signal == "Confirming"

    # ── Conviction — BLANK when Viewpoint = Neutral ──────────────────────────
    conviction = None
    if viewpoint != "Neutral":
        trade_lrr = timeframe_results["trade"]["lrr"]
        trade_hrr = timeframe_results["trade"]["hrr"]
        conviction = compute_conviction(
            h_trade, h_trend, vol_signal,
            price, trade_lrr, trade_hrr, trade_dir,
        )

    # ── Alert flag ⚡ ────────────────────────────────────────────────────────
    alert = bool(
        h_trade is not None and h_trade > 0.55 and
        h_trend is not None and h_trend > 0.55 and
        viewpoint != "Neutral" and
        conviction is not None and conviction >= 70.0
    )

    logger.info(
        f"{ticker}: viewpoint={viewpoint} conviction={conviction} "
        f"trade_dir={trade_dir} trend_dir={trend_dir} alert={alert}"
    )

    return {
        "ticker":         ticker,
        "viewpoint":      viewpoint,
        "conviction":     conviction,
        "vol_signal":     vol_signal,
        "obv_direction":  obv_dir,
        "obv_confirming": obv_confirming,
        "alert":          alert,
        "trade":          timeframe_results["trade"],
        "trend":          timeframe_results["trend"],
        "lt":             timeframe_results["lt"],
    }
