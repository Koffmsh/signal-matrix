# Signal Matrix Platform — Project Context

## What This Project Is
Signal Matrix is a multi-timeframe, probabilistic trading signal platform designed to identify
high-conviction trade opportunities across a diversified universe of ~51 assets. Built on fractal
market theory, wave structure analysis, and probabilistic statistics — not traditional lagging
indicators.

## Core Philosophy
- Fewer, higher quality signals beat more, lower quality signals
- Trend alignment across timeframes is the primary filter
- Risk ranges are mathematically derived, not discretionary
- The system tells you where the market is, not where you want it to be

---

## Current Tech Stack
- **Frontend:** React (Create React App)
- **Container:** Docker + docker-compose
- **Data:** Mock/simulated — real data not yet connected
- **Backend:** Not yet built (target: Python FastAPI)
- **Database:** Not yet built (target: SQLite locally → Supabase/PostgreSQL in cloud)
- **Dev environment:** Windows PC, Docker Desktop, VS Code, localhost:3000
- **Hot reload fix:** `docker-compose.yml` updated — `CHOKIDAR_USEPOLLING=true` → `WATCHPACK_POLLING=true` for CRA 5 / webpack-dev-server 4 compatibility
- **Claude Code:** Preview auto-verify disabled (`autoVerify: false` in `.claude/launch.json`) — verification is manual via browser at localhost:3000

## Project Folder Structure
```
signal-matrix/
├── docs/
│   ├── SignalMatrix_Spec_v1.2.docx   ← master platform spec
│   └── QuadTracker_Spec_v1.1.docx   ← quad tracker spec
├── node_modules/
├── public/
├── src/
│   ├── App.css          ← global styles
│   ├── App.js           ← main app + all dashboard logic currently lives here
│   ├── App.test.js
│   ├── index.css
│   ├── index.js         ← entry point
│   ├── logo.svg
│   ├── reportWebVitals.js
│   └── setupTests.js
├── .gitignore
├── CLAUDE.md            ← this file
├── docker-compose.yml
├── Dockerfile
├── package-lock.json
├── package.json
└── README.md
```

## As You Build — Expected New Structure
When adding components and data files, use this structure:
```
src/
├── components/          ← all React components
│   ├── Dashboard/       ← main signal matrix table
│   ├── Admin/           ← ticker management (password protected)
│   └── shared/          ← reusable UI elements
├── data/
│   └── tickers.js       ← ticker universe (source of truth)
├── hooks/               ← custom React hooks if needed
├── utils/               ← helper functions (formatting, calculations)
├── App.css
├── App.js
└── index.js
```

---

## Methodology Reference

### Timeframes
- **Trade** — ≤ 3 weeks — entry/exit timing
- **Trend** — ≤ 3 months — directional bias filter
- **Long Term** — 3 years — macro structural context

### Signal Components
1. **Fractal Dimension (D)** — D→1.0 trending, D→1.5 choppy, D→2.0 mean-reverting
2. **Hurst Exponent (H)** — H>0.5 trending, H<0.5 mean-reverting, H=0.5 random walk. D+H=2.
3. **Gaussian Component** — normal distribution of returns, foundation for LRR/HRR
4. **Relative IV** — IV as percentile of its own 52-week range. Stock-specific, not vs VIX.
5. **Volume Signal** — Confirming / Diverging / Neutral

### Direction Values (ALL three timeframes)
- **Bullish** (was: Up)
- **Bearish** (was: Down)
- **Neutral**

### LRR / HRR Logic
- LRR = entry zone, anchored between B and C pivot points
- HRR = profit target / partial exit zone
- Range is NOT symmetrical — conviction determines asymmetry
- HRR well above D → full position | HRR near D → reduced | HRR below D → pass | LRR below C → no trade
- Primary filter: Trade AND Trend must be aligned before LRR/HRR is calculated

---

## Statistical Framework

