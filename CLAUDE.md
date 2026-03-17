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
- **Data:** Real EOD prices via Yahoo Finance — FastAPI backend with SQLite cache
- **Backend:** Python FastAPI running at localhost:8000
- **Database:** SQLite cache at `backend/signal_matrix.db`
- **Dev environment:** Windows PC, Docker Desktop, VS Code, localhost:3000
- **Hot reload:** `WATCHPACK_POLLING=true` in docker-compose.yml
- **Claude Code:** `autoVerify: true` — verifies at localhost:3000 after every change
- **Claude in Chrome extension:** enabled and operational. Set to allow access to all sites including localhost:3000. When "started debugging this browser" banner appears in Chrome, do not click Cancel — leave it open so the debugger can attach and complete screenshot/page verification.
- **Yahoo Finance:** Manual REFRESH DATA button only — never auto-fetch on page load
- **Git:** No worktrees or feature branches — all changes committed directly to master
- **Version control:** Git initialized, first commit `42e6663` — "Phase 1 complete - Tasks 1-5"

## Project Folder Structure
```
signal-matrix/
├── .claude/
│   ├── launch.json
│   └── settings.local.json
├── Docs/
│   ├── SignalMatrix_Spec_v1.3.docx        ← current spec
│   └── QuadTracker_Spec_v1.1.docx
├── public/
├── src/
│   ├── components/
│   │   ├── Admin/
│   │   │   └── AdminPanel.js              ← Task 5 — admin panel, password gated
│   │   ├── Dashboard/                     ← placeholder, logic still in App.js
│   │   └── shared/                        ← placeholder
│   ├── data/
│   │   └── tickers.js                     ← Tier 1 + Tier 2 seed tickers, source of truth
│   ├── hooks/                             ← placeholder
│   ├── utils/                             ← placeholder
│   ├── App.css
│   ├── App.js                             ← main app — all dashboard logic lives here
│   ├── index.css
│   └── index.js
├── backend/
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── main.py
│   ├── database.py
│   ├── models/
│   │   └── price_cache.py
│   ├── services/
│   │   ├── yahoo_finance.py
│   │   ├── signal_engine.py               ← Task 3.1 — Hurst + Fractal Dimension (DFA)
│   │   ├── pivot_engine.py                ← Task 3.2 — ABC Pivot Detector
│   │   └── conviction_engine.py           ← Task 3.3 — LRR/HRR + Conviction Engine
│   └── routers/
│       └── market_data.py
├── .env                                   ← NOT in Git — contains REACT_APP_ADMIN_PASSWORD
├── .gitignore                             ← .env and signal_matrix.db excluded
├── CLAUDE.md                              ← this file
├── docker-compose.yml
├── Dockerfile
├── package.json
└── README.md
```

---

## Phase 1 — COMPLETE ✅

All five tasks are built, deployed, and committed to Git.

### Task 1 — Refactor & Clean Up ✅
- Ticker data moved to `src/data/tickers.js`
- All direction values: Bullish / Bearish / Neutral
- Asset class and sector fields standardized
- Component folder structure created

### Task 2 — Sector Column ✅
- Sector column added to dashboard table after Asset Class
- Populated from ticker data

### Task 3 — Tier 1 / Tier 2 Expand/Collapse ✅
- Tier 1 tickers display by default
- Chevron (›) appears on rows that have Tier 2 children
- Click chevron to expand/collapse Tier 2 rows inline beneath parent
- Tier 2 rows: darker background `#0a1018`, indented ticker cell, muted text
- `expandedTickers` Set state with `toggleExpand(ticker, e)` + `e.stopPropagation()`
- `TIER2_BY_PARENT` map: parentTicker → children[]
- `filtered.flatMap()` injects Tier 2 rows after sort

**Tier 2 seed tickers (5):**
- USO → XOP, OIH
- XLY → AMZN
- XLK → SOXX
- GLD → SGOL

### Task 4 — Sparklines + Column Cleanup ✅
- Pure SVG sparkline component — no charting library
- 60-day real price history from Yahoo Finance
- `Sparkline({ prices, color })`: 80×28px, 1.5px stroke, no axes
- Spark color: Bullish `#00e5a0`, Bearish `#ff4d6d`, Neutral `#8899aa`
- TREND column positioned after CLOSE

