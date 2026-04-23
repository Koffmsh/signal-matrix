# Signal Matrix — Conviction Engine v1.9 + Quad Factor
## Spec for Neo

**Read CLAUDE.md before starting. This spec supersedes all prior conviction engine specs.**
**Do not begin implementation until you have read this document in full and confirmed understanding.**

---

## Summary of Changes from v1.8

1. **VIX Regime Multiplier (Layer 4)** — re-engaged from deferred state; asset class gated
2. **Quad Multiplier (Layer 5)** — new; probability-weighted; requires new `quad_settings` table
3. **Dashboard** — Quad display in header; Asset Class + Sector removed from table, moved to popup
4. **Admin Panel** — new Quad Settings section
5. **signal_output** — two new columns: `quad_alignment`, `quad_mult`

---

## Part 1 — Conviction Formula (Complete Chain)

```
base             = 50
conviction_raw   = 50 × (0.70 + 0.30 × prox)         → 35–50
conviction_vol   = conviction_raw × obv_aligned_mult   → ×1.20 / ×1.00 / ×0.85
conviction_slope = conviction_vol × slope_boost_mult   → ×1.20 / ×1.00
conviction_vix   = conviction_slope × vix_mult         → asset class gated (see Layer 4)
conviction_quad  = conviction_vix × quad_mult          → probability weighted (see Layer 5)
conviction_final = min(conviction_quad, 100.0)
```

### Ceiling Verification
```
Best case — perfect prox, OBV fully aligned + accelerating,
            VIX Investable (Domestic Equities), Quad fully aligned at 100% probability:

50 × 1.00 × 1.20 × 1.20 × 1.10 × 1.25 = 99.0 → capped at 100 ✓

No-boost case — prox=0, all multipliers neutral:
50 × 0.70 × 1.00 × 1.00 × 1.00 × 1.00 = 35
```

### Rules (unchanged from v1.8)
- Conviction is **BLANK** when Viewpoint = Neutral
- Hard cap at **100.0**
- Alert threshold: conviction **≥ 65**
- Alert conditions: Viewpoint ≠ Neutral AND conviction ≥ 65

---

## Part 2 — Layer 1: Proximity (Price) — Unchanged

```python
# Direction-aware — peaks at 1.0 when at entry zone
Bullish: prox = 1 - (close - lrr) / (hrr - lrr)   # 1.0 at LRR
Bearish: prox = (close - lrr) / (hrr - lrr)         # 1.0 at HRR
prox = max(0.0, min(1.0, prox))                      # clamp

conviction_raw = 50 × (0.70 + 0.30 × prox)          # range: 35–50
```

---

## Part 3 — Layer 2: OBV Alignment (Volume) — Unchanged

```python
# OBV pivot direction + obv_slope both confirm viewpoint
Aligned:    OBV pivot=Bullish AND obv_slope=rising   (Bullish viewpoint) → ×1.20
            OBV pivot=Bearish AND obv_slope=falling  (Bearish viewpoint) → ×1.20
Misaligned: both oppose viewpoint                                         → ×0.85
Neutral:    anything else                                                 → ×1.00

conviction_vol = conviction_raw × obv_aligned_mult
```

---

## Part 4 — Layer 3: Slope Boost (Volume Acceleration) — Unchanged

```python
# Only fires when Layer 2 = Aligned
Bullish + aligned + obv_slope_trend=increasing → ×1.20
Bearish + aligned + obv_slope_trend=decreasing → ×1.20
Otherwise                                       → ×1.00

conviction_slope = conviction_vol × slope_boost_mult
```

---

## Part 5 — Layer 4: VIX Regime Multiplier — RE-ENGAGE (was deferred in v1.8)

### Asset Class Gate — CRITICAL
VIX only applies to US equity instruments. All other asset classes use ×1.00.

```python
VIX_REGIME_ASSET_CLASSES = {
    "Domestic Equities",
}

def get_vix_mult(vix_close: float, asset_class: str) -> tuple[float, str]:
    """Returns (multiplier, regime_label)"""
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

conviction_vix = conviction_slope × vix_mult
```

### VIX Value Source
Read `vix_close` from `price_cache` where `ticker = 'VIX'`. Same pattern as existing `get_vix_regime_multiplier()` — replace/update that function with the asset class gate added.

