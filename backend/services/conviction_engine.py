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


_OBV_LOOKBACK = 21   # 1-month (21 trading days) OBV level comparison


def _obv_direction(closes: list, volumes: list) -> str:
    """
    OBV trend direction via 21-bar lookback comparison.
    Current OBV vs OBV 21 bars ago: higher → Bullish, lower → Bearish, equal → Neutral.
    Requires at least 22 bars (21 lookback + current). Returns 'Bullish' | 'Bearish' | 'Neutral'.
    """
    obv = _build_obv(closes, volumes)
    if len(obv) < _OBV_LOOKBACK + 1:
        return "Neutral"

    current = obv[-1]
    prior   = obv[-1 - _OBV_LOOKBACK]

    if current > prior:
        return "Bullish"
    if current < prior:
        return "Bearish"
    return "Neutral"


def _build_obv_ma20(closes: list, volumes: list) -> list:
    """Build OBV series then compute its 20-period simple moving average."""
    obv = _build_obv(closes, volumes)
    if len(obv) < 20:
        return []
    return [sum(obv[i - 19 : i + 1]) / 20.0 for i in range(19, len(obv))]



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


# ── Vol Index Routing ─────────────────────────────────────────────────────────
# Maps ticker → vol index ticker for conviction Component 4.
# Tickers not listed here fall through to asset-class default (VIX for
# Domestic Equities, flat +15 for everything else).

VOL_INDEX_TICKER_MAP = {
    # VXN — Nasdaq-heavy
    "QQQ": "VXN", "NDX": "VXN", "XLK": "VXN", "SMH": "VXN", "SOXX": "VXN",
    "CIBR": "VXN", "QTUM": "VXN", "GRID": "VXN",
    "AAPL": "VXN", "MSFT": "VXN", "NVDA": "VXN", "AVGO": "VXN",
    "GOOGL": "VXN", "META": "VXN", "NFLX": "VXN",
    # RVX — Russell 2000
    "IWM": "RVX", "RUT": "RVX",
    # GVZ — Gold
    "GLD": "GVZ", "SGOL": "GVZ", "/GC": "GVZ",
    # OVX — Oil / Energy
    "USO": "OVX", "/CL": "OVX", "XOP": "OVX", "OIH": "OVX",
    # MOVE — Fixed Income
    "TLT": "MOVE", "/ZN": "MOVE", "SHY": "MOVE", "IEF": "MOVE",
    "VGIT": "MOVE", "LQD": "MOVE", "MBB": "MOVE", "PFF": "MOVE", "TIP": "MOVE",
}

# Per-index thresholds: (investable_ceiling, danger_floor)
# Three tiers: Investable (< ceiling), Choppy (ceiling to danger), Danger (≥ danger)
VOL_INDEX_THRESHOLDS = {
    "VIX":  (19, 30),
    "VXN":  (22, 32),
    "RVX":  (22, 32),
    "GVZ":  (22, 32),
    "OVX":  (38, 60),
    "MOVE": (85, 120),
}


def _resolve_vol_index(ticker: str, asset_class: str) -> str | None:
    """Return the vol index ticker for a given asset ticker, or None for flat +15."""
    if ticker in VOL_INDEX_TICKER_MAP:
        return VOL_INDEX_TICKER_MAP[ticker]
    if asset_class == "Domestic Equities":
        return "VIX"
    return None


def get_vol_score(vol_close: float | None, vol_hrr: float | None,
                  thresholds: tuple, viewpoint: str = "Neutral") -> tuple:
    """
    Component 4 — Volatility additive score (v2.2).
    Returns (vol_score, vol_zone).

    Generic scorer for any vol index. Three tiers (Edgy eliminated):

    Bullish / Neutral:
      Investable+  close < ceiling AND HRR < ceiling   +15
      Investable   close < ceiling                      +10
      Choppy       ceiling ≤ close < danger_floor         0
      Danger       close ≥ danger_floor                 -10

    Bearish (asymmetric — +5 floor):
      Danger       close ≥ danger_floor                 +15
      Choppy       ceiling ≤ close < danger_floor       +10
      Investable   close < ceiling                      + 5
    """
    if vol_close is None:
        return 15, "Unknown"

    ceiling, danger_floor = thresholds

    if viewpoint == "Bearish":
        if vol_close >= danger_floor:
            return 15, "Danger"
        elif vol_close >= ceiling:
            return 10, "Choppy"
        else:
            return 5, "Investable"

    if vol_close < ceiling:
        if vol_hrr is not None and vol_hrr < ceiling:
            return 15, "Investable"
        return 10, "Investable"
    elif vol_close < danger_floor:
        return 0, "Choppy"
    else:
        return -10, "Danger"


