# Signal Matrix — Conviction Engine v2.0 Spec

*Locked May 2026. Supersedes all prior conviction engine specs.*

---

## Pre-Implementation Status

Three changes were implemented ahead of this spec (current session):

| Change | File | Commit |
|---|---|---|
| `_obv_direction` → 40-bar linear regression | `conviction_engine.py` | `5447f07` |
| `obv_confirming` → strict check (direction + slope) | `conviction_engine.py` | `5447f07` |
| `hrr_warn` reference → D when d_extended (bug fix) | `conviction_engine.py` | `90bfca7` |

Remaining work: replace multiplier chain with additive formula (this spec).

---

## Summary of Changes from v1.9

| Element | v1.9 | v2.0 |
|---|---|---|
| Formula architecture | Sequential multiplier chain | Additive — four independent components summed |
| Proximity | Modulates base score (35–50 range) | **Removed** from conviction — alert/intraday system only |
| Conviction gate | Blank when Viewpoint = Neutral | Always calculates; display when >= 45 |
| Structural scoring | Implicit pass/fail gate | Explicit: +25 Trade, +25 Trend |
| OBV direction | ABCD pivot engine | 40-bar linear regression on OBV series ✅ done |
| Volume scoring | Multiplier (×1.20 / ×1.00 / ×0.85) | Additive (0–15 pts) |
| VIX scoring | Multiplier (×0.80–×1.10) | Additive (0–15 pts) |
| Quad scoring | Multiplier (×0.80–×1.25) | Additive (+20 / 0 / −15) |
| Alert threshold | >= 65 | **>= 80** |
| Display threshold | Any non-None value | **>= 45** (blank below) |
| Neutral viewpoint display | Blank | Grey (`#8899aa`) when >= 45 |
| hrr_warn conviction impact | None | ×0.92 dampener ✅ done (reference fixed) |

---

## Formula Architecture

Four independent components. Each produces a score. Scores sum to `conviction_final`.

```
conviction_final = structural_score
                 + quad_score
                 + volume_score
                 + vix_score
```

| Component | Max | Min | Notes |
|---|---|---|---|
| Structural | +50 | 0 | Trade +25, Trend +25 |
| Quad | +20 | −15 | Prob-weighted; can go negative |
| Volume | +15 | 0 | No penalty for misaligned |
| Vol/VIX | +15 | 0 | Domestic Equities only; others get +15 |
| **Total** | **100** | — | Floored at 0, capped at 100 |

---

## Component 1 — Structural (max 50 pts)

Measures price structure across timeframes. What price *does* over time, not where it sits in the range. Proximity removed entirely — proximity belongs to the alert system (PROXIMITY alert in intraday monitor).

### Scoring

```python
if trade_dir == trend_dir and trade_dir != "Neutral":
    structural_score = 50   # both Bullish or both Bearish — full alignment
elif trade_dir != "Neutral" and trend_dir == "Neutral":
    structural_score = 25   # trade only
elif trade_dir == "Neutral" and trend_dir != "Neutral":
    structural_score = 25   # trend only (unusual but valid)
else:
    structural_score = 0    # both Neutral, OR opposing directions
```

| Trade Dir | Trend Dir | structural_score | Notes |
|---|---|---|---|
| Bullish | Bullish | 50 | Full alignment |
| Bearish | Bearish | 50 | Full alignment |
| Bullish | Neutral | 25 | Trade only |
| Bearish | Neutral | 25 | Trade only |
| Neutral | Bullish | 25 | Trend only |
| Neutral | Bearish | 25 | Trend only |
| Bullish | Bearish | 0 | Opposing = conflicted structure |
| Neutral | Neutral | 0 | No structure |

**Opposing directions (Trade=Bullish, Trend=Bearish):** both timeframes have form but they disagree. Conflicted structure produces no conviction — score 0, same as both Neutral.

**BREAK_OF_TRADE:** direction HOLDS (Bullish/Bearish) until BREAK_CONFIRMED. Structural score does not degrade during a provisional break. BREAK_CONFIRMED → trade_dir = Neutral → trade contribution = 0.