### What Changes from v1.8
- Function existed but was not called in the conviction chain
- Re-wire it into `compute_output()` as Layer 4
- Add `asset_class` parameter with the gate above
- `vix_regime` column in `signal_output` already exists — continue writing it

---

## Part 6 — Layer 5: Quad Multiplier — NEW

### Multiplier Formula

```python
def get_quad_multiplier(
    viewpoint: str,
    asset_class: str,
    sector: str,
    current_quad: int,
    current_prob: float,    # stored as 0.0–1.0 (e.g. 0.58 for 58%)
) -> tuple[float, str]:
    """Returns (multiplier, label)"""

    if viewpoint == "Neutral" or current_quad is None:
        return 1.00, "Neutral"

    alignment = get_quad_alignment(asset_class, sector, current_quad)

    if alignment == 0.0:
        return 1.00, "Neutral"

    # Viewpoint/Quad aligned = boost; misaligned = dampen
    bullish_best  = (viewpoint == "Bullish" and alignment > 0)
    bearish_worst = (viewpoint == "Bearish" and alignment < 0)
    aligned = bullish_best or bearish_worst

    direction = 1.0 if aligned else -1.0
    magnitude = abs(alignment) * current_prob * 0.25
    mult = max(0.50, round(1.00 + (direction * magnitude), 4))

    label = "Aligned" if aligned else "Misaligned"
    return mult, label


def viewpoint_matches_alignment(viewpoint: str, alignment_score: float) -> bool:
    # Bullish + Best  = aligned (wind at back)
    # Bearish + Worst = aligned (wind at back)
    # Bullish + Worst = misaligned (fighting macro)
    # Bearish + Best  = misaligned (fighting macro)
    if viewpoint == "Bullish" and alignment_score > 0:
        return True
    if viewpoint == "Bearish" and alignment_score < 0:
        return True
    return False
```

### Multiplier Examples at Various Probabilities
```
Best alignment + 100% prob  → 1.00 + (0.25 × 1.00 × 1.0)  = ×1.25  (ceiling)
Best alignment + 80% prob   → 1.00 + (0.25 × 0.80 × 1.0)  = ×1.20
Best alignment + 58% prob   → 1.00 + (0.25 × 0.58 × 1.0)  = ×1.145
Neutral (not listed)        → ×1.00
Worst alignment + 80% prob  → 1.00 + (0.25 × 0.80 × -1.0) = ×0.80  (dampen)
Worst alignment + 58% prob  → 1.00 + (0.25 × 0.58 × -1.0) = ×0.855
Floor (never below)         → ×0.50
```

---

## Part 7 — Quad Alignment Lookup

```python
ALWAYS_NEUTRAL_SECTORS = {"Index"}    # VIX, VVIX only — always ×1.00


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

    q = QUAD_ALIGNMENT[quad]

    if sector in q["best"]["sector"]:
        return 1.0
    if sector in q["worst"]["sector"]:
        return -1.0
    if asset_class in q["best"]["asset_class"]:
        return 1.0
    if asset_class in q["worst"]["asset_class"]:
        return -1.0

    return 0.0
```

---

## Part 8 — QUAD_ALIGNMENT Dict

Add to `conviction_engine.py`. Uses Signal Matrix `asset_class` and `sector` field values exactly as stored in the `tickers` table.

