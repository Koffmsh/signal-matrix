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
- **yfinance:** v1.2.0 — do not downgrade (v0.2.x has persistent 429 block)
- **Dev environment:** Windows PC, Docker Desktop, VS Code, localhost:3000
- **Hot reload:** `WATCHPACK_POLLING=true` in docker-compose.yml
- **Claude Code:** `autoVerify: true` — verifies at localhost:3000 after every change
- **Claude in Chrome extension:** enabled and operational. Set to allow access to all sites including localhost:3000. When "started debugging this browser" banner appears in Chrome, do not click Cancel — leave it open so the debugger can attach and complete screenshot/page verification.
- **Yahoo Finance:** Manual REFRESH DATA button only — never auto-fetch on page load
- **Git:** No worktrees or feature branches — all changes committed directly to master
- **Version control:** Git initialized, first commit `42e6663` — "Phase 1 complete - Tasks 1-5"

---

## Known Fixes & Learnings

Critical issues already resolved — do not reintroduce these bugs:

### yfinance 1.2.0 — Do Not Downgrade
- v0.2.x had a persistent 429 block that could not be resolved by waiting
- v1.2.0 resolved it immediately — always use v1.2.0 or higher in `requirements.txt`

### tz-aware Date Comparison (`yahoo_finance.py`)
- yfinance 1.2.0 returns timezone-aware timestamps
- Old comparison `closes.index < pd.Timestamp(date.today())` crashes with tz-aware index
- **Fixed:** `closes.index.date < date.today()` — always use this pattern

### Stale Cache Fallback on 429 (`market_data.py`)
- Old behavior: batch endpoint returned empty on 429 — dashboard went blank
- **Fixed:** On 429, batch endpoint now serves whatever is cached in SQLite
- All 48 tickers stay visible even during rate limit windows

### `updated_at` Refreshes on Upsert (`market_data.py`)
- Old behavior: `updated_at` only stamped original insert date — never updated
- **Fixed:** Added `existing.updated_at = datetime.utcnow()` to upsert path
- Stamps actual fetch time on every successful refresh

### `updated_at` Format Consistent (`market_data.py`)
- **Fixed:** `row.updated_at.strftime("%m/%d/%y %H:%M")` — matches frontend expectation
- Do not use `str(row.updated_at)` — format mismatch breaks timestamp display

### EOD Timestamp Dynamic in Header (`App.js`)
- Old behavior: "EOD · 03/11/26" was hardcoded in JSX
- **Fixed:** Now reads from first ticker's `updated` field in `realDataMap`
- Never hardcode dates in JSX

### Cache Date Reset Pattern
- When `history_json` is NULL on existing rows (schema migration artifact), cache_date guard prevents re-fetch
- **Fix:** Reset all rows to `cache_date = '1970-01-01'` to force fresh fetch
- SQL: `UPDATE price_cache SET cache_date = '1970-01-01'`

### UTC vs ET Date in Docker — CRITICAL (Task 4.2)
- Docker containers run UTC. `date.today()` and `datetime.utcnow().date()` return UTC date.
- After ~8 PM ET (midnight UTC), UTC date flips to the next day while ET date has not.
- **Three places this causes bugs:**
  1. `cache_date` in `price_cache` — stored as UTC, checked as UTC → cache miss after 8 PM ET
  2. `run_date` in `scheduler_log` — stored as UTC, checked as UTC → `today_complete` returns false
  3. NYSE trading day check — should always use ET date (NYSE operates on ET)
- **Fix:** Use ET date everywhere. Pattern:
  ```python
  from zoneinfo import ZoneInfo
  from datetime import datetime
  _ET = ZoneInfo("America/New_York")
  today_et = datetime.now(_ET).strftime("%Y-%m-%d")   # for string storage
  today_et = datetime.now(_ET).date()                  # for date object
  ```
- **Files fixed:** `backend/routers/market_data.py`, `backend/services/scheduler.py`, `backend/routers/scheduler.py`
- **Do not use** `date.today()`, `str(date.today())`, or `datetime.utcnow().date()` for any date that represents a trading day or cache key

