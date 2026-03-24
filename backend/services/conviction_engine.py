"""
Conviction Engine — Task 3.3
LRR / HRR calculation + Conviction Score for each ticker / timeframe.

Reads from:
  - signal_hurst   (h_trade, h_trend, h_lt)
  - signal_pivots  (pivot_a/b/c/d, structural_state)
  - price_cache    (close, rel_iv, history_json)

Never calls yfinance directly.
"""
import json
import logging
import numpy as np
from models.signal_hurst  import SignalHurst
from models.signal_pivots import SignalPivots
from models.price_cache   import PriceCache

logger = logging.getLogger(__name__)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _h_factor(h: float | None) -> float | None:
    """
    Map Hurst value to LRR placement factor (0–1 between C and B).
    Returns None when H is None (no data — cannot compute LRR/HRR).
    Returns 0.0 when H < 0.50 — LRR defaults to C per spec.
    """
    if h is None:
        return None   # insufficient history
    if h < 0.50:
        return 0.00   # defaults LRR to C — shown grey (Neutral viewpoint)
    if h > 0.65:
        return 0.95
    if h >= 0.55:
        return 0.50
    return 0.05       # 0.50 – 0.55


def _iv_lrr_multiplier(rel_iv: int) -> float:
    if rel_iv > 80: return 0.94
    if rel_iv > 60: return 0.97
    if rel_iv > 30: return 1.00
    return 0.99


def _iv_hrr_multiplier(rel_iv: int) -> float:
    if rel_iv > 80: return 1.15
    if rel_iv > 60: return 1.10
    if rel_iv > 30: return 1.05
    return 1.02


def _sigma(prices: list, window: int = 20) -> float:
    """1σ of recent returns in price units (last `window` bars)."""
    if len(prices) < window + 1:
        return 0.0
    arr = np.array(prices[-(window + 1):], dtype=float)
    log_returns = np.log(arr[1:] / arr[:-1])
    return float(np.std(log_returns) * arr[-1])


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
    Determine OBV trend direction using pivot structure.
    Same structural logic as price pivot engine — applied to OBV series.
    Requires bar_window bars on BOTH sides of a pivot to confirm.
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

    last_high  = pivot_highs[-1][1]
    prior_high = pivot_highs[-2][1]
    last_low   = pivot_lows[-1][1]
    prior_low  = pivot_lows[-2][1]

    if last_high > prior_high and last_low > prior_low:
        return "Bullish"
    if last_high < prior_high and last_low < prior_low:
        return "Bearish"
    return "Neutral"


def _volume_multiplier(vol_signal: str) -> float:
    return {"Confirming": 1.15, "Diverging": 0.80}.get(vol_signal, 1.00)


def _infer_pivot_direction(pivot_row) -> str | None:
    """
    Infer 'uptrend' | 'downtrend' | None from the pivot row.
    NO_STRUCTURE returns None — no pivot data exists.
    BREAK states still infer direction from pivot levels so LRR/HRR
    can be computed and displayed grey. _compute_direction forces Neutral
    for BREAK states regardless of what this returns.
    """
    state = pivot_row.structural_state or "NO_STRUCTURE"
    if state == "NO_STRUCTURE":
        return None
    if "UPTREND" in state:
        return "uptrend"
    if "DOWNTREND" in state:
        return "downtrend"
    # FORMING / EXTENDED / WARNING / BREAK_OF_TRADE / BREAK_OF_TREND
    # — pivot levels exist, infer direction from them
    if pivot_row.pivot_a is not None and pivot_row.pivot_b is not None:
        return "uptrend" if pivot_row.pivot_b > pivot_row.pivot_a else "downtrend"
    return None


# ── LRR / HRR calculation ─────────────────────────────────────────────────────