```python
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
                # Equity sectors
                "Technology", "Consumer Discretionary",
                "Communication Services", "Industrials",
                "Materials", "Real Estate", "Financials",
                "Equities", "Small Caps",
                # Style factors
                "High Beta", "Momentum", "Secular Growth",
                "Mid Caps", "Leverage", "Cyclical Growth",
                # Fixed Income / Credit
                "High Yield", "Convertibles", "EM Credit",
                "Leveraged Loans", "BDCs",
            ],
        },
        "worst": {
            "asset_class": [
                "Domestic Fixed Income",
                "USD",
            ],
            "sector": [
                # Equity sectors
                "Utilities", "Consumer Staples", "Health Care",
                # Style factors
                "Low Beta", "Defensives", "Value", "Dividend Yield",
                # Fixed Income
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
                # Equity sectors
                "Technology", "Industrials", "Financials",
                "Energy", "Consumer Discretionary",
                "Equities", "Small Caps",
                # Style factors
                "Secular Growth", "High Beta", "Cyclical Growth", "Momentum",
                # Fixed Income / Credit
                "Convertibles", "BDCs", "Preferreds",
                "Leveraged Loans", "High Yield",
            ],
        },
        "worst": {
            "asset_class": [
                "Domestic Fixed Income",
                "USD",
            ],
            "sector": [
                # Equity sectors
                "Utilities", "Communication Services",
                "Consumer Staples", "Real Estate", "Health Care",
                # Style factors
                "Low Beta", "Dividend Yield", "Value", "Defensives",
                # Fixed Income
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
                # Gold — separate category
                "Gold",
                # Equity sectors
                "Utilities", "Energy", "Real Estate",
                "Technology", "Consumer Staples", "Health Care",
                # Style factors
                "Secular Growth", "Momentum", "Mid Caps",
                "Low Beta", "Quality",
                # Fixed Income
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
                # Equity sectors
                "Communication Services", "Financials",
                "Consumer Discretionary", "Industrials", "Materials",
                "Equities", "Small Caps",
                # Style factors
                "Dividend Yield", "Value", "Defensives",
                # Fixed Income / Credit
                "BDCs", "Preferreds", "Convertibles",
                "High Yield", "Leveraged Loans",
            ],
        },
    },

    4: {  # Deflation — growth ↓, inflation ↓
        "best": {
            "asset_class": [
                "Domestic Fixed Income",
                "USD",
            ],
            "sector": [
                # Gold — separate category
                "Gold",
                # Equity sectors
                "Consumer Staples", "Health Care", "Utilities",
                # Style factors
                "Low Beta", "Dividend Yield", "Quality",
                "Defensives", "Value",
                # Fixed Income
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
                # Equity sectors
                "Energy", "Technology", "Financials",
                "Industrials", "Consumer Discretionary",
                "Equities", "Small Caps",
                # Style factors
                "High Beta", "Momentum", "Leverage",
                "Secular Growth", "Cyclical Growth",
                # Fixed Income / Credit
                "Preferreds", "EM Local Currency",
                "BDCs", "Leveraged Loans", "TIPS",
            ],
        },
    },
}
```

---

## Part 9 — Database: `quad_settings` Table

### Alembic Migration — New Table

```python
# Migration description: "add quad_settings table"

def upgrade():
    op.create_table(
        'quad_settings',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('current_quad', sa.Integer(), nullable=False),
        sa.Column('current_prob', sa.Float(), nullable=False),   # 0.0–1.0
        sa.Column('next_quad', sa.Integer(), nullable=True),
        sa.Column('next_prob', sa.Float(), nullable=True),       # 0.0–1.0
        sa.Column('effective_date', sa.String(), nullable=False), # YYYY-MM-DD ET
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.String(), nullable=False),    # UTC timestamp
        sa.PrimaryKeyConstraint('id')
    )

def downgrade():
    op.drop_table('quad_settings')
```

### Rules
- **Never update rows** — append only (preserves regime change audit trail)
- **Always read most recent `effective_date`** — that is the active Quad
- Insert a seed row on first deploy (Quad = 3, prob = 0.58, effective_date = today)

### SQLAlchemy Model — `backend/models/quad_settings.py`

```python
from sqlalchemy import Column, Integer, Float, String, Text
from database import Base

class QuadSettings(Base):
    __tablename__ = "quad_settings"

    id             = Column(Integer, primary_key=True, index=True)
    current_quad   = Column(Integer, nullable=False)
    current_prob   = Column(Float, nullable=False)
    next_quad      = Column(Integer, nullable=True)
    next_prob      = Column(Float, nullable=True)
    effective_date = Column(String, nullable=False)
    notes          = Column(Text, nullable=True)
    created_at     = Column(String, nullable=False)
```

---

## Part 10 — Database: `signal_output` New Columns

### Alembic Migration — Add Columns

```python
# Migration description: "signal_output add quad fields"

def upgrade():
    op.add_column('signal_output',
        sa.Column('quad_alignment', sa.String(20), nullable=True))
    # 'Aligned' | 'Misaligned' | 'Neutral'

    op.add_column('signal_output',
        sa.Column('quad_mult', sa.Float(), nullable=True))
    # stored for debugging and popup display

def downgrade():
    op.drop_column('signal_output', 'quad_alignment')
    op.drop_column('signal_output', 'quad_mult')
```