### Which Paradigm Goes Where

The platform uses two statistical paradigms. Do NOT mix them up — each is the correct
tool for its specific job.

| Component | Paradigm | Reason |
|---|---|---|
| Hurst Exponent | **Frequentist** | Objective measurement of price series property |
| Fractal Dimension | **Frequentist** | Derived from H: D = 2 − H |
| Gaussian Return Distribution | **Frequentist** | Historical return frequency → confidence intervals |
| Relative IV Percentile | **Frequentist** | Rank within own 52-week historical distribution |
| Conviction Score (Signal Matrix) | **Frequentist** | How often has this signal profile historically hit HRR? |
| LRR / HRR Ranges | **Frequentist** | Anchored to Gaussian sigma bands and pivot points |
| Quad Probability Distribution | **Bayesian** | Continuously updated belief across 4 quads |
| Forward Quarter Projections Q2-Q4 | **Bayesian** | Prior decay without new confirming evidence |
| Policy Signal Modifiers | **Bayesian** | Discrete evidence updates to forward projections |

### Why Frequentist for Signal Matrix
Signal calculations answer frequency questions: "Given these statistical conditions,
how often has this type of price series produced a move to HRR historically?"
Parameters are computed from fixed historical windows and recalculated at EOD refresh.
They do not update dynamically mid-session.

### Why Bayesian for Quad Tracker
Quad detection answers a belief-updating question: "Given everything arriving in real
time, what macro regime is most probable over the next 1-4 quarters?" Each new
indicator release updates the posterior. Policy announcements are discrete evidence
injections. The momentum decay model (1.0 → 0.75 → 0.55 → 0.35) is a Bayesian
prior decay — confidence weakens over time without new confirming evidence.

---

## Signal Engine Math — Phase 3 Reference

> **Status:** These formulas define the target implementation for Phase 3.
> Do NOT build any of this during Phase 1 or Phase 2.
> Parameters marked OPEN are not yet finalized — flag before implementing.

### Fractal Dimension (D)
```
D = 2 - H
```
D is always derived from H. Do not calculate independently.

Interpretation:
  D → 1.0  =  smooth, strongly trending
  D → 1.5  =  random / choppy
  D → 2.0  =  highly mean-reverting

### Hurst Exponent (H)
```
H > 0.5  →  trending (persistent)
H < 0.5  →  mean-reverting (anti-persistent)
H = 0.5  →  random walk
```

Calculation method: [OPEN] — not yet decided. Three candidates:
  1. R/S Analysis (Rescaled Range) — classical, computationally simple
  2. DFA (Detrended Fluctuation Analysis) — more robust to non-stationarity,
     preferred for financial time series
  3. Higuchi Method — fastest, less standard in finance
  Recommended default: DFA. Confirm before implementing Phase 3.

Lookback windows: [OPEN] — not yet decided. Suggested starting points:
  Trade timeframe  (≤3 weeks):  63 trading days  (~3 months of daily data)
  Trend timeframe  (≤3 months): 252 trading days (~1 year)
  Long Term        (3 years):   756 trading days (~3 years)

Calculated independently at each of the three timeframes.

### Gaussian Return Distribution
```
r_t = ln(P_t / P_{t-1})        (daily log returns)

mu    = mean(r_t) over lookback window
sigma = std(r_t)  over lookback window
```
The Gaussian component provides probabilistic confidence intervals used to
calculate LRR and HRR bands. Recalculated at each timeframe independently
using the same lookback windows as H.

### Relative IV (Rel IV)
```
Rel IV % = (IV_current - IV_52w_low) / (IV_52w_high - IV_52w_low) * 100
```
- Uses the asset's own implied volatility — never compared to VIX
- 52-week rolling window (252 trading days)
- Output: 0-100 percentile
- Low Rel IV (< 25)  = volatility compressed → tighter LRR/HRR
- High Rel IV (> 75) = volatility expanded  → wider LRR/HRR
- Source: options chain IV via Schwab API (Phase 5)
  Proxy: use historical realized volatility until options data is connected

