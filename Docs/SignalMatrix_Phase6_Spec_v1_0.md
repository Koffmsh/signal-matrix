# Signal Matrix — Phase 6 Enhancement Spec
**Version 1.0 | April 2026 | Confidential**

---

## Overview

Four additive enhancements to the Signal Matrix conviction engine and signal pipeline. No existing methodology is removed. Each task is independently buildable and testable. Git commit after each confirmed working state.

**Files touched:** `conviction_engine.py`, `signal_engine.py`, `signals.py`, `market_data.py`, `App.js`, Alembic migrations, `signal_output` model, `signal_hurst` model, `price_cache` model.

**Build sequence:** Task 6.1 → commit → Task 6.2a → Task 6.2b → commit → Task 6.3 → commit

---

## Task 6.1 — Delta-H Trade Warning Signal

### What
Add `h_trade_delta` — the change in H_trade over the trailing ~20 trading days. Surfaces in the popup as an early warning that Trade timeframe trend persistence is deteriorating **before** C is broken. H_trade remains out of the conviction formula — this is display and warning only.

### Color logic
- **Green** — delta ≥ 0 (H improving, trend strengthening)
- **Amber** — delta < 0 but > −0.05 (mild deterioration)
- **Red** — delta ≤ −0.05 (sharp deterioration — structural alert)

The −0.05 threshold is a starting point. Tune after observing live values across the universe.

### Backend — `signal_engine.py`

```python
def compute_h_trade_delta(db, ticker: str, current_h_trade: float) -> float | None:
    """
    Returns current_h_trade minus h_value from the trade-timeframe snapshot ~20 trading days ago.
    Positive = H improving (trend strengthening).
    Negative = H deteriorating (trend weakening — early warning).
    Returns None if insufficient history.
    """
    from datetime import datetime, timedelta
    from zoneinfo import ZoneInfo
    _ET = ZoneInfo("America/New_York")
    cutoff = (datetime.now(_ET) - timedelta(days=28)).strftime("%Y-%m-%d")  # ~20 trading days

    row = db.query(SignalHistory)\
        .filter(SignalHistory.ticker == ticker,
                SignalHistory.timeframe == "trade",
                SignalHistory.snapshot_date >= cutoff)\
        .order_by(SignalHistory.snapshot_date.asc())\
        .first()

    if row is None or row.h_value is None:
        return None
    return round(current_h_trade - row.h_value, 4)
```

### DB — `signal_output` model
Add column: `h_trade_delta FLOAT NULL`

### Alembic migration
```sql
ALTER TABLE signal_output ADD COLUMN h_trade_delta FLOAT;
```

### `signals.py` — wire into `run_output()`
```python
h_trade_delta = compute_h_trade_delta(db, ticker, h_trade)
output.h_trade_delta = h_trade_delta
```

### API
Include `h_trade_delta` in the trade timeframe object returned by `/api/signals/stored`.

### Frontend — popup (`App.js`)
Add below `Hurst (T)` in the popup:

```jsx
{tradeSignal.h_trade_delta !== null && tradeSignal.h_trade_delta !== undefined && (
  <div className="popup-row">
    <span className="popup-label">ΔH (20d)</span>
    <span style={{
      color: tradeSignal.h_trade_delta >= 0 ? '#00e5a0'
           : tradeSignal.h_trade_delta < -0.05 ? '#ff4d6d'
           : '#f0b429'
    }}>
      {tradeSignal.h_trade_delta >= 0 ? '+' : ''}
      {tradeSignal.h_trade_delta.toFixed(3)}
    </span>
  </div>
)}
```

### Test checklist
- Open popup on GLD and SPY — confirm ΔH displays
- Confirm color changes sign correctly (positive = green, negative = amber or red)
- Confirm NULL renders as `—` gracefully when signal_history has < 20 trading days of snapshots

> **Note for Neo:** `h_trade_delta` will return NULL for most tickers initially if signal_history is young. This is expected — it populates naturally over ~20 trading days. No special handling needed.

---

## Task 6.2 — Realized Vol of VIX (VoV) + VIX Regime Conviction Multiplier

Two sub-tasks delivered together — they share the VIX price history already in `price_cache`.

---

### Task 6.2a — Compute Realized VoV