### Update `signal_output.py` Model
Add:
```python
quad_alignment = Column(String(20), nullable=True)
quad_mult      = Column(Float, nullable=True)
```

---

## Part 11 — API Endpoints: Quad Settings

### New file: `backend/routers/quad.py`

```python
GET  /api/quad/settings   ← returns most recent row (active Quad)
POST /api/quad/settings   ← inserts new row (never updates)
```

**GET response shape:**
```json
{
  "current_quad": 3,
  "current_prob": 0.58,
  "next_quad": 2,
  "next_prob": 0.37,
  "effective_date": "2026-04-22",
  "notes": "Tariff shock pushing growth expectations lower"
}
```

**POST request shape:**
```json
{
  "current_quad": 3,
  "current_prob": 0.58,
  "next_quad": 2,
  "next_prob": 0.37,
  "effective_date": "2026-04-22",
  "notes": "optional"
}
```

Register in `main.py`:
```python
from routers import quad
app.include_router(quad.router, prefix="/api")
```

---

## Part 12 — `signals.py`: Pass Quad Settings into compute_output()

```python
# At top of calculate_signals():
from models.quad_settings import QuadSettings

quad_row = db.query(QuadSettings)\
             .order_by(QuadSettings.effective_date.desc())\
             .first()

quad_current = quad_row.current_quad if quad_row else None
quad_prob    = quad_row.current_prob if quad_row else 0.0

# Pass into compute_output() for each ticker:
result = compute_output(
    ...,
    asset_class=ticker_obj.asset_class,
    sector=ticker_obj.sector,
    quad_current=quad_current,
    quad_prob=quad_prob,
)
```

Update `compute_output()` signature in `conviction_engine.py` to accept:
```python
def compute_output(
    ...,
    asset_class: str,
    sector: str,
    quad_current: int | None,
    quad_prob: float,
) -> dict:
```

---

## Part 13 — Dashboard Header: Quad Display

**Position:** Between VIX gauge and summary counts row (BULLISH / BEARISH / ALIGNED / ALERTS / ENTRY)

**Display format:**
```
QUAD 3  58%  →  QUAD 2  37%
```

- Current quad label color: Q1 `#00e5a0` green / Q2 `#a3c940` olive / Q3 `#f0b429` amber / Q4 `#ff4d6d` red
- Arrow `→` in grey `#8899aa`
- Next quad shown only when `next_quad` is not null
- Probability shown as integer `%` (multiply stored float × 100)
- Fetched once on page load from `GET /api/quad/settings`
- Falls back gracefully when no quad settings exist (hide the display)

**Fetch pattern in `App.js`:**
```javascript
// Add to page load useEffect alongside scheduler status
const fetchQuadSettings = async () => {
  try {
    const res = await fetch(`${API_URL}/api/quad/settings`);
    const data = await res.json();
    setQuadSettings(data);
  } catch (e) {
    setQuadSettings(null);
  }
};
```

---

## Part 14 — Dashboard Table: Column Changes

### Remove from table
- `Asset Class` column
- `Sector` column

### Add to popup (after `Updated` field)
```
Asset Class    Domestic Equities
Sector         Technology
```

### Add to popup (after VIX Regime field)
```
Quad Alignment    Aligned ✓  (green #00e5a0)
                  Misaligned ✗  (red #ff4d6d)
                  Neutral —  (grey #8899aa)
Quad Mult         ×1.15  (formatted to 2 decimal places)
```

---

## Part 15 — Admin Panel: Quad Settings Section

Add new section to existing `AdminPanel.js` — below the ticker table.

```
─── QUAD SETTINGS ──────────────────────────────────────────
Current Quad:      [1]  [2]  [3]  [4]     Probability: [58]%
Next Quad:         [1]  [2]  [3]  [4]     Probability: [37]%
Effective Date:    [2026-04-22]
Notes:             [                                        ]
                                          [SAVE QUAD SETTINGS]
─────────────────────────────────────────────────────────────
Last saved: Quad 3 · 58% · effective 2026-04-22
```

