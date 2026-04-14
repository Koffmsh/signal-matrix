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


def get_vix_regime_multiplier(db) -> tuple:
    """
    Returns (multiplier, zone_label) based on current VIX close.
    Falls back to 1.00 / 'Unknown' if VIX not in cache.

    Multiplier table (locked):
      Investable  VIX < 19   × 1.10 — VCFs mechanically adding, trend signals reliable
      Edgy        19–23      × 1.00 — elevated but tradeable
      Choppy      24–29      × 0.90 — signal degradation, whipsaws likely
      Danger      ≥ 30       × 0.80 — sit on hands
    """
    vix_row = db.query(PriceCache).filter(PriceCache.ticker == "VIX").first()
    if vix_row is None or vix_row.close is None:
        return 1.00, "Unknown"
    vix = vix_row.close
    if vix < 19:
        return 1.10, "Investable"
    elif vix < 24:
        return 1.00, "Edgy"
    elif vix < 30:
        return 0.90, "Choppy"
    else:
        return 0.80, "Danger"


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
                           h_trend: float | None,
                           ma20_regime: str | None,
                           pivot_dir: str | None = None,
                           ma20_tp: float | None = None,
                           std20_tp: float | None = None) -> tuple:
    """
    BB framework for Trade timeframe (v1.7 spec §2.7).

    Center: MA20 of typical price (H+L+C)/3 when available; falls back to
    MA20(close) during warmup while OHLC history accumulates.
    Width:  STD20 of typical price when available; falls back to STD20(close).

    Typical-price center dampens band movement asymmetrically:
      - Close-on-lows day (selloff):  TP > close → MA20_TP resists slicing down
      - Close-on-highs day (recovery): TP < close → MA20_TP stays low while price rises

    The ma20_regime check (above/below MA20) still uses close vs MA20(close) —
    it is a structural assessment, not a band calculation detail.

    Two k coefficients, named by function:
      k_wide  = 2.0                       # standard BB (2σ) — target side, never flips
      k_tight = max(0, H_trend - 0.5)    # entry side — tight near MA20 (0 when H < 0.5)

    Structural uptrend (ABC pivot = uptrend):
      HRR = center + k_wide  × vol       # target above — always BB upper
      LRR = center - k_tight × vol       # normal (above MA20): tight floor ≈ center
      LRR = center - k_wide  × vol       # counter-trend (below MA20): wide floor = BB lower

    Structural downtrend (mirror):
      LRR = center - k_wide  × vol       # target below — always BB lower
      HRR = center + k_tight × vol       # normal (below MA20): tight ceiling ≈ center
      HRR = center + k_wide  × vol       # counter-trend (above MA20): wide ceiling = BB upper

    Returns (None, None) if any required input is missing.
    """
    # Use typical-price metrics when available; fall back to close-based
    center = ma20_tp  if ma20_tp  is not None else ma20
    vol    = std20_tp if std20_tp is not None else std20

    if center is None or vol is None or h_trend is None:
        return None, None
    if vol <= 0:
        return None, None

    k_wide  = 2.0
    k_tight = max(0.0, h_trend - 0.5)
    above   = (ma20_regime or "uptrend") == "uptrend"   # close vs MA20(close) — unchanged

    if pivot_dir == "downtrend":
        # LRR is always the wide target; HRR switches tight/wide by regime
        lrr = round(center - k_wide  * vol, 4)
        hrr = round(center + (k_tight if not above else k_wide) * vol, 4)
    else:
        # uptrend or unknown: HRR is always the wide target; LRR switches tight/wide by regime
        hrr = round(center + k_wide  * vol, 4)
        lrr = round(center - (k_tight if above else k_wide) * vol, 4)

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


# ── Conviction Score (v1.7 spec §2.9) ────────────────────────────────────────

def compute_conviction(h_trend: float | None,
                       vol_signal: str, close: float,
                       trade_lrr: float | None, trade_hrr: float | None,
                       trade_dir: str,
                       db=None) -> tuple:
    """
    Conviction formula (H_trend only — single reliable H source):
      base             = H_trend × 100
      prox_boost       = 0.70 + 0.30 × prox   (direction-aware proximity)
      conviction_raw   = base × prox_boost
      conviction_obv   = conviction_raw × obv_multiplier   (1.15 / 1.00 / 0.80)
      conviction_final = conviction_obv × vix_mult          (1.10 / 1.00 / 0.90 / 0.80)
                       = min(conviction_final, 100.0)

    Returns (conviction_final: float | None, vix_zone: str).
    CRITICAL: caller must blank conviction when Viewpoint = Neutral.
    """
    if h_trend is None:
        return None, "Unknown"

    base = h_trend * 100.0

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
    conviction_obv = conviction_raw * _volume_multiplier(vol_signal)

    # Task 6.2b — VIX regime multiplier applied last
    vix_mult, vix_zone = get_vix_regime_multiplier(db) if db is not None else (1.00, "Unknown")
    conviction_final = conviction_obv * vix_mult
    conviction_final = min(max(conviction_final, 0.0), 100.0)

    return round(conviction_final, 2), vix_zone


# ── Main entry point ──────────────────────────────────────────────────────────

def compute_output(ticker: str, db, prior_ranges: dict = None,
                   asset_class: str = "") -> dict:
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
    # Typical-price metrics — better BB center (resists selloff slicing, stays low on recovery)
    ma20_tp     = float(cache_row.ma20_tp)     if (cache_row and getattr(cache_row, 'ma20_tp',  None) is not None) else None
    std20_tp    = float(cache_row.std20_tp)    if (cache_row and getattr(cache_row, 'std20_tp', None) is not None) else None

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
            lrr, hrr = compute_trade_lrr_hrr(ma20, std20, h_trend, ma20_regime, pivot_dir,
                                             ma20_tp=ma20_tp, std20_tp=std20_tp)

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

    # ── VIX regime — always fetched regardless of viewpoint ─────────────────
    _, vix_zone = get_vix_regime_multiplier(db) if db is not None else (1.00, "Unknown")

    # Task 6.3 — effective H: directionally-appropriate for Commodities/FX
    h_eff = get_effective_h_trend(
        asset_class, ticker, viewpoint,
        h_trend, h_trend_up, h_trend_down,
    )

    # ── Conviction — BLANK when Viewpoint = Neutral ──────────────────────────
    conviction = None
    if viewpoint != "Neutral":
        trade_lrr = timeframe_results["trade"]["lrr"]
        trade_hrr = timeframe_results["trade"]["hrr"]
        conviction, _ = compute_conviction(
            h_eff, vol_signal,
            price, trade_lrr, trade_hrr, trade_dir,
            db=db,
        )

    # ── Alert flag ⚡ ────────────────────────────────────────────────────────
    alert = bool(
        h_eff is not None and h_eff > 0.55 and
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
        "vix_regime":     vix_zone,
        "vol_signal":     vol_signal,
        "obv_direction":  obv_dir,
        "obv_confirming": obv_confirming,
        "alert":          alert,
        "trade":          timeframe_results["trade"],
        "trend":          timeframe_results["trend"],
        "lt":             timeframe_results["lt"],
    }