**Table columns — FINAL ORDER:**
`› | ⚡ | TICKER | DESCRIPTION | ASSET CLASS | SECTOR | CLOSE | TREND | VIEWPOINT | CONVICTION | TRADE DIR | TRADE LRR | TRADE HRR | TREND DIR | TREND LRR`

**Removed from table** (moved to popup only):
LT Dir, LT LRR, Hurst(T), Rel IV%, Vol Signal, Updated

**Default sort:** Asset class order → sector order → ticker alpha
```js
const ASSET_CLASS_ORDER = ["Domestic Equities","Domestic Fixed Income","Commodities",
  "Foreign Exchange","International Equities","Digital Assets"];
const SECTOR_ORDER = ["Index","Broad Market","Technology","Communication Services",
  "Consumer Discretionary","Consumer Staples","Energy","Financials","Health Care",
  "Industrials","Materials","Real Estate","Utilities","Factor"];
```
`sortKey` defaults to `"default"`. Column header clicks override.

**Popup fields — FINAL:**
Close, Viewpoint, Conviction, LT Dir, LT LRR, Trend LRR, Hurst(T), Rel IV%, Vol Signal, Updated
- Removed from popup: Aligned, Trade Dir, Trend Dir, Trade LRR, Trade HRR
- Label color: `#99aabb`

**Color conventions — locked:**
- Neutral color: `#8899aa` grey everywhere
- Amber `#f0b429` reserved for alerts/conviction bar only — and WARNING state cells
- `vpColor`, `dirColor` both use `#8899aa` for Neutral

### Task 5 — Admin Panel ✅
- Route: `localhost:3000/admin` — not visible in main nav
- Password gate: `REACT_APP_ADMIN_PASSWORD` from `.env`
- localStorage persistence: key `sm_tickers`, seeds from `tickers.js` on first load
- `loadTickers()` and `saveTickers()` exported from `App.js`
- Routing: `window.location.pathname === "/admin"` check in `App.js` default export

**Admin features:**
- View all tickers (ALL / ACTIVE / INACTIVE filter)
- Inline cell editing — click any cell, Tab/Enter to commit, Escape to cancel
- Asset Class and Tier dropdowns
- Parent ticker dropdown (enabled only when Tier = 2)
- Add Ticker button — appends blank row
- Deactivate / Reactivate on row hover — sets `active: false/true`, never hard deletes
- Display order field
- Toast "Saved" notification on every persist
- Back to Dashboard link
- 53 active tickers total (48 Tier 1 + 5 Tier 2 seeds)

---

## Phase 2 — COMPLETE ✅

Real data integration delivered:
- Yahoo Finance EOD prices for all Tier 1 tickers via Python FastAPI backend
- Real closing prices, sparklines (60-day), Rel IV (realized vol percentile), volume
- MA20/50/100 computed and cached in SQLite — not yet displayed in UI
- REFRESH DATA button in header — manual trigger only, no auto-fetch on load
- 429 rate limit handling — batch stops immediately and returns partial results
- SQLite cache at `backend/signal_matrix.db` — same-day fetches served instantly

---

## Phase 3 — IN PROGRESS 🔄

Signal engine build. All decisions locked — see full spec in `Docs/SignalMatrix_Spec_v1.3.docx`.

### Phase 3 Build Sequence

| Task | Deliverable | File | Status |
|---|---|---|---|
| 3.1 | Hurst + Fractal Dimension (DFA) | `backend/services/signal_engine.py` | ✅ Complete |
| 3.2 | ABC Pivot Detector | `backend/services/pivot_engine.py` | ⬜ Next |
| 3.3 | LRR/HRR + Conviction Engine | `backend/services/conviction_engine.py` | ⬜ Pending 3.2 |
| 3.4 | Wire to Dashboard | React frontend (App.js) | ⬜ Pending 3.3 |

### New Button — CALCULATE SIGNALS
- Added to dashboard header alongside REFRESH DATA
- Manual trigger only — never auto-calculates on page load
- Must be run AFTER REFRESH DATA (price history must be current)
- Calls: `/api/signals/hurst` → `/api/signals/pivots` → `/api/signals/output` in sequence

---

## Signal Engine Math — Phase 3 (ALL DECISIONS LOCKED)

### Hurst Exponent (H)
- **Method: DFA (Detrended Fluctuation Analysis)** — robust for financial time series
- **Lookback windows:**
  - Trade: 63 trading days
  - Trend: 252 trading days
  - Long Term: 756 trading days