def get_vix_score(vol_close: float | None, asset_class: str,
                  vix_hrr: float | None = None,
                  viewpoint: str = "Neutral",
                  vol_index: str | None = None) -> tuple:
    """
    Component 4 — Volatility additive score (v2.2).
    Returns (vix_score, vix_zone).

    Wraps get_vol_score with index routing. If vol_index is None, returns
    flat +15 (no applicable vol index for this asset class).
    """
    if vol_index is None:
        return 15, "N/A"
    thresholds = VOL_INDEX_THRESHOLDS.get(vol_index)
    if thresholds is None:
        return 15, "N/A"
    return get_vol_score(vol_close, vix_hrr, thresholds, viewpoint)


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
_RR_K_MAX            = 1.0   # snap side: max offset from MA
_RR_K_MIN            = 0.0   # snap side: floor (fully collapses to MA at peak impulse)
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


def _hv30_series_from_closes(closes: list[float], period: int = 21) -> list[float] | None:
    """
    Reconstruct a full HV30 series (annualized 21-return realized vol) from a
    close-price history, end-aligned to `closes` (out[-1] corresponds to
    closes[-1]). Mirrors accumulate_hv_only's per-bar formula exactly:
    std(log-returns[-21:], ddof=0) * sqrt(252).

    Returns a list of length len(closes) - period, or None if there are too
    few/invalid closes.
    """
    if not closes or len(closes) < period + 2:
        return None
    arr = np.asarray(closes, dtype=float)
    if not np.all(np.isfinite(arr)) or np.any(arr <= 0):
        return None
    rets = np.log(arr[1:] / arr[:-1])          # length n-1
    n = len(arr)
    sqrt252 = 252 ** 0.5
    # close index j → the 21 returns ending into bar j are rets[j-period:j]
    return [float(np.std(rets[j - period:j], ddof=0) * sqrt252) for j in range(period, n)]


def get_trade_rr_vol_series(ticker: str, db) -> tuple[list[float] | None, str | None]:
    """
    Returns (vol_series, source) where:
      vol_series = list of vol values (ascending date), at least RR_RANK_LOOKBACK + 3 long
      source     = 'iv' | 'hv' | 'hv_computed' | None (insufficient history)

    Primary:    IV30 from vol_history.implied_vol if >= RR_RANK_LOOKBACK + 4 obs
    Fallback 1: HV30 from vol_history.hv30 (forward-accumulated rows)
    Fallback 2: HV30 reconstructed on the fly from price_cache.history_json.
                A newly-activated ticker has a full bootstrapped 5y price
                history on day one but only a few accumulated vol_history rows,
                so its 252-day rank window can't be built from stored vol.
                HV is fully reconstructable from price history; IV30 is NOT (no
                historical option chains), so IV stays forward-only. Self-heals
                to stored IV/HV (Primary/Fallback 1) once ~1y of rows accumulate.
    """
    from models.vol_history import VolHistory

    needed = _RR_RANK_LOOKBACK + 4   # 4 bars: yesterday's 3-bar EMA needs bar-4

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

    # Fallback 2 — reconstruct HV30 from the bootstrapped close history. Reads the
    # same price_cache.history_json that compute_output passes as `closes`, so the
    # two series stay date-aligned.
    pc = db.query(PriceCache).filter(PriceCache.ticker == ticker).first()
    if pc and pc.history_json:
        try:
            closes = json.loads(pc.history_json)
        except (ValueError, TypeError):
            closes = None
        hv_series = _hv30_series_from_closes(closes) if closes else None
        if hv_series is not None and len(hv_series) >= needed:
            return hv_series, "hv_computed"

    return None, None


