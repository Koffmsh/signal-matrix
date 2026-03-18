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


def _volume_signal(prices: list) -> str:
    """
    Price-momentum proxy for volume signal until Schwab Phase 5.
    Returns 'Confirming' | 'Diverging' | 'Neutral'.
    """
    if len(prices) < 21:
        return "Neutral"
    mom5  = prices[-1] / prices[-6]  - 1
    mom20 = prices[-1] / prices[-21] - 1
    if mom5 > 0 and mom20 > 0:
        return "Confirming"
    if mom5 < 0 and mom20 < 0:
        return "Confirming"
    if abs(mom5) < 0.001:
        return "Neutral"
    return "Diverging"


def _volume_multiplier(vol_signal: str) -> float:
    return {"Confirming": 1.15, "Diverging": 0.80}.get(vol_signal, 1.00)


def _infer_pivot_direction(pivot_row) -> str | None:
    """
    Infer 'uptrend' | 'downtrend' | None from the pivot row.
    BREAK and NO_STRUCTURE always return None (direction = Neutral).
    FORMING and EXTENDED fall through to pivot level comparison.
    """
    state = pivot_row.structural_state or "NO_STRUCTURE"
    if state in ("BREAK_OF_TRADE", "BREAK_OF_TREND", "NO_STRUCTURE"):
        return None
    if "UPTREND" in state:
        return "uptrend"
    if "DOWNTREND" in state:
        return "downtrend"
    # FORMING / EXTENDED / WARNING — infer from pivot levels
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

    Uptrend:   effective_floor   = max(lrr, c) → Bullish if price > floor
    Downtrend: effective_ceiling = min(hrr, c) → Bearish if price < ceiling
    Break / no structure → Neutral always.
    """
    if state in ("BREAK_OF_TRADE", "BREAK_OF_TREND", "NO_STRUCTURE"):
        return "Neutral"
    if pivot_direction is None or c is None:
        return "Neutral"

    if pivot_direction == "uptrend":
        if lrr is None:
            return "Neutral"   # no H data → can't confirm Bullish
        effective_floor = max(lrr, c)
        return "Bullish" if price > effective_floor else "Neutral"

    if pivot_direction == "downtrend":
        if hrr is None:
            return "Neutral"
        effective_ceiling = min(hrr, c)
        return "Bearish" if price < effective_ceiling else "Neutral"

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
                       rel_iv: int, vol_signal: str) -> float | None:
    """
    Base Score = weighted average:
      Trade H (DFA 63-day)   → 55%
      Trend H (DFA 252-day)  → 25%
      Rel IV% inverted       → 20%   IV Score = (100 - RelIV%) / 100

    Volume Multiplier:
      Confirming → × 1.15
      Neutral    → × 1.00
      Diverging  → × 0.80

    Returns 0–100 float, or None if either H is unavailable.
    CRITICAL: caller must blank this when Viewpoint = Neutral.
    """
    if h_trade is None or h_trend is None:
        return None
    iv_score   = (100 - rel_iv) / 100
    base       = (h_trade * 0.55 + h_trend * 0.25 + iv_score * 0.20) * 100
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
    prices = []
    if cache_row and cache_row.history_json:
        prices = json.loads(cache_row.history_json)

    vol_signal = _volume_signal(prices)

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
        lrr_warn = False
        hrr_warn = False
        if pivot_dir == "uptrend":
            if lrr is not None and c is not None:
                lrr_warn = lrr < c
            if hrr is not None and b is not None:
                hrr_warn = hrr < b
        elif pivot_dir == "downtrend":
            if hrr is not None and c is not None:
                hrr_warn = hrr > c
            if lrr is not None and b is not None:
                lrr_warn = lrr > b

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

    # ── Conviction — BLANK when Viewpoint = Neutral ──────────────────────────
    conviction = None
    if viewpoint != "Neutral":
        conviction = compute_conviction(h_map["trade"], h_map["trend"], rel_iv, vol_signal)

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
        "ticker":     ticker,
        "viewpoint":  viewpoint,
        "conviction": conviction,
        "vol_signal": vol_signal,
        "alert":      alert,
        "trade":      timeframe_results["trade"],
        "trend":      timeframe_results["trend"],
        "lt":         timeframe_results["lt"],
    }