- **Minimum bars required:** same as lookback — return null if insufficient, do not skip ticker
- **D = 2 − H** (Fractal Dimension derived directly from H)

### DFA Algorithm
```python
def dfa(prices, window):
    # 1. Convert prices to log returns
    # 2. Compute cumulative sum (integration)
    # 3. Scales: log-spaced from 10 bars to window//4, ~20 points
    # 4. For each scale n: fit linear trend per segment, compute RMS of residuals F(n)
    # 5. H = slope of log(F(n)) vs log(n) via linear regression
    # Returns H in [0, 1]
    # H > 0.5 = trending, H < 0.5 = mean-reverting, H = 0.5 = random walk
```

### Conviction Score Formula
```
Base Score = weighted average:
  Trade H (DFA, 63-day)   → 55%   primary signal
  Trend H (DFA, 252-day)  → 25%   alignment filter
  Rel IV% inverted        → 20%   IV Score = (100 - RelIV%) / 100

Volume Multiplier (applied after base score):
  Confirming  → × 1.15
  Neutral     → × 1.00
  Diverging   → × 0.80

Final Conviction = Base Score × Volume Multiplier
```

**Long Term H (756-day):** calculated and stored, displayed in popup as context only.
Not used in conviction formula.

### Alert Flag ⚡ Trigger (ALL THREE must be true)
1. Trade H > 0.55 AND Trend H > 0.55
2. Trade direction and Trend direction both aligned (both Bullish or both Bearish)
3. Final Conviction ≥ 70%

### ABC Pivot Structure

**Uptrend:**
```
A = pivot low   (e.g. $100)
B = pivot high  (e.g. $110)  — higher high
C = higher low  (e.g. $105)  — C > A confirms uptrend
D = running high             — established when price closes above B, updates as price climbs
```

**Downtrend (mirror):**
```
A = pivot high  (e.g. $100)
B = pivot low   (e.g. $90)   — lower low
C = lower high  (e.g. $95)   — C < A confirms downtrend
D = running low              — established when price closes below B, updates as price falls
```

**Key rules:**
- D is established the moment price closes above B (uptrend) or below B (downtrend)
- D is a running value — updates continuously until a new pullback forms a new C
- The structure always references the most recent confirmed A/B/C pattern
- Old pivot levels are irrelevant once new structure forms

**Pivot detection bar windows:**
- Trade: 3 bars
- Trend: 20 bars
- Long Term: 90 bars

### LRR / HRR — Naming Convention
- **LRR = always the lower price value** (entry zone in uptrend, profit target in downtrend)
- **HRR = always the higher price value** (profit target in uptrend, entry zone in downtrend)

### LRR Formula — Uptrend
```
Base LRR = C + (B − C) × H_factor

H_factor lookup:
  H > 0.65        →  0.95  (near B — strong trend)
  H 0.55 – 0.65   →  0.50  (midpoint — moderate trend)
  H 0.50 – 0.55   →  0.05  (near C — weak trend)
  H < 0.50        →  no valid setup
```

### HRR Formula — Uptrend
```
Base HRR = D + (1σ of recent returns)
```

### Downtrend Mirror Formulas
```
Base HRR = C − (C − B) × H_factor   ← entry on bounce (higher price)
Base LRR = D − (1σ of recent returns) ← profit target (lower price)
```

### Rel IV Scaling (ATR Equivalent)
IV scales LRR/HRR width exactly as ATR expands and contracts with volatility.
No hard floor or ceiling — IV can push LRR below C or HRR above C.
When this occurs, WARNING state is flagged (amber cell in dashboard).

| Rel IV% | LRR Adj (Uptrend) | HRR Adj (Uptrend) |
|---|---|---|
| 0–30% | × 0.99 (tight) | × 1.02 |
| 31–60% | × 1.00 (neutral) | × 1.05 |
| 61–80% | × 0.97 (wider) | × 1.10 |
| > 80% | × 0.94 (max) | × 1.15 |

Downtrend: HRR pushed up, LRR pulled down (same widening logic, mirrored).

### Structural States