## Project Folder Structure
```
signal-matrix/
├── .claude/
│   ├── launch.json
│   └── settings.local.json
├── Docs/
│   ├── SignalMatrix_Spec_v1.4.docx        ← current spec
│   └── QuadTracker_Spec_v1.1.docx
├── public/
├── src/
│   ├── components/
│   │   ├── Admin/
│   │   │   └── AdminPanel.js              ← Tasks 4.6/4.7 — ticker CRUD + yfinance lookup
│   │   ├── Dashboard/                     ← placeholder, logic still in App.js
│   │   └── shared/                        ← placeholder
│   ├── data/
│   │   └── tickers.js                     ← Seed data only — source of truth is SQLite tickers table
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
│   │   ├── price_cache.py
│   │   ├── signal_hurst.py                ← Task 3.1 — Hurst DB model
│   │   ├── signal_pivots.py               ← Task 3.2 — Pivots DB model
│   │   ├── signal_output.py               ← Task 3.3 — Output DB model
│   │   └── scheduler_log.py               ← Task 4.2 — Scheduler run log DB model
│   ├── services/
│   │   ├── yahoo_finance.py
│   │   ├── signal_engine.py               ← Task 3.1 — Hurst + Fractal Dimension (DFA) ✅
│   │   ├── pivot_engine.py                ← Task 3.2 — ABC Pivot Detector ✅
│   │   ├── conviction_engine.py           ← Task 3.3 — LRR/HRR + Conviction Engine ✅
│   │   └── scheduler.py                   ← Task 4.2 — APScheduler EOD job ✅
│   └── routers/
│       ├── market_data.py
│       ├── signals.py                     ← Task 3.3/3.4 — Signal endpoints ✅
│       ├── scheduler.py                   ← Task 4.2 — Scheduler status endpoint ✅
│       └── tickers.py                     ← Task 4.6/4.7 — Ticker CRUD + yfinance lookup ✅
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
## Phase 2 — COMPLETE ✅
## Phase 3 — COMPLETE ✅
## Phase 4 — IN PROGRESS 🔄

### Phase 3 Build Sequence

| Task | Deliverable | File | Status |
|---|---|---|---|
| 3.1 | Hurst + Fractal Dimension (DFA) | `backend/services/signal_engine.py` | ✅ Complete |
| 3.2 | ABC Pivot Detector | `backend/services/pivot_engine.py` | ✅ Complete |
| 3.3 | LRR/HRR + Conviction Engine | `backend/services/conviction_engine.py` | ✅ Complete |
| 3.4 | Wire to Dashboard | `src/App.js` | ✅ Complete |

### New Button — CALCULATE SIGNALS
- Added to dashboard header alongside REFRESH DATA
- Manual trigger only — never auto-calculates on page load
- Must be run AFTER REFRESH DATA (price history must be current)
- Calls: `/api/signals/hurst` → `/api/signals/pivots` → `/api/signals/output` in sequence
- Signal engine reads from `price_cache` SQLite table — NEVER calls yfinance directly

---

## Phase 4 — Task 4.6: Tickers Table + Dynamic Backend ✅

### Overview
- SQLite `tickers` table is the source of truth — replaces `tickers.js` + localStorage
- `tickers.js` retained as seed-only bootstrap file — never modified directly
- `seed_tickers_if_empty(db)` runs on FastAPI startup — inserts 52 rows if table is empty (AMZN excluded from Tier 2 seed due to UNIQUE constraint, add via admin if needed)
- `market_data.py` and `signals.py` both call `get_active_tickers(db)` — no hardcoded list
- `App.js` fetches ticker universe from `GET /api/tickers?active=true` on mount

### Tickers API Endpoints
```
GET    /api/tickers              ← list all (active filter optional; admin fetches all)
POST   /api/tickers              ← create new ticker (409 if exists)
PUT    /api/tickers/{symbol}     ← update any field
DELETE /api/tickers/{symbol}     ← soft-delete (active=false) — never hard-delete
GET    /api/tickers/lookup/{sym} ← Task 4.7: yfinance suggestions (registered BEFORE /{symbol})
```

### Field Mapping
| DB / API | React state | Notes |
|---|---|---|
| `ticker` | `ticker` | Locked after creation |
| `description` | `description` | |
| `asset_class` | `assetClass` | |
| `sector` | `sector` | |
| `tier` | `tier` | 1 or 2 |
| `parent_ticker` | `parentTicker` | Tier 2 only |
| `active` | `active` | Soft-delete flag |
| `display_order` | `displayOrder` | |

### Admin Panel UX (Task 4.6/4.7)
- Add ticker: click `+ ADD TICKER` → type symbol → optionally click `LOOK UP` → edit cells → click `SAVE` (or Enter)
- Lookup pre-fills empty fields only — never overwrites existing values
- `_isNew` local flag: row posts on SAVE; existing rows PUT on any cell commit
- `newTickerValues` state tracks keystroke input independently to prevent focus loss on re-render
- Ticker cell locked (disabled) after row is saved — symbol cannot be changed
- Deactivate: soft-delete via DELETE API; Reactivate: PUT with `active: true`

### Task 4.7 — yfinance Lookup
- `GET /api/tickers/lookup/{symbol}` — calls yfinance, returns `{found, suggestions, already_exists, notes}`
- Returns: `description` (longName), `asset_class` (mapped), `sector` (category)
- `_map_asset_class()` maps yfinance quoteType + category to Signal Matrix vocabulary
- ETF gold symbols hardcoded: GLD, IAU, SGOL, GLDM, BAR → "Foreign Exchange"
- Category keywords used (not quoteType alone) — covers edge cases like "Miscellaneous Region" → International
- Suggestions only — never auto-saves

---

## Phase 4 — Task 4.2: EOD Scheduler ✅

### Scheduler Overview
- APScheduler `AsyncIOScheduler` inside FastAPI lifespan
- Fires at **4:15 PM ET** on NYSE trading days only (via `pandas_market_calendars`)
- On startup: catch-up check — if past 4:15 PM ET, trading day, and no successful run today → runs immediately
- All dates use **ET timezone** — never UTC (see UTC vs ET fix above)

### Scheduler Files
| File | Role |
|---|---|
| `backend/services/scheduler.py` | Core job logic, catch-up, start/shutdown |
| `backend/routers/scheduler.py` | `GET /api/scheduler/status` endpoint |
| `backend/models/scheduler_log.py` | SQLAlchemy model for `scheduler_log` table |

### scheduler_log Table
```sql
id, run_date (ET), trigger ('scheduled'|'catchup'|'manual'),
status ('success'|'failure'), refresh_ok, signals_ok,
error_msg, duration_s, created_at (UTC string)
```

### Scheduler Status Endpoint
`GET /api/scheduler/status` — returns last run info, next scheduled time, `today_complete` flag.
Read-only, no recalculation.

### Dashboard Header — Scheduler Indicator
`● SCHED` dot next to `● LIVE`:
- **Green** — today's EOD run complete (`today_complete = true`)
- **Amber** — scheduled, not yet run today
- **Red** — last run failed
- Hover tooltip shows run time or next scheduled time. Fetched once on page load, no polling.

### Refactors Made for Scheduler
- `refresh_data(db)` extracted from `get_batch` endpoint in `market_data.py` — callable directly
- `run_hurst(db)`, `run_pivots(db)`, `run_output(db)`, `calculate_signals(db)` extracted in `signals.py`
- HTTP endpoints now call these functions — behavior unchanged
- `main.py` converted from module-level startup to `lifespan` context manager

### FastAPI Endpoints (Phase 4)
```
GET /api/scheduler/status         ← Task 4.2 ✅  (read-only status)
GET /api/tickers                  ← Task 4.6 ✅  (list all, optional ?active filter)
POST /api/tickers                 ← Task 4.6 ✅  (create)
PUT /api/tickers/{symbol}         ← Task 4.6 ✅  (update)
DELETE /api/tickers/{symbol}      ← Task 4.6 ✅  (soft-delete)
GET /api/tickers/lookup/{symbol}  ← Task 4.7 ✅  (yfinance suggestions)
```

---

## Signal Engine Math — Phase 3 (ALL DECISIONS LOCKED)

### Hurst Exponent (H)
- **Method: DFA (Detrended Fluctuation Analysis)**
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

CRITICAL: Conviction is BLANK (not calculated) when Viewpoint = Neutral
```