def compute_trade_lrr_hrr(
    closes: list[float],
    vol_series: list[float],
    prior_hrr_snapped: bool,
    prior_lrr_snapped: bool,
    today_low: float | None = None,
    today_high: float | None = None,
) -> tuple:
    """
    v1.9.2 Trade RR — BB + Snap with directional proximity.

    Args:
        closes:       full price history, ascending date order. closes[-1] is
                      today's EOD close.
        vol_series:   IV30 or HV30 history aligned to closes. vol_series[-1] is
                      today's vol value. Length >= 255 (252 rank window + 3
                      proximity bars).
        prior_hrr_snapped, prior_lrr_snapped: snap state from yesterday's run.
        today_low:    today's intraday low — used for LRR breach check against
                      yesterday's published snap line. Falls back to today's
                      close when None.
        today_high:   today's intraday high — used for HRR breach check.
                      Falls back to today's close when None.

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
    if not vol_series or len(vol_series) < _RR_RANK_LOOKBACK + 4:
        return None, None, False, False

    # ── Per-bar dynamic N for the last 4 bars ──
    # bar_offsets: -4=two-days-ago, -3=day-before, -2=yesterday, -1=today
    # 4 bars are needed so both today's and yesterday's snap lines use a full
    # 3-bar EMA: yesterday = bars[-4,-3,-2]; today = bars[-3,-2,-1].
    bar_offsets = (-4, -3, -2, -1)

    # Directional proximity — signed, not absolute.
    # prox_lrr: positive when price is above maN (LRR snap is "working").
    #           negative when price is below maN — k_lrr_dyn then expands
    #           toward k_wide, pulling the snap line down to the BB rather
    #           than up into the falling price.
    # prox_hrr: mirror — positive when price is below maN.
    prox_lrr_raw_bars = []
    prox_hrr_raw_bars = []
    today_n   = None
    today_ma  = None
    today_std = None
    yest_ma   = None   # bar -2 values needed to reconstruct yesterday's snap line
    yest_std  = None

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

        # Population std (ddof=0) — matches ToS StDev() and Bollinger Band convention
        if n_t > 1:
            mean = ma_n_t
            sq_sum = sum((x - mean) ** 2 for x in window_closes)
            std_n_t = math.sqrt(sq_sum / n_t)
        else:
            std_n_t = 0.0

        if std_n_t <= 0:
            return None, None, False, False

        c_at = closes[c_end - 1]
        prox_lrr_raw_bars.append((c_at - ma_n_t) / std_n_t)
        prox_hrr_raw_bars.append((ma_n_t - c_at) / std_n_t)

        if off == -2:
            yest_ma  = ma_n_t
            yest_std = std_n_t
        if off == -1:
            today_n   = n_t
            today_ma  = ma_n_t
            today_std = std_n_t

    # ── EMA(3), alpha=0.5, seed at oldest of the 3 relevant bars ──
    # prox_lrr_raw_bars = [bar-4, bar-3, bar-2, bar-1]
    # Today's EMA:     seed bar-3 [1], update bar-2 [2], update bar-1 [3]
    # Yesterday's EMA: seed bar-4 [0], update bar-3 [1], update bar-2 [2]
    alpha = 2.0 / (_RR_PROXIMITY_BARS + 1)   # = 0.5

    prox_lrr = prox_lrr_raw_bars[1]
    for v in prox_lrr_raw_bars[2:]:
        prox_lrr = alpha * v + (1 - alpha) * prox_lrr

    prox_hrr = prox_hrr_raw_bars[1]
    for v in prox_hrr_raw_bars[2:]:
        prox_hrr = alpha * v + (1 - alpha) * prox_hrr

    # Yesterday's full 3-bar EMA (bars -4, -3, -2)
    prox_lrr_yest = prox_lrr_raw_bars[0]
    for v in prox_lrr_raw_bars[1:3]:
        prox_lrr_yest = alpha * v + (1 - alpha) * prox_lrr_yest

    prox_hrr_yest = prox_hrr_raw_bars[0]
    for v in prox_hrr_raw_bars[1:3]:
        prox_hrr_yest = alpha * v + (1 - alpha) * prox_hrr_yest

    # Directional k values — each clamped to [k_min, k_wide].
    # When prox goes negative (price crossed to wrong side of maN), the raw k
    # grows past k_max toward k_wide. The min() clamp ensures the snap line
    # can never exceed the standard BB — when k_dyn == k_wide the snap line
    # has merged cleanly into the BB.
    k_lrr_dyn = min(_RR_K_WIDE, max(_RR_K_MIN, _RR_K_MAX - _RR_K_DECAY * prox_lrr))
    k_hrr_dyn = min(_RR_K_WIDE, max(_RR_K_MIN, _RR_K_MAX - _RR_K_DECAY * prox_hrr))

    # Yesterday's published snap lines — used for breach detection.
    k_lrr_yest     = min(_RR_K_WIDE, max(_RR_K_MIN, _RR_K_MAX - _RR_K_DECAY * prox_lrr_yest))
    k_hrr_yest     = min(_RR_K_WIDE, max(_RR_K_MIN, _RR_K_MAX - _RR_K_DECAY * prox_hrr_yest))
    snap_lrr_yest  = yest_ma - k_lrr_yest * yest_std
    snap_hrr_yest  = yest_ma + k_hrr_yest * yest_std

    # Standard BB and today's snap lines
    bb_lower  = today_ma - _RR_K_WIDE * today_std
    bb_upper  = today_ma + _RR_K_WIDE * today_std
    snap_lrr  = today_ma - k_lrr_dyn * today_std
    snap_hrr  = today_ma + k_hrr_dyn * today_std

    # ── Snap trigger detection ──
    # Today's close vs the 22 prior closes (closes[-23:-1])
    today_close = closes[-1]
    bar_low     = today_low  if today_low  is not None else today_close
    bar_high    = today_high if today_high is not None else today_close

    prior_22_window   = closes[-(_RR_SNAP_WINDOW + 1):-1]
    prior_22_low      = min(prior_22_window)
    prior_22_high     = max(prior_22_window)
    is_22d_low_close  = today_close <= prior_22_low
    is_22d_high_close = today_close >= prior_22_high

    # ── Release conditions ──
    # Merge:   today's unclamped k has grown to k_wide → snap line == BB.
    #          Fires on gradual pullbacks when EMA tracks price closely.
    # Breach:  intraday low/high pierces yesterday's published snap line.
    #          Uses low (LRR) / high (HRR) — catches intraday tests even if
    #          close recovers. Compared against yesterday's snap, not today's,
    #          so the breach level is the one visible to the trader at open.
    lrr_merged   = (_RR_K_MAX - _RR_K_DECAY * prox_lrr) >= _RR_K_WIDE
    hrr_merged   = (_RR_K_MAX - _RR_K_DECAY * prox_hrr) >= _RR_K_WIDE
    lrr_breached = bar_low  < snap_lrr_yest
    hrr_breached = bar_high > snap_hrr_yest

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

    # OBV direction (21-bar lookback) + MA20 slope — computed once, used in vol_signal and conviction
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
                    today_low         = float(cache_row.daily_low)  if (cache_row and cache_row.daily_low  is not None) else None,
                    today_high        = float(cache_row.daily_high) if (cache_row and cache_row.daily_high is not None) else None,
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

    # ── OBV vol_signal — two independent layers: MA20 slope + 21-bar lookback
    # Compared against consensus direction (Trade OR Trend, not conflicting):
    #   Both aligned → use that direction
    #   One directional + one Neutral → use the directional one
    #   Opposing (Bullish vs Bearish) or both Neutral → no comparison, volume_score = 0
    if trade_dir != "Neutral" and trend_dir != "Neutral" and trade_dir != trend_dir:
        _vol_dir = "Neutral"   # conflicting — no consensus
    elif trade_dir != "Neutral":
        _vol_dir = trade_dir
    elif trend_dir != "Neutral":
        _vol_dir = trend_dir
    else:
        _vol_dir = "Neutral"

    _slope_confirms = (
        (_vol_dir == "Bullish" and obv_slope_early == "rising") or
        (_vol_dir == "Bearish" and obv_slope_early == "falling")
    )
    _slope_opposes = (
        (_vol_dir == "Bullish" and obv_slope_early == "falling") or
        (_vol_dir == "Bearish" and obv_slope_early == "rising")
    )
    _lookback_confirms = (_vol_dir in ("Bullish", "Bearish") and obv_dir == _vol_dir)
    _lookback_opposes  = (
        _vol_dir in ("Bullish", "Bearish") and
        obv_dir != "Neutral" and obv_dir != _vol_dir
    )

    if _vol_dir in ("Bullish", "Bearish") and _slope_confirms and _lookback_confirms:
        vol_signal = "Confirming"
    elif _vol_dir in ("Bullish", "Bearish") and _slope_opposes and _lookback_opposes:
        vol_signal = "Diverging"
    else:
        vol_signal = "Neutral"

    obv_confirming = vol_signal == "Confirming"

    # ── Vol index close + HRR — route ticker to its vol index ──────────────
    _vol_index = _resolve_vol_index(ticker, asset_class)
    if _vol_index and db:
        _vol_row = db.query(PriceCache).filter(PriceCache.ticker == _vol_index).first()
        vix_close = float(_vol_row.close) if (_vol_row and _vol_row.close is not None) else None
        _vol_sig = db.query(SignalOutput).filter(
            SignalOutput.ticker    == _vol_index,
            SignalOutput.timeframe == "trade",
        ).first()
        vix_hrr = float(_vol_sig.hrr) if (_vol_sig and _vol_sig.hrr is not None) else None
    else:
        vix_close = None
        vix_hrr = None

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
    # Viewpoint gate: fully Neutral (structural_score == 0, both timeframes Neutral or opposing)
    # → quad_score = 0. Partial structure (structural_score == 25, one timeframe confirmed)
    # → quad allowed to contribute. Macro tailwind is meaningful when at least one timeframe
    # has directional evidence.
    if quad_current is not None:
        _quad_alignment = get_quad_alignment(asset_class, sector, quad_current)
        if (structural_score == 0 and viewpoint == "Neutral") or _quad_alignment == 0.0:
            quad_score = 0
            quad_align_label = "Neutral"
        else:
            _bullish_best  = (viewpoint == "Bullish" and _quad_alignment > 0)
            _bearish_worst = (viewpoint == "Bearish" and _quad_alignment < 0)
            _aligned = _bullish_best or _bearish_worst
            if _aligned:
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
    # Two independent layers: MA20 slope confirms (+5), 21-bar lookback confirms (+5).
    # Acceleration bonus (+5) only when both layers confirm (Confirming).
    volume_score = 0
    if _slope_confirms:
        volume_score += 5
    if _lookback_confirms:
        volume_score += 5
    if obv_confirming:
        if ((trade_dir == "Bullish" and obv_slope_trend == "increasing") or
                (trade_dir == "Bearish" and obv_slope_trend == "decreasing")):
            volume_score += 5

    # Component 4 — Volatility (max 15, routed per vol index)
    vix_score, vix_zone = get_vix_score(vix_close, asset_class, vix_hrr=vix_hrr,
                                        viewpoint=viewpoint, vol_index=_vol_index)

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

    # NATH boost ×1.05: Viewpoint=Bullish AND trade HRR projects above all-time high
    # Mirrors the ×0.92 dampener — "buy every dip" when structure + target both point to new highs
    ath = float(cache_row.ath) if (cache_row and cache_row.ath is not None) else None
    _trade_hrr = timeframe_results["trade"]["hrr"]
    if (viewpoint == "Bullish" and
            _trade_hrr is not None and
            ath is not None and
            _trade_hrr > ath):
        conviction_sum *= 1.05

    conviction_final = min(conviction_sum, 105.0)   # cap — 105 allows NATH boost (×1.05) to be fully visible

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
        "structural_score": structural_score,
        "volume_score":    volume_score,
        "vix_score":       vix_score,
        "vol_signal":      vol_signal,
        "obv_direction":   obv_dir,
        "obv_confirming":  obv_confirming,
        "alert":           alert,
        "trade":           timeframe_results["trade"],
        "trend":           timeframe_results["trend"],
        "lt":              timeframe_results["lt"],
    }