def compute_lrr_hrr(b: float, c: float, d: float | None,
                    h: float | None, rel_iv: int,
                    prices: list, direction: str) -> tuple:
    """
    Compute (lrr, hrr) for one ticker / timeframe.
    Returns (None, None) when H data is unavailable (h is None).

    H < 0.50 → hf = 0.0 → LRR defaults to C (still computes, shown grey).
    LRR = always the lower price value.
    HRR = always the higher price value.
    """
    hf = _h_factor(h)
    if hf is None:
        return None, None   # no H data — cannot compute

    sigma  = _sigma(prices)
    anchor = d if d is not None else b

    lrr_mult = _iv_lrr_multiplier(rel_iv)
    hrr_mult = _iv_hrr_multiplier(rel_iv)

    if direction == "uptrend":
        base_lrr = c + (b - c) * hf
        lrr = round(base_lrr - sigma * (1.0 - lrr_mult), 4)
        hrr = round(anchor + sigma * hrr_mult, 4)
    else:  # downtrend
        base_hrr = c - (c - b) * hf
        hrr = round(base_hrr + sigma * (hrr_mult - 1.0), 4)
        lrr = round(anchor - sigma * hrr_mult, 4)

    # Clamp — IV can push them past each other (WARNING state check follows)
    if lrr > hrr:
        lrr, hrr = hrr, lrr

    return lrr, hrr


# ── Direction determination ───────────────────────────────────────────────────

def _compute_direction(price: float, lrr: float | None, hrr: float | None,
                       c: float | None, state: str,
                       pivot_direction: str | None) -> str:
    """
    Derive Bullish / Bearish / Neutral for one timeframe.

    C is the only invalidation level. Direction is Bullish/Bearish as long as price
    hasn't closed through C — regardless of structural state. FORMING, EXTENDED, and
    WARNING do not force Neutral; only BREAK_OF_TRADE, BREAK_OF_TREND, and NO_STRUCTURE do.

    Direction is determined by pivots only — H (and therefore LRR/HRR) has no role.
    """
    if state in ("BREAK_OF_TRADE", "BREAK_OF_TREND", "NO_STRUCTURE"):
        return "Neutral"
    if pivot_direction is None or c is None:
        return "Neutral"

    if pivot_direction == "uptrend":
        return "Bullish" if price > c else "Neutral"

    if pivot_direction == "downtrend":
        return "Bearish" if price < c else "Neutral"

    return "Neutral"


# ── WARNING state check ───────────────────────────────────────────────────────

def is_warning(lrr: float | None, hrr: float | None,
               c: float | None, direction: str | None) -> bool:
    """IV-driven only: LRR drifted below C (uptrend) or HRR drifted above C (downtrend)."""
    if c is None or lrr is None or hrr is None:
        return False
    if direction == "uptrend":
        return lrr < c
    if direction == "downtrend":
        return hrr > c
    return False


# ── Conviction Score ──────────────────────────────────────────────────────────

def compute_conviction(h_trade: float | None, h_trend: float | None,
                       vol_signal: str) -> float | None:
    """
    Base Score = weighted average:
      Trade H (DFA 63-day)   → 65%
      Trend H (DFA 252-day)  → 35%

    Rel IV removed from conviction formula — used for LRR/HRR width scaling only.

    Volume Multiplier (OBV-based):
      Confirming → × 1.15
      Neutral    → × 1.00
      Diverging  → × 0.80

    Returns 0–100 float, or None if either H is unavailable.
    CRITICAL: caller must blank this when Viewpoint = Neutral.
    """
    if h_trade is None or h_trend is None:
        return None
    base       = (h_trade * 0.65 + h_trend * 0.35) * 100
    conviction = base * _volume_multiplier(vol_signal)
    return round(min(max(conviction, 0.0), 100.0), 2)


# ── Main entry point ──────────────────────────────────────────────────────────