### LRR Calculation
LRR is anchored between B and C pivot points, scaled by conviction and IV.

```
LRR_position = B + conviction_weight * (C - B)

conviction_weight by H and volume:
  Strong  (H > 0.65, volume Confirming)    → 0.2  (LRR near B)
  Moderate                                 → 0.5  (LRR midpoint B-C)
  Weak    (H 0.50-0.60, volume Neutral)    → 0.8  (LRR near C)
  LRR below C                              → INVALIDATED, no trade

IV band around LRR_position:
  LRR_band = LRR_position ± (sigma * IV_scalar)

  IV_scalar:
    Rel IV < 25   → 0.5
    Rel IV 25-75  → 1.0
    Rel IV > 75   → 1.5
```
[OPEN] — exact IV_scalar values and conviction_weight breakpoints need validation.

### HRR Calculation
HRR is the expected move target above prior high D, driven by H and IV.

```
HRR = D + (H_scalar * sigma * IV_scalar)

H_scalar (converts H trending strength to expected move multiplier):
  H > 0.70      → 2.0   (strong trend, wide HRR)
  H 0.60-0.70   → 1.5
  H 0.50-0.60   → 1.0
  H < 0.50      → no HRR (mean-reverting, no trade)

Volume modifier applied to HRR:
  Confirming    → HRR * 1.10   (10% extension)
  Neutral       → HRR * 1.00   (no adjustment)
  Diverging     → HRR * 0.85   (15% reduction)
```
[OPEN] — H_scalar values and volume modifiers need validation against historical data.

HRR vs prior high D — position sizing:
```
HRR well above D  →  Full position
HRR near D        →  Reduced size
HRR below D       →  Pass or minimal size
LRR below C       →  No trade (uptrend invalidated)
```

### Conviction Score
```
Conviction % = weighted_average(H_score, volume_score, IV_score, trend_alignment_score)

Component scores (each 0-100):
  H_score          = (H - 0.5) / 0.5 * 100     [0 at H=0.5, 100 at H=1.0]
  volume_score     = Confirming→100 | Neutral→50 | Diverging→0
  IV_score         = 100 - Rel_IV               [low IV = higher score]
  trend_alignment  = Trade + Trend same direction→100 | misaligned→0
```

Weighting scheme: [OPEN] — two candidates:
  1. Equal weight     — 25% each. Simple, transparent.
  2. H-dominant       — H: 40%, others: 20% each.
     Rationale: H is the primary structural signal; others are modifiers.
  Recommended default: H-dominant. Confirm before implementing Phase 3.