| State | Uptrend Condition | Downtrend Condition | Display |
|---|---|---|---|
| UPTREND_VALID / DOWNTREND_VALID | C > A, price above LRR | C < A, price below HRR | Normal green/red |
| FORMING | Pullback from D, no new C yet | Bounce from D, no new C yet | LRR/HRR update each close |
| EXTENDED | Price above D, new C not formed | Price below D, new C not formed | LRR/HRR shown, context = awaiting reset |
| WARNING | LRR drifted below C | HRR drifted above C | LRR or HRR cell → amber |
| BREAK_OF_TRADE | Price closes below C (trade tf) | Price closes above C (trade tf) | Trade Dir flips, LRR/HRR cleared |
| BREAK_OF_TREND | Price closes below C (trend tf) | Price closes above C (trend tf) | Trend Dir flips, Trend LRR cleared |
| NO_STRUCTURE | H < 0.50 or insufficient history | H < 0.50 or insufficient history | LRR/HRR blank |

**Critical rules:**
- **C is the line in the sand** — not LRR. Break of Trade/Trend fires on price closing through C.
- **LRR = entry signal. C = invalidation level.** Different jobs.
- Trade and Trend structural states are **independent** — a Trend break does not auto-flip Trade.
- Diverging Trade/Trend states = diverging Viewpoint in dashboard. Useful, not an error.

### New Database Tables (Phase 3)
```sql
signal_hurst:   ticker, h_trade, h_trend, h_lt, d_trade, d_trend, d_lt, calculated_at
                UNIQUE(ticker)

signal_pivots:  ticker, timeframe, bar_window,
                pivot_a, pivot_b, pivot_c, pivot_d,
                pivot_a_date, pivot_b_date, pivot_c_date, pivot_d_date,
                structural_state, calculated_at
                UNIQUE(ticker, timeframe)

signal_output:  ticker, timeframe, lrr, hrr, structural_state,
                conviction, trade_direction, h_value, calculated_at
                UNIQUE(ticker, timeframe)
```

### New FastAPI Endpoints (Phase 3)
```
GET /api/signals/hurst    ← Task 3.1
GET /api/signals/pivots   ← Task 3.2
GET /api/signals/output   ← Task 3.3 — full signal set per ticker
```

### Sanity Checks After Task 3.1
| Ticker | Expected H(Trade) | Rationale |
|---|---|---|
| SPY | 0.50–0.65 | Broad market — moderate trend |
| GLD | 0.60–0.75 | Strong persistent trend last 12 months |
| VIX | 0.30–0.45 | Mean-reverting by nature |
| TLT | 0.45–0.60 | Range-bound recently |

---

## Data Layer

### Current: localStorage + FastAPI/SQLite
- `localStorage.getItem("sm_tickers")` → parse → use
- Falls back to `tickers.js` if nothing stored
- Admin panel writes back via `saveTickers()`
- Phase 4: FastAPI/SQLAlchemy replaces localStorage with no UI changes needed

### tickers.js — Tier 1 (48 tickers, STATIC)
Do not modify without explicit instruction. Source of truth for ticker universe.

Fields: `ticker, description, assetClass, sector, tier, parentTicker, active, displayOrder`

---

## Methodology Reference

### Timeframes
- **Trade** — ≤ 3 weeks — entry/exit timing
- **Trend** — ≤ 3 months — directional bias filter
- **Long Term** — 3 years — macro structural context (display/context only)

### Signal Components
1. **Fractal Dimension (D)** — D→1.0 trending, D→1.5 choppy, D→2.0 mean-reverting. D = 2 − H.
2. **Hurst Exponent (H)** — H>0.5 trending, H<0.5 mean-reverting, H=0.5 random walk. Method: DFA.
3. **Gaussian Component** — normal distribution of returns, foundation for HRR (1σ above/below D)
4. **Relative IV** — IV as percentile of its own 52-week range. Stock-specific, not vs VIX.
   Primary role: LRR/HRR width scaling (ATR equivalent). Secondary: conviction score component.
5. **Volume Signal** — Confirming / Diverging / Neutral. Applied as multiplier to conviction score.

### Direction Values (ALL three timeframes)
- **Bullish** / **Bearish** / **Neutral** — never Up / Down

---

## Statistical Framework