### Proximity — REMOVED

```python
# CONVICTION_V2_CLEANUP — remove after 30 days from implementation
# base = 50.0
# prox = 1 - (close - lrr) / (hrr - lrr)   # Bullish
# prox = (close - lrr) / (hrr - lrr)        # Bearish
# conviction_raw = base × (0.70 + 0.30 × prox)   → range 35–50
```

### hrr_warn Dampener

When the target-side warn flag fires, momentum is fading. Apply ×0.92 to `conviction_sum` **after** floor, **before** cap.

```python
# Uptrend:   hrr_warn = HRR < D (d_extended) or HRR < B (normal) → ×0.92
# Downtrend: lrr_warn = LRR > D (d_extended) or LRR > B (normal) → ×0.92
#
# lrr_warn (uptrend)  = proximity-to-break — display only, NO conviction impact
# hrr_warn (downtrend) = proximity-to-break — display only, NO conviction impact
```

---

## Component 2 — Quad (+20 / 0 / −15)

Macro environmental regime. Is the fundamental backdrop a tailwind, headwind, or neutral?

### Scoring

```python
# alignment = get_quad_alignment(asset_class, sector, current_quad)
# +1.0 = Aligned, 0.0 = Neutral, -1.0 = Misaligned
# prob = current quad probability (from quad_settings)

if viewpoint == "Neutral" or alignment == 0.0:
    quad_score = 0
elif alignment > 0:                        # Aligned
    quad_score = 20 if prob >= 0.45 else 15
else:                                      # Misaligned
    quad_score = -15 if prob >= 0.45 else -11
```

| Condition | quad_score |
|---|---|
| Aligned, prob >= 0.45 | +20 |
| Aligned, prob < 0.45 | +15 |
| Neutral (any prob) | 0 |
| Misaligned, prob < 0.45 | −11 |
| Misaligned, prob >= 0.45 | −15 |

**Probability threshold:** 0.45. In a 4-quad world, random = 0.25. Above 0.45 = genuine directional read. Below = partial lean (×0.75 weight on base score). Note: −15 × 0.75 = −11.25 → rounds to −11.

**Viewpoint gate:** when Viewpoint = Neutral, quad_score = 0. A macro tailwind with no structural direction is not conviction.

### Unchanged from v1.9

- `get_quad_alignment()` and `QUAD_ALIGNMENT` dict — unchanged
- Sector-first priority, `ALWAYS_NEUTRAL_SECTORS = {"Index"}`
- `quad_settings` table, month transition at midnight ET on the 1st
- `quad_alignment` and `quad_mult` columns in `signal_output` still written (informational/debug)

### v1.9 Multiplier — REPLACED

```python
# CONVICTION_V2_CLEANUP — remove after 30 days
# magnitude = abs(alignment) * current_prob * 0.25
# mult = max(0.50, round(1.00 + (direction * magnitude), 4))
# conviction_quad = conviction_vix × quad_mult
```

---

## Component 3 — Volume (max 15 pts)

Measures OBV trend direction, momentum, and acceleration.

### obv_direction — Rolling Z-Score Oscillator → 40-bar Regression ✅ Implemented (ADR-017)

```python
# 1. Build OBV from closes/volumes.
# 2. Rolling 20-bar z-score (_OBV_ZSCORE_WINDOW): each bar normalized by its OWN
#    trailing 20-bar mean/std → stationary oscillator (no inversion on vol shocks).
# 3. 40-bar linear-regression slope (_OBV_REGRESSION_WINDOW) on the z-score series.
# Sign-only (_OBV_NEUTRAL_BAND = 0.0):
#   slope > 0 → 'Bullish'   slope < 0 → 'Bearish'   slope == 0 → 'Neutral'
# Requires >= 59 OBV bars (20 + 40 - 1) else 'Neutral'.
```

Band `_OBV_NEUTRAL_BAND = 0.0` — sign-only, maximally responsive (no dead zone). Replaced
the single-window slope÷std (ADR-005, band 0.02) for responsiveness — the rolling z-score
turns ~3 trading days earlier on a volume shock. Tradeoff: `obv_direction` almost never reads
'Neutral' (only volumeless indices like VIX), so Confirming/Diverging vol_signals are more
frequent. See **ADR-017**.