### Multi-Timeframe Signal Flow (implementation order)
```python
# Pseudocode — implement calculations in this exact sequence

def calculate_signal(ticker, price_data, options_data):

    # Step 1 — Calculate H at all three timeframes
    H_lt    = hurst(price_data, lookback=756)    # Long Term
    H_trend = hurst(price_data, lookback=252)    # Trend
    H_trade = hurst(price_data, lookback=63)     # Trade

    # Step 2 — Structural filter (Long Term)
    if H_lt < 0.5:
        return Signal(direction="Neutral", conviction=0)  # Not a trending instrument

    # Step 3 — Trend direction
    trend_direction = "Bullish" if H_trend > 0.5 else "Bearish"

    # Step 4 — Trade alignment check (PRIMARY FILTER)
    trade_direction = "Bullish" if H_trade > 0.5 else "Bearish"
    if trade_direction != trend_direction:
        return Signal(direction="Neutral", conviction=0)  # Misaligned — no LRR/HRR

    # Step 5 — ABC pivot structure
    A, B, C, D = detect_pivots(price_data)
    if C < A:
        return Signal(direction="Neutral", conviction=0)  # Uptrend invalidated

    # Step 6 — Fractal Dimension (always derived from H)
    D_val = 2 - H_trade

    # Step 7 — Gaussian distribution parameters
    mu, sigma = gaussian_params(price_data, lookback=63)

    # Step 8 — Relative IV
    rel_iv = relative_iv(options_data, lookback=252)

    # Step 9 — Volume signal
    volume_signal = volume_conviction(price_data, volume_data)

    # Step 10 — LRR / HRR
    lrr = calculate_lrr(B, C, H_trade, volume_signal, rel_iv, sigma)
    hrr = calculate_hrr(D, H_trade, volume_signal, rel_iv, sigma)

    if lrr < C:
        return Signal(direction="Neutral", conviction=0)  # LRR below C — invalidated

    # Step 11 — Conviction score
    conviction = calculate_conviction(H_trade, volume_signal, rel_iv,
                                      trade_direction, trend_direction)

    return Signal(
        direction     = trade_direction,
        conviction    = conviction,
        lrr           = lrr,
        hrr           = hrr,
        hurst_trade   = H_trade,
        hurst_trend   = H_trend,
        hurst_lt      = H_lt,
        fractal_d     = D_val,
        rel_iv        = rel_iv,
        volume_signal = volume_signal
    )
```

---

## Quad Tracker Math — Future Phase Reference

> **Status:** Quad Tracker is NOT in current build scope.
> Captured here so full context is available when that phase begins.
> Full specification: docs/QuadTracker_Spec_v1.1.docx

### Indicator Scoring Formula
```
Score = Direction * min(|Magnitude_SD| / 2.0, 1.0) * Velocity_multiplier * 100

Direction:           +1 if ROC positive, -1 if negative
Magnitude_SD:        (current_value - historical_mean) / historical_std
                     Uses 10-year rolling window
                     [OPEN] — exclude COVID outlier period 2020-2021?
Velocity_multiplier: 1.2 if ROC accelerating (3+ consecutive months same direction)
                     0.8 if ROC decelerating
                     1.0 if stable
Output range:        -100 to +100 (hard capped)
```

Example:
```
PPI rising YoY, magnitude = 1.8 SD above mean, accelerating for 3 months:
Score = +1 * min(1.8/2.0, 1.0) * 1.2 * 100
      = +1 * 0.9 * 1.2 * 100
      = +108 → capped at +100
```

### Stream Aggregation
```
Growth_Score    = sum(indicator_score_i * weight_i) for all growth indicators
Inflation_Score = sum(indicator_score_i * weight_i) for all inflation indicators

Both scores: -100 to +100 scale.
Dual-stream indicators contribute partial weight to each stream independently.
```

### Quad Probability Mapping
```
Input:  Growth_Score (-100 to +100), Inflation_Score (-100 to +100)
Method: 2D bivariate normal distribution centered on (Growth_Score, Inflation_Score)
Output: probability mass across 4 quads, normalized to sum to 100%

Quad mapping:
  Q1: Growth > 0, Inflation < 0   (Growth up, Inflation down)
  Q2: Growth > 0, Inflation > 0   (Growth up, Inflation up)
  Q3: Growth < 0, Inflation > 0   (Growth down, Inflation up)
  Q4: Growth < 0, Inflation < 0   (Growth down, Inflation down)
```
[OPEN] — bivariate normal covariance parameters not yet defined.

### Momentum Decay (Forward Quarters)
```
Q1 (current):   decay = 1.00  (live data, no projection)
Q2 (1Q ahead):  decay = 0.75
Q3 (2Q ahead):  decay = 0.55
Q4 (3Q ahead):  decay = 0.35

Projected_Score_Qn = Current_Score * decay_n
```
Policy signals override decay when a clear policy path is established
(e.g. confirmed Fed rate cut cycle → growth modifier applied directly to Q2-Q4).