**What:** 30-day realized volatility of VIX log returns, annualized. Computed on every price refresh, stored on the VIX row in `price_cache`. Displayed in the popup as `VIX VoV (30d)`.

> **Method rationale:** Realized VoV from existing VIX price history is computable today with zero new data feeds and is what McCullough tracks when monitoring whether VIX's range is "narrowing" or "widening." VVIX (CBOE's implied vol of VIX options) is displayed as a secondary popup field if/when added as a ticker — it is not required for this task.

#### DB — `price_cache` model
Add column: `vov_30d FLOAT NULL` — populated on the VIX row only.

#### Alembic migration
```sql
ALTER TABLE price_cache ADD COLUMN vov_30d FLOAT;
```

#### `market_data.py` — inside `refresh_data()`, after VIX prices fetched

```python
def compute_vov(vix_history_json: str) -> float | None:
    """
    30-day realized vol of VIX log returns, annualized.
    Returns None if fewer than 31 bars available.
    """
    import numpy as np, json
    prices = json.loads(vix_history_json)  # list of closing prices, newest last
    if len(prices) < 31:
        return None
    recent = prices[-31:]
    log_returns = np.diff(np.log(recent))
    return float(np.std(log_returns, ddof=0) * np.sqrt(252))

# After VIX upsert:
vix_row = db.query(PriceCache).filter(PriceCache.ticker == "VIX").first()
if vix_row and vix_row.history_json:
    vix_row.vov_30d = compute_vov(vix_row.history_json)
```

> **VoV percentile rank:** Deferred to Phase 6.5 — needs 252 days of VoV values to accumulate in signal_history before a reliable percentile rank is meaningful. Display raw VoV for now.

---

### Task 6.2b — VIX Regime Conviction Multiplier

**What:** Apply a macro regime multiplier to the final conviction score based on current VIX level. Applied **after** the OBV multiplier as the last step in the conviction chain.

#### VIX Regime Multiplier Table (locked)

| Zone | VIX Range | Multiplier | Rationale |
|---|---|---|---|
| Investable | < 20 | × 1.10 | VCFs mechanically adding, trend signals reliable |
| Edgy | 20–23 | × 1.00 | Elevated but tradeable — neutral effect |
| Choppy | 24–29 | × 0.90 | Signal degradation, whipsaws likely — reduce size |
| Danger | ≥ 30 | × 0.80 | Sit on hands — structural breakdown, conviction dampened |

**Note on Danger bucket:** VIX ≥ 30 is explicitly sit-on-hands territory. The 0.80 multiplier dampens conviction but does not kill the signal — a genuinely high-conviction trade (e.g. INTC with all three timeframes aligned and OBV confirming) will still surface at an actionable level. The structural signals do the heavy lifting; the multiplier communicates regime, not a veto.

#### `conviction_engine.py` — helper function

```python
def get_vix_regime_multiplier(db) -> tuple[float, str]:
    """
    Returns (multiplier, zone_label) based on current VIX close.
    Falls back to 1.00 / 'Unknown' if VIX not in cache.
    """
    vix_row = db.query(PriceCache).filter(PriceCache.ticker == "VIX").first()
    if vix_row is None or vix_row.close is None:
        return 1.00, "Unknown"
    vix = vix_row.close
    if vix < 20:
        return 1.10, "Investable"
    elif vix < 24:
        return 1.00, "Edgy"
    elif vix < 30:
        return 0.90, "Choppy"
    else:
        return 0.80, "Danger"
```

#### Updated conviction formula

```python
# Existing chain (unchanged)
base = h_trend * 100
conviction_raw = base * (0.70 + 0.30 * prox)
conviction_obv = conviction_raw * obv_multiplier      # 1.15 / 1.00 / 0.80

# NEW — VIX regime multiplier applied last
vix_mult, vix_zone = get_vix_regime_multiplier(db)
conviction_final = conviction_obv * vix_mult
conviction_final = min(conviction_final, 100.0)        # hard cap at 100
```

#### Complete conviction formula (all layers)