def compute_output(ticker: str, db) -> dict:
    """
    Compute full signal output for all three timeframes for one ticker.

    Returns:
        {
            "ticker":     str,
            "viewpoint":  str,          # Bullish | Bearish | Neutral
            "conviction": float | None, # blank (None) when Neutral
            "vol_signal": str,
            "alert":      bool,         # ⚡ high-conviction aligned signal
            "trade": { lrr, hrr, structural_state, direction, h_value, warning },
            "trend": { ... },
            "lt":    { ... },
        }
    """
    hurst_row = db.query(SignalHurst).filter(SignalHurst.ticker == ticker).first()
    cache_row = db.query(PriceCache).filter(PriceCache.ticker == ticker).first()

    price  = float(cache_row.close  or 0.0) if cache_row else 0.0
    rel_iv = int(cache_row.rel_iv   or 50)  if cache_row else 50
    prices  = []
    volumes = []
    if cache_row and cache_row.history_json:
        prices = json.loads(cache_row.history_json)
    if cache_row and cache_row.volume_history_json:
        volumes = json.loads(cache_row.volume_history_json)

    # OBV pivot direction — replaces price-momentum proxy
    if prices and volumes and len(prices) == len(volumes):
        obv_dir = _obv_direction(prices, volumes, bar_window=9)
    else:
        obv_dir = "Neutral"

    h_map = {
        "trade": getattr(hurst_row, "h_trade", None) if hurst_row else None,
        "trend": getattr(hurst_row, "h_trend", None) if hurst_row else None,
        "lt":    getattr(hurst_row, "h_lt",    None) if hurst_row else None,
    }

    timeframe_results = {}

    for tf in ("trade", "trend", "lt"):
        pivot_row = db.query(SignalPivots).filter(
            SignalPivots.ticker    == ticker,
            SignalPivots.timeframe == tf,
        ).first()

        h_tf = h_map[tf]

        if pivot_row is None:
            timeframe_results[tf] = {
                "lrr": None, "hrr": None,
                "structural_state": "NO_STRUCTURE",
                "direction": "Neutral",
                "h_value": h_tf,
                "warning": False,
            }
            continue

        state     = pivot_row.structural_state or "NO_STRUCTURE"
        pivot_dir = _infer_pivot_direction(pivot_row)
        b, c, d   = pivot_row.pivot_b, pivot_row.pivot_c, pivot_row.pivot_d

        lrr, hrr = (None, None)
        if pivot_dir is not None and b is not None and c is not None:
            lrr, hrr = compute_lrr_hrr(b, c, d, h_tf, rel_iv, prices, pivot_dir)

        warning = is_warning(lrr, hrr, c, pivot_dir)
        if warning:
            state = "WARNING"

        direction = _compute_direction(price, lrr, hrr, c, state, pivot_dir)

        # Per-cell warning flags — price-based pivot threshold checks
        # LT: no warnings. Trade: C-based + B-based. Trend: C-based only.
        lrr_warn = False
        hrr_warn = False
        if tf != "lt":
            if pivot_dir == "uptrend":
                if lrr is not None and c is not None:
                    lrr_warn = lrr < c
                if tf == "trade" and hrr is not None and b is not None:
                    hrr_warn = hrr < b          # trade only: HRR below prior swing high
            elif pivot_dir == "downtrend":
                if hrr is not None and c is not None:
                    hrr_warn = hrr > c
                if tf == "trade" and lrr is not None and b is not None:
                    lrr_warn = lrr > b          # trade only: LRR above prior swing low

        timeframe_results[tf] = {
            "lrr":              lrr,
            "hrr":              hrr,
            "structural_state": state,
            "direction":        direction,
            "h_value":          h_tf,
            "warning":          warning,
            "lrr_warn":         lrr_warn,
            "hrr_warn":         hrr_warn,
            "pivot_b":          b,
            "pivot_c":          c,
        }

    # ── Viewpoint (trade + trend alignment — three states only) ─────────────
    trade_dir = timeframe_results["trade"]["direction"]
    trend_dir = timeframe_results["trend"]["direction"]

    if trade_dir == "Bullish" and trend_dir == "Bullish":
        viewpoint = "Bullish"
    elif trade_dir == "Bearish" and trend_dir == "Bearish":
        viewpoint = "Bearish"
    else:
        viewpoint = "Neutral"

    # ── OBV vol_signal — maps OBV direction to conviction multiplier tier ────
    if viewpoint in ("Bullish", "Bearish") and obv_dir == viewpoint:
        vol_signal = "Confirming"
    elif obv_dir != "Neutral" and obv_dir != viewpoint:
        vol_signal = "Diverging"
    else:
        vol_signal = "Neutral"

    obv_confirming = vol_signal == "Confirming"

    # ── Conviction — BLANK when Viewpoint = Neutral ──────────────────────────
    conviction = None
    if viewpoint != "Neutral":
        conviction = compute_conviction(h_map["trade"], h_map["trend"], vol_signal)

    # ── Alert flag ⚡ (all three conditions must be true) ───────────────────
    h_trade = h_map["trade"]
    h_trend = h_map["trend"]
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
        "ticker":        ticker,
        "viewpoint":     viewpoint,
        "conviction":    conviction,
        "vol_signal":    vol_signal,
        "obv_direction": obv_dir,
        "obv_confirming": obv_confirming,
        "alert":         alert,
        "trade":         timeframe_results["trade"],
        "trend":      timeframe_results["trend"],
        "lt":         timeframe_results["lt"],
    }
