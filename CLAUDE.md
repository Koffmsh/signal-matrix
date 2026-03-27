# Signal Matrix Platform — Project Context

## Important Note for Neo
The `.docx` spec files in `Docs/` cannot be read by Claude Code.
Readable `.txt` copies exist:
- `Docs/SignalMatrix_Spec_v1.5.txt` — full platform spec (methodology, signal engine, architecture)
- `Docs/SignalMatrix_Phase5_Spec_v1.0.txt` — Phase 5 spec (Supabase, Fly.io, Schwab OAuth, IV)
Neo should read the relevant spec before making methodology or architecture changes.
CLAUDE.md remains the authoritative source for rules and current state.

---

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
- **Data:** EOD prices via Schwab Trader API (primary) / Yahoo Finance (fallback) — FastAPI backend
- **Backend:** Python FastAPI running at localhost:8000 (local) / api.signal.suttonmc.com (production)
- **Database:** Supabase (managed Postgres) in production — SQLite (`backend/signal_matrix.db`) for local dev only
- **yfinance:** v1.2.0 — do not downgrade (v0.2.x has persistent 429 block)
- **Dev environment:** Windows PC, Docker Desktop, VS Code, localhost:3000
- **Hot reload:** `WATCHPACK_POLLING=true` in docker-compose.yml
- **Claude Code:** `autoVerify: true` — verifies at localhost:3000 after every change
- **Claude in Chrome extension:** enabled and operational. Set to allow access to all sites including localhost:3000. When "started debugging this browser" banner appears in Chrome, do not click Cancel — leave it open so the debugger can attach and complete screenshot/page verification.
- **Yahoo Finance:** Manual REFRESH DATA button only — never auto-fetch on page load
- **Git:** No worktrees or feature branches — all changes committed directly to master
- **Version control:** Git initialized, first commit `42e6663` — "Phase 1 complete - Tasks 1-5"

---

## Infrastructure & Domain
- **Domain:** suttonmc.com — Cloudflare nameservers active (kinsley + kyrie)
- **Cloudflare:** Active — DNS management, DDoS protection, free SSL. No hosting.
- **Supabase:** Managed Postgres — project `signal-matrix`, US East, free tier
  - Project ID: wxqioudsteiwaazrgbao
  - Direct connection: port 5432 (Alembic migrations only)
  - Pooled connection: port 6543, Transaction mode (app runtime)
- **Fly.io:** Two apps — `signal-matrix-api` (512MB) + `signal-matrix-web` (256MB), region `iad`
  - signal-matrix-web → signal.suttonmc.com
  - signal-matrix-api → api.signal.suttonmc.com
  - auto_stop_machines = false on API app (scheduler must stay running)
- **Current hosting:** Local Docker (dev) + Fly.io (production) — Phase 5
- **Schwab App:** Signal Matrix — Production, Ready For Use
  - Callback URL: https://api.signal.suttonmc.com/api/auth/schwab/callback ✅ (updated — was signal.suttonmc.com, corrected to api subdomain)
  - Schwab portal status: "Modification Pending" — Schwab must approve before OAuth loop resolves (typically hours to 1-2 business days)
  - APIs: Accounts and Trading Production + Market Data Production
  - Order Limit: 0 (order execution not in scope)
- **ngrok:** Available for 1-off demos — `ngrok http 3000`

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
- All active tickers stay visible even during rate limit windows

### `updated_at` Refreshes on Upsert (`market_data.py`)
- Old behavior: `updated_at` only stamped original insert date — never updated
- **Fixed:** Added `existing.updated_at = datetime.utcnow()` to upsert path
- Stamps actual fetch time on every successful refresh

### `updated_at` Format and Timezone (`market_data.py`)
- `updated_at` is stored as UTC naive datetime via `datetime.utcnow()`
- Old display: `row.updated_at.strftime(...)` — formatted UTC directly, showed wrong date after 8 PM ET
- **Fixed:** `row.updated_at.replace(tzinfo=timezone.utc).astimezone(_ET).strftime("%m/%d/%y %H:%M")` in `serialize_cache_row`
- Do not use `str(row.updated_at)` — format mismatch breaks timestamp display
- Do not call `datetime.now(_ET)` at write time — store UTC, convert at display

### EOD Timestamp Dynamic in Header (`App.js`)
- Old behavior: "EOD · 03/11/26" was hardcoded in JSX
- **Fixed:** Now reads from first ticker's `updated` field in `realDataMap`
- Never hardcode dates in JSX

### `updated` Timestamp Uses ET in `yahoo_finance.py`
- Old behavior: `datetime.now()` in Docker returns UTC — after 8 PM ET the date flips to the next day
- **Fixed:** `datetime.now(_ET).strftime("%m/%d/%y %H:%M")` — always stamps ET time
- `_ET = ZoneInfo("America/New_York")` declared at module level in `yahoo_finance.py`

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

### FORMING State Does Not Override Direction (`conviction_engine.py`)
- FORMING state was incorrectly forcing `trade_dir = Neutral` via `max(lrr, c)` floor check
- **Fixed:** Direction determined solely by `price > c` (uptrend) / `price < c` (downtrend)
- FORMING only affects display (LRR/HRR color grey) — never direction
- **States that force Neutral:** `BREAK_OF_TRADE`, `BREAK_OF_TREND`, `NO_STRUCTURE` only
- FORMING, EXTENDED, WARNING, UPTREND_VALID, DOWNTREND_VALID all allow Bullish/Bearish
- LRR above current price during a FORMING pullback is expected — do not treat as a break

### ABC Pivot Search — All A Candidates Tried (`pivot_engine.py`)
- Old behavior: `_find_uptrend_abc` / `_find_downtrend_abc` used only the single nearest pivot low/high before B as A
- When the nearest A is above C (uptrend) or below C (downtrend), a valid ABC exists with an older A — but the engine was moving to the next C candidate instead
- **Fixed:** For each (C, B) pair, iterate all A candidates newest-first and stop at the first satisfying `C > A` (uptrend) or `C < A` (downtrend)
- **Example:** SPX trend — engine was finding A=10/10/25 (6552.51) which is above C=11/20/25 (6538.76), causing the uptrend check to fail; correct A is 04/08/25 (4982.77); old engine fell back to a stale ABC (C=10/10/25, 111 trading days) and fired NO_STRUCTURE
- **Rule:** Never assume the nearest A before B is the correct A — always scan all candidates

