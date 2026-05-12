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
  - signal_pivots  (pivot_a/b/c/d, structural_state, d_extended)
  - signal_output  (prior hrr_snapped/lrr_snapped — v1.9.1 snap state)
  - vol_history    (implied_vol / hv30 — for trade RR vol rank lookup)
  - price_cache    (close, ma200, history_json, volume_history_json)

Never calls yfinance directly.
"""
import json
import logging
import numpy as np
from models.signal_hurst  import SignalHurst
from models.signal_pivots import SignalPivots
from models.signal_output import SignalOutput
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


_OBV_REGRESSION_WINDOW = 40
_OBV_NEUTRAL_BAND      = 0.02   # |normalized slope| below this → Neutral


def _obv_direction(closes: list, volumes: list) -> str:
    """
    Determine OBV trend direction using 40-bar linear regression slope on the OBV series.
    Slope is normalized by std(OBV) over the window to be scale-invariant across tickers.
    A small neutral band around zero prevents noise from registering as direction.
    Returns: 'Bullish' | 'Bearish' | 'Neutral'
    """
    obv = _build_obv(closes, volumes)
    n   = _OBV_REGRESSION_WINDOW
    if len(obv) < n:
        return "Neutral"

    y     = obv[-n:]
    x     = np.arange(n, dtype=float)
    slope = float(np.polyfit(x, y, 1)[0])   # units: OBV per bar

    # Normalize by std so the neutral band threshold is ticker-agnostic
    std = float(np.std(y))
    if std == 0:
        return "Neutral"

    normalized = slope / std
    if normalized >  _OBV_NEUTRAL_BAND:
        return "Bullish"
    if normalized < -_OBV_NEUTRAL_BAND:
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


def get_vix_score(vix_close: float | None, asset_class: str) -> tuple:
    """
    Component 4 — VIX additive score (v2.0).
    Returns (vix_score, vix_zone).

    Non-equity asset classes receive full credit (+15) — no VIX penalty.
    Missing VIX row defaults to full credit (no crash assumed).

    Thresholds (locked — same boundaries as v1.9 multiplier):
      Investable  VIX < 19   +15
      Edgy        19–23      +10
      Choppy      24–29      + 5
      Danger      ≥ 30         0
    """
    if asset_class not in VIX_REGIME_ASSET_CLASSES:
        return 15, "N/A"
    if vix_close is None:
        return 15, "Unknown"
    if vix_close < 19:
        return 15, "Investable"
    elif vix_close < 24:
        return 10, "Edgy"
    elif vix_close < 30:
        return  5, "Choppy"
    else:
        return  0, "Danger"


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

# ── v1.9.1 Trade RR — BB+Snap framework ──────────────────────────────────────
# Spec: Docs/SignalMatrix_RR_v1_9_1.txt
#
# Replaces v1.8 fixed-N (20) BB formula. Dynamic-N (8-15) BB with stateful
# snap mechanic on the trailing side that compresses toward MA during impulses.
# Vol source: IV30 percentile rank (primary) → HV30 rank (fallback).
# σ stays price-derived; vol rank only drives N selection.

# Locked parameters — TOS-validated values from production tuning.
# Spec defaults differed (k_extend=2.0, k_max=1.0, k_min=0.3); these reflect
# k_extend bumped to 2.2 (less leading-side lag) and k_min/k_max widened
# (0.4/1.4) for smoother snap behavior across SPX/GOOGL/AMZN regimes.
_RR_RANK_LOOKBACK    = 252
_RR_SNAP_WINDOW      = 22
_RR_K_WIDE           = 2.0
_RR_K_EXTEND         = 2.2   # leading impulse side (opposite the snap)
_RR_K_MAX            = 1.4   # snap side: max offset from MA
_RR_K_MIN            = 0.4   # snap side: floor
_RR_K_DECAY          = 0.5   # how fast k shrinks as proximity grows
_RR_PROXIMITY_BARS   = 3     # 3-bar EMA on proximity_raw

# 8-bucket lookup, right-inclusive on each upper bound
_RR_BUCKETS = (
    (10.0, 8),
    (20.0, 9),
    (35.0, 10),
    (50.0, 11),
    (64.0, 12),
    (79.0, 13),
    (89.0, 14),
)
_RR_BUCKET_TOP_N = 15  # for hv_rank > 89


def _rr_n_for_rank(rank: float) -> int:
    """Map vol percentile rank (0–100) to BB window length N (8..15)."""
    for upper, n in _RR_BUCKETS:
        if rank <= upper:
            return n
    return _RR_BUCKET_TOP_N


def _rr_rank_in_window(value: float, window: list[float]) -> float:
    """Percentile rank of value within window. Returns 50.0 if range is degenerate."""
    if not window:
        return 50.0
    w_min = min(window)
    w_max = max(window)
    if w_max <= w_min:
        return 50.0
    return ((value - w_min) / (w_max - w_min)) * 100.0


def get_trade_rr_vol_series(ticker: str, db) -> tuple[list[float] | None, str | None]:
    """
    Returns (vol_series, source) where:
      vol_series = list of vol values (ascending date), at least RR_RANK_LOOKBACK + 3 long
      source     = 'iv' | 'hv' | None (insufficient history)

    Primary: IV30 from vol_history.implied_vol if >= RR_RANK_LOOKBACK + 3 obs
    Fallback: HV30 from vol_history.hv30
    """
    from models.vol_history import VolHistory

    needed = _RR_RANK_LOOKBACK + 3   # need extra bars for the 3-bar proximity window

    iv_rows = (
        db.query(VolHistory)
        .filter(VolHistory.ticker == ticker, VolHistory.implied_vol.isnot(None))
        .order_by(VolHistory.iv_date.desc())
        .limit(needed + 5)
        .all()
    )
    if len(iv_rows) >= needed:
        values = [r.implied_vol for r in reversed(iv_rows)]
        return values, "iv"

    hv_rows = (
        db.query(VolHistory)
        .filter(VolHistory.ticker == ticker, VolHistory.hv30.isnot(None))
        .order_by(VolHistory.iv_date.desc())
        .limit(needed + 5)
        .all()
    )
    if len(hv_rows) >= needed:
        values = [r.hv30 for r in reversed(hv_rows)]
        return values, "hv"

    return None, None


def compute_trade_lrr_hrr(
    closes: list[float],
    vol_series: list[float],
    prior_hrr_snapped: bool,
    prior_lrr_snapped: bool,
) -> tuple:
    """
    v1.9.1 Trade RR — BB + Snap.

    Args:
        closes:       full price history, ascending date order. closes[-1] is
                      today's EOD close.
        vol_series:   IV30 or HV30 history aligned to closes. vol_series[-1] is
                      today's vol value. Length >= 255 (252 rank window + 3
                      proximity bars).
        prior_hrr_snapped, prior_lrr_snapped: snap state from yesterday's run.

    Returns:
        (lrr, hrr, hrr_snapped, lrr_snapped) — bands are floats; snap flags
        are booleans. Returns (None, None, False, False) on insufficient
        history.
    """
    import math

    # Cold-start guard — need 273+ closes (252 rank window + 21 prior returns
    # for oldest hv30 if HV path) AND vol_series must cover the rank window
    # plus 3 proximity bars.
    if not closes or len(closes) < 273:
        return None, None, False, False
    if not vol_series or len(vol_series) < _RR_RANK_LOOKBACK + 3:
        return None, None, False, False

    # ── Per-bar dynamic N for the last 3 bars (proximity) and today's band ──
    # vol_series[-1] = today, vol_series[-2] = yesterday, vol_series[-3] = day-before
    # closes are aligned analogously: closes[-1] = today.
    bar_offsets = (-3, -2, -1)   # ordered: day-before, yesterday, today

    # Directional proximity — signed, not absolute.
    # prox_lrr: positive when price is above maN (LRR snap is "working").
    #           negative when price is below maN — k_lrr_dyn then expands
    #           toward k_wide, pulling the snap line down to the BB rather
    #           than up into the falling price.
    # prox_hrr: mirror — positive when price is below maN.
    prox_lrr_raw_bars = []
    prox_hrr_raw_bars = []
    today_n = None
    today_ma = None
    today_std = None

    for off in bar_offsets:
        end_idx = len(vol_series) + off + 1   # exclusive end
        start_idx = end_idx - _RR_RANK_LOOKBACK
        if start_idx < 0:
            return None, None, False, False
        window = vol_series[start_idx:end_idx]
        v_at = vol_series[off]
        rank_t = _rr_rank_in_window(v_at, window)
        n_t = _rr_n_for_rank(rank_t)

        # Rolling-N MA + STD on closes ending at this bar
        c_end = len(closes) + off + 1   # exclusive
        c_start = c_end - n_t
        if c_start < 0:
            return None, None, False, False
        window_closes = closes[c_start:c_end]
        ma_n_t = sum(window_closes) / n_t

        # Sample std (ddof=1) — matches ToS StDev() default
        if n_t > 1:
            mean = ma_n_t
            sq_sum = sum((x - mean) ** 2 for x in window_closes)
            std_n_t = math.sqrt(sq_sum / (n_t - 1))
        else:
            std_n_t = 0.0

        if std_n_t <= 0:
            return None, None, False, False

        c_at = closes[c_end - 1]
        prox_lrr_raw_bars.append((c_at - ma_n_t) / std_n_t)
        prox_hrr_raw_bars.append((ma_n_t - c_at) / std_n_t)

        if off == -1:
            today_n   = n_t
            today_ma  = ma_n_t
            today_std = std_n_t

    # ── EMA(3), alpha=0.5, seed at oldest bar ──
    alpha = 2.0 / (_RR_PROXIMITY_BARS + 1)   # = 0.5

    prox_lrr = prox_lrr_raw_bars[0]
    for v in prox_lrr_raw_bars[1:]:
        prox_lrr = alpha * v + (1 - alpha) * prox_lrr

    prox_hrr = prox_hrr_raw_bars[0]
    for v in prox_hrr_raw_bars[1:]:
        prox_hrr = alpha * v + (1 - alpha) * prox_hrr

    # Directional k values — each clamped to [k_min, k_wide].
    # When prox goes negative (price crossed to wrong side of maN), the raw k
    # grows past k_max toward k_wide. The min() clamp ensures the snap line
    # can never exceed the standard BB — when k_dyn == k_wide the snap line
    # has merged cleanly into the BB.
    k_lrr_dyn = min(_RR_K_WIDE, max(_RR_K_MIN, _RR_K_MAX - _RR_K_DECAY * prox_lrr))
    k_hrr_dyn = min(_RR_K_WIDE, max(_RR_K_MIN, _RR_K_MAX - _RR_K_DECAY * prox_hrr))

    # Standard BB and snap lines
    bb_lower  = today_ma - _RR_K_WIDE * today_std
    bb_upper  = today_ma + _RR_K_WIDE * today_std
    snap_lrr  = today_ma - k_lrr_dyn * today_std
    snap_hrr  = today_ma + k_hrr_dyn * today_std

    # ── Snap trigger detection ──
    # Today's close vs the 22 prior closes (closes[-23:-1])
    today_close       = closes[-1]
    prior_22_window   = closes[-(_RR_SNAP_WINDOW + 1):-1]
    prior_22_low      = min(prior_22_window)
    prior_22_high     = max(prior_22_window)
    is_22d_low_close  = today_close <= prior_22_low
    is_22d_high_close = today_close >= prior_22_high

    # ── Release conditions ──
    # Merge:  unclamped k has grown to k_wide → snap line == BB → natural convergence.
    #         Fires on gradual pullbacks when the EMA tracks price closely.
    # Breach: price breaks through the compressed snap line before the EMA catches up.
    #         Fires on sharp/fast moves where the lagged EMA hasn't decayed k yet.
    lrr_merged   = (_RR_K_MAX - _RR_K_DECAY * prox_lrr) >= _RR_K_WIDE
    hrr_merged   = (_RR_K_MAX - _RR_K_DECAY * prox_hrr) >= _RR_K_WIDE
    lrr_breached = today_close < snap_lrr
    hrr_breached = today_close > snap_hrr

    # ── Snap state update — trigger takes priority over release ──
    if is_22d_high_close:
        lrr_snapped = True
    elif prior_lrr_snapped and (lrr_breached or lrr_merged):
        lrr_snapped = False
    else:
        lrr_snapped = prior_lrr_snapped

    if is_22d_low_close:
        hrr_snapped = True
    elif prior_hrr_snapped and (hrr_breached or hrr_merged):
        hrr_snapped = False
    else:
        hrr_snapped = prior_hrr_snapped

    # Coincidence rule — LRR (uptrend) takes priority
    if hrr_snapped and lrr_snapped:
        hrr_snapped = False

    # ── Band computation ──
    # When snap is active, output the snap line.
    # When released (breach or merge), output the standard BB — on a merge the
    # snap line already equals the BB so the transition is seamless; on a breach
    # the jump to bb_lower/bb_upper is intentional (snap support failed).
    if hrr_snapped:
        hrr = snap_hrr
        lrr = today_ma - _RR_K_EXTEND * today_std
    elif lrr_snapped:
        lrr = snap_lrr
        hrr = today_ma + _RR_K_EXTEND * today_std
    else:
        lrr = bb_lower
        hrr = bb_upper

    return round(lrr, 4), round(hrr, 4), hrr_snapped, lrr_snapped


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
                        d_extended: bool = False,
                        d: float | None = None) -> tuple:
    """
    Price-based pivot threshold flags (⚠ indicators on LRR/HRR cells).

    Break level = C normally; B when d_extended is True (D > B + bc_range).

    Trade:  LRR ⚠ when uptrend: lrr < break_level           · downtrend: lrr > b (or D when d_extended)
            HRR ⚠ when uptrend: hrr < b (or D when d_extended) · downtrend: hrr > break_level
              When d_extended: HRR (uptrend) / LRR (downtrend) compared against D — the extended
              high/low — not B. B is the break level; D is the "can the target still reach the peak" reference.
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

    # When d_extended, the target-side warn compares against D (the extended high/low).
    # If D is unavailable, fall back to B so the flag still fires conservatively.
    target_ref = (d if d is not None else b) if d_extended else b

    if tf == "trade":
        if pivot_dir == "uptrend":
            lrr_warn = lrr is not None and break_level is not None and lrr < break_level
            hrr_warn = hrr is not None and target_ref is not None and hrr < target_ref
        elif pivot_dir == "downtrend":
            hrr_warn = hrr is not None and break_level is not None and hrr > break_level
            lrr_warn = lrr is not None and target_ref is not None and lrr > target_ref

    elif tf == "trend":
        # lrr holds the Trend Level (single level); hrr is always None
        if pivot_dir == "uptrend":
            lrr_warn = lrr is not None and break_level is not None and lrr < break_level
        elif pivot_dir == "downtrend":
            lrr_warn = lrr is not None and break_level is not None and lrr > break_level

    return lrr_warn, hrr_warn