**Long Term H (756-day):** calculated and stored, displayed in popup as context only.
Not used in conviction formula.

### Direction Determination — Pivots Only (H has NO role)

**H does not determine direction. H drives conviction and LRR position only.**

```python
# Uptrend validity — price must be above higher of LRR or C
effective_floor = max(lrr, c)
if price > effective_floor:
    trade_dir = "Bullish"
else:
    trade_dir = "Neutral"

# Downtrend validity — price must be below lower of HRR or C
effective_ceiling = min(hrr, c)
if price < effective_ceiling:
    trade_dir = "Bearish"
else:
    trade_dir = "Neutral"

# Viewpoint — three states only
if trade_dir == "Bullish" and trend_dir == "Bullish":
    viewpoint = "Bullish"
elif trade_dir == "Bearish" and trend_dir == "Bearish":
    viewpoint = "Bearish"
else:
    viewpoint = "Neutral"
```

| Condition | Direction |
|---|---|
| Price above MAX(LRR, C) — valid uptrend | Bullish |
| Price below MIN(HRR, C) — valid downtrend | Bearish |
| Break of Trade (price closes through C) | Neutral |
| FORMING — no new C confirmed yet | Neutral |
| Insufficient pivot history | Neutral |
| Everything else | Neutral |

### LRR / HRR Display — Always Show