### Dominant Quad Classification
```
[OPEN] — threshold not yet decided. Suggested:
  dominant quad    = quad with highest probability
  high conviction  = dominant quad > 60%
  declared         = dominant quad > 40%
  ambiguous        = no quad exceeds 40%
```

---

## Ticker Universe — Tier 1 (51 tickers, STATIC — do not change without instruction)

```javascript
// Asset Classes: Domestic Equities, Domestic Fixed Income, Digital Assets,
//                Foreign Exchange, International Equities, Commodities

const tickers = [
  // DOMESTIC EQUITIES — Index
  { ticker: "SPX",   description: "S&P 500 Index",                        assetClass: "Domestic Equities", sector: "Index",                    tier: 1 },
  { ticker: "NDX",   description: "Nasdaq 100 Index",                     assetClass: "Domestic Equities", sector: "Index",                    tier: 1 },
  { ticker: "$DJI",  description: "Dow Jones Industrial Avg",             assetClass: "Domestic Equities", sector: "Index",                    tier: 1 },
  { ticker: "VIX",   description: "CBOE Volatility Index",                assetClass: "Domestic Equities", sector: "Index",                    tier: 1 },
  // DOMESTIC EQUITIES — Broad Market
  { ticker: "SPY",   description: "SPDR S&P 500 ETF",                     assetClass: "Domestic Equities", sector: "Broad Market",             tier: 1 },
  { ticker: "QQQ",   description: "Invesco Nasdaq 100 ETF",               assetClass: "Domestic Equities", sector: "Broad Market",             tier: 1 },
  { ticker: "IWM",   description: "iShares Russell 2000 ETF",             assetClass: "Domestic Equities", sector: "Broad Market",             tier: 1 },
  // DOMESTIC EQUITIES — Sector ETFs (State Street)
  { ticker: "XLK",   description: "Technology Select Sector",             assetClass: "Domestic Equities", sector: "Technology",               tier: 1 },
  { ticker: "XLF",   description: "Financial Select Sector",              assetClass: "Domestic Equities", sector: "Financials",               tier: 1 },
  { ticker: "XLE",   description: "Energy Select Sector",                 assetClass: "Domestic Equities", sector: "Energy",                   tier: 1 },
  { ticker: "XLV",   description: "Health Care Select Sector",            assetClass: "Domestic Equities", sector: "Health Care",              tier: 1 },
  { ticker: "XLI",   description: "Industrials Select Sector",            assetClass: "Domestic Equities", sector: "Industrials",              tier: 1 },
  { ticker: "XLY",   description: "Consumer Discr. Select Sector",        assetClass: "Domestic Equities", sector: "Consumer Discretionary",   tier: 1 },
  { ticker: "XLP",   description: "Consumer Staples Select Sector",       assetClass: "Domestic Equities", sector: "Consumer Staples",         tier: 1 },
  { ticker: "XLB",   description: "Materials Select Sector",              assetClass: "Domestic Equities", sector: "Materials",                tier: 1 },
  { ticker: "XLU",   description: "Utilities Select Sector",              assetClass: "Domestic Equities", sector: "Utilities",                tier: 1 },
  { ticker: "XLRE",  description: "Real Estate Select Sector",            assetClass: "Domestic Equities", sector: "Real Estate",              tier: 1 },
  { ticker: "XLC",   description: "Communication Services Select Sector", assetClass: "Domestic Equities", sector: "Communication Services",   tier: 1 },
  // DOMESTIC EQUITIES — Individual Stocks (GICS sectors)
  { ticker: "AAPL",  description: "Apple Inc.",                           assetClass: "Domestic Equities", sector: "Technology",               tier: 1 },
  { ticker: "MSFT",  description: "Microsoft Corp.",                      assetClass: "Domestic Equities", sector: "Technology",               tier: 1 },
  { ticker: "NVDA",  description: "NVIDIA Corp.",                         assetClass: "Domestic Equities", sector: "Technology",               tier: 1 },
  { ticker: "AVGO",  description: "Broadcom Inc.",                        assetClass: "Domestic Equities", sector: "Technology",               tier: 1 },
  { ticker: "GOOGL", description: "Alphabet Inc.",                        assetClass: "Domestic Equities", sector: "Communication Services",   tier: 1 },
  { ticker: "META",  description: "Meta Platforms Inc.",                  assetClass: "Domestic Equities", sector: "Communication Services",   tier: 1 },
  { ticker: "NFLX",  description: "Netflix Inc.",                         assetClass: "Domestic Equities", sector: "Communication Services",   tier: 1 },
  { ticker: "AMZN",  description: "Amazon.com Inc.",                      assetClass: "Domestic Equities", sector: "Consumer Discretionary",   tier: 1 },
  { ticker: "TSLA",  description: "Tesla Inc.",                           assetClass: "Domestic Equities", sector: "Consumer Discretionary",   tier: 1 },
  // DOMESTIC EQUITIES — Factor ETFs
  { ticker: "SMH",   description: "VanEck Semiconductor ETF",             assetClass: "Domestic Equities", sector: "Factor",                   tier: 1 },
  { ticker: "CIBR",  description: "First Trust Cybersecurity ETF",        assetClass: "Domestic Equities", sector: "Factor",                   tier: 1 },
  { ticker: "GRID",  description: "First Trust Clean Edge Smart Grid",    assetClass: "Domestic Equities", sector: "Factor",                   tier: 1 },
  { ticker: "QTUM",  description: "Defiance Quantum ETF",                 assetClass: "Domestic Equities", sector: "Factor",                   tier: 1 },
  { ticker: "ROBO",  description: "ROBO Global Robotics & Auto ETF",      assetClass: "Domestic Equities", sector: "Factor",                   tier: 1 },
  { ticker: "SATS",  description: "ETF Series Space & Defense",           assetClass: "Domestic Equities", sector: "Factor",                   tier: 1 },
  // DOMESTIC FIXED INCOME
  { ticker: "TLT",   description: "iShares 20+ Year Treasury Bond ETF",   assetClass: "Domestic Fixed Income", sector: "Treasury",            tier: 1 },
  // DIGITAL ASSETS
  { ticker: "IBIT",  description: "iShares Bitcoin Trust ETF",            assetClass: "Digital Assets",    sector: "Cryptocurrency",          tier: 1 },
  // FOREIGN EXCHANGE
  { ticker: "GLD",   description: "SPDR Gold Shares",                     assetClass: "Foreign Exchange",  sector: "Gold",                    tier: 1 },
  { ticker: "USD",   description: "US Dollar Index",                      assetClass: "Foreign Exchange",  sector: "Currency",                tier: 1 },
  { ticker: "JPY",   description: "Japanese Yen / USD",                   assetClass: "Foreign Exchange",  sector: "Currency",                tier: 1 },
  // INTERNATIONAL EQUITIES
  { ticker: "KWEB",  description: "KraneShares CSI China Internet ETF",   assetClass: "International Equities", sector: "China",             tier: 1 },
  { ticker: "EWJ",   description: "iShares MSCI Japan ETF",               assetClass: "International Equities", sector: "Japan",             tier: 1 },
  { ticker: "EWW",   description: "iShares MSCI Mexico ETF",              assetClass: "International Equities", sector: "Mexico",            tier: 1 },
  { ticker: "TUR",   description: "iShares MSCI Turkey ETF",              assetClass: "International Equities", sector: "Turkey",            tier: 1 },
  { ticker: "UAE",   description: "iShares MSCI UAE ETF",                 assetClass: "International Equities", sector: "UAE",               tier: 1 },
  // COMMODITIES
  { ticker: "USO",   description: "United States Oil Fund",               assetClass: "Commodities",       sector: "Energy",                  tier: 1 },
  { ticker: "SLV",   description: "iShares Silver Trust",                 assetClass: "Commodities",       sector: "Precious Metals",         tier: 1 },
  { ticker: "PALL",  description: "Aberdeen Physical Palladium",          assetClass: "Commodities",       sector: "Precious Metals",         tier: 1 },
  { ticker: "CANE",  description: "Teucrium Sugar Fund",                  assetClass: "Commodities",       sector: "Agricultural",            tier: 1 },
  { ticker: "WOOD",  description: "iShares Global Timber & Forestry ETF", assetClass: "Commodities",       sector: "Materials",               tier: 1 },
];
```