```
base             = H_trend × 100
prox_boost       = 0.70 + 0.30 × prox                 (direction-aware proximity)
conviction_raw   = base × prox_boost
conviction_obv   = conviction_raw × obv_multiplier     (1.15 / 1.00 / 0.80)
conviction_final = conviction_obv × vix_mult           (1.10 / 1.00 / 0.90 / 0.80)
                 = min(conviction_final, 100.0)
```

#### DB — `signal_output` model
Add column: `vix_regime VARCHAR(20) NULL` — useful for debugging and future filtering.

#### Alembic migration
```sql
ALTER TABLE signal_output ADD COLUMN vix_regime VARCHAR(20);
```

#### API
Expose `vix_regime` in `/api/signals/stored` response and `vov_30d` via the batch market data endpoint (VIX row in `price_cache`).

#### Frontend — popup additions

```jsx
{/* Below Rel IV% */}
<div className="popup-row">
  <span className="popup-label">VIX Regime</span>
  <span style={{ color:
    signal.vix_regime === 'Investable' ? '#00e5a0' :
    signal.vix_regime === 'Edgy'       ? '#f0b429' :
    signal.vix_regime === 'Choppy'     ? '#f0b429' :
    signal.vix_regime === 'Danger'     ? '#ff4d6d' : '#8899aa'
  }}>
    {signal.vix_regime || '—'}
  </span>
</div>

{cacheData?.vov_30d && (
  <div className="popup-row">
    <span className="popup-label">VIX VoV (30d)</span>
    <span>{(cacheData.vov_30d * 100).toFixed(1)}%</span>
  </div>
)}
```

> **Note for Neo:** `vov_30d` comes from `price_cache` (VIX row), not `signal_output`. Confirm it is accessible in the frontend batch state before wiring. The VIX row is already fetched by the batch endpoint.

### Test checklist — Task 6.2
- After REFRESH DATA: confirm `vov_30d` populates on VIX row in DB
- Confirm conviction values shift by expected multiplier at current VIX level
- Confirm `vix_regime` stores correctly in `signal_output`
- At current VIX: manually verify `conviction_final = conviction_obv × vix_mult` matches displayed value
- Confirm hard cap: no conviction value exceeds 100

---

## Task 6.3 — Asymmetric H for Commodities and FX

### What
For Commodity and FX asset classes, compute separate H values for up-move days and down-move days over the Trend (252-day) lookback. Use the directionally-appropriate H in the conviction base score. This captures the known asymmetry in these asset classes — persistent uptrends but sharp mean-reverting selloffs (and vice versa).

### Eligible asset classes
```python
ASYMMETRIC_H_ASSET_CLASSES = {"Commodities", "Foreign Exchange"}
```

### Excluded tickers
- `/ZN` (10-Year Treasury Note future) — Fixed Income behavior, standard H applies despite futures classification
- All Domestic Equities, Domestic Fixed Income, International Equities, Digital Assets — standard H_trend

### `signal_engine.py` — asymmetric DFA function

```python
def compute_asymmetric_h(prices: list[float], window: int = 252) -> tuple[float | None, float | None]:
    """
    Compute H separately for up-move days and down-move days over the Trend lookback.
    Returns (h_up, h_down). Either may be None if fewer than 30 observations.

    h_up:   persistence on positive-return days
    h_down: persistence on negative-return days

    Used in conviction for Commodities and FX only.
    Requires at least 30 observations per direction — returns None otherwise.
    """
    import numpy as np
    log_returns = np.diff(np.log(prices[-window:]))

    up_returns   = log_returns[log_returns > 0]
    down_returns = log_returns[log_returns < 0]

    h_up   = dfa(up_returns,   min_window=10) if len(up_returns)   >= 30 else None
    h_down = dfa(down_returns, min_window=10) if len(down_returns) >= 30 else None

    return h_up, h_down
```

### DB — `signal_hurst` model
Add columns: `h_trend_up FLOAT NULL`, `h_trend_down FLOAT NULL`

### Alembic migration
```sql
ALTER TABLE signal_hurst ADD COLUMN h_trend_up FLOAT;
ALTER TABLE signal_hurst ADD COLUMN h_trend_down FLOAT;
```

### Conviction — directional H selection