LRR and HRR always calculate and always display regardless of viewpoint.
Color communicates the state:
- Bullish viewpoint → green
- Bearish viewpoint → red
- Neutral viewpoint → grey (`#8899aa`)

### Viewpoint States — FINAL (LOCKED)

| Viewpoint | Condition | Conviction |
|---|---|---|
| **Bullish** | Trade Bullish + Trend Bullish | Calculated normally |
| **Bearish** | Trade Bearish + Trend Bearish | Calculated normally |
| **Neutral** | Any other combination — including one Neutral, one Bullish/Bearish, or opposite directions | BLANK |

**No Diverging state.** Three states only: Bullish, Bearish, Neutral.

### Alert Flag ⚡ Trigger (ALL THREE must be true)
1. Trade H > 0.55 AND Trend H > 0.55
2. Viewpoint = Bullish OR Bearish (never fires on Neutral)
3. Final Conviction ≥ 70%

### The Four Trading Scenarios

**Scenario 1 — Bearish Trend + Bearish Trade (Aligned Short)**
- Viewpoint = Bearish
- Add to short: price near or at HRR (entry zone on bounce)
- Remove short: Trade or Trend breaks (price closes above C)

**Scenario 2 — Bearish Trend, Trade Turning**
- Viewpoint = Neutral
- Trade breaks upward: higher low C forms, price closes above B on trade timeframe
- Either continues (→ Scenario 3) or Trade fails and breaks back below new C

**Scenario 3 — Bullish Trend + Bullish Trade (Aligned Long)**
- Viewpoint = Bullish
- Add to long: price near or at LRR
- Lighten long: price approaching HRR
- Remove long: Trade or Trend breaks (price closes below C)

**Scenario 4 — Bullish Trend, Trade Breaking Down**
- Viewpoint = Neutral (Trade broken, Trend still Bullish)
- Trade Dir flips to Neutral immediately on close below C
- LRR/HRR still show — displayed grey
- Watch for Trend break (price closes below Trend C)

### ABC Pivot Structure

**Uptrend:**
```
A = pivot low   (e.g. $100)
B = pivot high  (e.g. $110)  — higher high
C = higher low  (e.g. $105)  — C > A confirms uptrend
D = running high             — established when price closes above B
```

**Downtrend (mirror):**
```
A = pivot high  (e.g. $100)
B = pivot low   (e.g. $90)   — lower low
C = lower high  (e.g. $95)   — C < A confirms downtrend
D = running low              — established when price closes below B
```

**Pivot detection bar windows:**
- Trade: **5 bars** (before AND after — both sides required)
- Trend: 20 bars (before AND after — both sides required)
- Long Term: 90 bars (before AND after — both sides required)