### Downstream — Unchanged

```
obv_slope       ← 3-bar ROC on OBV MA20: rising / flat / falling
obv_confirming  ← obv_direction AND obv_slope both confirm Trade Dir  ✅ strict check done
vol_signal      ← Confirming / Diverging / Neutral (compared vs Trade Dir)
obv_slope_trend ← acceleration: increasing / decreasing / flat
```

### Scoring

```python
volume_score = 0
if obv_confirming:                                    # +10: direction + momentum both confirm
    volume_score += 10
    if ((trade_dir == "Bullish" and obv_slope_trend == "increasing") or
        (trade_dir == "Bearish" and obv_slope_trend == "decreasing")):
        volume_score += 5                             # +5 boost: acceleration = early in move
# OBV misaligned or neutral → 0 (no penalty)
```

| Condition | volume_score |
|---|---|
| OBV confirming + slope accelerating | +15 |
| OBV confirming, no acceleration | +10 |
| OBV neutral or misaligned | 0 |

**Note:** misaligned OBV applies no penalty in v2.0. Diverging volume is a caution signal (shown in popup as Vol Signal) but does not reduce conviction numerically.

### v1.9 Multipliers — REPLACED

```python
# CONVICTION_V2_CLEANUP — remove after 30 days
# alignment_mult: ×1.20 (aligned) / ×0.85 (misaligned) / ×1.00 (neutral)
# slope_boost:    ×1.20 (accelerating) / ×1.00
# conviction_vol   = conviction_raw × alignment_mult
# conviction_slope = conviction_vol × slope_boost
```

---

## Component 4 — Vol/VIX (max 15 pts)

Current VIX level regime. Is the market environment investable for systematic buyers?

### Scoring

```python
def get_vix_score(vix_close, asset_class):
    if asset_class != "Domestic Equities":
        return 15   # non-equity: no VIX penalty, full credit
    if vix_close is None:
        return 15   # missing VIX row: default to full credit (no crash)
    if vix_close < 19:  return 15   # Investable
    if vix_close < 24:  return 10   # Edgy
    if vix_close < 30:  return  5   # Choppy
    return 0                        # Danger (VIX >= 30)
```

| VIX Level | Regime | vix_score |
|---|---|---|
| < 19 | Investable | +15 |
| 19–23 | Edgy | +10 |
| 24–29 | Choppy | +5 |
| >= 30 | Danger | 0 |

**Asset class gate unchanged:** Domestic Equities only. All other asset classes receive +15 (no penalty, no boost). International Equities, Fixed Income, FX, Commodities, Digital Assets all get +15.

**VIX source unchanged:** `price_cache` where `ticker = 'VIX'`.

### Future Enhancements — Flagged, Not Implemented

- **VVIX rank:** `vvix_rank` in `price_cache` exists. When VVIX rank compresses (tail risk falling), could add +2 to vix_score for Investable regime.
- **HV30/HV90 regime:** vol control fund re-leveraging signal. When HV30 peaked and falling but still > HV90 = aggressive re-leveraging wave. Deferred.

### v1.9 Multiplier — REPLACED

```python
# CONVICTION_V2_CLEANUP — remove after 30 days
# vix_mult: ×1.10 (Investable) / ×1.00 (Edgy) / ×0.90 (Choppy) / ×0.80 (Danger)
# conviction_vix = conviction_slope × vix_mult
```

---

## Final Assembly

```python
# 1. Sum all four components
conviction_sum = structural_score + quad_score + volume_score + vix_score

# 2. Floor at 0 (quad misalignment can push negative)
conviction_sum = max(0.0, conviction_sum)

# 3. Apply momentum-fading dampener (after floor, before cap)
#    Target-side warn = "BB target can't reach the structural reference"
#    Uptrend:   hrr_warn fires → HRR < D (d_extended) or HRR < B (normal)
#    Downtrend: lrr_warn fires → LRR > D (d_extended) or LRR > B (normal)
trade_result   = timeframe_results["trade"]
trade_hrr_warn = trade_result["hrr_warn"]
trade_lrr_warn = trade_result["lrr_warn"]
trade_dir_local = trade_result["direction"]

if ((trade_dir_local == "Bullish" and trade_hrr_warn) or
    (trade_dir_local == "Bearish" and trade_lrr_warn)):
    conviction_sum = conviction_sum * 0.92

# 4. Cap at 100
conviction_final = min(conviction_sum, 100.0)
```