---

## Dashboard — Current State
- React app running at localhost:3000 via Docker
- All Tier 1 tickers loaded with mock/simulated data
- All data is mock — real data not yet connected

## Dashboard Columns (in order)
| Column | Description | Values |
|--------|-------------|--------|
| Alert Flag ⚡ | High conviction aligned signal | flag / empty |
| Ticker | Symbol | — |
| Description | Asset name | — |
| Asset Class | Classification | see ticker universe |
| Sector | GICS sector / Index / Broad Market / Factor / etc. | see ticker universe |
| Close Price | Last closing price | mock |
| Viewpoint | Trade + Trend alignment summary | — |
| Conviction % | Probability score | 0-100% |
| Trade Direction | Short-term direction | Bullish / Bearish / Neutral |
| Trade LRR | Lower risk range - trade timeframe | price |
| Trade HRR | Higher risk range - trade timeframe | price |
| Trend Direction | Medium-term direction | Bullish / Bearish / Neutral |
| Trend LRR | Support level - trend timeframe | price |
| LT Direction | Long-term direction | Bullish / Bearish / Neutral |
| LT LRR | Long-term structural support | price |
| Hurst (Trade) | H value at trade timeframe | 0.0-1.0 |
| Rel IV % | Relative IV % of 52-week range | 0-100% |
| Volume Signal | Volume conviction | Confirming / Neutral / Diverging |
| Last Updated | EOD data timestamp | — |