**CRITICAL — Pivot confirmation requires bar_window bars on BOTH sides:**
```python
# Pivot high at index i:
prices[i] == max(prices[i - bar_window : i + bar_window + 1])

# Pivot low at index i:
prices[i] == min(prices[i - bar_window : i + bar_window + 1])

# NEVER confirm a pivot without full bar_window on both sides
# This means the most recent bar_window bars can never be confirmed pivots
# D is always a running value — never a confirmed pivot
```

**CRITICAL — Today's bar must be excluded:**
```python
# Strip incomplete bars before running pivot detection
today = pd.Timestamp(date.today())
prices = prices[prices.index < today]
```

### C Update Logic — CRITICAL

**C is NOT set once and frozen. C updates dynamically as the trend develops.**

```python
# After initial C is confirmed, on every calculation run:

# UPTREND — C walks UP (higher lows)
new_pivot_low = find_most_recent_confirmed_pivot_low(prices, bar_window)
if new_pivot_low > current_C:
    current_C = new_pivot_low  # Update to higher low

# DOWNTREND — C walks DOWN (lower highs)
new_pivot_high = find_most_recent_confirmed_pivot_high(prices, bar_window)
if new_pivot_high < current_C:
    current_C = new_pivot_high  # Update to lower high

# Break of trade always uses CURRENT C — never stale C
if direction == UPTREND and current_price < current_C:
    state = BREAK_OF_TRADE

if direction == DOWNTREND and current_price > current_C:
    state = BREAK_OF_TRADE
```

**Why this matters:** A stale C means LRR is anchored to an old pivot, break levels are wrong,
and conviction is understated. C must always reflect the most recent confirmed higher low
(uptrend) or lower high (downtrend).

**Example — GLD trade timeframe:**
```
Initial C = $427.13  Feb 2    (first confirmed higher low)
Updated C = $448.20  Feb 17   (new higher low — C walks up)
Break of trade = price closes below $448.20 (current C)
NOT $427.13 (stale C)
```

### LRR / HRR — Naming Convention
- **LRR = always the lower price value**
- **HRR = always the higher price value**

**Uptrend:** Enter at LRR, target HRR (above D)
**Downtrend:** Enter at HRR (bounce), target LRR (below D)

### LRR Formula — Uptrend
```
Base LRR = C + (B − C) × H_factor

H_factor lookup:
  H > 0.65        →  0.95  (near B — strong trend)
  H 0.55 – 0.65   →  0.50  (midpoint — moderate trend)
  H 0.50 – 0.55   →  0.05  (near C — weak trend)
  H < 0.50        →  0.00  (default to C — LRR shows grey, no valid H signal)
```

LRR always calculates and always displays. H < 0.50 defaults LRR to C, shown in grey.

### HRR Formula — Uptrend
```
Base HRR = D + (1σ of recent returns)

HRR vs prior D interpretation:
  HRR well above prior D → full conviction, full size
  HRR near prior D       → moderate conviction, reduced size
  HRR below prior D      → caution confirmed, minimum size
```

### Downtrend Mirror Formulas
```
Base HRR = C − (C − B) × H_factor   ← entry on bounce (higher price)
Base LRR = D − (1σ of recent returns) ← profit target (lower price)
```

### Rel IV Scaling (ATR Equivalent)
IV scales LRR/HRR width — behaves like ATR expanding and contracting with volatility.

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
| UPTREND_VALID / DOWNTREND_VALID | C > A, price above MAX(LRR, C) | C < A, price below MIN(HRR, C) | Normal green/red |
| FORMING | Pullback from D, no new C yet | Bounce from D, no new C yet | LRR/HRR update, grey |
| EXTENDED | Price above D, new C not formed | Price below D, new C not formed | LRR/HRR shown, grey |
| WARNING | LRR drifted below C (IV-driven only) | HRR drifted above C (IV-driven only) | LRR or HRR cell → amber |
| BREAK_OF_TRADE | Price closes below C (trade tf) | Price closes above C (trade tf) | Trade Dir → Neutral, LRR/HRR grey |
| BREAK_OF_TREND | Price closes below C (trend tf) | Price closes above C (trend tf) | Trend Dir → Neutral, Trend LRR grey |
| NO_STRUCTURE | Insufficient pivot history | Insufficient pivot history | LRR/HRR grey |