**Order matters:** floor → dampener → cap. Quad negatives are absorbed by floor before dampener fires.

---

## Display and Alert Rules

```python
# Conviction always calculates regardless of Viewpoint
conviction = round(conviction_final, 2) if conviction_final >= 45.0 else None

# Alert — still requires non-Neutral viewpoint
alert = (viewpoint != "Neutral" and
         conviction is not None and
         conviction >= 80.0)
```

| Scenario | conviction value | Display | Color |
|---|---|---|---|
| Viewpoint Bullish/Bearish, score >= 45 | Calculated | Shown | Green/Red per viewpoint |
| Viewpoint Neutral, score >= 45 | Calculated | Shown | Grey `#8899aa` |
| Any viewpoint, score < 45 | None | Blank | — |
| Viewpoint Neutral, any score | Never alerts | — | — |

**Why 45 as display threshold:** structural max = 50. A score below 45 means structural is partial (one timeframe only) AND at least one other component is unfavorable. Not worth surfacing.

**Why 80 as alert threshold:** full structural (50) + quad aligned (20) + partial VIX (10) = 80. Alert now requires genuinely favorable conditions across multiple components, not just proximity.

---

## Reference Sanity Check — IWM

State as of implementation: Close 277.73, Viewpoint Bullish, VIX Investable, Quad Aligned ~67% prob, OBV confirming + accelerating.

| Component | Score | Notes |
|---|---|---|
| Structural: Trade Bullish + Trend Bullish | +50 | Full alignment |
| Quad: Aligned, prob 0.67 >= 0.45 | +20 | Full weight |
| Volume: OBV confirming + slope accelerating | +15 | Both confirming + boost |
| VIX: Investable (< 19) | +15 | Full credit |
| **Sum** | **100** | No hrr_warn → no dampener |
| **conviction_final** | **100** | Capped at 100 |

v1.9 score was 64.63 — suppressed by proximity (price mid-range). v2.0: structural, macro, volume, and volatility are all genuinely favorable → 100 is correct.

---

## Build Sequence

| Step | Status | Description |
|---|---|---|
| 1 | ✅ `90bfca7` | hrr_warn → D reference when d_extended |
| 2 | ✅ `5447f07` | OBV direction → 40-bar regression; obv_confirming → strict check |
| 3 | ✅ This doc | Write spec |
| 4 | ⬜ | Implement additive formula in `conviction_engine.py` |
| 5 | ⬜ | Validate outputs (IWM, TLT, VIX ticker, Neutral viewpoint ticker) |
| 6 | ⬜ | Update CLAUDE.md |

---

## Proactive Flags

- **`compute_conviction()` function:** currently called once internally inside `compute_output()`. After the rewrite, OBV signals (obv_slope, obv_slope_trend) are the only values needed from that function — either simplify it to return OBV signals only, or inline entirely.
- **Neutral viewpoint UI:** frontend currently blanks all Neutral tickers. After this change, some Neutral tickers will show a score in grey. Confirm `App.js` handles this — conviction cell should render `#8899aa` when `row.viewpoint === "Neutral"` but conviction is non-null.
- **`quad_mult` column:** still written for popup/debug display. Its value is now informational only — not used in formula. Document this in popup tooltip.
- **`vix_regime` column:** still written for popup display. Same 4 labels (Investable/Edgy/Choppy/Danger). Unchanged.
- **`CONVICTION_V2_CLEANUP` tags:** mark all commented-out multiplier code. Scheduled removal ~30 days after implementation date.

---

*Signal Matrix Conviction Engine v2.0 | Spec locked May 2026*