## Color Coding
- **Green** — Bullish signals, high conviction
- **Red** — Bearish signals
- **Amber** — Neutral, weak conviction, or caution

---

## Tier 1 / Tier 2 Behavior
- Dashboard shows **Tier 1 tickers only** by default
- Tier 1 rows that have Tier 2 children show a **chevron (›)** indicator
- Clicking the chevron **expands Tier 2 rows inline** beneath the parent
- Tier 2 rows are **indented and subtly styled** differently from Tier 1
- Tier 2 tickers only surface when parent Tier 1 hits conviction threshold
- Tier 2 mappings are managed via the Admin panel (not hardcoded)

---

## Admin Panel
- **Route:** `/admin` — hidden, not visible in main navigation
- **Access:** Password protected via `.env` variable `REACT_APP_ADMIN_PASSWORD`
- **Never hardcode the password in source code**
- **Functionality:**
  - Add new ticker (all fields)
  - Edit existing ticker (any field)
  - Deactivate ticker (soft delete — never hard delete)
  - Assign Tier 2 tickers to a Tier 1 parent
  - Set display order within asset class
- **Fields:** ticker, description, assetClass, sector, tier (1 or 2), parentTicker (Tier 2 only), active (bool), displayOrder

---

## Environment Variables
Create a `.env` file in the project root (never commit this file):
```
REACT_APP_ADMIN_PASSWORD=your_password_here
```
`.env` is already in `.gitignore` — confirm before committing anything.

---