**Critical rules:**
- **C is the line in the sand** — Break of Trade/Trend fires on price closing through C
- **Break of Trade = Trade Dir → Neutral immediately** — no intermediate state
- **WARNING state is IV-driven only** — never price-driven
- **LRR/HRR always show** — color reflects state (green/red/grey)
- **Effective floor (uptrend) = MAX(LRR, C)** — Bullish only when price above this
- **Effective ceiling (downtrend) = MIN(HRR, C)** — Bearish only when price below this
- **Direction determined by pivots only** — H has no role
- **Trade and Trend states are independent** — Trend break does not auto-flip Trade
- **C updates dynamically** — always references most recent confirmed higher low / lower high

### Database Tables (Phase 3)
```sql
signal_hurst:   ticker, h_trade, h_trend, h_lt, d_trade, d_trend, d_lt, calculated_at
                UNIQUE(ticker)

signal_pivots:  ticker, timeframe, bar_window,
                pivot_a, pivot_b, pivot_c, pivot_d,
                pivot_a_date, pivot_b_date, pivot_c_date, pivot_d_date,
                structural_state, calculated_at
                UNIQUE(ticker, timeframe)

signal_output:  ticker, timeframe, lrr, hrr, structural_state,
                trade_direction, conviction, h_value,
                viewpoint, alert, vol_signal,
                warning,                    ← IV-driven WARNING flag (per timeframe)
                lrr_warn, hrr_warn,         ← price-based pivot threshold flags (per timeframe)
                pivot_b, pivot_c,           ← pivot values for UI comparison
                calculated_at
                UNIQUE(ticker, timeframe)
```

### FastAPI Endpoints (Phase 3)
```
GET /api/signals/hurst    ← Task 3.1 ✅
GET /api/signals/pivots   ← Task 3.2 ✅
GET /api/signals/output   ← Task 3.3 ✅  (recalculates + writes to DB)
GET /api/signals/stored   ← Task 3.4 ✅  (read-only, grouped by ticker, used on page load)
```

### Sanity Checks
| Ticker | Expected H(Trade) | Rationale |
|---|---|---|
| SPY | 0.50–0.65 | Broad market — moderate trend |
| GLD | 0.60–0.75 | Strong persistent trend |
| VIX | 0.30–0.45 | Mean-reverting by nature |
| TLT | 0.45–0.60 | Range-bound recently |

---

## Data Layer

### Rules
- Signal engine NEVER calls yfinance directly — always reads from `price_cache` table
- REFRESH DATA populates the cache — CALCULATE SIGNALS reads from it
- Same-day cache invalidation — stale rows reset before re-fetch
- Price history excludes today's incomplete bar before pivot detection

### tickers.js — Tier 1 (48 tickers, STATIC)
Do not modify without explicit instruction. Source of truth for ticker universe.

---

## Methodology Reference

### Timeframes
- **Trade** — ≤ 3 weeks — entry/exit timing
- **Trend** — ≤ 3 months — directional bias filter
- **Long Term** — 3 years — macro structural context (display/context only)

### Signal Components
1. **Fractal Dimension (D)** — D→1.0 trending, D→1.5 choppy, D→2.0 mean-reverting. D = 2 − H
2. **Hurst Exponent (H)** — H>0.5 trending, H<0.5 mean-reverting, H=0.5 random walk. Method: DFA
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
| Conviction Score | **Frequentist** | Signal profile historically hit HRR frequency |
| LRR / HRR Ranges | **Frequentist** | Anchored to Gaussian sigma bands and pivot points |
| Quad Probability Distribution | **Bayesian** | Continuously updated belief across 4 quads |
| Forward Quarter Projections Q2-Q4 | **Bayesian** | Prior decay without new confirming evidence |
| Policy Signal Modifiers | **Bayesian** | Discrete evidence updates to forward projections |

---

## Dashboard — Current State
- React app running at localhost:3000 via Docker
- Close prices: real — from Yahoo Finance via FastAPI
- Sparklines: real — 60-day price history
- Rel IV: real — realized vol percentile proxy (Schwab IV Percentile in Phase 5)
- Volume: real — daily volume from Yahoo Finance
- Signal columns: **live** — populated from `/api/signals/stored` on page load; recalculated on CALCULATE SIGNALS
- REFRESH DATA: manual fetch only, never auto on page load
- CALCULATE SIGNALS: manual trigger only, reads from price_cache
- Admin panel at localhost:3000/admin — password protected