| Component | Paradigm | Reason |
|---|---|---|
| Hurst Exponent | **Frequentist** | Objective measurement of price series property |
| Fractal Dimension | **Frequentist** | Derived from H: D = 2 − H |
| Gaussian Return Distribution | **Frequentist** | Historical return frequency → confidence intervals |
| Relative IV Percentile | **Frequentist** | Rank within own 52-week historical distribution |
| Conviction Score | **Frequentist** | How often has this signal profile historically hit HRR? |
| LRR / HRR Ranges | **Frequentist** | Anchored to Gaussian sigma bands and pivot points |
| Quad Probability Distribution | **Bayesian** | Continuously updated belief across 4 quads |
| Forward Quarter Projections Q2-Q4 | **Bayesian** | Prior decay without new confirming evidence |
| Policy Signal Modifiers | **Bayesian** | Discrete evidence updates to forward projections |

---

## Dashboard — Current State
- React app running at localhost:3000 via Docker
- All Tier 1 tickers loaded with real + mock data merged
- Close prices: real — from Yahoo Finance via FastAPI
- Sparklines: real — 60-day price history
- Rel IV: real — realized vol percentile proxy (Schwab IV Percentile in Phase 5)
- Volume: real — daily volume from Yahoo Finance
- MA20/50/100: computed and cached — not yet displayed in UI
- Signal columns remain mock: Conviction, Trade Dir, LRR, HRR, Hurst, Vol Signal
- REFRESH DATA button in header — manual fetch only, never auto on page load
- CALCULATE SIGNALS button — added in Phase 3, manual trigger only
- Admin panel at localhost:3000/admin — password protected, localStorage backed

## Dashboard Columns (current, in order)
| Column | Description |
|--------|-------------|
| › | Tier 2 expand/collapse chevron |
| ⚡ | Alert flag — high conviction aligned signal |
| Ticker | Symbol |
| Description | Asset name |
| Asset Class | Classification |
| Sector | GICS sector / type |
| Close | Last closing price (real) |
| Trend | SVG sparkline — 60-day real price history |
| Viewpoint | Trade + Trend alignment summary |
| Conviction % | Probability score 0-100% |
| Trade Dir | Short-term direction |
| Trade LRR | Lower risk range - trade timeframe |
| Trade HRR | Higher risk range - trade timeframe |
| Trend Dir | Medium-term direction |
| Trend LRR | Support level - trend timeframe |

## Popup Fields (click any row)
Close, Viewpoint, Conviction, LT Dir, LT LRR, Trend LRR, Hurst(T), Rel IV%, Vol Signal, Updated

## Color Coding
- **`#00e5a0` green** — Bullish, high conviction, trending
- **`#ff4d6d` red** — Bearish, low conviction, mean-reverting
- **`#8899aa` grey** — Neutral (everywhere — not amber)
- **`#f0b429` amber** — Alerts, conviction bar, and WARNING state cells

---

## Version Control
- Git initialized at `C:\Users\shann\Projects\signal-matrix`
- First commit: `42e6663` — "Phase 1 complete - Tasks 1-5 - Dashboard + Admin Panel"
- `.env` excluded from Git via `.gitignore`
- `backend/signal_matrix.db` excluded from Git via `.gitignore`

### Git workflow
After any confirmed working state:
```
git add .
git commit -m "brief description"
```
Roll back if something breaks:
```
git checkout -- .
```

---

## Admin Panel
- **Route:** `localhost:3000/admin` — hidden, not in main nav
- **Access:** Password from `.env` → `REACT_APP_ADMIN_PASSWORD`
- **After changing `.env`:** Must restart Docker container (not just hot reload)
- **Never hardcode the password in source code**
- **Persistence:** localStorage key `sm_tickers`
- **Never hard delete tickers** — use `active: false` (soft deactivate)

---

## Environment Variables
`.env` file at project root — never commit this file:
```
REACT_APP_ADMIN_PASSWORD=yourpassword
```

---