## Project Rules — Read Before Making Changes
1. **Never modify the ticker universe without explicit instruction** — it is the source of truth
2. **Never hardcode passwords, API keys, or secrets** — always use `.env`
3. **Never hard delete tickers** — use active: false (soft deactivate)
4. **Direction values are Bullish / Bearish / Neutral** — never Up / Down
5. **Asset Class values must exactly match:** Domestic Equities | Domestic Fixed Income | Digital Assets | Foreign Exchange | International Equities | Commodities
6. **Keep components modular** — one component per file, organized in `src/components/`
7. **Move ticker data to `src/data/tickers.js`** if it isn't already there
8. **Docker:** changes to `src/` are reflected on save — no need to rebuild container for frontend changes
9. **Do not modify** `docker-compose.yml`, `Dockerfile`, or `package.json` without flagging it first
10. **Do not implement signal calculations** (Hurst, LRR/HRR, conviction score) until Phase 3 is explicitly started
11. **Flag all [OPEN] items** before implementing the component they belong to — do not assume defaults

---

## Open Decisions — Must Resolve Before Phase 3

These are not optional — implementation cannot proceed without answers:

| Decision | Options | Recommended Default |
|---|---|---|
| Hurst calculation method | R/S Analysis, DFA, Higuchi | DFA |
| Hurst lookback — Trade | 21, 42, 63 trading days | 63 |
| Hurst lookback — Trend | 126, 252 trading days | 252 |
| Hurst lookback — Long Term | 504, 756 trading days | 756 |
| Conviction weighting scheme | Equal (25% each) vs H-dominant (40/20/20/20) | H-dominant |
| LRR conviction_weight breakpoints | Exact H thresholds for strong/moderate/weak | See math section |
| IV_scalar values | Exact multipliers at low/mid/high Rel IV | See math section |
| HRR H_scalar values | Exact multipliers at H tiers | See math section |
| Quad dominant threshold | >40% declared, >60% high conviction | 40% / 60% |
| Quad SD baseline lookback | 10-year rolling, exclude COVID? | 10yr, exclude 2020-2021 |

---

## Current Priorities — Phase 1

Work through these in order. Confirm completion of each before moving to the next.

### ✅ Task 1 — Refactor & Clean Up
- Move ticker data into `src/data/tickers.js` using the ticker universe defined above
- Update all ticker fields: assetClass, sector, tier, active, displayOrder
- Update all direction values from Up/Down → Bullish/Bearish throughout codebase
- Create `src/components/` folder structure

### ✅ Task 2 — Sector Column
- Add Sector column to the dashboard table (after Asset Class column)
- Populate from ticker data

### Task 3 — Tier 1 / Tier 2 Expand/Collapse
- Show only Tier 1 tickers by default
- Add chevron (›) to Tier 1 rows that have Tier 2 children
- Click chevron to expand/collapse Tier 2 rows inline
- Tier 2 rows: indented, slightly muted background (e.g. bg-gray-50 or similar)
- No Tier 2 data yet — build the UI and expand/collapse mechanism

### Task 4 — Sparkline Charts
- Add a small sparkline chart column showing mock price history for each ticker
- Position: after Close Price column
- Keep compact — fits in table cell
- Use a lightweight charting library (recharts is already likely available, or use sparklines)

### Task 5 — Admin Panel
- Create `/admin` route — hidden from main nav
- Password gate using `REACT_APP_ADMIN_PASSWORD` from `.env`
- Ticker management table: view all tickers, add, edit, deactivate
- Tier 2 parent assignment field
- Display order field

---

## What Is NOT In Scope Yet
- Real data feeds (Yahoo Finance, Schwab API)
- Signal calculations (Hurst, Fractal Dimension, LRR/HRR engine)
- Python FastAPI backend
- SQLite or Supabase database
- Quad Tracker dashboard
- Any other dashboards beyond Signal Matrix

---

## Target Stack (for future phases — do not build yet)
- **Backend:** Python FastAPI
- **Database local:** SQLite via SQLAlchemy ORM
- **Database cloud:** Supabase (PostgreSQL)
- **Data EOD:** Yahoo Finance / Schwab API
- **Data live:** Schwab API WebSocket
- **Hosting:** Local now → AWS/Azure/GCP later