## Dashboard Columns (current, in order)
| Column | Description |
|--------|-------------|
| › | Tier 2 expand/collapse chevron |
| ⚡ | Alert flag — hover tooltip describes trigger conditions |
| Ticker | Symbol |
| Description | Asset name |
| Close | Last closing price (real) |
| Trend | SVG sparkline — 60-day real price history |
| Viewpoint | Bullish / Bearish / Neutral (three states only) |
| Conviction % | 0-100% — blank when Neutral; green ≥70%, amber 50-69%, grey <50% |
| Trade Dir | Short-term direction |
| Trade LRR | Lower risk range — color = trade direction; ⚠ when LRR < C (uptrend) or LRR > B (downtrend) |
| Trade HRR | Higher risk range — color = trade direction; ⚠ when HRR < B (uptrend) or HRR > C (downtrend) |
| Trend Dir | Medium-term direction |
| Trend LRR | Support level — color = trend direction; ⚠ when LRR < C (uptrend) or HRR > C (downtrend) |
| Asset Class | Classification — tightened badge, far right |
| Sector | GICS sector / type — tightened badge, far right |

## Popup Fields (click any row)
| Field | Notes |
|---|---|
| Close | Live price |
| Viewpoint | Bullish / Bearish / Neutral |
| Conviction | % or — when Neutral |
| Vol Signal | Confirming / Diverging / Neutral |
| Trade Dir | Direction + icon |
| Trade LRR | Color = trade dir; ⚠ + hover tooltip when warn |
| Trade HRR | Color = trade dir; ⚠ + hover tooltip when warn |
| Trade C | C pivot — trade invalidation level |
| Trade B | B pivot — prior swing high/low |
| Trade State | Structural state string |
| Trend Dir | Direction + icon |
| Trend LRR | Color = trend dir; ⚠ when LRR < C |
| Trend HRR | Color = trend dir; ⚠ when HRR > C |
| Trend C | C pivot — trend invalidation level |
| Trend State | Structural state string |
| LT Dir | Direction + icon |
| LT LRR | Color = LT direction |
| Hurst (T) | Trade timeframe H value |
| Hurst (Tr) | Trend timeframe H value |
| Hurst (LT) | Long term H value |
| Rel IV% | Realized vol percentile |
| Updated | Last data fetch timestamp |

## Color Coding
- **`#00e5a0` green** — Bullish direction, high conviction, trending H
- **`#ff4d6d` red** — Bearish direction, mean-reverting H
- **`#8899aa` grey** — Neutral direction/viewpoint (everywhere — not amber)
- **`#f0b429` amber** — ⚡ alerts, conviction bar 50-69%, WARNING state, ⚠ per-cell pivot breach

### LRR/HRR Cell Color Logic (LOCKED)
Each LRR/HRR cell uses its **own timeframe's direction** color, not the overall viewpoint:
- `dirRangeColor(dir, isWarn)` → amber if warn flag is true, otherwise `dirColor(dir)`
- Warn flags are price-based, independent of the IV-driven `warning` structural state

### Warning Flag Scope (LOCKED)
| Timeframe | LRR ⚠ condition | HRR ⚠ condition |
|---|---|---|
| **Trade** | Bullish: `lrr < c` · Bearish: `lrr > b` | Bullish: `hrr < b` · Bearish: `hrr > c` |
| **Trend** | Bullish: `lrr < c` only | Bearish: `hrr > c` only |
| **LT** | Never | Never |

---