## Project Rules — Read Before Making Changes
1. **Never modify the ticker universe without explicit instruction**
2. **Never hardcode passwords, API keys, or secrets** — always use `.env`
3. **Never hard delete tickers** — use `active: false`
4. **Direction values are Bullish / Bearish / Neutral** — never Up / Down
5. **HRR = Higher Risk Range** — always the higher price value — do not rename
6. **LRR = Lower Risk Range** — always the lower price value — do not rename
7. **Neutral color is `#8899aa` grey** — amber `#f0b429` is for alerts and WARNING state cells only
8. **Asset Class values must exactly match:** Domestic Equities | Domestic Fixed Income | Digital Assets | Foreign Exchange | International Equities | Commodities
9. **Keep components modular** — one component per file
10. **Docker:** changes to `src/` reflect on save — no rebuild needed for frontend
11. **Do not modify** `docker-compose.yml`, `Dockerfile`, or `package.json` without flagging first
12. **Phase 3 signal calculations are now in scope** — implement per spec above, no deviations
13. **Flag all [OPEN] items** before implementing — do not assume defaults
14. **Commit to Git** after every confirmed working state
15. **Neo = Claude Code** (VS Code extension) — all code changes go here
16. **No worktrees or feature branches** — all changes committed directly to master
17. **Never auto-fetch from Yahoo Finance** — REFRESH DATA button only
18. **Never auto-calculate signals** — CALCULATE SIGNALS button only
19. **`backend/signal_matrix.db` must never be committed to Git**
20. **C is the invalidation level** — not LRR. Break of Trade/Trend fires on price closing through C.

---

## Roadmap

| Phase | Description | Status |
|---|---|---|
| Phase 1 | Dashboard Refinement | ✅ Complete |
| Phase 2 | Real Data Integration | ✅ Complete |
| Phase 3 | Signal Engine | 🔄 In Progress |
| Phase 4 | Backend & Database | ⬜ Python FastAPI, SQLite, EOD scheduler, signal history |
| Phase 5 | Schwab API | ⬜ OAuth, real-time streaming, options IV |
| Phase 6 | Cloud Deployment | ⬜ Supabase, cloud provider, remote access |

---

## What Is NOT In Scope Yet
- Schwab API (real-time streaming, options IV)
- Supabase / PostgreSQL cloud database
- Quad Tracker dashboard
- Cloud deployment
- Tier 2 auto-surfacing based on conviction threshold
- MA20/50/100 display in dashboard UI

---

## Ticker Universe — Tier 1 (48 tickers, STATIC)