# ── Conviction Score (v1.8+) ──────────────────────────────────────────────────
# CONVICTION_V2_CLEANUP — remove after 30 days from v2.0 implementation date (May 2026)
# compute_conviction() replaced by additive formula in compute_output(); inlined below.
#
# def compute_conviction(close, trade_lrr, trade_hrr, trade_dir, viewpoint,
#                        obv_dir, obv_ma20):
#     base = 50.0
#     prox = 0.5
#     if trade_lrr is not None and trade_hrr is not None and trade_hrr > trade_lrr:
#         band = trade_hrr - trade_lrr
#         if trade_dir == "Bullish":
#             prox = 1.0 - (close - trade_lrr) / band
#         elif trade_dir == "Bearish":
#             prox = (close - trade_lrr) / band
#         prox = max(0.0, min(1.0, prox))
#     conviction_raw = base * (0.70 + 0.30 * prox)
#     obv_slope, obv_slope_trend, alignment_mult, slope_boost = _obv_slope_signals(
#         obv_ma20, viewpoint, obv_dir)
#     conviction_vol   = conviction_raw * alignment_mult
#     conviction_slope = conviction_vol * slope_boost
#     return round(conviction_slope, 4), obv_slope, obv_slope_trend


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

    # MA200 from price_cache — only consumer is compute_tail_level().
    # MA20, MA100, STD20, MA20 regime, ATR are populated on price_cache for legacy
    # / inspection purposes but no longer drive any signal. Trade RR uses dynamic-N
    # MA/STD computed from raw closes (v1.9.1); Trend Level uses break pivot directly.
    ma200       = float(cache_row.ma200)       if (cache_row and cache_row.ma200 is not None) else None

    # OBV direction (40-bar regression) + MA20 slope — computed once, used in vol_signal and conviction
    if prices and volumes and len(prices) == len(volumes):
        obv_dir  = _obv_direction(prices, volumes)
        obv_ma20 = _build_obv_ma20(prices, volumes)
    else:
        obv_dir  = "Neutral"
        obv_ma20 = []

    # OBV MA20 slope — needed for strict vol_signal check and v2.0 volume_score
    if len(obv_ma20) >= 6:
        _slope_now  = obv_ma20[-1] - obv_ma20[-4]
        _slope_prev = obv_ma20[-2] - obv_ma20[-5]
        obv_slope_early = ("rising"  if _slope_now > 0 else
                           "falling" if _slope_now < 0 else "flat")
        obv_slope_trend = ("increasing" if _slope_now > _slope_prev else
                           "decreasing" if _slope_now < _slope_prev else "flat")
    elif len(obv_ma20) >= 4:
        _slope_now  = obv_ma20[-1] - obv_ma20[-4]
        obv_slope_early = ("rising"  if _slope_now > 0 else
                           "falling" if _slope_now < 0 else "flat")
        obv_slope_trend = "flat"
    else:
        obv_slope_early = "flat"
        obv_slope_trend = "flat"

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
                "hrr_snapped": False, "lrr_snapped": False,
                "pivot_b": None, "pivot_c": None,
            }
            continue

        state      = pivot_row.structural_state or "NO_STRUCTURE"
        pivot_dir  = _infer_pivot_direction(pivot_row)
        b          = pivot_row.pivot_b
        c          = pivot_row.pivot_c
        d          = pivot_row.pivot_d
        d_extended = bool(getattr(pivot_row, "d_extended", False) or False)

        # Direction — pivot engine has already applied B-based break logic when d_extended
        direction = _compute_direction(price, c, state, pivot_dir)

        # ── LRR / HRR by timeframe ───────────────────────────────────────────
        if tf == "trade":
            # Load prior snap state from existing signal_output row (yesterday's value)
            existing_trade_row = db.query(SignalOutput).filter(
                SignalOutput.ticker    == ticker,
                SignalOutput.timeframe == "trade",
            ).first()
            prior_hrr_snap = bool(getattr(existing_trade_row, "hrr_snapped", False) or False) if existing_trade_row else False
            prior_lrr_snap = bool(getattr(existing_trade_row, "lrr_snapped", False) or False) if existing_trade_row else False

            # Load vol series (IV primary, HV fallback). Returns None if insufficient.
            vol_series, vol_source = get_trade_rr_vol_series(ticker, db)

            if vol_series is None or not prices:
                lrr, hrr, hrr_snapped, lrr_snapped = None, None, False, False
            else:
                lrr, hrr, hrr_snapped, lrr_snapped = compute_trade_lrr_hrr(
                    closes            = prices,
                    vol_series        = vol_series,
                    prior_hrr_snapped = prior_hrr_snap,
                    prior_lrr_snapped = prior_lrr_snap,
                )

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
            hrr_snapped  = False
            lrr_snapped  = False

        else:  # lt / tail
            lrr, hrr = compute_tail_level(ma200, prices, direction)
            warning      = False
            hrr_extended = False
            lrr_extended = False
            hrr_snapped  = False
            lrr_snapped  = False

        lrr_warn, hrr_warn = _compute_warn_flags(tf, pivot_dir, lrr, hrr, b, c, d_extended=d_extended, d=d)

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
            "hrr_snapped":      hrr_snapped,
            "lrr_snapped":      lrr_snapped,
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

    # ── OBV vol_signal — strict: regression direction AND MA20 slope both confirm Trade Dir
    # This matches the alignment_mult condition used in the conviction formula exactly.
    _obv_slope_confirms = (
        (trade_dir == "Bullish" and obv_slope_early == "rising") or
        (trade_dir == "Bearish" and obv_slope_early == "falling")
    )
    if trade_dir in ("Bullish", "Bearish") and obv_dir == trade_dir and _obv_slope_confirms:
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

    # ── Conviction v2.0 — Additive four-component formula ────────────────────
    # Always calculates regardless of Viewpoint.
    # Display when conviction_final >= 45 (else None/blank).
    # Neutral viewpoint: calculates same way; UI renders in grey (#8899aa) when >= 45.

    # Component 1 — Structural (max 50)
    # Trade=Bullish + Trend=Bearish (opposing) = 0 — conflicted structure = no conviction.
    if trade_dir == trend_dir and trade_dir != "Neutral":
        structural_score = 50    # both Bullish or both Bearish — full alignment
    elif trade_dir != "Neutral" and trend_dir == "Neutral":
        structural_score = 25    # trade only
    elif trade_dir == "Neutral" and trend_dir != "Neutral":
        structural_score = 25    # trend only (unusual but valid)
    else:
        structural_score = 0     # both Neutral, OR opposing directions (conflicted)

    # Component 2 — Quad (+20 / 0 / -15, prob-weighted)
    # Viewpoint gate: Neutral viewpoint → quad_score = 0 (macro tailwind ≠ conviction without structure)
    if quad_current is not None:
        _quad_alignment = get_quad_alignment(asset_class, sector, quad_current)
        if viewpoint == "Neutral" or _quad_alignment == 0.0:
            quad_score = 0
            quad_align_label = "Neutral"
        elif _quad_alignment > 0:
            quad_score = 20 if quad_prob >= 0.45 else 15
            quad_align_label = "Aligned"
        else:
            quad_score = -15 if quad_prob >= 0.45 else -11
            quad_align_label = "Misaligned"
        # Informational quad_mult — stored for popup/debug, not used in v2.0 formula
        quad_mult_val, _ = get_quad_multiplier(viewpoint, asset_class, sector, quad_current, quad_prob)
    else:
        quad_score       = 0
        quad_align_label = "Neutral"
        quad_mult_val    = 1.00

    # Component 3 — Volume (max 15)
    # obv_confirming = strict check: regression direction AND MA20 slope both confirm Trade Dir
    volume_score = 0
    if obv_confirming:
        volume_score += 10
        if ((trade_dir == "Bullish" and obv_slope_trend == "increasing") or
                (trade_dir == "Bearish" and obv_slope_trend == "decreasing")):
            volume_score += 5   # acceleration boost: +5 when slope is accelerating (early in move)

    # Component 4 — VIX/Vol (max 15, Domestic Equities only)
    vix_score, vix_zone = get_vix_score(vix_close, asset_class)

    # Assembly: sum → floor(0) → dampener → cap(100)
    conviction_sum = structural_score + quad_score + volume_score + vix_score
    conviction_sum = max(0.0, conviction_sum)   # floor — quad misalignment can push negative

    # Dampener ×0.92: target-side warn = "BB target can't reach the structural reference"
    #   Uptrend:   hrr_warn fires (HRR < D when d_extended, HRR < B normally)
    #   Downtrend: lrr_warn fires (LRR > D when d_extended, LRR > B normally)
    _tr          = timeframe_results["trade"]
    _trade_dir   = _tr["direction"]
    _hrr_warn    = _tr["hrr_warn"]
    _lrr_warn    = _tr["lrr_warn"]
    if ((_trade_dir == "Bullish" and _hrr_warn) or
            (_trade_dir == "Bearish" and _lrr_warn)):
        conviction_sum = conviction_sum * 0.92

    conviction_final = min(conviction_sum, 100.0)   # cap

    # Display threshold: blank below 45
    conviction = round(conviction_final, 2) if conviction_final >= 45.0 else None

    # ── Alert flag ⚡ ────────────────────────────────────────────────────────
    # Threshold raised to 80 (v2.0). Still requires non-Neutral viewpoint.
    alert = bool(
        viewpoint != "Neutral" and
        conviction is not None and conviction >= 80.0
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
        "quad_score":      quad_score,
        "vol_signal":      vol_signal,
        "obv_direction":   obv_dir,
        "obv_confirming":  obv_confirming,
        "alert":           alert,
        "trade":           timeframe_results["trade"],
        "trend":           timeframe_results["trend"],
        "lt":              timeframe_results["lt"],
    }