- Quad selector = button group [1] [2] [3] [4], colored per quad on selection
- Probability = integer input (0–100), stored as float (÷100 before POST)
- Next Quad + Probability are optional — omit from POST if not set
- SAVE inserts a new row (POST) — never edits existing
- Show last saved row below the form for confirmation
- Fetches current settings on mount to pre-populate form

---

## Part 16 — `/api/signals/stored` Response: Add New Fields

Add to the per-ticker signal output response:
```json
{
  "quad_alignment": "Aligned",
  "quad_mult": 1.145,
  "vix_regime": "Choppy"
}
```

---

## Build Sequence for Neo

Run in this exact order. Confirm each step before proceeding.

```
Step 1  — Alembic: create quad_settings table
           docker exec signal-matrix-backend-1 alembic revision --autogenerate -m "add quad_settings table"
           Review migration → upgrade head locally → confirm in Supabase

Step 2  — Alembic: add quad_alignment + quad_mult to signal_output
           docker exec signal-matrix-backend-1 alembic revision --autogenerate -m "signal_output add quad fields"
           Review migration → upgrade head locally → confirm in Supabase

Step 3  — backend/models/quad_settings.py — new SQLAlchemy model

Step 4  — backend/routers/quad.py — GET + POST /api/quad/settings
           Register in main.py

Step 5  — conviction_engine.py
           a. Add QUAD_ALIGNMENT dict
           b. Add ALWAYS_NEUTRAL_SECTORS constant
           c. Add get_quad_alignment() function
           d. Add get_quad_multiplier() function
           e. Update get_vix_mult() — add asset_class gate, replace existing function
           f. Update compute_output() signature — add asset_class, sector, quad_current, quad_prob
           g. Wire Layer 4 (VIX) and Layer 5 (Quad) into conviction chain
           h. Write quad_alignment + quad_mult to output dict

Step 6  — signals.py
           a. Fetch quad_settings at top of calculate_signals()
           b. Fetch asset_class + sector from tickers table per ticker
           c. Pass all new params into compute_output()

Step 7  — signals.py: expose quad_alignment + quad_mult in /api/signals/stored response

Step 8  — App.js
           a. Add fetchQuadSettings() to page load useEffect
           b. Add quadSettings state
           c. Add Quad display to dashboard header
           d. Remove Asset Class + Sector columns from table
           e. Add Asset Class + Sector to popup
           f. Add Quad Alignment + Quad Mult to popup

Step 9  — AdminPanel.js — add Quad Settings section

Step 10 — Deploy sequence (per CLAUDE.md pre-migration checklist):
           - Confirm local SQLite passes
           - Run migrations on Supabase via fly ssh console
           - fly deploy --app signal-matrix-api
           - ./deploy-web.sh
           - Smoke test: CALCULATE SIGNALS → verify quad_alignment populating

Step 11 — Insert seed Quad Settings row via Admin Panel

Step 12 — CLAUDE.md — update conviction formula section, add quad_settings schema,
           update signal_output schema, update project rules
```

---

## Proactive Flags for Neo

1. **`asset_class` and `sector` availability in signals.py** — currently `calculate_signals()` works from a ticker list but may not have asset_class/sector attached. Verify `get_active_tickers(db)` returns these fields or add a join to the tickers table. Do not hardcode asset class per ticker.

2. **VIX close availability** — `get_vix_mult()` reads from `price_cache`. Confirm VIX row exists before calling. Already handled in existing implementation — verify the pattern carries over.

3. **Quad Settings cold start** — if `quad_settings` table is empty, `compute_output()` must handle `quad_current=None` gracefully: return `quad_mult=1.00`, `quad_alignment="Neutral"`. Do not crash.

4. **`vix_regime` column already exists** in `signal_output` from Phase 6. Do not re-add it in the migration. Just confirm the existing column is being written correctly when VIX multiplier is re-engaged.

5. **Sector field values** — the QUAD_ALIGNMENT dict uses exact sector strings as stored in the tickers table. If a ticker's sector doesn't match any entry, `get_quad_alignment()` returns 0.0 (neutral) silently. This is correct behavior — do not raise an error.

6. **Alembic SQLite fallback** — local migrations use pooled connection string per CLAUDE.md. If alembic fails locally, check `alembic/env.py` is using `SUPABASE_POOLED_CONNECTION_STRING`, not direct.
```