```python
def get_effective_h_trend(
    asset_class: str,
    viewpoint: str,
    h_trend: float,
    h_trend_up: float | None,
    h_trend_down: float | None
) -> float:
    """
    Returns the H value to use as the conviction base score.
    Asymmetric H applied for Commodities and FX only.
    Falls back to symmetric h_trend if asymmetric values unavailable.
    """
    if asset_class not in ASYMMETRIC_H_ASSET_CLASSES:
        return h_trend
    if viewpoint == "Bullish" and h_trend_up is not None:
        return h_trend_up
    if viewpoint == "Bearish" and h_trend_down is not None:
        return h_trend_down
    return h_trend  # fallback — insufficient directional history
```

Replace `h_trend` with `get_effective_h_trend(...)` in the conviction base score calculation.

### API
Expose `h_trend_up` and `h_trend_down` in `/api/signals/stored` for eligible asset classes.

### Frontend — popup additions (Commodities and FX only)

```jsx
{isAsymmetricEligible && (
  <>
    <div className="popup-row">
      <span className="popup-label">H↑ Trend</span>
      <span>{signal.h_trend_up != null ? signal.h_trend_up.toFixed(3) : '—'}</span>
    </div>
    <div className="popup-row">
      <span className="popup-label">H↓ Trend</span>
      <span>{signal.h_trend_down != null ? signal.h_trend_down.toFixed(3) : '—'}</span>
    </div>
  </>
)}
```

Where: `isAsymmetricEligible = ['Commodities', 'Foreign Exchange'].includes(ticker.assetClass)`

### Test checklist — Task 6.3
- Confirm `h_trend_up` / `h_trend_down` populate for GLD, USO, SLV, FXE, JPY
- Confirm `/ZN` → `h_trend_up` and `h_trend_down` remain NULL (asset class = Commodities future but explicitly excluded)
- Confirm TLT, SPY, IBIT → NULL (not in eligible asset classes)
- Bullish GLD: confirm `conviction base = h_trend_up × 100` (not symmetric h_trend)
- Bearish USO: confirm `conviction base = h_trend_down × 100`
- Fallback: temporarily null out `h_trend_up` for one ticker, confirm fallback to `h_trend` gracefully

> **Note on /ZN exclusion:** `/ZN` has asset_class set to Commodities in the tickers table because it is a futures ticker. Add it to a `ASYMMETRIC_H_EXCLUDED` set alongside the asset class check:
> ```python
> ASYMMETRIC_H_EXCLUDED = {"/ZN"}
> if ticker in ASYMMETRIC_H_EXCLUDED:
>     return h_trend
> ```

---

## Summary — New DB Columns

| Table | Column | Type | Task |
|---|---|---|---|
| `signal_output` | `h_trade_delta` | `FLOAT NULL` | 6.1 |
| `price_cache` | `vov_30d` | `FLOAT NULL` | 6.2a |
| `signal_output` | `vix_regime` | `VARCHAR(20) NULL` | 6.2b |
| `signal_hurst` | `h_trend_up` | `FLOAT NULL` | 6.3 |
| `signal_hurst` | `h_trend_down` | `FLOAT NULL` | 6.3 |

---

## Summary — New Popup Fields

| Field | Location | Task | Source |
|---|---|---|---|
| `ΔH (20d)` | Below Hurst (T) | 6.1 | `signal_output.h_trade_delta` |
| `VIX Regime` | Below Rel IV% | 6.2b | `signal_output.vix_regime` |
| `VIX VoV (30d)` | Below VIX Regime | 6.2a | `price_cache.vov_30d` (VIX row) |
| `H↑ Trend` | Below Hurst (Tr) | 6.3 | `signal_hurst.h_trend_up` — eligible only |
| `H↓ Trend` | Below H↑ Trend | 6.3 | `signal_hurst.h_trend_down` — eligible only |

---

## Deferred — Phase 6.5+

- **VoV percentile rank:** Requires 252 days of accumulated VoV values. Add once history exists.
- **VVIX display:** Add `^VVIX` as a ticker via admin panel; display in popup as secondary VoV reference.
- **Delta-H threshold tuning:** −0.05 red threshold reviewed after 30 days of live signal_history.
- **Quad Tracker modifier matrix:** Separate session — 4 quads × 6 asset classes = 24 multipliers to define before build.

---

*Signal Matrix Platform — Phase 6 Spec v1.0 | SuttonMC | Confidential*