### OBV Pivot Engine Replaces Price-Momentum Proxy (`conviction_engine.py`)
- Old `_volume_signal` used 5-day / 20-day price momentum — not real volume
- **Replaced with:** `_build_obv` + `_obv_direction` — pivot-based OBV trend detection
- Volume history stored in `price_cache.volume_history_json` (aligned to `history_json` dates)
- OBV bar_window = 9 — requires confirmed pivots on both sides (same rule as price pivot engine)
- **Vol Signal compared against Trade Dir** (not Viewpoint) — volume is a short-term signal; confirming/diverging against the trade timeframe move is methodologically correct
- Confirming = OBV direction matches Trade Dir; Diverging = opposes Trade Dir; Neutral = OBV has no structure or Trade Dir is Neutral
- Conviction math unaffected: multiplier only applies when Viewpoint ≠ Neutral, where Trade Dir always equals Viewpoint anyway
- `obv_direction` (Vol Direction) + `obv_confirming` (Vol Signal) stored in `signal_output`, served via `/api/signals/stored`
- Phase 5 swap point flagged with `# PHASE 5 TODO` in `yahoo_finance.py` — OBV engine is source-agnostic

### VIX Regime Threshold — Green Cutoff is 20, Not 19 (`App.js`)
- Correct thresholds: `VIX < 20` → Green, `20 ≤ VIX < 30` → Amber, `VIX ≥ 30` → Red
- Bug: `App.js` line 568 was originally implemented with `vix < 19` — off by one on the green/amber boundary
- **Fixed:** Both ternary expressions on line 568 updated to `vix < 20` (color and label)
- **Do not** use 19 as the cutoff — VIX = 19 is investable territory, not choppy

### Vol Signal / Vol Direction — Popup Field Naming (`App.js`)
- Backend field `vol_signal` (Confirming/Diverging/Neutral) is the OBV-based conviction multiplier tier — "Vol" is the right label because it communicates meaning to the trader; OBV is the calculation method detail
- Popup shows two fields:
  - **Vol Direction** — raw OBV pivot trend direction: Bullish / Bearish / Neutral (maps to `obv_direction`)
  - **Vol Signal vs Trade** — Confirming ✓ / Diverging ✗ / Neutral — (maps to `obv_confirming`; compared against Trade Dir)
- The old duplicate "Vol Signal" row that appeared above OBV Direction was removed — it was a leftover from the price-momentum proxy era
- **Do not rename** `vol_signal` → `obv_signal` in the DB — "Vol Signal" is the correct trader-facing name

### Warning Tooltip — C Pivot Price Injected Inline (`App.js`)
- LRR/HRR ⚠ tooltips now include the C pivot value inline: e.g. `"LRR is below C ($448.20) — approaching trade invalidation level"`
- `warnTip(dir, which, cVal, bVal)` helper builds the tooltip string — formats price as `$X,XXX.XX`
- All 7 call sites (table rows + popup) pass `row.tradeC` / `row.tradeB` and `row.trendC` / `row.trendB`
- C and B pivot values flow from `signal_output.pivot_c` / `signal_output.pivot_b` via `mergeSignalData()` → `tradeC`, `tradeB`, `trendC`, `trendB`

### Filter UX — Dropdown Multi-Select (`App.js`)
- Asset Class button row replaced with `MultiSelectDropdown` component — compact, multi-select, count badge, click-outside-to-close
- New Sector dropdown added alongside Asset Class — same `MultiSelectDropdown` component
- Both dropdowns populate dynamically from the active ticker universe (no hardcoded values)
- Viewpoint, ALIGNED ONLY, and ALERTS filters unchanged (remain as buttons)
- Filters apply instantly on selection — no submit button

### ENTRY Signal Column — Null-Safe Sort Comparator (`App.js`)
- `entrySignal` is computed in the `ALL_DATA` useMemo pipeline: `"BUY"` | `"SELL"` | `null`
- **BUY conditions:** Viewpoint = Bullish AND Trade Dir = Bullish AND Trend Dir = Bullish AND `Math.abs(close - tradeLRR) / tradeLRR ≤ 0.02`
- **SELL conditions:** Viewpoint = Bearish AND Trade Dir = Bearish AND Trend Dir = Bearish AND `Math.abs(close - tradeHRR) / tradeHRR ≤ 0.02`
- Neutral viewpoint never triggers ENTRY signal regardless of price proximity
- Sort comparator must handle `null` — `typeof null === "object"` causes NaN on subtraction
- **Fix:** Null values explicitly sorted to bottom before string/numeric comparison in the sort function
- `ENTRY` count shown in header summary row alongside BULLISH / BEARISH / ALIGNED / ALERTS

### Schwab IV Unit Convention — Percentage In, Decimal Stored (`schwab_options.py`)
- Schwab `get_option_chain()` returns `volatility` as a percentage (e.g. `18.7` = 18.7%)
- **Must divide by 100** before writing to `iv_history.implied_vol` — stored as decimal (e.g. `0.187`)
- IV Percentile computed via `percentileofscore(252-day history, today_iv, kind='rank')` after writing today's row
- Cold start: returns `50` (neutral percentile) when fewer than 5 observations in `iv_history`
- Updates `price_cache.rel_iv` (replaces Yahoo proxy) + sets `price_cache.iv_source = 'schwab'`
- **Per-ticker fallback:** on any per-ticker error, leaves Yahoo proxy `rel_iv` intact and tags `iv_source = 'proxy'`
- **No-tokens fallback:** if Schwab token missing/expired, entire batch tagged `'proxy'` immediately — no options calls made
- `iv_source` exposed in `serialize_cache_row()` in `market_data.py` — popup label shows `IV% — schwab` or `IV% — proxy`

### Conviction Score Rebalance — Rel IV Removed
- Old weights: Trade H × 0.55 + Trend H × 0.25 + IV Score × 0.20
- **New weights:** Trade H × 0.65 + Trend H × 0.35
- Rel IV retained for LRR/HRR width scaling only — no longer in conviction formula
- Volume multiplier unchanged: Confirming × 1.15, Neutral × 1.00, Diverging × 0.80 (now OBV-driven)

### Supabase Direct Connection — IPv6 Only from Docker (`alembic/env.py`)
- `db.wxqioudsteiwaazrgbao.supabase.co:5432` resolves to **IPv6 only** inside the Docker container
- Docker Desktop on Windows does not route IPv6 egress — connection fails with "Network is unreachable"
- **Fix:** Use `SUPABASE_POOLED_CONNECTION_STRING` for all `alembic` CLI runs from Docker
- Pooled host (`aws-1-us-east-1.pooler.supabase.com:6543`) resolves to IPv4 and is reachable from Docker
- `alembic/env.py` prefers `SUPABASE_CONNECTION_STRING` but falls back to `SUPABASE_POOLED_CONNECTION_STRING` automatically
- **Do not** attempt alembic migrations via the direct connection string from inside Docker