## Version Control
- Git initialized at `C:\Users\shann\Projects\signal-matrix`
- Key commits:
  - `42e6663` — Phase 1 complete (Tasks 1-5)
  - `927f8ce` — Phase 3 Tasks 3.1 + 3.2
  - `28d6b71` — gitignore fix
  - `0b0c4e3` — Per-cell LRR/HRR warning flags + direction-based coloring
  - `ba1d7d6` — Pivot B/C in popup + ⚠ hover tooltips
  - `a90b1d1` — Warning scope: trade-only B-based, no LT warnings, LT popup trimmed
  - `4ab3208` — Task 4.2: EOD Scheduler (APScheduler + NYSE calendar)
  - `96346bc` — Fix scheduler run_date timezone (ET date, not UTC)
  - `0e510dd` — Fix cache_date timezone (ET date, not UTC)
  - `cd15150` — Task 4.6: Tickers table + dynamic backend + Task 4.7: yfinance lookup
- `.env` excluded from Git
- `backend/signal_matrix.db` excluded from Git
- `__pycache__` excluded from Git

### Git workflow
```
git add .
git commit -m "brief description"
git checkout -- .   # roll back if needed
```

---

## Admin Panel
- **Route:** `localhost:3000/admin` — hidden, not in main nav
- **Access:** Password from `.env` → `REACT_APP_ADMIN_PASSWORD`
- **After changing `.env`:** Must restart Docker container
- **Never hardcode the password in source code**
- **Never hard delete tickers** — use `active: false`

---

## Project Rules — Read Before Making Changes
1. **Never modify the ticker universe without explicit instruction**
2. **Never hardcode passwords, API keys, or secrets** — always use `.env`
3. **Never hard delete tickers** — use `active: false`
4. **Direction values are Bullish / Bearish / Neutral** — never Up / Down
5. **HRR = Higher Risk Range** — always the higher price value — do not rename
6. **LRR = Lower Risk Range** — always the lower price value — do not rename
7. **Neutral color is `#8899aa` grey** — amber `#f0b429` is for alerts, conviction 50-69%, WARNING state, and ⚠ per-cell pivot breach flags
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
20. **C is the invalidation level** — Break of Trade/Trend fires on price closing through C
21. **Signal engine never calls yfinance directly** — always reads from price_cache table
22. **Pivot confirmation requires bar_window bars on BOTH sides** — before AND after
23. **Today's incomplete bar must be excluded** before pivot detection runs
24. **C updates dynamically** — never stale, always most recent confirmed higher low / lower high
25. **Conviction is blank when Viewpoint = Neutral**
26. **Direction determined by pivots only** — H has no role in direction or viewpoint
27. **LRR/HRR always show** — grey when Neutral, green when Bullish, red when Bearish
28. **Viewpoint has three states only** — Bullish, Bearish, Neutral (no Diverging)
29. **Effective floor (uptrend) = MAX(LRR, C)** — Bullish only when price above this
30. **Effective ceiling (downtrend) = MIN(HRR, C)** — Bearish only when price below this
31. **LRR/HRR cell color = timeframe direction** — use `dirRangeColor(dir, isWarn)`, NOT viewpoint color
32. **Per-cell ⚠ warn flags are price-based** — separate from IV-driven `warning` structural state
33. **Warning scope is timeframe-specific** — Trade: full (C+B); Trend: C-based only; LT: none

---

## Roadmap

| Phase | Description | Status |
|---|---|---|
| Phase 1 | Dashboard Refinement | ✅ Complete |
| Phase 2 | Real Data Integration | ✅ Complete |
| Phase 3 | Signal Engine | ✅ Complete |
| Phase 4 | Backend & Database | 🔄 Tasks 4.2/4.6/4.7 complete — Task 4.4 (deploy) deferred |
| Phase 5 | Schwab API | ⬜ OAuth, real-time streaming, options IV |
| Phase 6 | Cloud Deployment | ⬜ Supabase, cloud provider, remote access |

---

## What Is NOT In Scope Yet
- Schwab API (real-time streaming, options IV)
- Supabase / PostgreSQL cloud database
- Quad Tracker dashboard
- Quad alignment column in Signal Matrix table (deferred to Quad Tracker phase)
- Cloud deployment
- Tier 2 auto-surfacing based on conviction threshold
- MA20/50/100 display in dashboard UI

---

## Ticker Universe — Tier 1 (48 tickers, STATIC)

```javascript
const tickers = [
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
  { ticker: "MSFT",  description: "Microsoft Corp.",                      assetClass: "Domestic Equities", sector: "Technology",               tier: 1, parentTicker: null, active: true, displayOrder: 20 },
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