```javascript
const tickers = [
  // DOMESTIC EQUITIES — Index
  { ticker: "SPX",   description: "S&P 500 Index",                        assetClass: "Domestic Equities", sector: "Index",                    tier: 1, parentTicker: null, active: true, displayOrder: 1  },
  { ticker: "NDX",   description: "Nasdaq 100 Index",                     assetClass: "Domestic Equities", sector: "Index",                    tier: 1, parentTicker: null, active: true, displayOrder: 2  },
  { ticker: "$DJI",  description: "Dow Jones Industrial Avg",             assetClass: "Domestic Equities", sector: "Index",                    tier: 1, parentTicker: null, active: true, displayOrder: 3  },
  { ticker: "VIX",   description: "CBOE Volatility Index",                assetClass: "Domestic Equities", sector: "Index",                    tier: 1, parentTicker: null, active: true, displayOrder: 4  },
  { ticker: "SPY",   description: "SPDR S&P 500 ETF",                     assetClass: "Domestic Equities", sector: "Broad Market",             tier: 1, parentTicker: null, active: true, displayOrder: 5  },
  { ticker: "QQQ",   description: "Invesco Nasdaq 100 ETF",               assetClass: "Domestic Equities", sector: "Broad Market",             tier: 1, parentTicker: null, active: true, displayOrder: 6  },
  { ticker: "IWM",   description: "iShares Russell 2000 ETF",             assetClass: "Domestic Equities", sector: "Broad Market",             tier: 1, parentTicker: null, active: true, displayOrder: 7  },
  { ticker: "XLK",   description: "Technology Select Sector",             assetClass: "Domestic Equities", sector: "Technology",               tier: 1, parentTicker: null, active: true, displayOrder: 8  },
  { ticker: "XLF",   description: "Financial Select Sector",              assetClass: "Domestic Equities", sector: "Financials",               tier: 1, parentTicker: null, active: true, displayOrder: 9  },
  { ticker: "XLE",   description: "Energy Select Sector",                 assetClass: "Domestic Equities", sector: "Energy",                   tier: 1, parentTicker: null, active: true, displayOrder: 10 },
  { ticker: "XLV",   description: "Health Care Select Sector",            assetClass: "Domestic Equities", sector: "Health Care",              tier: 1, parentTicker: null, active: true, displayOrder: 11 },
  { ticker: "XLI",   description: "Industrials Select Sector",            assetClass: "Domestic Equities", sector: "Industrials",              tier: 1, parentTicker: null, active: true, displayOrder: 12 },
  { ticker: "XLY",   description: "Consumer Discr. Select Sector",        assetClass: "Domestic Equities", sector: "Consumer Discretionary",   tier: 1, parentTicker: null, active: true, displayOrder: 13 },
  { ticker: "XLP",   description: "Consumer Staples Select Sector",       assetClass: "Domestic Equities", sector: "Consumer Staples",         tier: 1, parentTicker: null, active: true, displayOrder: 14 },
  { ticker: "XLB",   description: "Materials Select Sector",              assetClass: "Domestic Equities", sector: "Materials",                tier: 1, parentTicker: null, active: true, displayOrder: 15 },
  { ticker: "XLU",   description: "Utilities Select Sector",              assetClass: "Domestic Equities", sector: "Utilities",                tier: 1, parentTicker: null, active: true, displayOrder: 16 },
  { ticker: "XLRE",  description: "Real Estate Select Sector",            assetClass: "Domestic Equities", sector: "Real Estate",              tier: 1, parentTicker: null, active: true, displayOrder: 17 },
  { ticker: "XLC",   description: "Communication Services Select Sector", assetClass: "Domestic Equities", sector: "Communication Services",   tier: 1, parentTicker: null, active: true, displayOrder: 18 },
  { ticker: "AAPL",  description: "Apple Inc.",                           assetClass: "Domestic Equities", sector: "Technology",               tier: 1, parentTicker: null, active: true, displayOrder: 19 },
  { ticker: "MSFT",  description: "Microsoft Corp.",                      assetClass: "Microsoft Corp.",   sector: "Technology",               tier: 1, parentTicker: null, active: true, displayOrder: 20 },
  { ticker: "NVDA",  description: "NVIDIA Corp.",                         assetClass: "Domestic Equities", sector: "Technology",               tier: 1, parentTicker: null, active: true, displayOrder: 21 },
  { ticker: "AVGO",  description: "Broadcom Inc.",                        assetClass: "Domestic Equities", sector: "Technology",               tier: 1, parentTicker: null, active: true, displayOrder: 22 },
  { ticker: "GOOGL", description: "Alphabet Inc.",                        assetClass: "Domestic Equities", sector: "Communication Services",   tier: 1, parentTicker: null, active: true, displayOrder: 23 },
  { ticker: "META",  description: "Meta Platforms Inc.",                  assetClass: "Domestic Equities", sector: "Communication Services",   tier: 1, parentTicker: null, active: true, displayOrder: 24 },
  { ticker: "NFLX",  description: "Netflix Inc.",                         assetClass: "Domestic Equities", sector: "Communication Services",   tier: 1, parentTicker: null, active: true, displayOrder: 25 },
  { ticker: "AMZN",  description: "Amazon.com Inc.",                      assetClass: "Domestic Equities", sector: "Consumer Discretionary",   tier: 1, parentTicker: null, active: true, displayOrder: 26 },
  { ticker: "TSLA",  description: "Tesla Inc.",                           assetClass: "Domestic Equities", sector: "Consumer Discretionary",   tier: 1, parentTicker: null, active: true, displayOrder: 27 },
  { ticker: "SMH",   description: "VanEck Semiconductor ETF",             assetClass: "Domestic Equities", sector: "Factor",                   tier: 1, parentTicker: null, active: true, displayOrder: 28 },
  { ticker: "CIBR",  description: "First Trust Cybersecurity ETF",        assetClass: "Domestic Equities", sector: "Factor",                   tier: 1, parentTicker: null, active: true, displayOrder: 29 },
  { ticker: "GRID",  description: "First Trust Clean Edge Smart Grid",    assetClass: "Domestic Equities", sector: "Factor",                   tier: 1, parentTicker: null, active: true, displayOrder: 30 },
  { ticker: "QTUM",  description: "Defiance Quantum ETF",                 assetClass: "Domestic Equities", sector: "Factor",                   tier: 1, parentTicker: null, active: true, displayOrder: 31 },
  { ticker: "ROBO",  description: "ROBO Global Robotics & Auto ETF",      assetClass: "Domestic Equities", sector: "Factor",                   tier: 1, parentTicker: null, active: true, displayOrder: 32 },
  { ticker: "SATS",  description: "ETF Series Space & Defense",           assetClass: "Domestic Equities", sector: "Factor",                   tier: 1, parentTicker: null, active: true, displayOrder: 33 },
  { ticker: "TLT",   description: "iShares 20+ Year Treasury Bond ETF",   assetClass: "Domestic Fixed Income", sector: "Treasury",            tier: 1, parentTicker: null, active: true, displayOrder: 34 },
  { ticker: "IBIT",  description: "iShares Bitcoin Trust ETF",            assetClass: "Digital Assets",    sector: "Cryptocurrency",           tier: 1, parentTicker: null, active: true, displayOrder: 35 },
  { ticker: "GLD",   description: "SPDR Gold Shares",                     assetClass: "Foreign Exchange",  sector: "Gold",                     tier: 1, parentTicker: null, active: true, displayOrder: 36 },
  { ticker: "USD",   description: "US Dollar Index",                      assetClass: "Foreign Exchange",  sector: "Currency",                 tier: 1, parentTicker: null, active: true, displayOrder: 37 },
  { ticker: "JPY",   description: "Japanese Yen / USD",                   assetClass: "Foreign Exchange",  sector: "Currency",                 tier: 1, parentTicker: null, active: true, displayOrder: 38 },
  { ticker: "KWEB",  description: "KraneShares CSI China Internet ETF",   assetClass: "International Equities", sector: "China",              tier: 1, parentTicker: null, active: true, displayOrder: 39 },
  { ticker: "EWJ",   description: "iShares MSCI Japan ETF",               assetClass: "International Equities", sector: "Japan",              tier: 1, parentTicker: null, active: true, displayOrder: 40 },
  { ticker: "EWW",   description: "iShares MSCI Mexico ETF",              assetClass: "International Equities", sector: "Mexico",             tier: 1, parentTicker: null, active: true, displayOrder: 41 },
  { ticker: "TUR",   description: "iShares MSCI Turkey ETF",              assetClass: "International Equities", sector: "Turkey",             tier: 1, parentTicker: null, active: true, displayOrder: 42 },
  { ticker: "UAE",   description: "iShares MSCI UAE ETF",                 assetClass: "International Equities", sector: "UAE",                tier: 1, parentTicker: null, active: true, displayOrder: 43 },
  { ticker: "USO",   description: "United States Oil Fund",               assetClass: "Commodities",       sector: "Energy",                   tier: 1, parentTicker: null, active: true, displayOrder: 44 },
  { ticker: "SLV",   description: "iShares Silver Trust",                 assetClass: "Commodities",       sector: "Precious Metals",          tier: 1, parentTicker: null, active: true, displayOrder: 45 },
  { ticker: "PALL",  description: "Aberdeen Physical Palladium",          assetClass: "Commodities",       sector: "Precious Metals",          tier: 1, parentTicker: null, active: true, displayOrder: 46 },
  { ticker: "CANE",  description: "Teucrium Sugar Fund",                  assetClass: "Commodities",       sector: "Agricultural",             tier: 1, parentTicker: null, active: true, displayOrder: 47 },
  { ticker: "WOOD",  description: "iShares Global Timber & Forestry ETF", assetClass: "Commodities",       sector: "Materials",                tier: 1, parentTicker: null, active: true, displayOrder: 48 },
  // TIER 2 — seed data
  { ticker: "XOP",   description: "SPDR S&P Oil & Gas Explor & Prod ETF", assetClass: "Commodities",       sector: "Energy",                   tier: 2, parentTicker: "USO",  active: true, displayOrder: 1 },
  { ticker: "OIH",   description: "VanEck Oil Services ETF",              assetClass: "Commodities",       sector: "Energy",                   tier: 2, parentTicker: "USO",  active: true, displayOrder: 2 },
  { ticker: "AMZN",  description: "Amazon.com Inc.",                      assetClass: "Domestic Equities", sector: "Consumer Discretionary",   tier: 2, parentTicker: "XLY",  active: true, displayOrder: 1 },
  { ticker: "SOXX",  description: "iShares Semiconductor ETF",            assetClass: "Domestic Equities", sector: "Technology",               tier: 2, parentTicker: "XLK",  active: true, displayOrder: 1 },
  { ticker: "SGOL",  description: "Aberdeen Physical Gold Shares ETF",    assetClass: "Foreign Exchange",  sector: "Gold",                     tier: 2, parentTicker: "GLD",  active: true, displayOrder: 1 },
];
```
