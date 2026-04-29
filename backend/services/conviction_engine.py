"""
Conviction Engine — v1.9
LRR / HRR calculation + Conviction Score for each ticker / timeframe.

Trade timeframe:  Bollinger Band framework (MA20 ± k×STD20).
  k_wide  = 2.0  (fixed — standard 2σ BB, target/exit side)
  k_tight = 0.0  (fixed — entry side collapses to MA20 exactly)
  H is NOT used in band width. H drives conviction score and regime
  classification only: H < 0.45 → mean-reverting (use oscillators);
  H > 0.55 → trending (use trend-following indicators).

Trend timeframe:  Single MA100 level — floor (uptrend) or ceiling (downtrend).
Tail/LT timeframe: Single MA200 level — structural floor or ceiling.

Reads from:
  - signal_hurst   (h_trade, h_trend, h_lt, h_trend_up, h_trend_down)
  - signal_pivots  (pivot_a/b/c/d, structural_state)
  - price_cache    (close, ma20, std20, ma20_regime, ma100, ma200, atr,
                    history_json, volume_history_json)

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


def _obv_direction(closes: list, volumes: list, bar_window: int = 5) -> str:
    """
    Determine OBV trend direction using ABCD pivot logic (bar_window=5 each side).
    Mirrors the price pivot engine: A (extreme) → B → C (confirmed) → D running > B = Bullish.
    Searches the most recent 60 bars — matches the trade timeframe A lookback.
    Returns: 'Bullish' | 'Bearish' | 'Neutral'
    """
    obv = _build_obv(closes, volumes)
    n   = len(obv)
    if n < bar_window * 2 + 2:
        return "Neutral"

    search_start = max(bar_window, n - 60)
    pivot_highs = []
    pivot_lows  = []
    for i in range(search_start, n - bar_window):
        window = obv[i - bar_window : i + bar_window + 1]
        if obv[i] == max(window):
            pivot_highs.append((i, obv[i]))
        if obv[i] == min(window):
            pivot_lows.append((i, obv[i]))

    if not pivot_highs or not pivot_lows:
        return "Neutral"

    current_obv = obv[-1]

    # Uptrend: A (most extreme low) → B (first high after A) → C (low after B, C > A) → D > B
    a_idx, a_val = min(pivot_lows, key=lambda x: x[1])
    b_up = next(((i, v) for i, v in pivot_highs if i > a_idx), None)
    if b_up:
        b_idx, b_val = b_up
        c_up = next(((i, v) for i, v in pivot_lows if i > b_idx and v > a_val), None)
        if c_up and current_obv > b_val:
            return "Bullish"

    # Downtrend: A (most extreme high) → B (first low after A) → C (high after B, C < A) → D < B
    a_idx, a_val = max(pivot_highs, key=lambda x: x[1])
    b_dn = next(((i, v) for i, v in pivot_lows if i > a_idx), None)
    if b_dn:
        b_idx, b_val = b_dn
        c_dn = next(((i, v) for i, v in pivot_highs if i > b_idx and v < a_val), None)
        if c_dn and current_obv < b_val:
            return "Bearish"

    return "Neutral"


def _build_obv_ma20(closes: list, volumes: list) -> list:
    """Build OBV series then compute its 20-period simple moving average."""
    obv = _build_obv(closes, volumes)
    if len(obv) < 20:
        return []
    return [sum(obv[i - 19 : i + 1]) / 20.0 for i in range(19, len(obv))]


def _obv_slope_signals(obv_ma20: list, viewpoint: str,
                       obv_dir: str) -> tuple:
    """
    Compute 3-bar OBV MA20 slope signals and derived multipliers.

    obv_slope:       'rising' | 'falling' | 'flat'
        Sign of the 3-bar rate of change on the OBV MA20.
        slope_now = obv_ma20[-1] - obv_ma20[-4]  (current vs 3 bars ago)

    obv_slope_trend: 'increasing' | 'decreasing' | 'flat'
        Acceleration — whether the 3-bar slope itself is growing or shrinking.
        slope_prev = obv_ma20[-2] - obv_ma20[-5]  (prior 3-bar window)

    Alignment (Layer 1):
        Aligned   — OBV pivot direction AND OBV MA20 slope both confirm viewpoint
                    Bullish: obv_dir=Bullish AND obv_slope=rising
                    Bearish: obv_dir=Bearish AND obv_slope=falling
        Misaligned — both oppose viewpoint
        Neutral   — everything else

    alignment_mult: 1.20 (aligned) | 0.85 (misaligned) | 1.00 (neutral)

    Slope boost (Layer 2 — only when aligned):
        Bullish + slope_trend=increasing → 1.17   (acceleration — early in the move)
        Bearish + slope_trend=decreasing → 1.17
        Otherwise                        → 1.00

    Returns (obv_slope, obv_slope_trend, alignment_mult, slope_boost).
    Requires len(obv_ma20) >= 6.
    """
    if len(obv_ma20) < 6:
        return "flat", "flat", 1.00, 1.00

    slope_now  = obv_ma20[-1] - obv_ma20[-4]   # 3-bar rate of change
    slope_prev = obv_ma20[-2] - obv_ma20[-5]   # prior 3-bar window

    obv_slope = ("rising"  if slope_now > 0 else
                 "falling" if slope_now < 0 else "flat")

    obv_slope_trend = ("increasing" if slope_now > slope_prev else
                       "decreasing" if slope_now < slope_prev else "flat")

    # Layer 1 — OBV pivot + MA20 slope both confirm viewpoint direction
    aligned = (
        (viewpoint == "Bullish" and obv_dir == "Bullish"
         and obv_slope == "rising") or
        (viewpoint == "Bearish" and obv_dir == "Bearish"
         and obv_slope == "falling")
    )
    misaligned = (
        (viewpoint == "Bullish" and obv_dir == "Bearish"
         and obv_slope == "falling") or
        (viewpoint == "Bearish" and obv_dir == "Bullish"
         and obv_slope == "rising")
    )

    alignment_mult = 1.20 if aligned else 0.85 if misaligned else 1.00

    # Layer 2 — slope acceleration boost (only fires when Layer 1 aligned)
    slope_boost = 1.00
    if aligned:
        if viewpoint == "Bullish" and obv_slope_trend == "increasing":
            slope_boost = 1.20
        elif viewpoint == "Bearish" and obv_slope_trend == "decreasing":
            slope_boost = 1.20

    return obv_slope, obv_slope_trend, alignment_mult, slope_boost


ASYMMETRIC_H_ASSET_CLASSES = {"Commodities", "Foreign Exchange"}
ASYMMETRIC_H_EXCLUDED      = {"/ZN"}   # Fixed Income behavior despite Commodities classification


def get_effective_h_trend(asset_class: str, ticker: str, viewpoint: str,
                          h_trend: float | None,
                          h_trend_up: float | None,
                          h_trend_down: float | None) -> float | None:
    """
    Returns the H value to use as the conviction base score.
    Asymmetric H applied for Commodities and FX only; falls back to symmetric h_trend.
    """
    if asset_class not in ASYMMETRIC_H_ASSET_CLASSES or ticker in ASYMMETRIC_H_EXCLUDED:
        return h_trend
    if viewpoint == "Bullish" and h_trend_up is not None:
        return h_trend_up
    if viewpoint == "Bearish" and h_trend_down is not None:
        return h_trend_down
    return h_trend  # fallback — insufficient directional history


VIX_REGIME_ASSET_CLASSES = {"Domestic Equities"}


def get_vix_mult(vix_close: float | None, asset_class: str) -> tuple:
    """
    Layer 4 — VIX regime multiplier, asset-class gated.
    Only applies to Domestic Equities; all other asset classes return (1.00, 'N/A').

    Thresholds (locked):
      Investable  VIX < 19   × 1.10
      Edgy        19–23      × 1.00
      Choppy      24–29      × 0.90
      Danger      ≥ 30       × 0.80
    """
    if asset_class not in VIX_REGIME_ASSET_CLASSES:
        return 1.00, "N/A"
    if vix_close is None:
        return 1.00, "Unknown"
    if vix_close < 19:
        return 1.10, "Investable"
    elif vix_close < 24:
        return 1.00, "Edgy"
    elif vix_close < 30:
        return 0.90, "Choppy"
    else:
        return 0.80, "Danger"


def get_vix_regime_multiplier(db) -> tuple:
    """Legacy helper — returns (multiplier, zone_label) for non-gated VIX display."""
    vix_row = db.query(PriceCache).filter(PriceCache.ticker == "VIX").first()
    vix_close = float(vix_row.close) if (vix_row and vix_row.close is not None) else None
    if vix_close is None:
        return 1.00, "Unknown"
    if vix_close < 19:
        return 1.10, "Investable"
    elif vix_close < 24:
        return 1.00, "Edgy"
    elif vix_close < 30:
        return 0.90, "Choppy"
    else:
        return 0.80, "Danger"


# ── Quad Alignment ────────────────────────────────────────────────────────────

ALWAYS_NEUTRAL_SECTORS = {"Index"}   # VIX, VVIX only — always ×1.00

QUAD_ALIGNMENT = {

    1: {  # Goldilocks — growth ↑, inflation ↓
        "best": {
            "asset_class": [
                "Domestic Equities",
                "International Equities",
                "Commodities",
                "Foreign Exchange",
            ],
            "sector": [
                "Technology", "Consumer Discretionary",
                "Communication Services", "Industrials",
                "Materials", "Real Estate", "Financials",
                "Equities", "Small Caps",
                "High Beta", "Momentum", "Secular Growth",
                "Mid Caps", "Leverage", "Cyclical Growth",
                "High Yield", "Convertibles", "EM Credit",
                "Leveraged Loans", "BDCs",
            ],
        },
        "worst": {
            "asset_class": [
                "Domestic Fixed Income",
            ],
            "sector": [
                "USD",
                "Utilities", "Consumer Staples", "Health Care",
                "Low Beta", "Defensives", "Value", "Dividend Yield",
                "Treasury", "Long Bond", "MBS", "TIPS",
            ],
        },
    },

    2: {  # Reflation — growth ↑, inflation ↑
        "best": {
            "asset_class": [
                "Commodities",
                "Domestic Equities",
                "International Equities",
                "Foreign Exchange",
            ],
            "sector": [
                "Technology", "Industrials", "Financials",
                "Energy", "Consumer Discretionary",
                "Equities", "Small Caps",
                "Secular Growth", "High Beta", "Cyclical Growth", "Momentum",
                "Convertibles", "BDCs", "Preferreds",
                "Leveraged Loans", "High Yield",
            ],
        },
        "worst": {
            "asset_class": [
                "Domestic Fixed Income",
            ],
            "sector": [
                "USD",
                "Utilities", "Communication Services",
                "Consumer Staples", "Real Estate", "Health Care",
                "Low Beta", "Dividend Yield", "Value", "Defensives",
                "Long Bond", "Treasury", "Munis", "MBS", "IG Credit",
            ],
        },
    },

    3: {  # Stagflation — growth ↓, inflation ↑
        "best": {
            "asset_class": [
                "Commodities",
                "Domestic Fixed Income",
            ],
            "sector": [
                "Gold",
                "Utilities", "Energy", "Real Estate",
                "Technology", "Consumer Staples", "Health Care",
                "Secular Growth", "Momentum", "Mid Caps",
                "Low Beta", "Quality",
                "Munis", "EM Credit", "Long Bond", "TIPS", "Treasury",
            ],
        },
        "worst": {
            "asset_class": [
                "Domestic Equities",
                "International Equities",
                "Digital Assets",
            ],
            "sector": [
                "Communication Services", "Financials",
                "Consumer Discretionary", "Industrials", "Materials",
                "Equities", "Small Caps",
                "Dividend Yield", "Value", "Defensives",
                "BDCs", "Preferreds", "Convertibles",
                "High Yield", "Leveraged Loans",
            ],
        },
    },

    4: {  # Deflation — growth ↓, inflation ↓
        "best": {
            "asset_class": [
                "Domestic Fixed Income",
            ],
            "sector": [
                "Gold", "USD",
                "Consumer Staples", "Health Care", "Utilities",
                "Low Beta", "Dividend Yield", "Quality",
                "Defensives", "Value",
                "Long Bond", "Treasury", "IG Credit", "Munis", "MBS",
            ],
        },
        "worst": {
            "asset_class": [
                "Commodities",
                "Domestic Equities",
                "International Equities",
                "Foreign Exchange",
                "Digital Assets",
            ],
            "sector": [
                "Energy", "Technology", "Financials",
                "Industrials", "Consumer Discretionary",
                "Equities", "Small Caps",
                "High Beta", "Momentum", "Leverage",
                "Secular Growth", "Cyclical Growth",
                "Preferreds", "EM Local Currency",
                "BDCs", "Leveraged Loans", "TIPS",
            ],
        },
    },
}


def get_quad_alignment(asset_class: str, sector: str, quad: int) -> float:
    """
    Returns:
      +1.0 = Best (Quad tailwind)
       0.0 = Neutral (not listed)
      -1.0 = Worst (Quad headwind)

    Sector takes priority over asset class.
    """
    if not sector or sector in ALWAYS_NEUTRAL_SECTORS:
        return 0.0

    q = QUAD_ALIGNMENT.get(quad)
    if q is None:
        return 0.0

    if sector in q["best"]["sector"]:
        return 1.0
    if sector in q["worst"]["sector"]:
        return -1.0
    if asset_class in q["best"]["asset_class"]:
        return 1.0
    if asset_class in q["worst"]["asset_class"]:
        return -1.0

    return 0.0


def get_quad_multiplier(viewpoint: str, asset_class: str, sector: str,
                        current_quad: int | None,
                        current_prob: float) -> tuple:
    """
    Layer 5 — Quad multiplier.
    Returns (multiplier, label).

    Aligned:    viewpoint matches quad tailwind  → boost
    Misaligned: viewpoint fights quad headwind   → dampen
    Floor: 0.50 (never below)
    Ceiling: 1.25 (at 100% prob, best alignment)
    """
    if viewpoint == "Neutral" or current_quad is None:
        return 1.00, "Neutral"

    alignment = get_quad_alignment(asset_class, sector, current_quad)

    if alignment == 0.0:
        return 1.00, "Neutral"

    bullish_best  = (viewpoint == "Bullish" and alignment > 0)
    bearish_worst = (viewpoint == "Bearish" and alignment < 0)
    aligned = bullish_best or bearish_worst

    direction = 1.0 if aligned else -1.0
    magnitude = abs(alignment) * current_prob * 0.25
    mult = max(0.50, round(1.00 + (direction * magnitude), 4))

    label = "Aligned" if aligned else "Misaligned"
    return mult, label


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


# ── Trade timeframe: Bollinger Band LRR/HRR ──────────────────────────────────

def compute_trade_lrr_hrr(ma20: float | None, std20: float | None,
                           ma20_regime: str | None,
                           pivot_dir: str | None = None,
                           close: float | None = None,
                           atr: float | None = None) -> tuple:
    """
    Bollinger Band framework for Trade timeframe.

    Center:  MA20(close) — standard 20-day simple moving average.
    Width:   STD20(close) — std(prices[-20:], ddof=0).
    k_wide = 2.0  (target/exit side — standard 2σ BB, never changes)
    k_tight = 0.0 (entry side — MA20 exactly; H removed from band width)

    H is calculated and stored in signal_hurst for indicator regime classification
    (H < 0.45 → oscillators; H > 0.55 → trend-following) but does NOT affect bands.

    Regime flip (2 consecutive closes above/below MA20) switches tight vs wide:

      Uptrend + above MA20 (normal):
        LRR = min(MA20, close - 0.5×ATR)
              ATR buffer: when close approaches MA20 from above, ensures LRR
              sits at least 0.5×ATR below close. Collapses to MA20 when close
              is far above it (buffer inactive). Mirrors downtrend tight ceiling.
        HRR = MA20 + 2σ           (BB upper — target)

      Uptrend + below MA20 (counter-trend):
        LRR = MA20 - 2σ           (BB lower — widens to full band)
        HRR = MA20 + 2σ           (BB upper — target)

      Downtrend + below MA20 (normal):
        LRR = MA20 - 2σ           (BB lower — target)
        HRR = max(MA20, close + 0.5×ATR)
              ATR buffer: when close approaches MA20 from below, ensures HRR
              sits at least 0.5×ATR above close. Collapses to MA20 when close
              is far below it (buffer inactive). Mirror of uptrend tight floor.

      Downtrend + above MA20 (counter-trend / flip):
        LRR = MA20 - 2σ           (BB lower — target)
        HRR = MA20 + 2σ           (BB upper — widens to full band)

    Returns (None, None) if any required input is missing.
    """
    center = ma20
    vol    = std20

    if center is None or vol is None:
        return None, None
    if vol <= 0:
        return None, None

    k_wide = 2.0
    above  = (ma20_regime or "uptrend") == "uptrend"   # close vs MA20(close)

    if pivot_dir == "downtrend":
        lrr = round(center - k_wide * vol, 4)
        if not above:
            # Normal downtrend: tight HRR = MA20 with ATR buffer near close
            if atr and close is not None:
                hrr = round(max(center, close + 0.5 * atr), 4)
            else:
                hrr = round(center, 4)
        else:
            # Counter-trend flip (2 closes above MA20): widen to BB upper
            hrr = round(center + k_wide * vol, 4)
    else:
        # Uptrend
        hrr = round(center + k_wide * vol, 4)
        if above:
            # Normal uptrend: tight LRR = MA20 with ATR buffer near close
            if atr and close is not None:
                lrr = round(min(center, close - 0.5 * atr), 4)
            else:
                lrr = round(center, 4)
        else:
            lrr = round(center - k_wide * vol, 4)  # counter-trend: widen to BB lower

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
                       pivot_direction: str | None) -> str:
    """
    Derive Bullish / Bearish / Neutral for one timeframe.

    C is the invalidation level for normal structures. When d_extended is True,
    the pivot engine has already handled the B-based break state machine and will
    have returned BREAK_OF_TRADE/BREAK_CONFIRMED if B was breached — so this
    function only sees the resulting clean state values.

    Direction is determined by pivots only — H (and therefore LRR/HRR) has no role.
    """
    if state in ("BREAK_CONFIRMED", "NO_STRUCTURE"):
        return "Neutral"
    if pivot_direction is None:
        return "Neutral"

    # BREAK_OF_TRADE / BREAK_OF_TREND: first close through break level — direction holds
    # until BREAK_CONFIRMED (2nd consecutive close). State cell shows the break warning.
    if state in ("BREAK_OF_TRADE", "BREAK_OF_TREND"):
        return "Bullish" if pivot_direction == "uptrend" else "Bearish"

    if c is None:
        return "Neutral"
    if pivot_direction == "uptrend":
        return "Bullish" if price > c else "Neutral"
    if pivot_direction == "downtrend":
        return "Bearish" if price < c else "Neutral"
    return "Neutral"


# ── WARNING state check ───────────────────────────────────────────────────────

def is_warning(lrr: float | None, hrr: float | None,
               c: float | None, pivot_direction: str | None,
               d_extended: bool = False,
               b: float | None = None) -> bool:
    """
    Structural WARNING: LRR drifted below break level (uptrend) or HRR above break level (downtrend).
    Break level = C normally; B when d_extended is True (D > B + bc_range).
    Applied to Trade timeframe only — Trend/LT use single levels.
    WARNING is a boolean flag only — it is NOT written to structural_state.
    """
    if pivot_direction is None:
        return False
    break_level = b if (d_extended and b is not None) else c
    if break_level is None:
        return False
    if pivot_direction == "uptrend":
        return lrr is not None and lrr < break_level
    if pivot_direction == "downtrend":
        return hrr is not None and hrr > break_level
    return False


# ── Per-cell warn flags ───────────────────────────────────────────────────────

def _compute_warn_flags(tf: str, pivot_dir: str | None,
                        lrr: float | None, hrr: float | None,
                        b: float | None, c: float | None,
                        d_extended: bool = False) -> tuple:
    """
    Price-based pivot threshold flags (⚠ indicators on LRR/HRR cells).

    Break level = C normally; B when d_extended is True (D > B + bc_range).

    Trade:  LRR ⚠ when uptrend: lrr < break_level  · downtrend: lrr > b
            HRR ⚠ when uptrend: hrr < b             · downtrend: hrr > break_level
    Trend:  LRR ⚠ when uptrend: lrr < break_level  · downtrend: lrr > break_level
            HRR = None → hrr_warn always False
    LT:     Never

    Returns (lrr_warn: bool, hrr_warn: bool).
    """
    if tf == "lt":
        return False, False

    lrr_warn = False
    hrr_warn = False

    # Break level shifts from C to B when d_extended is True
    break_level = b if (d_extended and b is not None) else c

    if tf == "trade":
        if pivot_dir == "uptrend":
            lrr_warn = lrr is not None and break_level is not None and lrr < break_level
            hrr_warn = hrr is not None and b is not None and hrr < b
        elif pivot_dir == "downtrend":
            hrr_warn = hrr is not None and break_level is not None and hrr > break_level
            lrr_warn = lrr is not None and b is not None and lrr > b

    elif tf == "trend":
        # lrr holds the Trend Level (single level); hrr is always None
        if pivot_dir == "uptrend":
            lrr_warn = lrr is not None and break_level is not None and lrr < break_level
        elif pivot_dir == "downtrend":
            lrr_warn = lrr is not None and break_level is not None and lrr > break_level

    return lrr_warn, hrr_warn


# ── Conviction Score (v1.8+) ──────────────────────────────────────────────────

def compute_conviction(close: float,
                       trade_lrr: float | None, trade_hrr: float | None,
                       trade_dir: str, viewpoint: str,
                       obv_dir: str, obv_ma20: list) -> tuple:
    """
    Conviction Layers 1–3 (proximity + OBV alignment + slope boost).
    Layers 4 (VIX) and 5 (Quad) are applied in compute_output after this call.

      base             = 50
      conviction_raw   = 50 × (0.70 + 0.30 × prox)   → 35–50
      conviction_vol   = conviction_raw × obv_mult      (1.20 / 0.85 / 1.00)
      conviction_slope = conviction_vol × slope_boost   (1.20 / 1.00)

    Returns (conviction_slope, obv_slope, obv_slope_trend).
    CRITICAL: caller must blank conviction when Viewpoint = Neutral.
    """
    base = 50.0

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

    obv_slope, obv_slope_trend, alignment_mult, slope_boost = _obv_slope_signals(
        obv_ma20, viewpoint, obv_dir,
    )

    conviction_vol   = conviction_raw * alignment_mult
    conviction_slope = conviction_vol * slope_boost

    return round(conviction_slope, 4), obv_slope, obv_slope_trend


# ── Main entry point ──────────────────────────────────────────────────────────

def compute_output(ticker: str, db, prior_ranges: dict = None,
                   asset_class: str = "", sector: str = "",
                   quad_current: int | None = None,
                   quad_prob: float = 0.0) -> dict:
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
    atr         = float(cache_row.atr)     if (cache_row and getattr(cache_row, 'atr',     None) is not None) else None

    # OBV pivot direction + MA20 slope signals
    if prices and volumes and len(prices) == len(volumes):
        obv_dir   = _obv_direction(prices, volumes)
        obv_ma20  = _build_obv_ma20(prices, volumes)
    else:
        obv_dir  = "Neutral"
        obv_ma20 = []

    h_map = {
        "trade": getattr(hurst_row, "h_trade", None) if hurst_row else None,
        "trend": getattr(hurst_row, "h_trend", None) if hurst_row else None,
        "lt":    getattr(hurst_row, "h_lt",    None) if hurst_row else None,
    }

    h_trend      = h_map["trend"]
    h_trend_up   = getattr(hurst_row, "h_trend_up",   None) if hurst_row else None
    h_trend_down = getattr(hurst_row, "h_trend_down", None) if hurst_row else None

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

        state      = pivot_row.structural_state or "NO_STRUCTURE"
        pivot_dir  = _infer_pivot_direction(pivot_row)
        b          = pivot_row.pivot_b
        c          = pivot_row.pivot_c
        d_extended = bool(getattr(pivot_row, "d_extended", False) or False)

        # Direction — pivot engine has already applied B-based break logic when d_extended
        direction = _compute_direction(price, c, state, pivot_dir)

        # ── LRR / HRR by timeframe ───────────────────────────────────────────
        if tf == "trade":
            lrr, hrr = compute_trade_lrr_hrr(ma20, std20, ma20_regime, pivot_dir,
                                             close=price, atr=atr)

            # WARNING: LRR drifted below break level (uptrend) or HRR above break level (downtrend)
            # Break level = C normally; B when d_extended is True.
            # WARNING is a boolean flag only — structural_state is never overridden to "WARNING".
            warning = is_warning(lrr, hrr, c, pivot_dir, d_extended=d_extended, b=b)

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
            # Trend Level = break pivot (B when d_extended, else C); no MA100 slope check.
            if direction != "Neutral" and (b is not None or c is not None):
                break_pivot = b if d_extended else c
                lrr = round(break_pivot, 4) if break_pivot is not None else None
            else:
                lrr = None
            hrr          = None
            warning      = False
            hrr_extended = False
            lrr_extended = False

        else:  # lt / tail
            lrr, hrr = compute_tail_level(ma200, prices, direction)
            warning      = False
            hrr_extended = False
            lrr_extended = False

        lrr_warn, hrr_warn = _compute_warn_flags(tf, pivot_dir, lrr, hrr, b, c, d_extended=d_extended)

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
            "d_extended":       d_extended,
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

    # ── VIX close — read once; used for Layer 4 and display ─────────────────
    vix_row   = db.query(PriceCache).filter(PriceCache.ticker == "VIX").first() if db else None
    vix_close = float(vix_row.close) if (vix_row and vix_row.close is not None) else None

    # ── Effective H — display + regime classification only (not in conviction) ─
    h_eff = get_effective_h_trend(
        asset_class, ticker, viewpoint,
        h_trend, h_trend_up, h_trend_down,
    )

    # ── Conviction — BLANK when Viewpoint = Neutral ──────────────────────────
    conviction      = None
    quad_align_label = "Neutral"
    quad_mult_val    = 1.00
    vix_zone         = "N/A"
    obv_slope        = "flat"
    obv_slope_trend  = "flat"

    if viewpoint != "Neutral":
        trade_lrr = timeframe_results["trade"]["lrr"]
        trade_hrr = timeframe_results["trade"]["hrr"]

        # Layers 1–3: proximity + OBV alignment + slope boost
        conviction_slope, obv_slope, obv_slope_trend = compute_conviction(
            price, trade_lrr, trade_hrr, trade_dir, viewpoint,
            obv_dir, obv_ma20,
        )

        # Layer 4: VIX regime (Domestic Equities only)
        vix_mult, vix_zone = get_vix_mult(vix_close, asset_class)
        conviction_vix = conviction_slope * vix_mult

        # Layer 5: Quad multiplier
        quad_mult_val, quad_align_label = get_quad_multiplier(
            viewpoint, asset_class, sector, quad_current, quad_prob,
        )
        conviction_quad = conviction_vix * quad_mult_val

        conviction = round(min(conviction_quad, 100.0), 2)

    # ── Alert flag ⚡ ────────────────────────────────────────────────────────
    alert = bool(
        viewpoint != "Neutral" and
        conviction is not None and conviction >= 65.0
    )

    logger.info(
        f"{ticker}: viewpoint={viewpoint} conviction={conviction} "
        f"trade_dir={trade_dir} trend_dir={trend_dir} alert={alert}"
    )

    return {
        "ticker":          ticker,
        "viewpoint":       viewpoint,
        "conviction":      conviction,
        "vix_regime":      vix_zone,
        "quad_alignment":  quad_align_label,
        "quad_mult":       quad_mult_val,
        "vol_signal":      vol_signal,
        "obv_direction":   obv_dir,
        "obv_confirming":  obv_confirming,
        "alert":           alert,
        "trade":           timeframe_results["trade"],
        "trend":           timeframe_results["trend"],
        "lt":              timeframe_results["lt"],
    }