### Supabase Runtime Uses psycopg2 Sync Engine — Not asyncpg (`database.py`)
- All FastAPI routers use synchronous SQLAlchemy (`Session`, `Depends(get_db)`) — asyncpg would require rewriting every router
- `database.py` converts `SUPABASE_POOLED_CONNECTION_STRING` (which has `postgresql+asyncpg://` prefix) to `postgresql+psycopg2://` via `_make_sync_url()`
- `_make_sync_url()` also URL-encodes the password — the Supabase password contains `@`, `#`, `/` characters that break standard URL parsing if raw
- **Do not** use `create_async_engine` or `AsyncSession` until a deliberate async migration is planned for all routers
- The `asyncpg` package is still in `requirements.txt` (Alembic dependency + future use) but is not used by the running app

### Fly.io Web App — Production Build Required (nginx, not CRA dev server)
- CRA dev server (`npm start`) exits immediately with code 0 on Fly.io Firecracker VMs (no TTY, headless)
- Root cause was two bugs stacked: (1) no `.dockerignore` → `COPY . .` overwrote Linux node_modules with Windows binaries → instant clean exit; (2) 256MB Firecracker VM too small for webpack compilation
- **Fix:** `Dockerfile.web.fly` uses a multi-stage build — `npm run build` on Depot's cloud builder (plenty of RAM), then `nginx:alpine` serves the static `build/` folder at runtime
- Image size: 23MB (vs 403MB dev server image)
- `REACT_APP_API_URL` is baked in at build time via Docker `ARG` + `ENV`, set in `fly.web.toml` `[build.args]`
- `REACT_APP_ADMIN_PASSWORD` must also be passed as a build arg — it is NOT available as a Fly.io runtime secret (React env vars bake in at build time)
- **Rule:** Never deploy CRA with `npm start` to Fly.io — always `npm run build` → nginx
- **Rule:** `.dockerignore` must always exclude `node_modules` — Windows binaries will crash Linux containers
- **Rule:** All web deploys must use `deploy-web.sh` — never bare `fly deploy` (password won't bake in)

### nginx SPA Routing — React Router 404 on Direct URL
- Default nginx config has no fallback rule — `/admin` and any non-root route returns 404 Not Found
- **Fix:** `nginx.conf` in project root with `try_files $uri $uri/ /index.html` — copied into image via `Dockerfile.web.fly`
- Requires `COPY nginx.conf /etc/nginx/conf.d/default.conf` in `Dockerfile.web.fly`
- **Rule:** Any new React route added to the app works automatically — no nginx changes needed

### Web Deploy Script — `deploy-web.sh`
- All web deploys run via `./deploy-web.sh` in project root — never bare `fly deploy`
- Script sources `.env` to pick up `REACT_APP_ADMIN_PASSWORD` and passes it as `--build-arg`
- `REACT_APP_API_URL` still set via `fly.web.toml` `[build.args]` — no duplication needed
- `deploy-web.sh` is safe to commit (reads from `.env`, contains no secrets)

### Fly.io Secrets — Special Characters in Passwords
- Fly.io's dotenv-style secret storage mangles passwords containing `#` (comment delimiter) and `$` (variable expansion)
- Password `k,/2#RY@Jma$8rw` stored as `SUPABASE_POOLED_CONNECTION_STRING` was silently truncated by `#`
- **Fix:** Store a pre-encoded `DATABASE_URL` secret where the password is already percent-encoded: `k%2C%2F2%23RY%40Jma%248rw` — no special chars to mangle
- `database.py` checks `DATABASE_URL` first, falls back to `SUPABASE_POOLED_CONNECTION_STRING` (with `_make_sync_url()` encoding pass)
- **Rule:** For any Fly.io secret containing `#`, `$`, `@`, `,`, or `/` in the password, pre-encode to percent-encoding before setting

### yfinance Asset Class Mapping — ETFs Default to Domestic Equities
- yfinance returns `quoteType: 'ETF'` for most ETFs but `category` is often empty or uses Morningstar taxonomy
- The mapping layer falls through to `Domestic Equities` default for international, fixed income, FX, and commodity ETFs
- **Fix:** `ASSET_CLASS_OVERRIDES` dict in `backend/routers/tickers.py` — checked first before any inference
- **Rule:** When adding new ETFs via admin panel, always verify asset class after lookup and correct if needed
- **Known good overrides already in place:** TLT, LQD, HYG, CLOX (Fixed Income); EWG, EWQ, EWP, KWT, KWEB, EWJ, EWW, TUR, UAE (International); GLD, SGOL, FXB, FXE, FXY (FX); USO, SLV, PALL, PPLT, CANE, WOOD, CORN, WEAT (Commodities); IBIT (Digital Assets)

### Futures Tickers — 3-File Checklist
Futures use continuous front-month symbols stored with a leading slash (e.g. `/CL`). Schwab does not serve continuous futures contracts via its standard quotes API, so all futures route through Yahoo Finance (which uses `XX=F` format for continuous series).

**When adding any new futures ticker:**
1. **`YAHOO_SYMBOL_MAP`** in `yahoo_finance.py` — add `"/XX": "XX=F"` mapping
2. **`SCHWAB_UNSUPPORTED`** in `schwab_market_data.py` — add `"/XX"` so it always routes to Yahoo
3. **`IV_INELIGIBLE`** in `schwab_options.py` — add `"/XX"` to skip options chain fetch

**Currently configured futures:**
- `/CL` → `CL=F` (WTI Crude Oil)
- `/ZN` → `ZN=F` (10-Year Treasury Note)
- `/GC` → `GC=F` (Gold)

**Admin panel note:** Ticker symbol stored with slash (e.g. `/CL`). The PUT/DELETE/lookup endpoints use `{symbol:path}` to allow slashes in URL paths.

**History fetch:** Schwab fetches 5-year history on bootstrap (< 252 bars cached), 3 months on subsequent daily updates. The merge logic in `_upsert` preserves existing long history when new data is shorter — prevents 3-month overwrite of 4-year history.

**Idempotency check:** Uses first Schwab-supported ticker (excludes `SCHWAB_UNSUPPORTED`) to avoid perpetual cache miss when a Yahoo-only ticker sorts first.

### Button Freshness Indicators — REFRESH DATA / CALCULATE SIGNALS
Buttons change color to communicate data/signal state — no separate status dots needed:
- **REFRESH DATA**: green = data is from today ET; **amber** = cache is from a prior day (hit to refresh)
- **CALCULATE SIGNALS**: blue = signals current; **amber** = signals predate today's data fetch (hit to recalculate)
- Both go grey with processing text while running
- `calculated_at` exposed in `/api/signals/stored` response for freshness comparison
- Freshness logic lives in the button render block in `App.js` — compares `updated` date from `realDataMap` against today ET, and `calculated_at` against data date

---

## Project Folder Structure
```
signal-matrix/
├── .claude/
│   ├── launch.json
│   └── settings.local.json
├── Docs/
│   ├── SignalMatrix_Spec_v1.5.txt         ← ✅ Neo's readable copy — full spec (v1.5)
│   ├── SignalMatrix_Phase5_Spec_v1.0.docx ← spec — NOT readable by Neo (.docx)
│   ├── SignalMatrix_Phase5_Spec_v1.0.txt  ← ✅ Neo's readable copy — Phase 5 spec
│   └── QuadTracker_Spec_v1.1.docx        ← spec — NOT readable by Neo (.docx)
├── public/
├── src/
│   ├── components/
│   │   ├── Admin/
│   │   │   └── AdminPanel.js              ← Tasks 4.6/4.7 — ticker CRUD + yfinance lookup
│   │   ├── Dashboard/                     ← placeholder, logic still in App.js
│   │   └── shared/                        ← placeholder
│   ├── data/
│   │   └── tickers.js                     ← SEED DATA ONLY — source of truth is SQLite tickers table
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
│   │   ├── signal_history.py              ← Task 4.3 — Signal history snapshots DB model
│   │   ├── scheduler_log.py               ← Task 4.2 — Scheduler run log DB model
│   │   ├── ticker.py                      ← Task 4.6 — Tickers DB model
│   │   ├── schwab_tokens.py               ← Task 5.3 — Schwab OAuth tokens DB model ✅
│   │   └── iv_history.py                  ← Task 5.5 — IV history DB model ✅
│   ├── alembic/                           ← Task 5.1 — DB migration tooling ✅
│   │   ├── env.py
│   │   └── versions/
│   │       └── aa2d62ea88e4_initial_schema.py
│   ├── services/
│   │   ├── yahoo_finance.py
│   │   ├── signal_engine.py               ← Task 3.1 — Hurst + Fractal Dimension (DFA) ✅
│   │   ├── pivot_engine.py                ← Task 3.2 — ABC Pivot Detector ✅
│   │   ├── conviction_engine.py           ← Task 3.3 — LRR/HRR + Conviction Engine ✅
│   │   ├── scheduler.py                   ← Task 4.2 — APScheduler EOD job ✅
│   │   ├── schwab_client.py               ← Task 5.3 — Token management + Schwab client ✅
│   │   ├── schwab_market_data.py          ← Task 5.4 — EOD quote + history fetch ✅
│   │   └── schwab_options.py              ← Task 5.5 — IV fetch + iv_history write ✅
│   └── routers/
│       ├── market_data.py
│       ├── signals.py                     ← Task 3.3/3.4/4.3 — Signal endpoints + history ✅
│       ├── scheduler.py                   ← Task 4.2 — Scheduler status endpoint ✅
│       ├── auth.py                        ← Task 5.3 — Schwab OAuth endpoints ✅
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
## Phase 4 — COMPLETE ✅
## Phase 5 — COMPLETE ✅

### Phase 3 Build Sequence

| Task | Deliverable | File | Status |
|---|---|---|---|
| 3.1 | Hurst + Fractal Dimension (DFA) | `backend/services/signal_engine.py` | ✅ Complete |
| 3.2 | ABC Pivot Detector | `backend/services/pivot_engine.py` | ✅ Complete |
| 3.3 | LRR/HRR + Conviction Engine | `backend/services/conviction_engine.py` | ✅ Complete |
| 3.4 | Wire to Dashboard | `src/App.js` | ✅ Complete |

### Phase 4 Build Sequence

| Task | Deliverable | Status |
|---|---|---|
| 4.1 | GitHub private repo + .env history cleanup | ✅ Complete |
| 4.2 | EOD Scheduler (APScheduler + NYSE calendar) | ✅ Complete |
| 4.3 | Signal History daily snapshots | ✅ Complete |
| 4.4 | Fly.io cloud deployment | ⬜ Absorbed into Phase 5 |
| 4.5 | Auto-load cache on page load | ✅ Complete |
| 4.6 | Tickers table + dynamic backend | ✅ Complete |
| 4.7 | yfinance lookup endpoint for new tickers | ✅ Complete |
| 4.8 | viewpoint_since timestamp | ✅ Complete |
| 4.9 | FORMING state direction fix | ✅ Complete |
| 4.10 | Staleness thresholds (pivot engine) | ✅ Complete |
| 4.11 | Conviction rebalance (65/35, Rel IV removed) | ✅ Complete |
| 4.12 | OBV pivot engine | ✅ Complete |
| 4.13 | VIX header indicator | ✅ Complete |

### Phase 5 Build Sequence

| Task | Deliverable | Status |
|---|---|---|
| 5.1 | Supabase setup + SQLAlchemy migration (SQLite → Postgres) | ✅ Complete |
| 5.2 | Fly.io deployment — Docker, secrets, signal.suttonmc.com DNS | ✅ Complete |
| 5.3 | Schwab OAuth — token exchange, storage, proactive auto-refresh | ✅ Complete |
| 5.4 | Schwab quote polling — replaces Yahoo Finance EOD fetch | ✅ Complete |
| 5.5 | IV Percentile — options chain fetch, iv_history table | ✅ Complete |
| 5.6 | OBV source swap — volume_history_json from Schwab | ✅ Complete |

### New Button — CALCULATE SIGNALS
- Added to dashboard header alongside REFRESH DATA
- Manual trigger only — never auto-calculates on page load
- Must be run AFTER REFRESH DATA (price history must be current)
- Calls: `GET /api/signals/calculate` — runs full pipeline (hurst → pivots → output → snapshot) in one call
- Signal engine reads from `price_cache` SQLite table — NEVER calls yfinance directly

---

## Phase 4 — Task 4.2: EOD Scheduler ✅

### Scheduler Overview
- APScheduler `AsyncIOScheduler` inside FastAPI lifespan
- Fires at **4:15 PM ET** on NYSE trading days only (via `pandas_market_calendars`)
- On startup: catch-up check — if past 4:15 PM ET, trading day, and no successful run today → runs immediately
- All dates use **ET timezone** — never UTC (see UTC vs ET fix above)

### EOD Flow (4:15 PM ET, NYSE trading days)
```
APScheduler
    → refresh_data()        writes → price_cache
    → calculate_signals()   writes → signal_hurst
                                   → signal_pivots
                                   → signal_output
                                   → signal_history (snapshot)
    → scheduler_log         writes → success/failure entry
```

### Page Load Flow
```
App.js useEffect (Task 4.5)
    → /api/market-data/batch    reads price_cache   → close, sparklines, rel IV
    → /api/signals/stored       reads signal_output → viewpoint, conviction, LRR/HRR
    → /api/scheduler/status     reads scheduler_log → ● SCHED indicator
```

### Manual Override Buttons
```
REFRESH DATA        → force Yahoo fetch outside scheduler window
CALCULATE SIGNALS   → force recalculation mid-day or after code change
```

### Edge Case Coverage
```
Docker down at 4:15 PM → startup catchup fires on restart if past 4:15 ET and today's job missing
PC off at 4:15 PM      → same catchup pattern covers this
Run twice same day     → signal_history idempotency check prevents duplicate snapshots
429 from Yahoo         → stale cache served, scheduler_log records failure
```

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

### Dashboard Header — Scheduler Indicator
`● SCHED` dot next to data timestamp:
- **Green** — today's EOD run complete (`today_complete = true`)
- **Amber** — scheduled, not yet run today
- **Red** — last run failed
- Hover tooltip shows run time or next scheduled time. Fetched once on page load, no polling.

### Refactors Made for Scheduler
- `refresh_data(db)` extracted from `get_batch` endpoint in `market_data.py` — callable directly
- `run_hurst(db)`, `run_pivots(db)`, `run_output(db)`, `calculate_signals(db)` extracted in `signals.py`
- HTTP endpoints now call these functions — behavior unchanged
- `main.py` converted from module-level startup to `lifespan` context manager

---

## Phase 4 — Task 4.3: Signal History Daily Snapshots ✅

### Overview
- Every time `calculate_signals()` runs (manual or scheduled), a snapshot of all `signal_output` rows is written to `signal_history`
- Idempotent — one snapshot per ticker/timeframe per ET calendar day; re-runs same day are skipped
- Trigger string (`"manual"`, `"scheduled"`, `"catchup"`) recorded per snapshot

### signal_history Table
```sql
id, snapshot_date (ET YYYY-MM-DD), trigger, ticker, timeframe,
lrr, hrr, structural_state, trade_direction, conviction, h_value,
viewpoint, alert, vol_signal, warning, lrr_warn, hrr_warn,
pivot_b, pivot_c, calculated_at (copied from signal_output), created_at (UTC)

INDEX: (snapshot_date, ticker)
No UNIQUE constraint — idempotency enforced in Python, not DB
```

### Snapshot Logic (`snapshot_signals` in `signals.py`)
- Called inside `calculate_signals()` after output is written — failure is non-fatal (logged, not raised)
- Checks for existing row with same `snapshot_date` + `ticker` + `timeframe` before inserting
- `snapshot_date` uses ET timezone — `datetime.now(ZoneInfo("America/New_York")).strftime("%Y-%m-%d")`

### History API Endpoint
`GET /api/signals/history` — query params: `ticker`, `timeframe`, `start_date`, `end_date`, `limit` (default 30, max 500)
- Returns rows newest-first
- Not currently wired to dashboard UI — available for future analysis and backtesting

### CALCULATE SIGNALS Button
- Frontend calls `GET /api/signals/calculate` — runs full pipeline + snapshot in one call
- `/calculate` returns output results in same shape as `/output` — no frontend shape change needed

---

## Phase 4 — Task 4.5: Auto-Load Cache on Page Load ✅

### Overview
- `App.js` calls `/api/market-data/batch` on mount via `useEffect` — populates close prices, sparklines, rel IV from SQLite cache
- Cache is always warm from scheduler — page load is instant, no Yahoo Finance call
- REFRESH DATA button retained as manual override to force a fresh Yahoo fetch
- Signals also auto-load from `/api/signals/stored` on page load (Task 3.4, unchanged)

### Rule Clarification
- Auto-loading from **SQLite cache** on page load is allowed — this is a local DB read
- Auto-fetching from **Yahoo Finance** on page load is still prohibited
- The distinction: cache read = instant + safe; Yahoo fetch = external call + rate limit risk

---

## Phase 4 — Task 4.6: Tickers Table + Dynamic Backend ✅

### Overview
- SQLite `tickers` table is the source of truth — replaces `tickers.js` + localStorage
- `tickers.js` retained as seed-only bootstrap file — never modified directly
- `seed_tickers_if_empty(db)` runs on FastAPI startup — inserts 52 rows if table is empty
  (AMZN excluded from Tier 2 seed due to UNIQUE constraint — add via admin panel if needed)
- `market_data.py` and `signals.py` both call `get_active_tickers(db)` — no hardcoded lists
- `App.js` fetches ticker universe from `GET /api/tickers?active=true` on mount

### Tickers Table Schema
```sql
id            INTEGER PRIMARY KEY AUTOINCREMENT
ticker        TEXT NOT NULL UNIQUE
description   TEXT
asset_class   TEXT
sector        TEXT
tier          INTEGER DEFAULT 1
parent_ticker TEXT
active        BOOLEAN DEFAULT TRUE
display_order INTEGER
created_at    TEXT    -- UTC timestamp
updated_at    TEXT    -- UTC timestamp
```

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
- Asset Class field is a dropdown — enforces exact vocabulary, not free text

---

## Phase 4 — Task 4.7: yfinance Lookup Endpoint ✅

### Overview
- `GET /api/tickers/lookup/{symbol}` — on-demand metadata fetch for new tickers
- Returns suggested description, asset class, sector — never auto-saves
- User reviews and corrects suggestions before saving via admin panel

### Response Schema
```json
{
  "symbol": "EWG",
  "found": true,
  "suggestions": {
    "description": "iShares MSCI Germany ETF",
    "asset_class": "International Equities",
    "sector": "Germany"
  },
  "already_exists": false,
  "notes": null
}
```

### Asset Class Override Table (in `backend/routers/tickers.py`)
Override table is checked FIRST before any yfinance inference. Add new entries here when lookup returns wrong asset class:

```python
ASSET_CLASS_OVERRIDES = {
    # Domestic Fixed Income
    'TLT': 'Domestic Fixed Income', 'LQD': 'Domestic Fixed Income',
    'HYG': 'Domestic Fixed Income', 'CLOX': 'Domestic Fixed Income',
    # International Equities
    'EWG': 'International Equities', 'EWQ': 'International Equities',
    'EWP': 'International Equities', 'KWT': 'International Equities',
    'KWEB': 'International Equities', 'EWJ': 'International Equities',
    'EWW': 'International Equities', 'TUR': 'International Equities',
    'UAE': 'International Equities',
    # Foreign Exchange
    'GLD': 'Foreign Exchange', 'SGOL': 'Foreign Exchange',
    'FXB': 'Foreign Exchange', 'FXE': 'Foreign Exchange', 'FXY': 'Foreign Exchange',
    # Commodities
    'USO': 'Commodities', 'SLV': 'Commodities', 'PALL': 'Commodities',
    'PPLT': 'Commodities', 'CANE': 'Commodities', 'WOOD': 'Commodities',
    'CORN': 'Commodities', 'WEAT': 'Commodities',
    # Digital Assets
    'IBIT': 'Digital Assets',
}
```

### Lookup Rules
1. Override table wins — always checked first
2. Only fills empty form fields — never overwrites existing values
3. Graceful on missing data — `null` fields returned, no error
4. Never writes to DB — suggestions only
5. yfinance inference runs as fallback for unknown tickers

---

## Phase 5 — Infrastructure Decisions (LOCKED)

### Database: Supabase (Postgres)
- Replaces SQLite in production — all existing tables migrated via Alembic
- Two new tables: `schwab_tokens` (encrypted OAuth tokens), `iv_history` (rolling IV per ticker)
- `price_cache` gains `data_source` column: `'schwab'` | `'yahoo'` | `'yahoo_fallback'`
- Direct connection string → Alembic migrations only
- Pooled connection string (Transaction mode, port 6543) → app runtime

### Schwab API: schwab-py library
- `pip install schwab-py` — do not write raw HTTP calls against Schwab API
- Token storage: Fernet-encrypted in `schwab_tokens` table
- Token refresh: proactive background task every 25 minutes (APScheduler)
- Fallback: all Schwab calls fall back to Yahoo Finance on token expiry or API error
- Data source tagged in `price_cache.data_source` — visible in dashboard header

### EOD Scheduler: Updated Flow (Phase 5)
```
4:00 PM ET — Schwab data fetch (NEW)
    schwab_fetch_quotes()    1 request, all 51 tickers
    schwab_fetch_history()   51 requests, 0.5s delay between calls
    schwab_fetch_iv()        47 requests (options-eligible only)
                             writes price_cache + iv_history

4:15 PM ET — calculate_signals() (unchanged)
```

### IV-Eligible Tickers
All Tier 1 tickers EXCEPT: VIX, $DJI, SPX, NDX — index options have different chain structure.

### Yahoo Finance Role (Phase 5+)
Yahoo Finance is a permanent silent fallback — never removed. Called automatically when:
- Schwab token is expired or missing
- Schwab API returns an error
- Manual REFRESH DATA during development

### REACT_APP_API_URL
Must be environment-variable driven — not hardcoded to localhost:8000.
- Local `.env`: `REACT_APP_API_URL=http://localhost:8000`
- Fly.io secret: `REACT_APP_API_URL=https://api.signal.suttonmc.com`

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
  Trade H (DFA, 63-day)   → 65%   primary signal
  Trend H (DFA, 252-day)  → 35%   alignment filter

Rel IV removed from conviction formula — used for LRR/HRR width scaling only.

Volume Multiplier (OBV pivot direction vs Trade Dir — applied after base score):
  Confirming  → × 1.15   Vol Direction matches Trade Dir
  Neutral     → × 1.00   Vol Direction Neutral or mixed
  Diverging   → × 0.80   Vol Direction opposes Trade Dir

Final Conviction = Base Score × Volume Multiplier

CRITICAL: Conviction is BLANK (not calculated) when Viewpoint = Neutral
```

**Long Term H (756-day):** calculated and stored, displayed in popup as context only.
Not used in conviction formula.

### Direction Determination — Pivots Only (H has NO role)

**H does not determine direction. H drives conviction and LRR position only.**

```python
# Direction check — C is the only invalidation level, LRR has no role in direction
if structural_state == "BREAK_OF_TRADE":
    trade_dir = "Neutral"
elif direction == "uptrend" and current_price > c:
    trade_dir = "Bullish"
elif direction == "downtrend" and current_price < c:
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
| Uptrend + price above C | Bullish |
| Downtrend + price below C | Bearish |
| Break of Trade (one close through C) | Neutral — immediate, no two-close rule |
| FORMING — pullback from D, price still above C | Bullish (trend intact) |
| FORMING — bounce from D, price still below C | Bearish (trend intact) |
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

### LRR / HRR Formula — Redesigned (conviction_engine.py)

**Two bugs fixed from original formula:**
1. H_factor was inverted — high H now correctly means shallow pullback (LRR near anchor), not deep
2. Anchor switches from C to B when price has extended well beyond B, so old C is no longer the relevant anchor

#### H_factor lookup (same values, applied as `1 − hf` for entry-side ranges)
```
H > 0.65   →  hf = 0.95  (strong trend  → shallow pullback → entry close to anchor)
H 0.55–0.65 →  hf = 0.50  (moderate trend)
H 0.50–0.55 →  hf = 0.05  (weak trend)
H < 0.50   →  hf = 0.00  (mean-reverting → deep pullback → entry far from anchor)
```

#### Uptrend
```python
bc_range = abs(b - c)
anchor   = c if d < b + bc_range else b   # switch to B when price extended well above B
lrr = anchor + bc_range * (1 - hf) - sigma * lrr_mult   # entry on pullback
hrr = d      + bc_range * hf        + sigma * hrr_mult   # target above D
```

#### Downtrend (mirror)
```python
bc_range = abs(b - c)
anchor   = c if d > b - bc_range else b   # switch to B when price extended well below B
hrr = anchor - bc_range * (1 - hf) + sigma * hrr_mult   # entry on bounce
lrr = d      - bc_range * hf        - sigma * lrr_mult   # target below D
```

**Rule: both sides use `sigma × lrr_mult` and `sigma × hrr_mult` directly — never `sigma × (1 − mult)`.**
The brief contained an error on downtrend LRR (`1 - lrr_mult`); verified fix gives correct output.

#### Rel IV Multipliers (sigma scaling)
| Rel IV% | lrr_mult | hrr_mult |
|---|---|---|
| 0–30%  | 0.99 | 1.02 |
| 31–60% | 1.00 | 1.05 |
| 61–80% | 0.97 | 1.10 |
| > 80%  | 0.94 | 1.15 |

#### Verified output — SPX trade timeframe (Bearish FORMING)
```
B=6798.40  C=6946.13  D=6506.48  H=0.298  rel_iv=69
anchor = B (D < B − bc_range → extended below B)
Trade LRR = $6,454  ✅   (Hedgeye benchmark ~$6,465)
Trade HRR = $6,710  ✅   (Hedgeye benchmark ~$6,707)
```

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
- **One close below C = BREAK_OF_TRADE immediately** — no two-close rule, no grace period
- **Price recovers above C** → Trade Dir = Bullish restored (engine recalculates fresh each run)
- **Intraday violations irrelevant** — engine uses EOD closes only
- **Break of Trade = reduce to minimum position** — Trend break = go to zero
- **WARNING state is IV-driven only** — never price-driven
- **LRR/HRR always show** — color reflects state (green/red/grey); BREAK states show grey LRR/HRR
- **Direction determined by pivots only — C only** — LRR has no role in direction check
- **Trade and Trend states are independent** — Trend break does not auto-flip Trade
- **C updates dynamically** — always references most recent confirmed higher low / lower high

**Staleness thresholds (`pivot_engine.py` — `_STALE_C_DAYS`):**
```
Trade:     C older than  60 trading days → NO_STRUCTURE (structure too old to trade)
Trend:     C older than 100 trading days → NO_STRUCTURE (structure too old for directional bias)
Long Term: No cutoff                     → LT structures are inherently old
```

**ABC transition to bearish after uptrend break:**
```
When uptrend breaks (BREAK_OF_TREND):
  Bearish A = old bullish D             (highest confirmed point — already exists)
  Bearish C = first lower high after D  (lower high — already confirmed, C < A ✅)
  Bearish B = first confirmed lower low (confirms AFTER the break — needs bar_window bars after)
  DOWNTREND_VALID fires as soon as bearish B confirms — bearish C already existed
```
No new downtrend can print until bearish B confirms (bar_window × 2 bars minimum after the break).

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
                viewpoint, viewpoint_since, ← ISO timestamp ET — when current aligned viewpoint began
                alert, vol_signal,
                warning,                    ← IV-driven WARNING flag (per timeframe)
                lrr_warn, hrr_warn,         ← price-based pivot threshold flags (per timeframe)
                pivot_b, pivot_c,           ← pivot values for UI comparison
                obv_direction,              ← Vol Direction: OBV pivot trend: Bullish | Bearish | Neutral
                obv_confirming,             ← True when Vol Direction aligns with Trade Dir (not Viewpoint)
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

### FastAPI Endpoints (Phase 4)
```
GET /api/scheduler/status         ← Task 4.2 ✅  (read-only status)
GET /api/signals/calculate        ← Task 4.3 ✅  (full pipeline + snapshot, replaces /output for button)
GET /api/signals/history          ← Task 4.3 ✅  (query snapshots, not wired to UI yet)
GET /api/tickers                  ← Task 4.6 ✅  (list all, optional ?active filter)
POST /api/tickers                 ← Task 4.6 ✅  (create)
PUT /api/tickers/{symbol}         ← Task 4.6 ✅  (update)
DELETE /api/tickers/{symbol}      ← Task 4.6 ✅  (soft-delete)
GET /api/tickers/lookup/{symbol}  ← Task 4.7 ✅  (yfinance suggestions)
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
- Auto-loading from SQLite cache on page load is allowed — it is a local DB read, not a Yahoo call

### Ticker Universe — Source of Truth
- **SQLite `tickers` table** is the source of truth as of Task 4.6
- `tickers.js` is seed data only — runs once on first FastAPI startup if table is empty
- Do not modify `tickers.js` — use the admin panel to add/edit/deactivate tickers
- `get_active_tickers(db)` is the only way backend should retrieve the ticker list — no hardcoded arrays

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
- Close prices: real — auto-loaded from SQLite cache on page load
- Sparklines: real — 60-day price history
- Rel IV: real — Schwab IV Percentile from options chain (`iv_source = 'schwab'`); falls back to Yahoo proxy (`iv_source = 'proxy'`) on token expiry or per-ticker error
- Volume: real — daily volume from Yahoo Finance
- Signal columns: **live** — populated from `/api/signals/stored` on page load; recalculated on CALCULATE SIGNALS
- REFRESH DATA: manual fetch only — forces fresh Yahoo Finance fetch outside scheduler window
- CALCULATE SIGNALS: manual trigger only, reads from price_cache
- Admin panel at localhost:3000/admin — password protected
- Ticker universe: loaded from `/api/tickers?active=true` on page load

### VIX Regime Indicator — Dashboard Header
Reads from existing `VIX` row in `price_cache` — no new data fetch needed:
```
VIX < 20   → Green  — INVESTABLE
VIX 20–29  → Amber  — CHOPPY
VIX ≥ 30   → Red    — DANGER
```
The old `● VIX X.XX` text indicator has been superseded by the VIX Gauge (see below). Regime logic unchanged.

### VIX Gauge — Dashboard Header
Horizontal gauge bar positioned between the title and summary counts (BULLISH / BEARISH / ALIGNED / ALERTS / ENTRY).
- **Range:** 9 to 45+ (needle clamped at right edge when VIX > 45; numeric display shows actual value)
- **Zone widths** (based on 36-unit span, 9–45):
  - Green (9–20): 30.6% · Amber (20–30): 27.8% · Red (30–45): 41.6%
- **Needle:** 3px wide, extends 4px above/below bar, colored to match current zone, glow + white inner shadow
- **Scale labels:** 9 · 20 · 30 · 45+ at zone boundaries, 11px, `#8899aa`
- **Needle position formula:** `Math.min(Math.max((vix - 9) / 36, 0), 1) * 100` percent
- Labels: INVESTABLE (green) · CHOPPY (amber) · DANGER (red) shown inline next to numeric VIX value

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
| ENTRY | ▲ BUY (green) or ▼ SELL (red) badge — see ENTRY Signal rules below; blank when conditions not met; sortable |
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
| Aligned Since | ET timestamp — when current Bullish/Bearish viewpoint began. Hidden when Neutral |
| Conviction | % or — when Neutral |
| Vol Direction | Bullish / Bearish / Neutral — OBV pivot trend direction (`obv_direction`) |
| Vol Signal vs Trade | Confirming ✓ / Diverging ✗ / Neutral — compared against Trade Dir (`obv_confirming`) |
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
  - `cd15150` — Tasks 4.6 + 4.7: Tickers table + dynamic backend + yfinance lookup
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
- **Never hard delete tickers** — use `active: false` via DELETE endpoint

---

## Project Rules — Read Before Making Changes
1. **Never modify the ticker universe without explicit instruction** — use admin panel, not code edits
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
12. **Phase 3 signal calculations are locked** — implement per spec above, no deviations
13. **Flag all [OPEN] items** before implementing — do not assume defaults
14. **Commit to Git** after every confirmed working state
15. **Neo = Claude Code** (VS Code extension) — all code changes go here
16. **No worktrees or feature branches** — all changes committed directly to master
17. **Never auto-fetch from Yahoo Finance** — REFRESH DATA button only; auto-loading from SQLite cache on page load IS allowed
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
29. **Direction check uses C only** — `price > c` for Bullish, `price < c` for Bearish; LRR is not part of the direction check
30. **LRR/HRR always compute for BREAK states** — `_infer_pivot_direction` infers underlying direction even for BREAK_OF_TRADE/BREAK_OF_TREND so LRR/HRR render grey
31. **LRR/HRR cell color = timeframe direction** — use `dirRangeColor(dir, isWarn)`, NOT viewpoint color
32. **Per-cell ⚠ warn flags are price-based** — separate from IV-driven `warning` structural state
33. **Warning scope is timeframe-specific** — Trade: full (C+B); Trend: C-based only; LT: none
34. **All cache_date and run_date writes use ET date** — never UTC date for trading day keys
35. **`get_active_tickers(db)`** is the only way to retrieve the ticker list in backend — no hardcoded arrays
36. **tickers.js is seed data only** — never import it for the live ticker universe; use `/api/tickers`
37. **Asset class overrides checked first** — add new entries to `ASSET_CLASS_OVERRIDES` in `tickers.py` when yfinance returns wrong asset class
38. **Neo cannot read .docx files** — CLAUDE.md is the primary spec source for Neo; keep it current
39. **One close below C = BREAK_OF_TRADE immediately** — no two-close rule, no grace period; recovery above C restores direction on next calculation
40. **Break of Trade = reduce to minimum position** — Trend break = go to zero (full exit)
41. **OBV pivot bar_window = 9 bars** — confirmed pivots require bar_window on both sides, same rule as price pivot engine
42. **Schwab API approved for Phase 5** — OBV volume source swap point flagged with `# PHASE 5 TODO` in `yahoo_finance.py`; OBV engine in `conviction_engine.py` is source-agnostic
43. **schwab-py is the only Schwab API client** — never write raw HTTP calls against Schwab endpoints
44. **Yahoo Finance is a permanent fallback** — never remove it; always called when Schwab is unavailable
45. **Token encryption is mandatory** — Schwab tokens must be Fernet-encrypted before writing to DB
46. **REACT_APP_API_URL must be env-variable driven** — never hardcode localhost:8000 in production code
47. **auto_stop_machines = false on API app** — Fly.io must not stop the API container or scheduler won't fire
48. **Alembic manages all schema changes** — never modify Supabase tables directly via dashboard
49. **IV-eligible tickers exclude VIX, $DJI, SPX, NDX** — index options chains have different structure
50. **data_source column must be written on every price_cache upsert** — 'schwab', 'yahoo', or 'yahoo_fallback'

---

## Roadmap

| Phase | Description | Status |
|---|---|---|
| Phase 1 | Dashboard Refinement | ✅ Complete |
| Phase 2 | Real Data Integration | ✅ Complete |
| Phase 3 | Signal Engine | ✅ Complete |
| Phase 4 | Backend & Database | ✅ Complete — all tasks 4.1–4.13 done |
| Phase 5 | Schwab API + Cloud Deployment | ✅ Complete — all tasks 5.1–5.6 done |
| Phase 6 | Production Hardening | ⬜ Volume surge, positions display, Supabase hardening |

---

## Phase 5 — Planned Features

### Phase 5 — Volume Surge Indicator (deferred from Phase 4)
- OBV pivot engine now live in `conviction_engine.py` — replaces price-momentum proxy
- Phase 5 upgrade: swap Yahoo Finance `volume_history_json` for Schwab streaming volume history
- Swap point flagged with `# PHASE 5 TODO` comment in `yahoo_finance.py`
- OBV engine is source-agnostic — reads from `volume_history_json` regardless of origin
- Volume signal tiers (Phase 5 upgrade — Schwab real-time):
  - Confirming:  today's volume > 20-day avg (any elevated volume)
  - Surge:       today's volume > 150% of 20-day avg (exceptional participation)
  - Neutral:     today's volume within normal range
  - Diverging:   price moving on declining volume
- Dashboard display: icon on conviction cell
  - ▲ green = Confirming
  - ▲▲ green = Surge (150%+)
  - ▼ amber = Diverging
  - no icon = Neutral
- 20-day avg volume already available from Schwab streaming feed

---

## What Is NOT In Scope Yet
- Account positions display (deferred — manage in ThinkorSwim; Phase 6 or later)
- WebSocket streaming (deferred — REST polling is sufficient for EOD signals)
- Volume surge icon on dashboard rows (deferred to Phase 6)
- Schwab order execution (permanently out of scope)
- Quad Tracker dashboard (Phase QT)
- Quad alignment column in Signal Matrix table (Phase QT)
- Tier 2 auto-surfacing based on conviction threshold
- MA20/50/100 display in dashboard UI
- Signal history UI (table exists, endpoint exists — frontend consumption is future scope)

---

## Ticker Universe — Seed Data (tickers.js — DO NOT USE AS LIVE SOURCE)

The live ticker universe is managed via the SQLite `tickers` table and admin panel.
The list below is the original seed data only — reference for recovery purposes.

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
  { ticker: "SOXX",  description: "iShares Semiconductor ETF",            assetClass: "Domestic Equities", sector: "Technology",               tier: 2, parentTicker: "XLK",  active: true, displayOrder: 1 },
  { ticker: "SGOL",  description: "Aberdeen Physical Gold Shares ETF",    assetClass: "Foreign Exchange",  sector: "Gold",                     tier: 2, parentTicker: "GLD",  active: true, displayOrder: 1 },
];
// NOTE: AMZN excluded from Tier 2 seed — already exists as Tier 1. Add via admin panel if needed as Tier 2.
```
                                  