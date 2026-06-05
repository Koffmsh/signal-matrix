# Signal Matrix Platform — Project Context

## Read order (authoritative)
1. CLAUDE.md (this file) — current rules, constraints, and state. Authoritative.
2. Before ANY methodology or architecture change → read DECISIONS.md (the "why" / regression guards; ADR-lite).
3. Before touching a superseded component → check the Docs/ archive.

Document maintenance is governed by `Docs/CLAUDE_md_Maintenance_Protocol.md`. To record a change, the trigger is **"Log this change."**

## Important Note for Neo
The `.docx` spec files in `Docs/` cannot be read by Claude Code.
Readable `.txt` copies exist:
- `Docs/SignalMatrix_Spec_v1.7.txt` — **current** full platform spec (v1.7 — BB LRR/HRR framework, Trend/Tail Levels, proximity conviction, ENTRY prox threshold, EXTENDED redesign)
- `Docs/SignalMatrix_Spec_v1.6.txt` — **superseded** by v1.7 (Phases 1–5 complete, OBV, VIX gauge, futures — retained for reference)
- `Docs/SignalMatrix_Spec_v1.5.txt` — prior version (Phase 4 era — superseded by v1.6)
- `Docs/SignalMatrix_Phase5_Spec_v1.0.txt` — Phase 5 spec (Supabase, Fly.io, Schwab OAuth, IV)
- `Docs/SignalMatrix_ConvictionEngine_v1_9_Spec.md` — v1.9 spec (Quad Multiplier, VIX gate, 5-layer conviction formula) ✅ Superseded by v2.0
- `Docs/SignalMatrix_ConvictionEngine_v2_0_Spec.md` — v2.0 spec (Additive formula, 4 components, display threshold 45, alert threshold 80) ✅ Implemented
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
- **Twilio:** SMS alerts via `twilio>=8.0.0`; credentials in `.env` (TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_FROM, TWILIO_TO)
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
  - Schwab portal status: ✅ Approved — callback URL modification confirmed 2026-03-25
  - APIs: Accounts and Trading Production + Market Data Production
  - Order Limit: 0 (order execution not in scope)
- **ngrok:** Available for 1-off demos — `ngrok http 3000`

---

## Known Fixes & Learnings

Critical issues already resolved — do not reintroduce these bugs:

### Data, timezone & cache guardrails
- **yfinance ≥ 1.2.0** — never downgrade; v0.2.x has an unresolvable persistent 429 block.
- **Date comparison** (`yahoo_finance.py`): `closes.index.date <= date.today()` — `.date` avoids the tz-aware crash; `<=` includes today's confirmed EOD close.
- **429 fallback** (`market_data.py`): on 429 the batch endpoint serves cached SQLite (never returns empty) so all tickers stay visible.
- **`updated_at`** (`market_data.py`): stamp `datetime.utcnow()` on every upsert path; store UTC-naive, convert to ET at display (`.replace(tzinfo=timezone.utc).astimezone(_ET)` in `serialize_cache_row`); never `str(row.updated_at)`.
- **`updated` field** (`yahoo_finance.py`): stamp `datetime.now(_ET)` — Docker is UTC, bare `datetime.now()` flips the date after 8 PM ET. `_ET = ZoneInfo("America/New_York")` at module level.
- **Never hardcode dates in JSX** (`App.js`) — read from data (e.g. first ticker's `updated`).
- **All trading-day / cache-key dates use ET, never UTC** — see **ADR-001** and rule #34. Never `date.today()`, `str(date.today())`, or `datetime.utcnow().date()` for a trading day or cache key (Docker UTC date flips after 8 PM ET → cache miss, false `today_complete`, wrong NYSE day).

### Pivot engine guardrails (`pivot_engine.py`)
- **`structural_state` has exactly 6 values** — UPTREND_VALID, DOWNTREND_VALID, BREAK_OF_TRADE, BREAK_OF_TREND, BREAK_CONFIRMED, NO_STRUCTURE. FORMING was eliminated (a pullback from D is just `*_VALID`); EXTENDED → boolean `d_extended`; WARNING → boolean `warning`. BREAK_OF_TRADE/TREND hold direction (provisional, first-day forgiveness); only BREAK_CONFIRMED (2+ closes) → Neutral. Amber state cell for BREAK_OF_*, red for BREAK_CONFIRMED. See **ADR-002** + rules #53–#60.
- **`d_extended`** = `D > B + 0.5·abs(B−A)` (50%-of-AB threshold; resets when a new C forms). B becomes the break level while True. Drives B-vs-C selection in warn flags, the popup `*`, and the B-based break machine; independent of `structural_state`. Distinct from the daily-overshoot `lrr_extended`/`hrr_extended` flags — three separate "extended" concepts, never conflate.
- **ABC selection & dynamic update** — A anchors at the most extreme confirmed pivot in the lookback window (`_MAX_A_LOOKBACK` trade=60 / trend=150 / lt=None; never raise trade above 60), iterating most→least extreme for V-recoveries. B advances to the most recent pivot AFTER C is finalized (`update_b_dynamically` runs after `update_c_dynamically` — never reorder/remove). `find_abc_structure()` prefers the price-intact structure and rejects any ABC spanning a prior BREAK_CONFIRMED (`_has_prior_break_confirmed`, `_price_on_correct_side`, `_d_has_established`). Do not simplify to "most-recent-C-wins" — the priority logic is load-bearing. See **ADR-003**.
- **Yahoo `auto_adjust=False`** — store actual traded prices, never dividend-adjusted (Yahoo fallback only; Schwab always actual). See **ADR-004**.
- **EOD bar inclusion:** `closes.index.date <= date.today()` — today's EOD bar is a confirmed close; never revert to `<`.
- **Bar windows:** `TIMEFRAMES["lt"]=50`, `TIMEFRAMES["trend"]=10` — do not increase without verifying that 3–4-month-old (lt) / <6-week (trend) reversals still register.

### Conviction / OBV / UI guardrails
- **OBV direction** (`conviction_engine.py`) — current method is a 40-bar linear regression (rule #41); prior ABCD-pivot / HH+HL / price-momentum methods are superseded. Vol Signal compares OBV direction against **Trade Dir** (not Viewpoint): Confirming = matches, Diverging = opposes, Neutral = no structure. `obv_direction`/`obv_confirming` stored in `signal_output`. See **ADR-005**.
- **VIX regime cutoff is strictly `< 19`** (Green/Investable) — never use 20. `19 ≤ VIX < 30` amber, `≥ 30` red.
- **Vol popup naming** (`App.js`) — never rename DB field `vol_signal` → `obv_signal`. Popup shows "Vol Direction" (`obv_direction`) + "Vol Signal vs Trade" (`obv_confirming`, vs Trade Dir).
- **EXTENDED architectural cleanup** — `d_extended` boolean replaced the EXTENDED/WARNING `structural_state` values; `is_warning`/`_compute_warn_flags` take `d_extended` (`break_level = b if d_extended else c`); `compute_output` never sets `state="WARNING"`. See **ADR-002** (migration `e2f4a6b8c1d0`).
- **Q FIT column** — uses `quad_fit` (viewpoint-INDEPENDENT: Best/Neutral/Worst); **never** `quad_alignment` (viewpoint-dependent → wrong ▼ for bearish securities in bullish-tailwind quads). International Equities use country quarterly quad; US uses monthly.

### Schwab IV & volatility metrics (`schwab_options.py`)
- **IV source** — never read the option chain's top-level `volatility` (that's realized vol). IV30 = 30-day constant-maturity ATM IV via `_extract_atm_iv` (interpolate the two expirations bracketing 30 DTE). IV Rank is **range-based** `(cur-min_252)/(max_252-min_252)×100`, not frequency percentile. `iv_source` ∈ schwab | proxy | price_rank; per-ticker/no-token errors fall back to the Yahoo proxy. See **ADR-006**.
- **25Δ skew / risk reversal** — `_extract_25d_skew` uses a **strike-based Black-Scholes approximation** (compute K_call/K_put_25d from S and ATM IV, read nearest strike's IV), **never the delta field** (Schwab omits OTM delta → would land on ATM, near-zero RR). `risk_reversal = call_iv_25d − put_iv_25d` (positive = bullish forward skew). `strike_count = 20`. See **ADR-006**.
- **HV / VRP** — `hv30`/`hv90` = std of last 21/63 log returns × √252 (from `history_json`, no API call); `vrp = IV30 − HV30`. Skew Rank / VRP Rank / HV Rank each = 252-day range rank (`_RANK_MIN_HISTORY = 30`). P/C ratio = total put OI ÷ call OI (`>1.2` fear, `<0.6` complacency).
- **`vol_history`** holds all vol metrics; `implied_vol` nullable. `accumulate_hv_only(db)` writes HV-only rows for Yahoo-only tickers (SPX, NDX, RUT, VIX, $DJI, USD, JPY, /CL, /ZN, /GC, VVIX) and must stamp `price_cache.hv30/hv90/hv_rank` too. Idempotency checked against `vol_history` (clear rows to force re-fetch).
- **HV Rank label** — `iv_source='proxy'` shows "HV Rank" (realized-vol rank, never implied); `'schwab'` → "IV Rank — schwab"; `'price_rank'` → "VVIX Rank — price".

### Trade LRR/HRR — v1.9.2 BB+Snap Formula (Dynamic-N BB + Snap)
- **Spec:** `Docs/SignalMatrix_RR_v1_9_1.txt` (authoritative — full Steps 1–8, 8-bucket N lookup, computation). Supersedes v1.8 fixed-N BB + ATR buffer + MA20-regime (ATR/MA20/STD20/`ma20_regime` columns remain on `price_cache` but no longer drive the band).
- **Constants** (TOS-validated, hardcoded in `conviction_engine.py` — **code is source of truth**, see **ADR-013**): `k_wide=2.0, k_extend=2.2, k_max=1.0, k_min=0.0, k_decay=0.5`; `rank_lookback=252, hv_period_bars=21, snap_window=22, proximity_smooth=3`. Do not revert to spec defaults without re-validating bands against Hedgeye in ToS.
- **Framework:** dynamic-N BB (N 8→15 by IV30 percentile rank, HV30 fallback) + a stateful snap that compresses the trailing band toward MA during impulses. σ is **price-derived** `std(closes[-N:], ddof=0)`; IV/HV only drives N selection. Directional proximity `prox_lrr=(close−maN)/sdN` (signed, EMA-3) lets per-side k expand toward k_wide when price crosses MA — eliminates LRR inversion. Snap trigger = **today's close** vs prior 22 closes; releases via merge (k→k_wide) or breach (intraday extreme crosses yesterday's snap line); LRR wins coincidence.
- **State & contract:** snap state persists in `signal_output.hrr_snapped`/`lrr_snapped` (+`signal_history`; migration `q2r3s4t5u6v7`); cold start `len(closes) < 273` → `(None,None,False,False)`. `compute_trade_lrr_hrr(closes, vol_series, prior_hrr_snapped, prior_lrr_snapped)` is **pure**; caller (`compute_output`) handles vol-series lookup (`get_trade_rr_vol_series`, IV-primary/HV-fallback) + snap I/O. EOD-batch (today's close is confirmed, no forward displacement). See rule #77.

### Trend Level and Tail Level — Single MA (v1.7)
- One level per timeframe (replaces dual Trend/LT LRR/HRR). **Trend Level** = break pivot (C; B when `d_extended=True`), shown when Trend Dir ≠ Neutral — MA100 slope check removed; always shows the active invalidation level (uptrend green floor / downtrend red ceiling). **Tail Level** = MA200, shown only when LT Dir ≠ Neutral AND 20-day slope confirms. Code/DB key stays `"lt"`; display label is "Tail". Trend HRR removed from table/popup.

### MA20_TP Center Dropped (historical)
- MA20_TP / typical-price center was dropped (migration `13fb636fe76a`); v1.9.1 replaced the BB center with dynamic-N MA per-run from `closes[-N:]`. `price_cache.ma20` still populates for legacy only. **Never re-add MA20_TP.** See **ADR-007**.

### H/L History 3-Bar Alignment Fix (One-Time Data Migration)
- **Root cause:** When `history_high_json` / `history_low_json` columns were first added (migration `f7a3b2c1d9e6`), the initial "short" fill started 3 trading days later than the existing close history. Those 3 leading dates never received H/L values, leaving every ticker's H/L array 3 bars shorter than its close array.
- **Symptom:** `highs[i]` contained data for `dates[i+3]`, not `dates[i]` — ATR calculations for 14-day windows touching that zone were incorrect (inflated, since misaligned H/L appeared to spike relative to close).
- **Fix (2026-04-14):** One-time data script padded the front of `history_high_json` and `history_low_json` with the close price for the missing dates (H=L=C proxy), making all arrays equal-length. ATR was recomputed from the corrected arrays for all 63 local (SQLite) and 79 production (Supabase) tickers.
- **Code is correct:** Both the Schwab path (`_schwab_fetch` uses candles directly) and Yahoo path (`fetch_ticker_data` uses `.reindex(history_closes.index)`) correctly align H/L to close dates. The misalignment was a legacy bootstrap artifact only.
- **All future fetches:** append/skip/short/bootstrap paths all preserve or rebuild correct alignment — no ongoing issue.
- **Rule:** If adding new OHLC-based columns (e.g. ATR variants), always verify `len(history_high_json) == len(history_json)` after the first data run.

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

**History fetch:** Schwab uses gap detection to determine what history to fetch per ticker — see Gap Detection section below. The merge logic in `_upsert` preserves existing long history when new data is shorter.

**Idempotency check:** Uses first Schwab-supported ticker (excludes `SCHWAB_UNSUPPORTED`) to avoid perpetual cache miss when a Yahoo-only ticker sorts first.

### Schwab API — Instrument Type Limitations (Architectural Decision)
Why certain tickers permanently route to Yahoo Finance — this is not a bug or a gap to close, it is a deliberate permanent architecture decision based on what the Schwab API actually supports.

- **Equities and ETFs:** Fully supported — `get_quotes()` (batch) + `get_price_history()` (per-ticker). Primary data source for all equity/ETF tickers.
- **Indices (SPX, NDX, $DJI, VIX, RUT, VVIX):** `SCHWAB_SYMBOL_MAP` translates these to Schwab format (`$SPX.X`, `$NDX.X`, etc.) but `get_quotes()` silently drops them — no error, just missing keys in the response. `get_price_history()` per-ticker may work but requires 6 separate HTTP calls vs. one Yahoo batch; the skip/append gap-detection path makes this near-zero cost on normal daily runs anyway. **Yahoo is the right permanent answer for indices.**
- **FX (USD = DXY index, JPY = USDJPY):** These are not securities — Schwab's API is equity/ETF-only and has no FX endpoint. DXY and spot FX rates simply do not exist in their quote infrastructure. **Yahoo is the right permanent answer for FX.**
- **Futures (/CL, /ZN, /GC):** Schwab uses contract-specific symbols (e.g. `/CLM26`). The "continuous front-month" concept used here (`CL=F`, `GC=F`) is a Yahoo abstraction — Yahoo handles the monthly roll automatically. Replicating that on Schwab would require tracking expiration calendars and rolling contracts, significant complexity for no signal quality gain at EOD resolution. **Yahoo is the right permanent answer for futures.**
- **Speed:** On skip/append days (the normal case after the first fetch), both Yahoo and Schwab are essentially instant due to gap detection. On bootstrap/short fetches Yahoo's batch call is faster than equivalent per-ticker Schwab calls. No speed advantage to switching.
- **Rule:** Do not attempt to replace Yahoo with Schwab for indices, FX, or futures — the mixed-source architecture is intentional and permanent. When adding new tickers in any of these categories, add them to `SCHWAB_UNSUPPORTED`, `YAHOO_SYMBOL_MAP`, and (if futures) `IV_INELIGIBLE`.

### SCHWAB_UNSUPPORTED Expanded — Indices Now Route to Yahoo (`schwab_market_data.py`)
- Schwab batch quotes API silently drops index symbols (SPX, NDX, $DJI, VIX) when mixed with equity symbols — no error, just missing keys in the response
- Without this fix, these tickers never get `updated_at` stamped, causing REFRESH DATA to stay amber even after a successful refresh (SPX is `display_order=1` and its timestamp drives the header)
- **Fix:** Added `"SPX"`, `"NDX"`, `"$DJI"`, `"VIX"` to `SCHWAB_UNSUPPORTED` set — they always route to Yahoo Finance
- Full set: `{"USD", "JPY", "/CL", "/ZN", "/GC", "SPX", "NDX", "$DJI", "VIX", "RUT", "VVIX"}`
- **Idempotency fix:** When Schwab cache is fresh and early return fires, the code now still runs `_yahoo_fetch_subset` for the unsupported tickers — without this, SPX/VIX/etc. would never get their `updated_at` stamped on subsequent manual refreshes
- **RUT added 2026-04-10:** Russell 2000 Index — `YAHOO_SYMBOL_MAP["RUT"] = "^RUT"`, added to `SCHWAB_UNSUPPORTED` and `IV_INELIGIBLE`
- **VVIX added 2026-04-11:** CBOE VIX of VIX Index — `YAHOO_SYMBOL_MAP["VVIX"] = "^VVIX"`, added to `SCHWAB_UNSUPPORTED` and `IV_INELIGIBLE`

### Initial Page Load Indicator — `isInitialLoading` (`App.js`)
- On fresh page load, 4 parallel fetches fire; tickers resolve first, causing `ALL_DATA` to recompute with `generateMockData()` — shows fake sparklines, prices, and signal values
- Batch fetch (hitting Fly.io → Supabase) takes 20–30 seconds; during this window REFRESH DATA and CALCULATE SIGNALS showed misleadingly green/blue with no loading indication
- **Fix:** Added `isInitialLoading` state (starts `true`, set `false` in `.finally()` of the batch fetch)
- Both buttons grey and disabled during initial load; REFRESH DATA shows "⟳ LOADING..." text
- Loading banner "⟳ LOADING MARKET DATA..." appears above the table rows (shared with `isRefreshing` banner)
- "⚠ LIVE DATA UNAVAILABLE — DISPLAYING MOCK DATA" banner shows when batch returns empty after load completes

### Page Load vs REFRESH DATA — Separated Endpoints (`market_data.py`, `api.js`)
- **Root problem:** Page load and REFRESH DATA both called `/api/market-data/batch` → both triggered Schwab/Yahoo fetch → every navigation to Dashboard caused a 20-30s wait and made CALCULATE SIGNALS go amber
- **Fix:** Two separate endpoints with different responsibilities:
  - `GET /api/market-data/cached` — **page load only** — pure DB read, never calls Schwab or Yahoo; returns whatever is in `price_cache` right now; single `IN` query with `load_only` (no large JSON blobs loaded)
  - `GET /api/market-data/batch` — **REFRESH DATA button only** — triggers full Schwab/Yahoo fetch pipeline
- `fetchCachedMarketData()` in `api.js` calls `/cached` — used in page load `useEffect`
- `fetchBatchMarketData()` in `api.js` calls `/batch` — used by REFRESH DATA button handler only
- **Rule:** Never call `/batch` on page load or navigation — it always triggers external API calls

### React Router SPA Navigation (`App.js`, `AdminPanel.js`)
- **Root problem:** Routing used `window.location.pathname` check — admin → dashboard was a full page reload, destroying all React state and re-firing all 5 API calls every navigation
- **Fix:** `react-router-dom` v7 installed; `App` now uses `<BrowserRouter><Routes><Route>` — navigation is an SPA transition, no page reload, no white flash
- `AdminPanel` uses `useNavigate()` hook; `← DASHBOARD` button calls `navigate("/")` instead of `window.location.href = "/"`
- Dashboard still remounts on navigation (Routes unmounts inactive routes) but with `/cached` the re-fetch is instant (pure DB read)
- nginx `try_files` config already handles SPA routing in production — no nginx changes needed

### Global Header (`src/components/shared/Header.js`)
- Fixed top bar: `position: fixed, top: 0, left: 0, right: 0, height: 48px, zIndex: 200`
- Background matches sidebar: `#060e1a`, border-bottom `1px solid #1a2a3a`
- **Left side — brand:** 4px gradient bar (`#00e5a0` → `#0077ff`) + "SIGNAL MATRIX" (11px, 700, `#e8f4ff`, 0.2em tracking) + "MULTI-TIMEFRAME · PROBABILISTIC" subtitle (9px, `#445566`)
- **Right side — user profile placeholder:** 30px circle button with SVG person icon; future home for CALCULATE SIGNALS, REFRESH DATA, and real user profile
- `zIndex: 200` — above sidebar (`zIndex: 100`) so header always covers the sidebar top edge
- **Future:** CALCULATE SIGNALS and REFRESH DATA buttons will migrate here from the dashboard header; user profile will link to settings

### Left Sidebar Navigation (`src/components/shared/Sidebar.js`)
- Collapsible icon rail: **48px collapsed** (icon only), **180px expanded** (icon + label) on `onMouseEnter`/`onMouseLeave`; `transition: width 200ms ease`
- `position: fixed`, `top: 48px` (below global header), `height: calc(100vh - 48px)` — `position: fixed` eliminates ResizeObserver stutter caused by Recharts `ResponsiveContainer` firing during flex-layout width changes
- Active item: `3px solid #00e5a0` left border + `rgba(0,229,160,0.07)` background; detected via `useLocation()` (exact match for `/`, prefix for sub-routes)
- **Lock toggle** at bottom: click to lock sidebar open or return to hover mode; icon-only (no text label), tooltip = "Collapse Sidebar" / "Expand Sidebar"; green lock icon when locked, grey when unlocked
- `locked` and `onToggleLock` props — `sidebarLocked` state lives in `AppLayout`; `expanded = locked || hovered`; mouse enter/leave events disabled when locked
- **NAV_ITEMS array** in `Sidebar.js` is the single place to add future dashboards — each entry is `{ icon, label, path, exact }`
- **Admin is NOT in the sidebar** — admin remains accessible only by direct URL (`/admin`); settings gear icon (deferred) will be the future password gate
- **AppLayout pattern in `App.js`:** `App` renders `<BrowserRouter><AppLayout />` — `AppLayout` renders `<Header />` first (fixed), then a flex container with `paddingTop: 48`; `sidebarWidth = locked ? 180 : 48`; content div uses `marginLeft: sidebarWidth` with matching transition
- **Routes defined:**
  - `/ticker/:symbol` → `TickerAnalysis` stub (future ticker drill-down analysis page)
  - `/vol` → `SpxVolChart`
  - `/vol/macro` → `MacroVolChart`
  - `/spx-impact` → `SpxImpactDashboard`
  - `/sector` → `SectorPerformance`
  - `/admin` → `AdminPanel` (no sidebar)
  - `*` → `Dashboard` (catch-all)
- **Rule:** Add new dashboards by appending to `NAV_ITEMS` in `Sidebar.js` — no other files need changing for basic nav items
- **Rule:** Sidebar must remain `position: fixed` — reverting to `position: sticky` re-introduces ResizeObserver stutter on any page with Recharts `ResponsiveContainer`

### SPX Vol Chart (`src/components/Vol/SpxVolChart.js`)
- Route: `/vol` (registered as `/vol/*` in AppLayout)
- **Data:** `fetchSpxVolHistory()` → `/api/signals/spx-vol-history` — returns `{ dates, hv30, hv90, pct_change, updated }`
- **Chart:** Recharts `ComposedChart` — HV30 (blue line, left axis), HV90 (orange line, left axis), daily % change (green/red bars, right axis)
- **X-axis:** Year labels only — `getJanTicks(dates)` pre-filters to first Jan date per year, passed as explicit `ticks` prop; eliminates grey phantom tick marks from null-returning custom tick components
- **Right Y-axis:** Symmetric domain callback `([dataMin, dataMax]) => [-bound, bound]` where `bound = ceil(max(|dataMin|, |dataMax|) × 10) / 10` — ensures zero-centered bar chart
- **2Y/MAX toggle:** Default 2Y; `useMemo` filters data by ISO date string comparison; toggle buttons styled with active border/background matching dashboard aesthetic
- **Layout:** 75px horizontal padding on both sides; chart area has `border: 1px solid #1a2a3a`, `borderRadius: 6`, `background: #07111f`
- **`position: fixed` sidebar fix:** Sidebar stutter on this page was caused by Recharts `ResponsiveContainer` ResizeObserver firing as the flex-layout content width changed during hover transitions. Fixed by making sidebar `position: fixed` — content width never changes.

### Macro Volatility Dashboard (`src/components/Vol/MacroVolChart.js`)
- Route: `/vol/macro` — sidebar nav item "MACRO VOL" with dual-wave SVG icon (`MacroVolIcon`)
- **Data:** `fetchMacroVolHistory()` → `GET /api/vol/macro-history` — returns `{ dates, series, stats, updated }`
- **Tickers displayed:** VIX, VXN (NazVol), RVX, GVZ, OVX — 5 series on chart and stats table. MOVE is collected in the data pipeline (SCHWAB_INDEX_HISTORY_MAP) and stored in price_cache but intentionally excluded from this dashboard — reserved for the future Fixed Income dashboard.
- **Chart:** Recharts `ComposedChart` — VIX/VXN/RVX/GVZ on left Y-axis; OVX on right Y-axis (crude oil vol — higher scale). 2Y/MAX toggle. Dynamic filtering: tickers with no API data are excluded automatically.
- **Stats table:** Last · Prior Day · 1 Wk Ago · 1 Mo Ago · 3 Mo Ago · DoD (Δ bps / %Δ) · WoW · MoM. Vol up = red, vol down = green. MOVE row tagged with "bond" badge. Header labels (DoD/WoW/MoM) are on the Δ bps column (not colspan=2).
- **Date alignment:** `common_dates` = set intersection of all 6 tickers' date arrays. DoD stats anchored to `common_dates[-1]` / `common_dates[-2]` — avoids 0-delta artifact when Schwab includes weekend bars for some tickers.
- **Backend:** `GET /api/vol/macro-history` in `backend/routers/vol.py`
  - Queries `price_cache` for `_MACRO_VOL_TICKERS = ["VIX", "VXN", "RVX", "GVZ", "OVX", "MOVE"]`
  - Intersects date sets; builds `series {ticker: [close, ...]}` and `stats {ticker: {...}}` aligned to intersection
  - Stats use `bisect.bisect_right` for historical lookups (1d/1w/1m/3m)

### Macro Vol — Data Source Architecture
- **VIX:** Yahoo Finance (`^VIX`) — in `SCHWAB_UNSUPPORTED`, not in `SCHWAB_INDEX_HISTORY_MAP`
- **VXN, RVX, GVZ, OVX, MOVE:** Schwab `get_price_history()` using `$-prefix` symbols (`$VXN`, `$RVX`, `$GVZ`, `$OVX`, `$MOVE`) — defined in `SCHWAB_INDEX_HISTORY_MAP` in `schwab_market_data.py`
  - These stay in `SCHWAB_UNSUPPORTED` (batch quotes don't work for them) but are fetched via `_schwab_fetch_index_histories()`
  - Called from the tail of `_schwab_fetch()` after splitting `unsupported` into `yahoo_only` vs `schwab_index`
- **Gap detection modes for index history tickers:**
  - `skip`: no-op (cache_date == today)
  - `append` (1–5 day gap): 10-day DAY period fetch → `_append_bar` last candle (fast, avoids buggy 1-month endpoint)
  - `short` (6–45 day gap) / `bootstrap`: 5-year YEAR period fetch → full `_upsert` with merge (reliable; 1-month endpoint mis-scales MOVE values)
- **Yahoo fallback protection:** `_yahoo_fallback()` excludes `SCHWAB_INDEX_HISTORY_MAP` tickers entirely. When Schwab tokens expire, these tickers keep stale Schwab data rather than being overwritten with Yahoo garbage (Yahoo returns ~73 stale bars for `^RVX` starting from the same date as existing history, causing `_upsert` merge `cut=0` → full history replaced)
- **`YAHOO_SYMBOL_MAP`** still has entries for VXN/RVX/GVZ/OVX/MOVE (`^VXN` etc.) — used only for intraday Yahoo quotes, not EOD history
- **`IV_INELIGIBLE` and `_HV_ONLY_TICKERS`** in `schwab_options.py` include all 5 tickers — no options chain fetch; HV30/HV90 accumulated via `accumulate_hv_only()`
- **Production bootstrap:** After first deploy or after RVX/MOVE data corruption, clear the row and re-run `_schwab_fetch_index_histories(db, list(SCHWAB_INDEX_HISTORY_MAP.keys()), client)` directly in Python

### Sector Performance Dashboard (`src/components/Macro/SectorPerformance.js`)
- Route: `/sector` — sidebar nav item "SECTOR PERF" with pie-sector icon
- **Data:** `apiFetch("/api/sector-performance")` → `{ absolute, relative, labels, as_of }`
- **Two tables stacked vertically:**
  1. **Sector Performance** — 11 sector ETFs + S&P 500 (SPX bolded, double-border separator at top)
  2. **Sector Relative Performance** — same 11 sectors, % change minus SPX for each period; no SPX row
- **Columns:** SECTOR | TICKER | PRICE | 1-DAY % | MTD % | QTD % | YTD %
- **Sub-labels** on period columns: e.g. "May 2026" under MTD %, "Q2 2026" under QTD %, "2026" under YTD %
- **Cell coloring:** positive → `rgba(0,229,160,0.13)` bg + `#00e5a0` text; negative → `rgba(255,77,109,0.13)` bg + `#ff4d6d` text; null → transparent + grey dash
- **Header:** title left, "SIGNAL MATRIX / EOD · {date}" right — same layout on both tables
- **Layout:** `padding: "28px 164px"` — matches SPX Impact page cushion
- **Backend:** `GET /api/sector-performance` in `backend/routers/sector_performance.py`
  - Reads `history_json` + `history_dates_json` from `price_cache` for all 12 tickers (single `IN` query + `load_only`)
  - Uses `bisect_left` on the date array to find period-start prices: last close strictly before YTD/QTD/MTD start dates; `prices[-2]` for 1-day prior
  - Relative = sector % − SPX % for each period column
  - Returns `labels` dict `{ mtd, qtd, ytd }` with human-readable strings and `as_of` date string
- **Sector ticker list (hardcoded in router):** XLY, XLF, XLV, XLK, XLP, XLI, XLB, XLE, XLU, XLRE, XLC, SPX
- **Rule:** SPX price displayed without `$` prefix (index, not a dollar price); all sector ETFs display with `$` prefix

### Ticker Analysis Page — Stub (`src/components/Analysis/TickerAnalysis.js`)
- Route: `/ticker/:symbol` — reads symbol from `useParams()`
- Has a ticker input form: submit navigates to `/ticker/{SYMBOL}` (uppercased, trimmed)
- Placeholder "COMING SOON" body — full charts/IV/structure/regime content is future scope
- Sidebar is present (rendered by AppLayout for all non-admin routes)
- **Rule:** Dashboard row-click behavior is unchanged (popup still fires) — when the full analysis page is built, wire it by replacing the row-click handler in `App.js`

### N+1 Query Fix — Batch Read Path (`market_data.py`)
- **Root problem:** `refresh_data()` read cache results with a per-ticker loop: `for ticker in tickers: db.query(PriceCache).filter(ticker == t).first()` — 51 round trips to Supabase to build a single page load response
- **Fix:** Single `IN` query with `load_only` — fetches only the columns needed for `serialize_cache_row`, skips `history_json` and `volume_history_json` blobs (252-756 data points each, never used in page load response)
- Same pattern applied in the new `/cached` endpoint
- **Rule:** Never re-introduce per-ticker query loops in read paths — always use `.filter(PriceCache.ticker.in_(tickers))`

### Gap Detection — Incremental History Fetch (`schwab_market_data.py`)
- **Root problem:** Every REFRESH DATA call fetched 3 months of history per ticker from Schwab, even though the DB already had the full history and only 1 new bar was needed
- **Fix:** `_history_fetch_mode(existing_row, today_str)` determines what to fetch per ticker:
  ```
  "skip"      — last stored date == today → update quote fields only (no history change)
  "append"    — gap 1-5 calendar days (normal day, weekend, holiday) → append today's bar from batch quote, no Schwab history API call
  "short"     — gap 6-45 calendar days → 1-month targeted fetch (covers short outages)
  "bootstrap" — no history, < 252 bars, or gap > 45 days → full 5-year fetch
  ```
- `_append_bar()` — appends close/volume from batch quote to existing `history_json`; recomputes MA20/50/100/200, STD20, spark from merged history; no API call
- `_update_quote_only()` — updates close/volume/timestamp only when history already contains today
- Pre-load all existing cache rows before the ticker loop (one `IN` query) — eliminates another N+1 inside `_schwab_fetch`
- `time.sleep(0.5)` rate-limit guard only executes when a Schwab history API call is actually made — not on skip/append paths
- **Normal daily result (Schwab tickers):** 1 batch quote call (all tickers) + 0 per-ticker history calls → completes in seconds
- **New ticker result:** bootstrap path fires automatically — no special handling needed; existing tickers are unaffected

### Gap Detection — Yahoo-Only Tickers (`schwab_market_data.py`, `yahoo_finance.py`)
- **Root problem:** `_yahoo_fetch_subset` had no cache awareness — fetched full 5-year history from Yahoo for every Yahoo-only ticker (SPX, NDX, VIX, RUT, USD, JPY, /CL, /ZN, /GC, $DJI) on every REFRESH DATA call. Second hit of the day: ~66 seconds.
- **Fix:** Same four-mode gap detection applied to the Yahoo path:
  - `skip` — cache_date == today → no-op; second hit of the day is now instant for all Yahoo tickers
  - `append` — gap 1-5 days → `fetch_ticker_close()` (5-day fetch, returns close+volume only) + `_append_bar()`; avoids full 5-year pull on normal daily runs
  - `short` / `bootstrap` — full `fetch_ticker_data()` (5-year fetch) as before
- `fetch_ticker_close(ticker)` added to `yahoo_finance.py` — uses `yf.Ticker().history(period="5d")`, returns `(close, volume)` tuple; fast, no history processing
- Pre-load all existing rows before Yahoo loop (one `IN` query) — same N+1 fix as Schwab path
- **Result:** Second REFRESH DATA same day → instant (all skip). Normal daily first hit → ~10s instead of ~60s (lightweight 5d fetch × 10 tickers)

### CALCULATE SIGNALS — Hurst + Pivots Skip on Repeat Manual Runs (`signals.py`)
- **Root problem:** Manual CALCULATE SIGNALS mid-day recomputed Hurst (~130s) + Pivots (~40s) every press, even though both are EOD-only calculations that don't change until new price data arrives
- **Fix:** `calculate_signals()` checks `calculated_at` date against today ET for both `SignalHurst` and `SignalPivots` before running. If already computed today and `trigger == "manual"`, stage is skipped
- **Scheduler path unchanged:** `trigger="scheduled"` always runs full pipeline — Hurst + Pivots always recompute at 4 PM EOD
- **First manual press of the day:** full pipeline (~263s for 95 tickers) — unavoidable, Hurst hasn't run yet
- **Subsequent manual presses same day:** only output stage runs (~76s) — Hurst + Pivots skipped
- **Rule:** Never apply this skip to `trigger="scheduled"` — EOD run must always recompute everything with fresh price data

### IV Fetch — Idempotent on Manual REFRESH DATA (`market_data.py`, `schwab_options.py`)
- **Root problem:** `market_data.py` called `schwab_fetch_iv(db, force=True)` — bypassed the built-in idempotency check on every manual REFRESH DATA press, running ~65 Schwab options chain calls (~55 seconds) even when IV was already fresh
- **Fix:** Changed to `schwab_fetch_iv(db, force=False)` — the existing idempotency check now fires: if IV already fetched today, skip entirely
- **Scheduler path unchanged:** Scheduler calls `schwab_fetch_iv(db)` (default `force=False`) — since IV has never been fetched when the 4 PM job runs, the idempotency check never fires and IV always fetches fresh at EOD
- **First manual REFRESH DATA of the day:** IV fetches (~55 seconds) — unavoidable, 65 options chain calls
- **Subsequent REFRESH DATA same day:** IV skipped entirely → near-instant
- **Rule:** Never change back to `force=True` in `market_data.py` — it re-introduces the 55-second penalty on every button press

### Intraday Price Refresh — `schwab_fetch_intraday_quotes` vs `schwab_fetch_all` (`schwab_market_data.py`)
- **Root problem:** The intraday monitor originally called `schwab_fetch_all(db)` for price updates. `schwab_fetch_all()` has an idempotency check that returns early once `cache_date == today AND data_source == "schwab"` — meaning after the first intraday call, every subsequent 15-minute call would skip `get_quotes()` entirely and `price_cache.close` would stay frozen at the first read value.
- **Fix:** Added `schwab_fetch_intraday_quotes(db)` — a dedicated lightweight function for intraday use only:
  - No idempotency check — always calls `get_quotes()` every time it is invoked
  - Uses `lastPrice` exclusively — never falls back to `closePrice` (which is yesterday's EOD)
  - Does NOT update `cache_date` — preserves the EOD idempotency check for `schwab_fetch_all()`
  - Updates `close`, `volume`, `daily_high`, `daily_low`, and `updated_at` only
- **Rule:** The intraday monitor must ALWAYS use `schwab_fetch_intraday_quotes(db)` — never `schwab_fetch_all(db)`. Using `schwab_fetch_all` intraday silently freezes prices after the first call.

### Live Dot Removed from Header (`App.js`)
- The `● LIVE` dot in the dashboard header was removed — it added no signal value and confused users about data freshness
- SCHED indicator, EOD timestamp, and button colors already communicate all relevant freshness state

### Button Freshness Indicators — REFRESH DATA / CALCULATE SIGNALS
Buttons change color to communicate data/signal state — no separate status dots needed:
- **REFRESH DATA**: green = data is current; **amber** = past 4:15 PM ET on a weekday AND cache is from a prior day
  - Before 4:15 PM ET: always green — yesterday's EOD close IS the freshest data available (market hasn't closed)
  - Weekends: always green — Friday's close is correct, no trading
  - After 4:15 PM ET on a weekday with stale cache: amber (scheduler should have run)
- **CALCULATE SIGNALS**: blue = signals current; **amber** = signals timestamp is older than data timestamp (full timestamp comparison, not date-only)
  - Same-day staleness is now caught — if data refreshed at 10 PM but signals last ran at 8 PM, button goes amber
- Both go grey with "⟳ LOADING..." text while running; REFRESH DATA also shows "⟳ LOADING..." during initial page load
- `calculated_at` exposed in `/api/signals/stored` response for freshness comparison
- Freshness logic lives in the button render block in `App.js`
- **Admin-only:** both buttons are hidden for non-admin users (`isAdmin` check in App.js); backend endpoints `/api/market-data/batch` and `/api/signals/calculate` enforce the same with `require_admin_user`

### Auth & User Management — JWT Cookie + RBAC ✅
- Replaced `REACT_APP_ADMIN_PASSWORD` (shared client-side gate) with full session-auth layer
- JWT in httpOnly cookie (`sm_session`), 12-hour expiry, `samesite="lax"`, `secure=IS_PRODUCTION`
- Two new tables: `users`, `password_reset_tokens` (UUID primary keys; SQLAlchemy stores as TEXT in SQLite, native UUID in Postgres)
- Two new routers: `routers/auth.py` (renamed existing `router` → `schwab_router`, added new JWT auth `router`) and `routers/users.py` (admin-only user CRUD)
- New service: `services/auth_service.py` — bcrypt hashing, JWT encode/decode, password strength validation, reset tokens, `seed_admin_if_empty`, `require_admin_user` dependency
- Self-registration → `pending` state → admin approval → `active` flow
- Password reset via email link; 15-minute token TTL; reset-tokens are one-shot (consume marks `used=True`)
- Admin Users tab at `/admin/users` (UserList.js): list / activate / disable / change role / reset password (admin-side, no email)
- Self-protection guards in admin endpoints: cannot disable own account, cannot demote self from admin
- Session middleware in `main.py` checks cookie → user → status on every request; `PUBLIC_PATHS` set covers auth endpoints + Schwab OAuth callback + `/health` + `/`
- slowapi rate limits: register 3/hour, login 5/5min, forgot-password 3/hour, reset-password 5/hour
- Recovery: `backend/scripts/reset_admin.py` (idempotent — creates or resets admin from `ADMIN_EMAIL` / `ADMIN_PASSWORD` env vars). Run via `fly ssh console --app signal-matrix-api -C "python -m scripts.reset_admin"`. Documented in `Docs/RUNBOOK_AUTH_RECOVERY.md`.
- `Base.metadata.create_all()` in `main.py` creates auth tables at startup; alembic migrations are guarded with `if "table_name" not in inspector.get_table_names()` so `alembic upgrade head` post-deploy is idempotent and just stamps the version table.
- New env vars: `JWT_SECRET`, `ADMIN_EMAIL`, `ADMIN_PASSWORD`, `ADMIN_DISPLAY_NAME`, `ENVIRONMENT`, `APP_BASE_URL` (defaults to `https://signal.suttonmc.com`; local `.env` sets to `http://localhost:3000` for email-link clickthrough during dev).
- Removed env var: `REACT_APP_ADMIN_PASSWORD` (and accompanying `Dockerfile.web.fly` build arg, `deploy-web.sh` plumbing).
- Logout clears cookie only; JWT remains valid until natural expiry. To force-revoke a session, set `users.status = "disabled"` — middleware blocks every subsequent request from that user.
- Frontend: `AuthProvider` (top-level wrapper in `App.js`), `apiFetch` (in `services/api.js`; auto-redirects to `/login` on 401), `ProtectedRoute` (in `components/shared/ProtectedRoute.js`; supports `requireAdmin` prop). Header dropdown displays "Signed in as / email / role badge" + admin panel link (admin only) + sign out.
- See `Docs/Auth_User_Management_Spec_v1.0.md` for full spec including deferred decisions (token blocklist, useApiFetch hook, Cloudflare WAF rate limiting).

---

## Project Folder Structure
```
signal-matrix/
├── .claude/
│   ├── launch.json
│   └── settings.local.json
├── Docs/
│   ├── SignalMatrix_Spec_v1.7.txt         ← ✅ Neo's readable copy — CURRENT spec (v1.7)
│   ├── SignalMatrix_Spec_v1.6.txt         ← ✅ Neo's readable copy — superseded by v1.7
│   ├── SignalMatrix_Spec_v1.5.txt         ← ✅ Neo's readable copy — Phase 4 era (superseded)
│   ├── SignalMatrix_Phase5_Spec_v1.0.docx ← spec — NOT readable by Neo (.docx)
│   ├── SignalMatrix_Phase5_Spec_v1.0.txt  ← ✅ Neo's readable copy — Phase 5 spec
│   └── QuadTracker_Spec_v1.1.docx        ← spec — NOT readable by Neo (.docx)
├── public/
├── src/
│   ├── components/
│   │   ├── Admin/
│   │   │   ├── AdminPanel.js              ← admin shell: password gate + header + tab nav + nested Routes
│   │   │   ├── TickerList.js              ← ticker CRUD tab (/admin/tickers) — extracted from AdminPanel
│   │   │   └── QuadSetup.js              ← quad config tab (/admin/quad) — US monthly NTM grid (12 rows, auto-save) + country quarterly table (16 countries × 4 quarters)
│   │   ├── Analysis/
│   │   │   └── TickerAnalysis.js          ← stub — /ticker/:symbol route; full page future scope
│   │   ├── Dashboard/                     ← placeholder, logic still in App.js
│   │   ├── Macro/
│   │   │   └── SectorPerformance.js       ← /sector route; absolute + relative sector perf tables (1D/MTD/QTD/YTD vs SPX)
│   │   ├── Vol/
│   │   │   └── SpxVolChart.js             ← SPX realized vol chart (HV30/HV90 lines + daily % change bars); 2Y/MAX toggle
│   │   └── shared/
│   │       ├── Header.js                  ← global top bar (48px fixed); brand left, user profile right
│   │       └── Sidebar.js                 ← collapsible left sidebar (48px→180px); lock toggle; position: fixed at top: 48px
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
│   │   ├── vol_history.py                  ← Task 5.5 — IV history DB model ✅
│   │   └── intraday_alert_log.py          ← Intraday monitor alert dedup log
│   ├── alembic/                           ← Task 5.1 — DB migration tooling ✅
│   │   ├── env.py
│   │   └── versions/
│   │       ├── aa2d62ea88e4_initial_schema.py
│   │       ├── b3f1c9d2e4a7_price_cache_add_ma_columns.py   ← v1.7 Phase A
│   │       ├── c9a4e1f2b8d3_signal_output_add_ma_levels.py  ← v1.7 Phase B
│   │       ├── d5e3f1a2c4b7_signal_output_add_extended_flags.py ← v1.7 Phase C
│   │       ├── e2f4a6b8c1d0_add_d_extended_to_pivots_and_output.py ← EXTENDED architectural cleanup
│   │       ├── f7a3b2c1d9e6_price_cache_add_ohlc_tp.py      ← added daily_high/low, history H/L, vov
│   │       ├── j7e5f3g1h2i0_price_cache_add_atr.py          ← added price_cache.atr (14-day ATR)
│   │       ├── 13fb636fe76a_price_cache_drop_tp_columns.py  ← dropped ma20_tp, std20_tp (±7pt SPX, negligible)
│   │       ├── k1a2b3c4d5e6_iv_history_vol_rename_and_skew.py ← rv21→hv30, rv63→hv90; added call_iv_25d, put_iv_25d, risk_reversal, put_call_ratio
│   │       ├── l2b3c4d5e6f7_price_cache_add_vol_columns.py  ← added hv30, hv90, iv30, risk_reversal, skew_rank, put_call_ratio
│   │       ├── m3c4d5e6f7g8_iv_history_rename_vol_premium_vrp_add_vrp_rank.py  ← vol_premium→vrp; added price_cache.vrp_rank
│   │       ├── 08f62d15c8b7_iv_history_add_skew_rank.py                        ← added vol_history.skew_rank (Integer 0–100)
│   │       ├── a1b2c3d4e5f6_add_intraday_alert_log.py                          ← intraday_alert_log table (PROXIMITY + RETRACEMENT_50 dedup)
│   │       ├── n1o2p3q4r5s6_rename_iv_history_to_vol_history.py                ← renamed iv_history → vol_history; added accumulate_hv_only() for Yahoo-only tickers
│   │       ├── cc64e88accc0_merge_heads.py                                      ← merge two divergent heads before new revision
│   │       ├── 312d2abdf53d_vol_history_implied_vol_nullable.py                 ← vol_history.implied_vol nullable (allows HV-only rows)
│   │       ├── o1p2q3r4s5t6_signal_output_add_quad_score.py                    ← added signal_output.quad_score (Integer) — v2.0 additive contribution
│   │       ├── p1q2r3s4t5u6_price_cache_add_hv_rank.py                          ← added price_cache.hv_rank (Integer 0–100)
│   │       ├── q2r3s4t5u6v7_add_snap_state_columns.py                           ← v1.9.1 hrr_snapped / lrr_snapped on signal_output + signal_history
│   │       ├── t5u6v7w8x9y0_add_spx_impact_cache.py                              ← spx_impact_cache table (EOD constituent impact)
│   │       └── u6v7w8x9y0z1_spx_impact_add_label_weights.py                      ← added snapshot_label + weights_json (intraday snapshot support)
│   ├── services/
│   │   ├── yahoo_finance.py
│   │   ├── signal_engine.py               ← Task 3.1 — Hurst + Fractal Dimension (DFA) ✅
│   │   ├── pivot_engine.py                ← Task 3.2 — ABC Pivot Detector ✅
│   │   ├── conviction_engine.py           ← Task 3.3 — LRR/HRR + Conviction Engine ✅
│   │   ├── scheduler.py                   ← Task 4.2 — APScheduler EOD + intraday monitor + SPX impact jobs ✅
│   │   ├── schwab_client.py               ← Task 5.3 — Token management + Schwab client ✅
│   │   ├── schwab_market_data.py          ← Task 5.4 — EOD quote + history fetch + intraday quotes ✅
│   │   ├── schwab_options.py              ← Task 5.5 — IV fetch + vol_history write ✅
│   │   ├── intraday_monitor.py            ← PROXIMITY + RETRACEMENT_50 alert engine ✅
│   │   ├── spx_constituents.py            ← SPX constituent impact — IVV weights + Schwab batch quotes ✅
│   │   └── sms.py                         ← Twilio SMS wrapper ✅
│   └── routers/
│       ├── market_data.py
│       ├── signals.py                     ← Task 3.3/3.4/4.3 — Signal endpoints + history ✅
│       ├── scheduler.py                   ← Task 4.2 — Scheduler status endpoint ✅
│       ├── auth.py                        ← Task 5.3 — Schwab OAuth endpoints ✅
│       ├── tickers.py                     ← Task 4.6/4.7 — Ticker CRUD + yfinance lookup ✅
│       ├── spx_impact.py                  ← GET /api/spx-impact — returns eod + intraday snapshots ✅
│       └── sector_performance.py          ← GET /api/sector-performance — 1D/MTD/QTD/YTD absolute + relative sector tables
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
| 5.5 | IV Percentile — options chain fetch, vol_history table | ✅ Complete |
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
- **Three registered jobs:**
  1. `schwab_data_job` — CronTrigger 4:00 PM ET NYSE trading days (prices → IV → signals)
  2. `schwab_refresh` — interval every 25 min (proactive Schwab token refresh)
  3. `intraday_monitor` — CronTrigger mon–fri 9:30 AM–3:45 PM ET at :00/:15/:30/:45
- On startup: catch-up check — if past 4:00 PM ET, trading day, and no successful run today → runs immediately
- All dates use **ET timezone** — never UTC (see UTC vs ET fix above)
- **Five registered jobs:** `schwab_data_job` (4 PM EOD), `schwab_refresh` (25 min interval), `intraday_monitor` (15 min market hours), `spx_impact_11am` (11 AM ET Mon-Fri), `spx_impact_1pm` (1 PM ET Mon-Fri)

### EOD Flow (4:00 PM ET, NYSE trading days) — single chained job
```
APScheduler (schwab_data_job)
    → schwab_fetch_all()                writes → price_cache (Schwab primary, Yahoo fallback)
    → schwab_fetch_iv()                 writes → price_cache.rel_iv + vol_history (IV-eligible tickers)
    → accumulate_hv_only()              writes → vol_history hv30/hv90 (Yahoo-only: SPX, NDX, RUT, VIX, $DJI, USD, JPY, futures, VVIX)
    → calculate_signals()               writes → signal_hurst / signal_pivots / signal_output / signal_history
    → compute_and_cache_spx_impact()    writes → spx_impact_cache (label='eod') — non-fatal step 4
    → scheduler_log                     writes → success/failure entry
```
Previously two separate jobs (data at 4:00 PM, signals at 4:15 PM). Merged into one — signals run
immediately after data fetch, both buttons go green together by ~4:02 PM.

### Intraday SPX Impact Snapshots (11 AM + 1 PM ET, Mon-Fri)
```
APScheduler (spx_impact_11am / spx_impact_1pm)
    → Read weights_json from most recent EOD row in spx_impact_cache — no IVV fetch
    → _batch_schwab_quotes()    3 calls × 200-ticker chunks (~5 seconds total)
    → _compute_impacts()        no AH strip (lastPrice is live intraday)
    → Upsert spx_impact_cache   label='11am' or '1pm', computed_date=today_et
```
- Non-fatal per-job (each job is standalone, not chained to EOD)
- Idempotent: re-run same day overwrites the existing intraday row
- Trading day guard: `_is_trading_day()` check inside job — no-op on holidays/weekends

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
Docker down at 4:00 PM → startup catchup fires on restart if past 4:00 ET and today's job missing
PC off at 4:00 PM      → same catchup pattern covers this
Run twice same day     → signal_history idempotency check prevents duplicate snapshots
429 from Yahoo         → stale cache served, scheduler_log records failure
```

### Scheduler Files
| File | Role |
|---|---|
| `backend/services/scheduler.py` | Core job logic, catch-up, start/shutdown; all three jobs |
| `backend/routers/scheduler.py` | `GET /api/scheduler/status` endpoint |
| `backend/models/scheduler_log.py` | SQLAlchemy model for `scheduler_log` table |
| `backend/services/intraday_monitor.py` | PROXIMITY + RETRACEMENT_50 alert engine |
| `backend/services/sms.py` | Twilio SMS wrapper |
| `backend/models/intraday_alert_log.py` | Alert dedup log model |

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

## Intraday Monitor — PROXIMITY + RETRACEMENT_50 SMS Alerts ✅

### Overview
Lightweight price monitor running every 15 minutes during NYSE trading hours (9:30 AM–3:45 PM ET).
Does NOT recalculate pivots, Hurst, or conviction. Reads EOD-calculated signal state and watches
live price against it. Fires SMS alerts via Twilio when triggers are met.

**Critical design constraint:** Never call `calculate_signals()` intraday — pivot states require
confirmed EOD closes. Running signals intraday would produce false BREAK_OF_TRADE states.
The monitor is purely observational.

### Two Triggers (each fires at most once per ticker per day)

**PROXIMITY** — `prox >= 0.85` toward entry zone:
```
Bullish: prox = 1 - (close - lrr) / (hrr - lrr)   peaks at 1.0 when close = LRR
Bearish: prox = (close - lrr) / (hrr - lrr)         peaks at 1.0 when close = HRR
Not clamped — price below LRR (Bullish) reports as 110%+ etc.
```
- Fires once per ticker per day (first time prox >= 0.85)
- SMS: ticker, viewpoint, price, entry level, prox %, range, conviction

**RETRACEMENT_50** — price retraces 50% from D back toward C (pullback entry):
```
Gate: structural_state must be UPTREND_VALID or DOWNTREND_VALID
Uptrend:   d_eff = max(pivot_d, close)          # intraday D may extend higher
           level_50 = pivot_c + 0.50 × (d_eff - pivot_c)
           fires when close <= level_50
Downtrend: d_eff = min(pivot_d, close)          # intraday D may extend lower
           level_50 = d_eff + 0.50 × (pivot_c - d_eff)
           fires when close >= level_50
```
- Dedup key includes `pivot_c` — new C = new setup = alert resets for same ticker same day
- SMS: ticker, viewpoint, price, D level, C pivot, 50% level, conviction

### Scheduler — CronTrigger (clock-aligned)
```python
CronTrigger(
    day_of_week = "mon-fri",
    hour        = "9-15",
    minute      = "0,15,30,45",
    timezone    = "America/New_York",
)
```
- Fires at :00/:15/:30/:45 aligned to clock — NOT relative to container start time
- `hour="9-15"` includes 9:00 and 9:15; pre-market guard skips those: `if now_et.hour == 9 and now_et.minute < 30: return`
- Effective window: 9:30 AM, 9:45 AM, 10:00 AM … 3:30 PM, 3:45 PM ET
- NYSE trading days only (via `_is_trading_day()` check inside the job)
- **Rule:** Never switch back to `"interval", minutes=15` — interval fires relative to container start and will miss the 9:30 AM open

### Per-Run Flow (`run_intraday_check(db)`)
```
1. schwab_fetch_intraday_quotes(db)      — fast batch quotes, lastPrice only, no cache_date update
2. Load signal_output                    — trade tf, non-Neutral viewpoints only (read-only)
3. Load signal_pivots                    — trade tf, matching tickers (read-only)
4. Load price_cache                      — current close after step 1
5. For each ticker:
   a. PROXIMITY check → send SMS + log if prox >= 0.85 and not already fired today
   b. RETRACEMENT_50 check → send SMS + log if at/past 50% level and not already fired today
6. db.commit()
```

### intraday_alert_log Table
```sql
id          INTEGER PRIMARY KEY AUTOINCREMENT
ticker      TEXT NOT NULL (index)
alert_date  TEXT NOT NULL                -- ET YYYY-MM-DD
alert_type  TEXT NOT NULL                -- 'PROXIMITY' | 'RETRACEMENT_50'
pivot_c     FLOAT nullable               -- dedup key for retracement (NULL for PROXIMITY)
fired_at    TEXT NOT NULL                -- ET HH:MM
price       FLOAT NOT NULL
metric      FLOAT nullable               -- prox% or retrace% (e.g. 0.88 or 0.50)
conviction  FLOAT nullable
created_at  TEXT NOT NULL                -- UTC timestamp

UNIQUE(ticker, alert_date, alert_type, pivot_c)
```
**Postgres NULL caveat:** `UNIQUE` with a nullable column does NOT prevent duplicate NULL rows in
Postgres (NULL != NULL). For PROXIMITY alerts (`pivot_c = NULL`) the Python `_already_fired()`
check is the primary dedup guard. The constraint only guarantees uniqueness for RETRACEMENT_50
rows (where `pivot_c` is set).

### SMS Service (`sms.py`)
- `send_sms(message)` → True/False
- Reads from env: `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_FROM`, `TWILIO_TO`
- No-ops silently (with warning log) if any credential is missing — safe in dev without Twilio configured
- Lazy import of `twilio.rest.Client` — won't crash on import if twilio package issue

### Why Volume Surge Was Excluded
The first 15-minute bar always has elevated volume relative to the daily average (opening spike) —
any volume pace comparison in the first 1–2 bars would fire false positives on nearly every ticker.
Dropped entirely. OBV direction already computed in EOD signals and displayed in the popup.

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
- After `/calculate` completes, frontend immediately fetches `GET /api/signals/stored` to populate React state
- **Critical:** `/calculate` response only contains raw `compute_output` data — it does NOT include `h_trade_delta`, `vix_regime`, or other fields written separately during the signal loop. Always use `/stored` as the source of truth for React state after calculation.

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
- Two new tables: `schwab_tokens` (encrypted OAuth tokens), `vol_history` (all vol metrics — IV30, HV30/HV90, VRP, skew; renamed from `iv_history`)
- `price_cache` gains `data_source` column: `'schwab'` | `'yahoo'` | `'yahoo_fallback'`
- Direct connection string → Alembic migrations only
- Pooled connection string (Transaction mode, port 6543) → app runtime

### Schwab API: schwab-py library
- `pip install schwab-py` — do not write raw HTTP calls against Schwab API
- Token storage: Fernet-encrypted in `schwab_tokens` table
- Token refresh: proactive background task every 25 minutes (APScheduler)
- Fallback: all Schwab calls fall back to Yahoo Finance on token expiry or API error
- Data source tagged in `price_cache.data_source` — visible in dashboard header

### EOD Scheduler: Updated Flow (Phase 5+)
```
4:00 PM ET — single chained job (prices → IV → signals)
    schwab_fetch_all()       Schwab primary / Yahoo fallback — writes price_cache
    schwab_fetch_iv()        ~65 requests (options-eligible only) — writes vol_history
    calculate_signals()      full pipeline — writes signal_output + signal_history
    scheduler_log            success/failure entry
```
Both REFRESH DATA and CALCULATE SIGNALS go green together by ~4:02 PM.

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
  - Tail / Long Term: 756 trading days
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

### Conviction Score Formula — v2.0 (Additive Four-Component)
```
H completely removed from conviction formula.
H is still calculated and stored for regime classification display only:
  H < 0.45 → mean-reverting regime (use oscillators: RSI, Stochastics)
  H > 0.55 → trending regime (use trend-following: MA, momentum)

conviction_final = structural_score + quad_score + volume_score + vix_score
                 → floor(0) → ×0.92 dampener (target-side hrr/lrr_warn) → ×1.05 NATH boost → cap(105)

Structural (0 / 25 / 50):
  Both aligned (Bullish+Bullish or Bearish+Bearish) → 50
  One direction, one Neutral → 25
  Both Neutral OR opposing (Bullish+Bearish) → 0

Quad (−15 / −11 / 0 / +15 / +20):
  Gate: structural_score==0 AND Viewpoint=Neutral → 0 (both timeframes Neutral/opposing).
        structural_score==25 (one timeframe confirmed) → quad CONTRIBUTES (not gated).
  Aligned, prob≥0.45 → +20; Aligned, prob<0.45 → +15
  Neutral alignment → 0
  Misaligned, prob≥0.45 → −15; Misaligned, prob<0.45 → −11

Volume (0 / +10 / +15):
  obv_direction: 40-bar regression on OBV series, normalized by std(OBV[-40:])
  obv_confirming: STRICT — regression dir AND MA20 slope (3-bar ROC) both confirm Trade Dir
  obv_confirming → +10; + obv_slope_trend accelerating in trade dir → +15

  OBV signals:
    obv_slope: sign of 3-bar ROC on OBV MA20: 'rising' | 'falling' | 'flat'
    obv_slope_trend: acceleration: slope_now vs slope_prev: 'increasing' | 'decreasing' | 'flat'

VIX/Vol (0 / +5 / +10 / +15 — Domestic Equities only; all other asset classes receive +15 flat):
  VIX < 19 AND VIX HRR < 19 → +15  (Investable+ — vol firmly locked below threshold)
  VIX < 19 (HRR still elevated) → +10  (Investable)
  VIX 19–23 → +5  (Edgy)
  VIX 24–29 → +0  (Choppy)
  VIX ≥ 30  → +0  (Danger)
  VIX HRR sourced from signal_output where ticker='VIX', timeframe='trade'
  Missing VIX row → +15 (default full credit)

Range: 0–105 (v2.0 additive formula; 105 only when NATH boost fires)
  Base max:  Structural 50 + Quad 20 + Volume 15 + VIX 15 = 100
  NATH max:  100 × 1.05 = 105 (Viewpoint=Bullish AND trade HRR > ATH)
  Floor: 0 (quad misalignment absorbed by floor before dampener)

Alert threshold: conviction >= 80 (v2.0 — requires full structural + aligned quad + some VIX)
Display threshold: conviction >= 45 (blank below); Neutral viewpoint shows in grey #8899aa when >= 45
CRITICAL: Conviction ALWAYS CALCULATES regardless of Viewpoint. Viewpoint = Neutral shows grey, never alerts.

vol_signal (Confirming/Diverging/Neutral) still computed and stored for popup display.
It no longer drives a multiplier — used only for popup Vol Signal display.
```

**Tail/Long Term H (756-day):** calculated and stored, displayed in popup as context only.
Not used in conviction formula.

### Direction Determination — Pivots Only (H has NO role)

**H does not determine direction. H is stored for regime classification display only (v1.8+: H removed from conviction formula and band width).**

```python
# Direction check — pivot engine pre-handles B-based breaks when d_extended; _compute_direction
# receives clean state values and applies C-based check for VALID states.
if structural_state in ("BREAK_CONFIRMED", "NO_STRUCTURE"):
    trade_dir = "Neutral"
elif structural_state in ("BREAK_OF_TRADE", "BREAK_OF_TREND"):
    trade_dir = "Bullish" if pivot_direction == "uptrend" else "Bearish"  # direction HOLDS
elif pivot_direction == "uptrend" and current_price > c:
    trade_dir = "Bullish"
elif pivot_direction == "downtrend" and current_price < c:
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
| BREAK_OF_TRADE (one close through break level) | **Bullish or Bearish — direction HOLDS** (provisional, first-day forgiveness) |
| BREAK_OF_TREND (one close through break level) | **Bullish or Bearish — direction HOLDS** (provisional, first-day forgiveness) |
| BREAK_CONFIRMED (2+ consecutive closes through break level) | Neutral |
| Pullback from D, price still above C | Bullish (UPTREND_VALID — trend intact; FORMING state eliminated v1.7) |
| Bounce from D, price still below C | Bearish (DOWNTREND_VALID — trend intact; FORMING state eliminated v1.7) |
| d_extended=True: D > B + bc_range — B is break level | Direction = Bullish/Bearish per state (pivot engine handles B-based break machine) |
| Insufficient pivot history | Neutral |
| Everything else | Neutral |

### LRR / HRR Display — Always Show

Trade LRR and HRR always calculate and always display regardless of viewpoint.
Trend Level and Tail Level display only when direction is not Neutral AND slope confirms direction.
Color communicates the state:
- Bullish direction → green
- Bearish direction → red
- Neutral direction → grey (`#8899aa`)
Each LRR/HRR cell uses its own timeframe's direction for color — not the overall viewpoint.

### Viewpoint States — FINAL (LOCKED)

| Viewpoint | Condition | Conviction |
|---|---|---|
| **Bullish** | Trade Bullish + Trend Bullish | Calculated; shown in green when ≥ 45 |
| **Bearish** | Trade Bearish + Trend Bearish | Calculated; shown in red when ≥ 45 |
| **Neutral** | Any other combination — including one Neutral, one Bullish/Bearish, or opposite directions | Calculated; shown in **grey `#8899aa`** when ≥ 45; never alerts |

**No Diverging state.** Three states only: Bullish, Bearish, Neutral.
**Conviction always calculates (v2.0)** — blank (None) only when score < 45. Neutral viewpoint displays score in grey; it does not suppress calculation.

### Alert Flag ⚡ Trigger (v2.0 — TWO conditions)
1. Viewpoint = Bullish OR Bearish (never fires on Neutral)
2. Conviction ≥ 80 (v2.0; requires full structural 50 + quad aligned 20 + partial VIX 10 minimum)

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
- Trend: **10 bars** (before AND after — both sides required)
- Long Term: **50 bars** (before AND after — both sides required)

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

**CRITICAL — Today's EOD bar IS included in price history:**
```python
# yahoo_finance.py stores today's close when fetched after market close
history_closes = closes[closes.index.date <= date.today()]
```
The scheduler runs at 4:00 PM ET after market close, so today's close is a confirmed EOD price —
not an incomplete intraday bar. Including it lets today count as a post-pivot confirmation bar
(e.g. the 5th bar after a pivot fires on the day of data fetch, not the next trading day).

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

### LRR / HRR Formula — Bollinger Band + Snap Framework v1.9.1 (`conviction_engine.py`)

**SUPERSEDES:** v1.8 fixed-N (20) BB + ATR buffer + MA20-regime switch. ATR/MA20-regime no longer drive the trade band; their columns remain on `price_cache` for legacy/inspection purposes only. See full v1.9.1 doc above ("Trade LRR/HRR — v1.9.1 Formula").

**Authoritative spec:** `Docs/SignalMatrix_RR_v1_9_1.txt`. Constants are TOS-validated values, not the spec defaults — see top of `conviction_engine.py` for current values.

#### Daily Overshoot Flag (Tactical — Unrelated to Snap)
```python
# uptrend:   if today_close > prior_hrr → hrr_extended = True  (↑ flag, "do not chase" tooltip)
# downtrend: if today_close < prior_lrr → lrr_extended = True  (↓ flag, "do not chase" tooltip)
# Stored in signal_output.lrr_extended / hrr_extended (Boolean)
# Independent of hrr_snapped/lrr_snapped — different concept.
```

### Structural States

`structural_state` has exactly **six valid values** — nothing else. EXTENDED and WARNING are NOT structural states.

| State | Uptrend Condition | Downtrend Condition | Display | Direction |
|---|---|---|---|---|
| UPTREND_VALID | C > A, D established, price above C | — | Green | Bullish |
| DOWNTREND_VALID | — | C < A, D established, price below C | Red | Bearish |
| BREAK_OF_TRADE | Price closes below break level (trade tf) | Price closes above break level (trade tf) | **Amber** state cell — direction HOLDS | Bullish / Bearish |
| BREAK_OF_TREND | Price closes below break level (trend tf) | Price closes above break level (trend tf) | **Amber** state cell — direction HOLDS | Bullish / Bearish |
| BREAK_CONFIRMED | 2+ consecutive closes on wrong side of break level | same | **Red** state cell — direction → Neutral | Neutral |
| NO_STRUCTURE | Insufficient pivot history | Insufficient pivot history | Grey — LRR/HRR grey | Neutral |

**Break level = C normally; B when `d_extended = True` (D > B + abs(B-C)).** The break level applies to all state transitions (BREAK_OF_TRADE, BREAK_OF_TREND, BREAK_CONFIRMED) and to all warn flags (⚠ on LRR/HRR cells).

**WARNING is a boolean flag only** — `warning` field in `signal_output`. It fires when LRR drifts below break level (uptrend) or HRR drifts above break level (downtrend). It is communicated via ⚠ on the LRR/HRR cells, NOT by overriding `structural_state`. Break level respects `d_extended` for this check too.

**Critical rules:**
- **Break level = C normally; B when d_extended = True** — applies to BREAK_OF_TRADE, BREAK_CONFIRMED, and warn flags
- **One close through break level = BREAK_OF_TRADE immediately** — direction HOLDS (Bullish/Bearish), state cell → amber; forgiveness: recovery before day 2 restores the prior state
- **2+ consecutive closes through break level = BREAK_CONFIRMED** — direction → Neutral, state cell → red; recovery requires close above B (same as before `d_extended` logic)
- **BREAK_OF_TRADE does NOT change direction** — only BREAK_CONFIRMED does
- **Price recovers above break level after 1-day break** → prior state restored (engine recalculates fresh each run)
- **Price recovers above break level after BREAK_CONFIRMED** → still Neutral until price closes above B
- **Intraday violations irrelevant** — engine uses EOD closes only
- **Break of Trade = reduce to minimum position** — Trend break = go to zero
- **LRR/HRR always show** — color reflects state (green/red/grey); BREAK states show grey LRR/HRR
- **Direction determined by pivots only** — LRR has no role in direction check
- **Trade and Trend states are independent** — Trend break does not auto-flip Trade
- **C updates dynamically** — always references most recent confirmed higher low / lower high

**Staleness thresholds (`pivot_engine.py` — `_STALE_C_DAYS`):**
```
Trade:     C older than  60 trading days → NO_STRUCTURE (structure too old to trade)
Trend:     C older than 120 trading days → NO_STRUCTURE (structure too old for directional bias)
Tail/LT:   No cutoff                     → LT structures are inherently old
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

### Database Tables (Phase 3 + Phase 6)
```sql
signal_hurst:   ticker, h_trade, h_trend, h_lt, d_trade, d_trend, d_lt,
                h_trend_up,                 ← Phase 6: asymmetric H — uptrend DFA (Commodities/FX only)
                h_trend_down,               ← Phase 6: asymmetric H — downtrend DFA (Commodities/FX only)
                calculated_at
                UNIQUE(ticker)

signal_pivots:  ticker, timeframe, bar_window,
                pivot_a, pivot_b, pivot_c, pivot_d,
                pivot_a_date, pivot_b_date, pivot_c_date, pivot_d_date,
                structural_state,           ← UPTREND_VALID | DOWNTREND_VALID | BREAK_OF_TRADE | BREAK_OF_TREND | BREAK_CONFIRMED | NO_STRUCTURE
                d_extended,                 ← Boolean: True when D > B + abs(B-C); B becomes break level
                calculated_at
                UNIQUE(ticker, timeframe)

signal_output:  ticker, timeframe, lrr, hrr, structural_state,
                trade_direction, conviction, h_value,
                viewpoint, viewpoint_since, ← ISO timestamp ET — when current aligned viewpoint began
                alert, vol_signal,
                warning,                    ← Boolean: LRR below / HRR above break level (per timeframe). NOT in structural_state.
                lrr_warn, hrr_warn,         ← price-based pivot threshold flags (per timeframe)
                pivot_b, pivot_c,           ← pivot values for UI comparison
                d_extended,                 ← Boolean: True when D > B + abs(B-C); copied from signal_pivots; drives B/C break level in warn flags and popup
                lrr_extended, hrr_extended, ← daily overshoot flags (close vs prior LRR/HRR) — SEPARATE from d_extended
                obv_direction,              ← Vol Direction: OBV pivot trend: Bullish | Bearish | Neutral
                obv_confirming,             ← True when Vol Direction aligns with Trade Dir (not Viewpoint)
                h_trade_delta,              ← Phase 6: change in H_trade over ~20 trading days (display only)
                vix_regime,                 ← Phase 6: 'Investable' | 'Edgy' | 'Choppy' | 'Danger' (from VIX at calc time)
                quad_alignment,             ← 'Aligned' | 'Misaligned' | 'Neutral' — quad alignment (stored for popup/debug and Q FIT); NOT viewpoint-dependent in v2.0
                quad_mult,                  ← Float — informational only in v2.0 (stored for debug only); not applied in additive formula; not shown in popup
                quad_score,                 ← Integer — additive conviction contribution: +20/+15/0/−11/−15; shown in popup (v2.0)
                hrr_snapped,                ← Boolean — v1.9.1 trade RR snap state (HRR side, persistent across runs)
                lrr_snapped,                ← Boolean — v1.9.1 trade RR snap state (LRR side, persistent across runs)
                calculated_at
                UNIQUE(ticker, timeframe)

quad_settings:  id (INTEGER PRIMARY KEY),
                country        (STRING(10) NOT NULL, DEFAULT 'US')       -- 'US', 'JP', 'CN', etc.
                forecast_month (STRING(7)  NOT NULL)                     -- 'YYYY-MM' monthly | 'YYYY-QN' quarterly
                quad           (INTEGER    NOT NULL)                     -- 1–4
                probability    (FLOAT      NOT NULL)                     -- 0.0–1.0 (1.0 for country quarterly rows)
                quad_type      (STRING(20) NOT NULL, DEFAULT 'monthly')  -- 'monthly' | 'quarterly'
                notes (TEXT, nullable),
                created_at (STRING UTC)
                UNIQUE(country, forecast_month, quad_type)
                -- Upsert semantics: POST checks UNIQUE key → update if exists, insert if not
                -- Conviction reads US monthly quad for current ET month
                -- GET /api/quad/settings?country=US&type=monthly → list ordered by forecast_month ASC
                -- GET /api/quad/current → {monthly, next_monthly} for current + next ET month
                -- Alembic migration: e6d00527381b (drops old single-row schema, recreates)

vol_history:     ticker, iv_date,
                implied_vol,                ← IV30 (30d constant-maturity ATM IV)
                hv30, hv90,                 ← annualized realized vol (21-day, 63-day)
                vrp,                        ← IV30 − HV30 (vol risk premium)
                call_iv_25d, put_iv_25d,    ← raw 25Δ component IVs
                risk_reversal,              ← call_iv_25d − put_iv_25d
                skew_rank,                  ← Integer 0–100: RR rank within 252-day history (migration 08f62d15c8b7)
                put_call_ratio,             ← total put OI / total call OI
                created_at
                UNIQUE(ticker, iv_date)

price_cache:    ticker, close, volume, ma20, ma50, ma100, ma200, std20, ma20_regime,
                                            ← ma20_regime is STALE post v1.9.1 (no longer written or read; column kept for legacy)
                rel_iv, iv_source, data_source, cache_date,
                history_json, volume_history_json,
                history_dates_json, history_high_json, history_low_json,
                daily_high, daily_low,
                spark_json, updated_at,
                atr,                        ← 14-day ATR; STALE post v1.9.1 (no longer written or read; column kept for legacy)
                vov_30d,                    ← Phase 6: 30-day VIX volatility-of-volatility (decimal, e.g. 0.15)
                vov_rank,                   ← Phase 6: VoV rank within its own 252-day rolling history (0–100)
                hv30,                       ← annualized realized vol, 21-day (≈30 cal days); decimal (migration l2b3c4d5e6f7)
                hv90,                       ← annualized realized vol, 63-day (≈90 cal days); decimal (migration l2b3c4d5e6f7)
                iv30,                       ← 30-day constant-maturity ATM IV; decimal (migration l2b3c4d5e6f7)
                risk_reversal,              ← 25Δ call IV − 25Δ put IV; decimal (migration l2b3c4d5e6f7)
                skew_rank,                  ← Integer 0–100: RR rank within 252-day history (migration l2b3c4d5e6f7)
                put_call_ratio,             ← total put OI / total call OI across fetched chain (migration l2b3c4d5e6f7)
                vrp_rank,                   ← Integer 0–100: VRP rank within 252-day history (migration m3c4d5e6f7g8)
                hv_rank,                    ← Integer 0–100: HV30 rank within 252-day history (migration p1q2r3s4t5u6)
                UNIQUE(ticker)
# NOTE: ma20_tp and std20_tp were added (f7a3b2c1d9e6) then dropped (13fb636fe76a) —
#       MA20_TP center improvement over MA20(close) was negligible (±7 pts on SPX)
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
- **Trade** — ≤ 3 weeks — entry/exit timing; risk level: LRR + HRR (BB framework)
- **Trend** — ≤ 3 months — directional bias filter; risk level: Trend Level (MA100 single floor/ceiling)
- **Tail / Long Term** — ~3 years — macro structural context (display only); risk level: Tail Level (MA200); code/DB key stays "lt"; display label is "Tail"

### Signal Components
1. **Fractal Dimension (D)** — D→1.0 trending, D→1.5 choppy, D→2.0 mean-reverting. D = 2 − H
2. **Hurst Exponent (H)** — H>0.5 trending, H<0.5 mean-reverting, H=0.5 random walk. Method: DFA
3. **Bollinger Band LRR/HRR** — MA20 ± k×STD20; k modulated by H. Replaces Gaussian sigma framework (v1.7)
4. **Relative IV** — IV as percentile of its own 52-week range. Stock-specific, not vs VIX.
   **v1.7 role: informational display in popup only.** NOT in conviction formula. NOT in LRR/HRR formula.
5. **Volume Signal (OBV)** — Confirming / Diverging / Neutral. +10/+15 additive in conviction v2.0 (was multiplier in v1.9).

### Direction Values (ALL three timeframes)
- **Bullish** / **Bearish** / **Neutral** — never Up / Down

---

## Statistical Framework

| Component | Paradigm | Reason |
|---|---|---|
| Hurst Exponent | **Frequentist** | Objective measurement of price series property |
| Fractal Dimension | **Frequentist** | Derived from H: D = 2 − H |
| Bollinger Band LRR/HRR | **Frequentist** | MA20 ± k×STD20; k modulated by H (v1.7) |
| Relative IV Percentile | **Frequentist** | Rank within own 52-week history — informational only (v1.7) |
| Conviction Score | **Frequentist** | Structural + Quad + Volume + VIX additive (v2.0) |
| Trend / Tail Level | **Frequentist** | MA100 / MA200 slope-confirmed floor or ceiling (v1.7) |
| OBV Direction | **Frequentist** | 40-bar linear regression on OBV series, normalized slope |
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
VIX < 19   → Green  — INVESTABLE
VIX 19–29  → Amber  — CHOPPY
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
- **VVIX line** — `VVIX 85.3 · 42nd pct` displayed in grey below scale labels; VVIX close from `realDataMap.get("VVIX").close`, rank from `rel_iv` (252-day price rank stored on VVIX price_cache row); hidden when VVIX close is null. Answers: "is VVIX signaling elevated tail risk today vs. history?"
- **VoV (realized)** — still computed and stored in `price_cache.vov_30d` + `vov_rank` for future use (e.g. VVIX vs realized VoV spread signal); not currently displayed

## Dashboard Columns (current, in order) — v1.7
| Column | Description |
|--------|-------------|
| › | Tier 2 expand/collapse chevron |
| ⚡ | Alert flag — hover tooltip describes trigger conditions |
| Ticker | Symbol |
| Description | Asset name |
| Close | Last closing price (real) |
| Trend | SVG sparkline — 60-day real price history |
| Viewpoint | Bullish / Bearish / Neutral (three states only) |
| Conviction % | 0-100% (v2.0 additive) — shown when ≥ 45; blank below; green/red when Bullish/Bearish; grey `#8899aa` when Neutral; ⚡ alerts at ≥ 80 (non-Neutral only) |
| ENTRY | ▲ BUY (green) or ▼ SELL (red) badge — prox > 0.85 at entry zone, all timeframes aligned; blank when conditions not met; sortable |
| Trade Dir | Short-term direction |
| Trade LRR | BB lower band (MA20 - k_lrr×STD20) — color = trade direction; ⚠ when LRR < C (uptrend) or LRR > B (downtrend); ↑↓ overshoot flag |
| Trade HRR | BB upper band (MA20 + k_hrr×STD20) — color = trade direction; ⚠ when HRR < B (uptrend) or HRR > C (downtrend); ↑↓ overshoot flag |
| Trend Dir | Medium-term direction |
| Trend Level | MA100 — floor (uptrend, green) or ceiling (downtrend, red); hidden when Neutral or slope contradicts direction |
| [Quad Now] | Current month US quad box + probability |
| [Quad Next] | Next month US quad box + probability |
| Q FIT | ▲ green (Performs Well) / — grey (Neutral) / ▼ red (Performs Poorly) — asset class historical performance in current quad; sortable; uses `signal_output.quad_alignment` ("Aligned"/"Misaligned"/"Neutral"); sort key `qFitSort` (1/0/−1); column appears before the quad month columns |

## Popup Fields (click any row) — Phase 6
**Layout:** popup is `position: fixed, top: 48px, right: 0` — anchored top-right, below the global header. Outer div is a flex column with `maxHeight: calc(100vh - 48px)`. Ticker/price header is `flexShrink: 0` (always visible). ⚡ HIGH CONVICTION ALERT banner (when applicable) is pinned directly below the header, also `flexShrink: 0`. All fields scroll in a single `overflowY: auto` container below the banner. Popup never exceeds viewport height.

| Field | Notes |
|---|---|
| ⚡ HIGH CONVICTION ALERT | Amber banner pinned below ticker header (before scrollable fields) — shown when `isAlert = true`; displays conviction % inline. Always visible without scrolling. |
| Close | Live price |
| Viewpoint | Bullish / Bearish / Neutral |
| Aligned Since | ET timestamp — when current Bullish/Bearish viewpoint began. Hidden when Neutral |
| Conviction | % shown when ≥ 45; grey when Neutral viewpoint; blank when < 45 |
| ΔH (20d) | Change in H_trade (63-day DFA, Trade timeframe) over ~20 trading days — green when rising, red when falling; from `h_trade_delta` in `signal_output` |
| VIX Regime | Investable / Edgy / Choppy / Danger — regime at time of signal calculation; from `vix_regime` in `signal_output`; tooltip shows v2.0 additive scores (+15/+10/+5/+0) |
| Vol Direction | Bullish / Bearish / Neutral — OBV pivot trend direction (`obv_direction`) |
| Vol Signal vs Trade | Confirming ✓ / Diverging ✗ / Neutral — compared against Trade Dir (`obv_confirming`) |
| Quad Alignment | Aligned ✓ / Misaligned ✗ / Neutral — quad environment vs viewpoint direction |
| Quad Score | Additive conviction contribution: +20 / +15 / 0 / −11 / −15 — green positive, red negative, grey zero; from `quad_score` in `signal_output` |
| Trade Dir \| Trade State | Side-by-side dual-field row — direction + icon on left; structural state string on right |
| Trade LRR | BB lower band; color = trade dir; ⚠ + hover tooltip when warn; ↑↓ overshoot flag |
| Trade HRR | BB upper band; color = trade dir; ⚠ + hover tooltip when warn; ↑↓ overshoot flag |
| Trade B | B pivot — prior swing high/low |
| Trade C | C pivot — active invalidation level (or B when d_extended=True) |
| Trend Dir | Direction + icon |
| Trend Level | MA100 floor/ceiling — hidden when Neutral or slope contradicts direction; ⚠ when warn |
| Trend C | C pivot — trend invalidation level |
| Trend State | Structural state string |
| Tail Dir | Direction + icon (code/DB key: "lt") |
| Tail Level | MA200 floor/ceiling — hidden when Neutral |
| Hurst (T) | Trade timeframe H value; hover tooltip shows color thresholds |
| Hurst (Tr) | Trend timeframe H value (symmetric 252-day DFA — all tickers); hover tooltip shows color thresholds |
| H↑ Trend | Uptrend asymmetric Hurst — Commodities/FX only; from `h_trend_up` in `signal_hurst`; arrow rendered at 13px in label |
| H↓ Trend | Downtrend asymmetric Hurst — Commodities/FX only; from `h_trend_down` in `signal_hurst`; arrow rendered at 13px in label |
| Hurst (Tail) | Tail/LT timeframe H value; hover tooltip shows color thresholds; context only — not in conviction |
| IV Rank | IV Rank % — source tagged (schwab / proxy); `< 20` green (cheap), `> 80` red (expensive) |
| IV30 | 30-day constant-maturity ATM implied vol % — Schwab only, "—" on proxy |
| HV30 | 21-day (≈30 cal day) annualized realized vol % — Schwab only |
| HV90 | 63-day (≈90 cal day) annualized realized vol % — Schwab only |
| VRP | IV30 − HV30 (Volatility Risk Premium); negative = options cheap vs realized = green; positive = expensive = amber |
| VRP Rank | VRP rank within 252-day rolling history; `< 20` green (options historically cheap); `> 80` red (historically expensive) |
| Risk Reversal | 25Δ call IV − 25Δ put IV; positive = forward skew = bullish (green); negative = normal smirk |
| Skew Rank | RR rank within 252-day history; `< 20` green (puts cheap); `> 80` red (fear/puts expensive) |
| P/C Ratio | Total put OI ÷ call OI; `> 1.2` green (fear/contrarian bullish); `< 0.6` red (complacency) |
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
Trade timeframe has full warn flags (LRR + HRR, both C and B checks). Trend has a single Trend Level (MA100) — the warn flag applies to that level vs C. Tail never warns.

Two distinct reference points — break level and target reference — are used depending on `d_extended`:

| Condition | `lrr_warn` reference (break level) | `hrr_warn` reference (target) |
|---|---|---|
| `d_extended=False` | C (uptrend) / B (downtrend) | B (uptrend) / C (downtrend) |
| `d_extended=True` | **B** — break level, unchanged | **D** — extended high/low; "can BB target still reach the peak?" |

Full table by timeframe:

| Timeframe | LRR/Level ⚠ condition | HRR ⚠ condition |
|---|---|---|
| **Trade** | Bullish: `lrr < c` (or `< b` when d_extended) · Bearish: `lrr > b` (or `> d` when d_extended) | Bullish: `hrr < b` (or `< d` when d_extended) · Bearish: `hrr > c` (or `> b` when d_extended) |
| **Trend** | Bullish: `level < c` only (MA100 below C pivot) | Bearish: `level > c` only |
| **Tail** | Never | Never (no HRR column) |

**Why D for target-side warn when d_extended:** B is the break level (invalidation). D is the extended high/low the market has already reached. When `d_extended=True`, `hrr_warn` (uptrend) fires when HRR falls below D — "the BB target can no longer reach the extended peak." Comparing against B instead would be nearly impossible to fire in practice (B is far below D) and is the wrong reference for a momentum signal. `lrr_warn` stays anchored to B (the break level) — correct because it is a proximity-to-invalidation warning, not a target warning.

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
  - `b91cb92` — EXTENDED architectural cleanup: d_extended boolean, structural_state clean set, BREAK_OF_TRADE direction holds
  - `e02db23` — Perf: page load /cached endpoint, React Router SPA nav, N+1 fix, gap detection, RUT ticker
  - `110deaf` — Perf: Yahoo-only ticker gap detection, fetch_ticker_close lightweight fetch
  - `d05d5b1` — Perf: IV fetch idempotent on manual REFRESH DATA (force=False)
  - `f7b5197` — migration: drop ma20_tp/std20_tp, add atr to price_cache
  - `893c773` — feat: v1.8 LRR/HRR — TP center, fixed k_tight=0, ATR buffer, ATR backfill fix
  - `ad3d728` — docs: update CLAUDE.md — drop MA20_TP, add ATR, alembic SQLite fallback
  - `7f1eeda` — feat: conviction engine v1.8 — remove H, OBV slope layers, auto_adjust fix
  - `3432b45` — feat: volatility tracking — HV30/HV90, IV30, risk reversal, skew rank, P/C ratio
  - `8afa3d3` — feat: VRP and VRP Rank — rename vol_premium→vrp in vol_history, add vrp_rank to price_cache
  - `f2ec28b` — feat: left sidebar navigation + /ticker/:symbol stub route (AppLayout pattern, NAV_ITEMS array)
  - `8463a95` — feat: admin shell with horizontal tab nav — AdminPanel→shell, TickerList extracted, QuadSetup stub
  - `ae066f3` — feat: redesign quad settings — monthly NTM grid + country quarterly table (migration e6d00527381b, upsert API, QuadSetup full rewrite)
  - `a736d6e` — fix: QuadSetup text hierarchy — #c8d8e8 for headers/labels, #8899aa for descriptive text
  - `af7fce3` — fix: QuadSetup active quad button — 33% opacity fill + white text (matches Hedgeye colored box style)
  - `b41375c` — feat: simplify conviction tooltip to 2-line formula + color regime
  - `d477733` — feat: add current + next month quad columns to dashboard table (solid color box + probability)
  - `5ea6e37` — feat: route international tickers to country quarterly quads in conviction + dashboard
  - `2b0e780` — fix: update QuadSetup quad colors to match dashboard palette (Q1 dark green, Q2 system green, Q3 amber, Q4 red)
  - `1d999be` — feat: OBV ABCD pivot logic + popup section dividers
  - `3a6b5a4` — fix: remove delta-H, VRP Change, and P/C Ratio from popup
  - `fb9f5dc` — docs: update CLAUDE.md — country quad routing, quad colors, conviction tooltip format
  - `5a08815` — feat: intraday monitor — PROXIMITY + RETRACEMENT_50 SMS alerts every 15 min
  - `ad1f0fe` — fix: intraday monitor — CronTrigger aligned to clock boundaries, fires at 9:30 AM open
  - `20a367d` — feat: ATR buffer symmetry, VVIX rank, popup trade reorder, UI polish
  - `bd01710` — feat: add Yahoo intraday quotes pass — covers indices, FX, futures in 15-min monitor
  - `96e81b7` — feat: add email alerts as backup to SMS
  - `6f2ad32` — refactor: rename iv_history → vol_history, add accumulate_hv_only() for HV-only tickers, fix HV Rank label
  - `190d5f3` — feat: global header bar + sidebar lock toggle + SPX vol chart improvements (2Y/MAX toggle, X-axis fix, symmetric Y-axis, margins, border)
  - `efabd56` — feat: add Q Fit column — quad environment fit for asset class/sector (▲/—/▼, sortable, uses signal_output.quad_alignment)
  - `84eb874` — fix: Q Fit column — move before quad cols, fix Aligned/Misaligned string check (was checking Best/Worst)
  - `b30dc45` — feat: QUAD MAP button — opens PNG modal (public/quad-map.png)
  - `600b8e1` — feat: QUAD MAP button polish + remove legend bar
  - `f52ad17` — feat: International Equities separator shows QUARTERLY QUADS label
  - `635ba25` — docs: update CLAUDE.md — QUAD MAP button, Q Fit fixes, legend removal
  - `d0957c2` — fix: Q FIT — viewpoint-independent quad_fit field (Best/Worst/Neutral, no viewpoint dependency; KWEB in Q1 now shows ▲)
  - `44f5a62` — fix: QUARTERLY QUADS label floated right on IE separator (above quad columns)
  - `ecc8ec6` — perf: batch DB commits + pre-load queries in signal calculation
  - `ed472db` — fix: Q FIT viewpoint-independent + separator + schema fixes
  - `90bfca7` — fix: hrr_warn when d_extended uses D not B — BB target compared against extended high/low
  - `cc64e88` — alembic: merge two heads (a1b2c3d4e5f6 + n1o2p3q4r5s6) before new revision
  - `312d2ab` — fix: vol_history.implied_vol nullable — allows accumulate_hv_only() HV-only rows
  - `2825e55` — perf: skip Hurst+Pivots on repeat manual CALCULATE SIGNALS; fix vol_history nullable
  - `5447f07` — fix: OBV direction → 40-bar linear regression; obv_confirming → strict check
  - `3d5de8e` — docs: update CLAUDE.md — hrr_warn d_extended fix, warn flag scope table
  - `90bfca7` — fix: hrr_warn when d_extended uses D not B — BB target compared against extended high/low
  - `acc750a` — docs: Conviction Engine v2.0 spec + CLAUDE.md + App.js (additive formula, Neutral grey, alert ≥ 80, display ≥ 45)
  - `11006f0` — feat: replace Quad Mult popup field with Quad Score (additive +20/+15/0/−11/−15); migration o1p2q3r4s5t6
  - `422fb92` — fix: popup header hidden by alert banner — flex column layout, maxHeight, header pinned
  - `a776a81` — fix: move popup to top-right below global header (top: 48px)
  - `d3cc9e1` — fix: HIGH CONVICTION ALERT banner pinned below ticker header (always visible, not scrolled)
  - `bdaa6f8` — feat: HV Rank column + accumulate_hv_only price_cache fix + one-time HV backfill script (migration p1q2r3s4t5u6)
  - `f07ed99` — feat: v1.9.1 Trade RR BB+Snap formula (dynamic-N, IV-primary HV-fallback, stateful snap; migration q2r3s4t5u6v7)
  - `9dc3c34` — feat: add Sector Performance dashboard — absolute + relative sector tables (/sector route, bisect-based period calcs)
  - `0cc78d2` — feat: Macro Vol — Schwab index history fetch + DoD stats fix (SCHWAB_INDEX_HISTORY_MAP, _schwab_fetch_index_histories, common_dates DoD anchor)
  - `4428b35` — fix: MacroVolChart — align DoD/WoW/MoM headers to first (Δ bps) sub-column
  - `536e96e` — fix: Macro Vol — prevent Yahoo fallback from corrupting index vol history (_yahoo_fallback excludes SCHWAB_INDEX_HISTORY_MAP)
  - `37ec9c4` — fix: Macro Vol — use 10-day fetch for append, 5-year for short/bootstrap
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
- **Route:** `localhost:3000/admin` (redirects to `/admin/tickers`) — hidden, not in main nav or sidebar
- **Access:** Password from `.env` → `REACT_APP_ADMIN_PASSWORD` — gate is in `AdminPanel.js` shell
- **Tab nav:** Horizontal tabs below the header — [TICKERS] [QUAD SETUP] — add new tabs by extending `TABS` array in `AdminPanel.js`
- **Sub-routes:** `/admin/tickers` → `TickerList.js` · `/admin/quad` → `QuadSetup.js` · unknown paths redirect to tickers
- **App.js route:** `/admin/*` (wildcard required for nested routing)
- **Sidebar:** Hidden on all `/admin/*` paths via `showSidebar` check in `AppLayout`
- **After changing `.env`:** Must restart Docker container
- **Never hardcode the password in source code**
- **Never hard delete tickers** — use `active: false` via DELETE endpoint
- **Adding a new admin tab:** (1) create the component, (2) add `{ label, path }` to `TABS` in `AdminPanel.js`, (3) add `<Route path="x" element={<X />} />` inside `AdminPanel`'s `<Routes>`

---

## Project Rules — Read Before Making Changes
1. **Never modify the ticker universe without explicit instruction** — use admin panel, not code edits
2. **Never hardcode passwords, API keys, or secrets** — always use `.env`
3. **Never hard delete tickers** — use `active: false`
4. **Direction values are Bullish / Bearish / Neutral** — never Up / Down
5. **HRR = Higher Risk Range** — always the higher price value — do not rename
6. **LRR = Lower Risk Range** — always the lower price value — do not rename
7. **Neutral color is `#8899aa` grey** — amber `#f0b429` is for alerts, conviction 50-69%, BREAK_OF_TRADE/BREAK_OF_TREND state cells, and ⚠ per-cell pivot breach flags
8. **Asset Class values must exactly match:** Domestic Equities | Domestic Fixed Income | Digital Assets | Foreign Exchange | International Equities | Commodities | Indices
9. **Keep components modular** — one component per file
10. **Docker:** changes to `src/` reflect on save — no rebuild needed for frontend
11. **Do not modify** `docker-compose.yml`, `Dockerfile`, or `package.json` without flagging first
12. **Phase 3 signal calculations are locked** — implement per spec above, no deviations
13. **Flag all [OPEN] items** before implementing — do not assume defaults
14. **Commit to Git** after every confirmed working state
15. **Neo = Claude Code** (VS Code extension) — all code changes go here
16. **No worktrees or feature branches** — all changes committed directly to master
17. **Never auto-fetch from Yahoo Finance or Schwab** — REFRESH DATA button only (`/api/market-data/batch`); page load uses `/api/market-data/cached` which is a pure DB read and never calls external APIs. `fetchCachedMarketData()` for page load, `fetchBatchMarketData()` for REFRESH DATA — never swap these.
18. **Never auto-calculate signals** — CALCULATE SIGNALS button only
19. **`backend/signal_matrix.db` must never be committed to Git**
20. **C is the invalidation level** — Break of Trade/Trend fires on price closing through C
21. **Signal engine never calls yfinance directly** — always reads from price_cache table
22. **Pivot confirmation requires bar_window bars on BOTH sides** — before AND after
23. **Today's EOD bar IS included** in price history (`<= date.today()`) — the scheduler fetches after market close so today's close is a confirmed EOD price; excluding it delays pivot confirmation by one trading day
24. **C updates dynamically** — never stale, always most recent confirmed higher low / lower high
25. **Conviction always calculates (v2.0)** — displayed when score ≥ 45 regardless of Viewpoint. Neutral viewpoint shows conviction in grey (`#8899aa`); Bullish/Bearish shows in green/red. Blank only when score < 45. Alert still requires non-Neutral viewpoint AND conviction ≥ 80.
26. **Direction determined by pivots only** — H has no role in direction or viewpoint
27. **LRR/HRR always show** — grey when Neutral, green when Bullish, red when Bearish
28. **Viewpoint has three states only** — Bullish, Bearish, Neutral (no Diverging)
29. **Direction check uses C normally; B when d_extended=True** — `price > c` for Bullish, `price < c` for Bearish; LRR is not part of the direction check. When `d_extended=True`, pivot engine pre-handles B-based breaks before `_compute_direction` is called — no EXTENDED case needed in direction logic.
30. **LRR/HRR always compute for BREAK states** — `_infer_pivot_direction` infers underlying direction even for BREAK_OF_TRADE/BREAK_OF_TREND/BREAK_CONFIRMED so LRR/HRR render grey
31. **LRR/HRR cell color = timeframe direction** — use `dirRangeColor(dir, isWarn)`, NOT viewpoint color
32. **Per-cell ⚠ warn flags are price-based** — separate from IV-driven `warning` structural state
33. **Warning scope is timeframe-specific** — Trade: full (C+B, or B+D when d_extended); Trend: C-based only; LT: none. When `d_extended=True`, `lrr_warn` stays anchored to B (break level); `hrr_warn` (uptrend) / `lrr_warn` (downtrend) target-side compares against D (the extended high/low), not B.
34. **All cache_date and run_date writes use ET date** — never UTC date for trading day keys
35. **`get_active_tickers(db)`** is the only way to retrieve the ticker list in backend — no hardcoded arrays
36. **tickers.js is seed data only** — never import it for the live ticker universe; use `/api/tickers`
37. **Asset class overrides checked first** — add new entries to `ASSET_CLASS_OVERRIDES` in `tickers.py` when yfinance returns wrong asset class
38. **Neo cannot read .docx files** — CLAUDE.md is the primary spec source for Neo; keep it current
39. **One close through break level = BREAK_OF_TRADE immediately** — break level = C normally; B when `d_extended=True`. Direction HOLDS during BREAK_OF_TRADE (not Neutral). Forgiveness: recovery on day 1 restores prior state; 2+ consecutive closes = BREAK_CONFIRMED → direction → Neutral. Recovery from BREAK_CONFIRMED: close above B (non-extended); close at or above D when `d_extended=True` (B is too close to oscillation noise — only re-establishing D proves the extension can be reclaimed). Implemented in `compute_d_and_state`: early-return `UPTREND_VALID` when `current_price >= d_price`; `_check_break_confirmed` receives `d_price` as recovery threshold instead of `b_price` in d_extended branches.
40. **Break of Trade = reduce to minimum position** — Trend break = go to zero (full exit)
41. **OBV direction uses 40-bar linear regression (v2.0)** — `_obv_direction()` computes a 40-bar linear regression slope on the OBV series, normalized by `std(OBV[-40:])` to be scale-invariant across tickers. `|normalized slope| ≤ 0.02` (_OBV_NEUTRAL_BAND) → Neutral; > 0.02 → Bullish; < -0.02 → Bearish. Replaces the prior ABCD pivot engine on OBV. `obv_confirming` is strict: regression direction AND OBV MA20 3-bar ROC slope must both confirm Trade Dir.
42. **Schwab API approved for Phase 5** — OBV volume source swap point flagged with `# PHASE 5 TODO` in `yahoo_finance.py`; OBV engine in `conviction_engine.py` is source-agnostic
43. **schwab-py is the only Schwab API client** — never write raw HTTP calls against Schwab endpoints
44. **Yahoo Finance is a permanent fallback** — never remove it; always called when Schwab is unavailable
45. **Token encryption is mandatory** — Schwab tokens must be Fernet-encrypted before writing to DB
46. **REACT_APP_API_URL must be env-variable driven** — never hardcode localhost:8000 in production code
47. **auto_stop_machines = false on API app** — Fly.io must not stop the API container or scheduler won't fire
48. **Alembic manages all schema changes** — never modify Supabase tables directly via dashboard
49. **IV-eligible tickers exclude VIX, $DJI, SPX, NDX** — index options chains have different structure
50. **data_source column must be written on every price_cache upsert** — 'schwab', 'yahoo', or 'yahoo_fallback'
51. **`ma20_regime` is no longer computed (v1.9.1)** — was a v1.7/v1.8 concept used by the old ATR-buffer trade RR formula to switch between tight and wide entry-side bands. v1.9.1 replaced that with snap state. The `price_cache.ma20_regime` column still exists in the schema but is never written or read. Don't reintroduce it without a redesign.
52. **LT timeframe code/DB key stays `"lt"` everywhere** — display label only changes to "Tail" (UI, popup headers, table header). Never rename in models, DB columns, or backend API responses.
53. **Three independent "extended" concepts — never conflate:**
    - `d_extended` (Boolean field) — D > B + abs(B-C); B becomes break level; drives warn flags and popup `*`; NOT in structural_state
    - `lrr_extended` / `hrr_extended` (Boolean fields) — daily overshoot: today's close vs prior LRR/HRR; drives ↑↓ flags on LRR/HRR cells
    - "EXTENDED" string — **no longer exists** in structural_state or anywhere in the system
54. **Trend Level and Tail Level display `None` when direction is Neutral** — no level shown; also hidden when MA slope contradicts Trend/Tail direction
55. **ENTRY prox threshold = 0.85** — do not revert to 2%-of-price absolute threshold; prox is range-normalized via HRR-LRR (STD20-derived, automatically volatility-scaled)
56. **Proximity removed from conviction formula (v2.0)** — proximity belongs to the alert/intraday system (PROXIMITY alert in intraday monitor) and the ENTRY signal column. It is no longer a conviction component. Conviction v2.0 uses Structural + Quad + Volume + VIX additive scoring only.
57. **`structural_state` has exactly six valid values** — `UPTREND_VALID`, `DOWNTREND_VALID`, `BREAK_OF_TRADE`, `BREAK_OF_TREND`, `BREAK_CONFIRMED`, `NO_STRUCTURE`. Never add EXTENDED, WARNING, or any other value.
58. **BREAK_OF_TRADE / BREAK_OF_TREND do NOT change direction to Neutral** — direction holds (Bullish/Bearish) during provisional break; only BREAK_CONFIRMED flips direction to Neutral
59. **WARNING is a boolean flag only** — `signal_output.warning`; never override `structural_state` to "WARNING" in `conviction_engine.py`
60. **`d_extended` is the sole source of truth for B vs C break level** — `is_warning`, `_compute_warn_flags`, popup `tradeBreakIsB`/`trendBreakIsB`, and `warnTip` all read `d_extended` directly; never derive from state string comparison
61. **VIX score tiers (v2.1)** — Investable+ (VIX < 19 AND VIX HRR < 19) +15 · Investable (VIX < 19) +10 · Edgy (19–23) +5 · Choppy (24–29) +0 · Danger (≥ 30) +0. VIX HRR read from `signal_output` (ticker='VIX', timeframe='trade'). **Applies to Domestic Equities only** — all other asset classes receive +15. `get_vix_score(vix_close, asset_class, vix_hrr)`. **NATH Boost (×1.05):** Viewpoint=Bullish AND trade HRR > `price_cache.ath` → multiply conviction_sum by 1.05 after dampener, before cap. Do not change without explicit instruction.
66. **Quad score is probability-weighted (v2.0)** — `alignment = get_quad_alignment(asset_class, sector, current_quad)` → +1.0/0.0/-1.0. Viewpoint=Neutral → quad_score=0. Aligned: +20 (prob≥0.45) or +15 (prob<0.45). Misaligned: -15 (prob≥0.45) or -11 (prob<0.45). Neutral alignment: 0. `quad_score` (Integer) is stored in `signal_output` and shown in popup (green/red/grey). `quad_mult` still written to `signal_output` for debug only — not in v2.0 formula and not shown in popup. Index sectors always return 0.
67. **Quad settings use upsert semantics** — POST to `/api/quad/settings` checks `UNIQUE(country, forecast_month, quad_type)`: updates existing row if found, inserts new row otherwise. `forecast_month` replaces the old `effective_date` key. Conviction reads the US monthly row whose `forecast_month` = current ET month (not most-recent-row). Admin Panel → QUAD SETUP manages this.
68. **Quad alignment uses sector-first priority** — `get_quad_alignment()` checks `sector` key first, then `asset_class`. This correctly handles USD (sector="USD"), GLD/SGOL//GC (sector="Gold"), JPY/FXY (sector="Yen"), FXB (sector="British Pound"), FXE (sector="Euro"), IBIT (sector="Cryptocurrency"). Foreign Exchange asset_class is the fallback for any unlisted FX ticker.
71. **International Equities route to country quarterly quads** — `signals.py` `run_output()` routes tickers with `asset_class = "International Equities"` to their country's current-quarter quad (e.g. EWJ sector="Japan" → "JP" → `YYYY-QN` quarterly row) instead of the US monthly quad. `_SECTOR_TO_CODE` dict in `signals.py` maps sector labels to ISO country codes. If no country quarterly quad is set, falls back to no quad (multiplier = 1.00). Dashboard columns for international rows show the country quarterly quad (no probability — quarterly rows always store 1.0); US monthly quad + probability shown for all other rows. Quarterly data fetched in `App.js` from `/api/quad/settings?country=ALL&type=quarterly` on page load, mapped via `CODE_TO_SECTOR` to build `countryQuads` state `{sector: {cur, next}}`.
72. **Quad UI colors (dashboard + QuadSetup)** — Q1: `#007a55` (dark green, white text) · Q2: `#00e5a0` (system green) · Q3: `#f0b429` (system amber) · Q4: `#ff4d6d` (system red). Box style: `background: color + "55"` (33% opacity) + `border: 1px solid color` + white text — matches QuadBtn active style. Do not introduce new quad color values.
73. **Conviction tooltip — 2-line format (v2.0)** — Line 1: formula `Structural (50) + Quad (±20) + Volume (15) + VIX (15) → floor(0) → dampener → NATH boost → cap(105)`. Line 2: display rules `Show ≥ 45 · Green/Red ≥ 45 (Bullish/Bearish) · Grey ≥ 45 (Neutral) · ⚡ ≥ 80`. Do not revert to proximity/multiplier descriptions.
69. **Slope boost changed to × 1.20 in v1.9** (was × 1.17 in v1.8). Do not revert to 1.17.
62. **H_eff (asymmetric Hurst) asset class scope (Phase 6)** — asymmetric H (H_trend_up / H_trend_down) applies to Commodities and Foreign Exchange ONLY. All other asset classes use symmetric H_trend. `/ZN` (10-Year Treasury futures) is EXCLUDED from asymmetric H despite being a futures ticker — its price series is driven by rate policy, not directional commodity flows; always uses symmetric H_trend.
63. **ΔH (delta-H) threshold for display color** — `h_trade_delta >= 0` → green (momentum improving or stable); `h_trade_delta < -0.05` → red (meaningful deterioration); between -0.05 and 0 → neutral grey. Stored in `signal_output.h_trade_delta`; display only — NOT in conviction formula.
64. **VoV rank computed from existing VIX price history** — no separate accumulation period needed. `compute_vov_with_rank()` computes 30-day rolling std of VIX log returns (VoV series) from 5-year history in `price_cache`, then ranks current VoV within its own 252-day trailing window. Returns `(vov_30d, vov_rank)` tuple. Stored in `price_cache.vov_30d` and `price_cache.vov_rank`. Updated on every REFRESH DATA when VIX history is fetched. Not currently displayed — retained for future VVIX vs realized VoV spread signal.
**VVIX price rank** — computed in `refresh_data()` in `market_data.py` after VoV. Ranks VVIX close within its own 252-day price history (0–100). Stored in `price_cache.rel_iv` for the VVIX row (VVIX has no options chain so rel_iv is otherwise unused). `iv_source` set to `"price_rank"`. Displayed in VIX gauge header as `VVIX 85.3 · 42nd pct`. Popup shows `IV Rank — price_rank`. Do not replace with the Yahoo realized-vol proxy — price rank answers the correct question (is VVIX elevated vs history?).
65. **Proactive spec review** — when reading a spec or reviewing methodology, flag any inconsistencies with existing code or other parts of the spec before implementing. Do not implement silently when something looks wrong or contradictory.
70. **UI text contrast — 3-level hierarchy** — Never use `#445566` or darker for readable text. Three levels: (1) `#00e5a0` green for section titles/headers; (2) `#c8d8e8` for column headers, data labels, group separators; (3) `#8899aa` for descriptive/secondary text (subtitles, inactive controls, units). Reserve `#445566` and darker for decorative borders only.
74. **Intraday monitor uses `schwab_fetch_intraday_quotes` — never `schwab_fetch_all`** — `schwab_fetch_all()` has an idempotency check that freezes `price_cache.close` after the first same-day call. `schwab_fetch_intraday_quotes()` always calls `get_quotes()`, uses `lastPrice` only, and does not update `cache_date`. Swapping them silently breaks the 15-minute price refresh.
75. **Never call `calculate_signals()` intraday** — pivot states require confirmed EOD closes; running signals intraday produces false BREAK_OF_TRADE states. The intraday monitor is purely observational.
76. **Intraday scheduler uses `CronTrigger` — never `"interval"`** — `CronTrigger(day_of_week="mon-fri", hour="9-15", minute="0,15,30,45", timezone="America/New_York")` aligns to clock boundaries, guaranteeing the first fire is exactly 9:30 AM ET. An interval trigger fires relative to container start time and will miss the open if the container starts at an off-minute.
77. **Trade RR uses v1.9.2 BB+Snap formula with directional proximity** — see "Trade LRR/HRR — v1.9.1 Formula" section (computation steps updated to v1.9.2). Constants: TOS-validated (`k_extend=2.2, k_max=1.0, k_min=0.0, k_wide=2.0, k_decay=0.5` — code in `conviction_engine.py` is source of truth; see ADR-013). Vol source: IV-primary (`vol_history.implied_vol`) with HV30 fallback. σ price-derived. Snap trigger: **closes** vs prior 22 closes (unchanged). **Directional proximity**: `prox_lrr = (close − maN) / sdN` (signed); when price falls below maN, prox goes negative, k_lrr_dyn expands toward k_wide, pulling snap line down to BB — eliminates LRR inversion during price pullback below MA. **Snap releases via merge** (k_dyn reaches k_wide, gradual) **or breach** (price crosses the compressed snap line, fast/sharp moves). Snap state persists in `signal_output.hrr_snapped/lrr_snapped`.
78. **`compute_trade_lrr_hrr` is pure** — receives `(closes, vol_series, prior_hrr_snapped, prior_lrr_snapped)` and returns `(lrr, hrr, hrr_snapped, lrr_snapped)`. No DB access in the math function. The caller (`compute_output`) handles vol source lookup (`get_trade_rr_vol_series`) and snap state I/O. Cold-start floor: `len(closes) >= 273` (252 rank window + 21 prior bars for oldest HV computation in fallback path).
79. **ATR + MA20 regime are out of the trade RR path (v1.9.1)** — `compute_trade_lrr_hrr` reads `closes` + `vol_series` only. The columns split into two groups:
    - **Still updated daily:** `price_cache.ma20`, `ma50`, `ma100`, `ma200`, `std20` — written on every fetch (cheap; useful for popup display, MA200 for Tail Level, future signals).
    - **Frozen (no longer written):** `price_cache.atr`, `price_cache.ma20_regime` — the writers and computation functions were deleted in the post-v1.9.1 cleanup. Existing rows keep their last-fetched values; new fetches don't touch these columns. Schema kept (no migration needed).
    - Don't re-add ATR or MA20 regime to the trade-tf branch in `compute_output` without a redesign of the v1.9.1 framework.
80. **Cookie config: `secure=IS_PRODUCTION`, `samesite="lax"`** — never hardcode `secure=True` (breaks local dev cookies on `http://localhost:3000`) or `samesite="strict"` (breaks password reset email link clickthroughs). `IS_PRODUCTION` is `os.getenv("ENVIRONMENT") == "production"`.
81. **Live DB role check in admin endpoints** — `require_admin_user(request, db)` (in `services/auth_service.py`) re-fetches the user from DB and checks `user.role == "admin"`. Never trust the JWT role payload directly (it can be stale up to 12h after a demotion). Use this dependency on every admin-only endpoint (`/api/users/*`, `/api/signals/calculate`, `/api/market-data/batch`).
82. **`/api/auth/check`, `/api/auth/login`, `/api/auth/logout` use raw `fetch` in `AuthContext.js`** — never `apiFetch`. `/check` returns 200 with `{authenticated: false}` when not logged in (never 401), so the apiFetch 401-redirect path could otherwise loop. Auth pages (`/register`, `/forgot-password`, `/reset-password`) also use raw fetch since the user isn't authenticated yet.
83. **No approval email to new users** — admin manually activates users via `/admin/users` and notifies them out of band. Do not add an automatic approval email without explicit instruction.
84. **Recovery: Supabase direct edit is the documented Path 1** — see `Docs/RUNBOOK_AUTH_RECOVERY.md`. Path 2 is the `python -m scripts.reset_admin` recovery script via `fly ssh console`. Path 3 is nuke-and-reseed (last resort).
85. **Logout is cookie-clear only — JWT remains valid until natural expiry (12h max)** — `POST /api/auth/logout` deletes the cookie client-side. The JWT itself is not blocklisted. For true session revocation (e.g., compromised account), set `users.status = "disabled"` in admin — the middleware checks status on every request and rejects disabled users immediately. See "Deferred decisions" in `Docs/Auth_User_Management_Spec_v1.0.md`.
86. **`apiFetch` is a static function, not a hook** — hard navigation on 401 (`window.location.href = "/login"`) is intentional. Do not refactor to a `useApiFetch` hook. See "Deferred decisions" in `Docs/Auth_User_Management_Spec_v1.0.md`.
87. **Email links in `email_alert.py` use `APP_BASE_URL` env var** — defaults to `https://signal.suttonmc.com` if unset. Local `.env` overrides to `http://localhost:3000` so reset/registration emails clickthrough to local during dev. Never hardcode the production URL.
88. **JWT_SECRET MUST differ between local dev and production** — local in `.env`, production in Fly.io secrets. Never reuse. Rotating JWT_SECRET invalidates every existing session cookie (forces re-login) but does not affect user accounts.
89. **Local Docker connects to PRODUCTION Supabase** — `SUPABASE_CONNECTION_STRING` in `.env` points at the same DB as production. There is no separate local DB. Therefore: every local backend test/registration writes to production. When iterating on auth or any DB-touching feature, expect test users to appear in production. Clean up test fixtures before and after.
90. **Idempotent migrations for new tables** — `Base.metadata.create_all()` runs at startup and creates any new tables from SQLAlchemy models, BEFORE alembic gets a chance to run on a fresh deploy. New `op.create_table` migrations must guard with `if "table_name" not in inspector.get_table_names(): ...` (see `add_users_table.py` / `add_password_reset_tokens_table.py` for the pattern). Otherwise `alembic upgrade head` after deploy fails with "table already exists".
91. **`REFRESH DATA` and `CALCULATE SIGNALS` are admin-only** — both UI buttons (gated by `isAdmin` in App.js) and backend endpoints (`/api/market-data/batch`, `/api/signals/calculate` use `require_admin_user`). Viewers see cached data via `/api/market-data/cached` and `/api/signals/stored`; they cannot trigger expensive recalcs.

---

## Session-Start Checklist — Run at the Start of Every Backend Session

Neo must run these steps at the start of any session that touches backend code, signals, or schema.
Do not skip. Do not assume the environment is already in sync.

```
1. Confirm Docker is running
   docker ps | grep signal-matrix

2. Sync local SQLite schema with production
   docker exec signal-matrix-backend-1 alembic upgrade head
   (uses local SQLite — keeps dev schema in sync with Alembic migrations)

3. Confirm Fly.io auth is valid (only needed before deploys)
   fly auth whoami

4. Confirm production API is alive (only needed before deploys)
   curl https://api.signal.suttonmc.com/health
```

If step 2 fails, stop and diagnose before making any code changes. A schema mismatch between
local SQLite and the Alembic migration history means local test results are unreliable.

---

## Pre-Migration Checklist — Run Before Every Alembic Migration

Every schema change must follow this sequence exactly. Do not skip steps, do not reorder.

### Step 1 — Write and review the migration file
- Generate: `docker exec signal-matrix-backend-1 alembic revision --autogenerate -m "description"`
- Review the generated file in `backend/alembic/versions/` before running it
- Confirm upgrade() and downgrade() are correct
- Confirm no unexpected table drops or column renames

### Step 2 — Test migration against local SQLite first
```bash
docker exec signal-matrix-backend-1 alembic upgrade head
```
- If this fails, fix the migration file before touching production
- Local SQLite: `alembic/env.py` falls back to `sqlite:////app/signal_matrix.db` when no DB env vars are set

### Step 3 — Encode the Supabase password before production migration
The Supabase password contains `#`, `$`, `/`, and `@` — these are silently mangled by Fly.io
secret storage and break URL parsing if passed raw.

Use the pre-encoded `DATABASE_URL` secret (already set in Fly.io) which has the password
percent-encoded. Confirm it is set:
```bash
fly secrets list --app signal-matrix-api | grep DATABASE_URL
```

The encoded form is: `k%2C%2F2%23RY%40Jma%248rw`
Never pass the raw password in any connection string that goes through Fly.io secret storage.

### Step 4 — Run migration against production (Supabase via pooled connection)
```bash
# SSH into the running Fly.io API container
fly ssh console --app signal-matrix-api

# Inside the container — use pooled connection string (IPv4, port 6543)
# DATABASE_URL env var is already set and pre-encoded
alembic upgrade head

exit
```

Do NOT use the direct connection string (port 5432) from inside Docker on Windows —
it resolves to IPv6 only and Docker Desktop cannot route IPv6 egress.

### Step 5 — Verify migration applied
```bash
fly ssh console --app signal-matrix-api
alembic current   # should show the new revision head
exit
```

Check the Supabase dashboard to confirm new columns/tables are present.

### Step 6 — Redeploy both apps
```bash
fly deploy --app signal-matrix-api
./deploy-web.sh                    # sources .env, passes REACT_APP_ADMIN_PASSWORD as build arg
```

Deploy API first, web second. Confirm both are healthy after deploy:
```bash
fly status --app signal-matrix-api
fly status --app signal-matrix-web
curl https://api.signal.suttonmc.com/health
```

### Step 7 — Smoke test
- Open https://signal.suttonmc.com
- Confirm dashboard loads, signals render, no console errors
- If schema added new columns: run CALCULATE SIGNALS once to populate them

### Step 8 — Commit
```bash
git add .
git commit -m "migration: <description>"
```
Only commit after production is confirmed healthy.

---

## Roadmap

| Phase | Description | Status |
|---|---|---|
| Phase 1 | Dashboard Refinement | ✅ Complete |
| Phase 2 | Real Data Integration | ✅ Complete |
| Phase 3 | Signal Engine | ✅ Complete |
| Phase 4 | Backend & Database | ✅ Complete — all tasks 4.1–4.13 done |
| Phase 5 | Schwab API + Cloud Deployment | ✅ Complete — all tasks 5.1–5.6 done |
| Phase 6 | Conviction Engine Enhancements | ✅ Complete — tasks 6.1–6.3 done |
| v1.9 | Quad Multiplier + VIX gate + 5-layer conviction | ✅ Complete |

### Phase 6 Build Sequence

| Task | Deliverable | Status |
|---|---|---|
| 6.1 | Delta-H (ΔH) — 20-day change in H_trade; display in popup | ✅ Complete |
| 6.2a | VoV percentile rank — 30-day VIX volatility-of-volatility + 252-day rank | ✅ Complete |
| 6.2b | VIX regime multiplier — Investable/Edgy/Choppy/Danger tiers applied to conviction | ✅ Complete |
| 6.3 | Asymmetric H (H_eff) — directional Hurst for Commodities/FX; symmetric for all others | ✅ Complete |

### v1.9 Build Sequence

| Task | Deliverable | Status |
|---|---|---|
| v1.9-1 | `quad_settings` table + model + Alembic migration | ✅ Complete |
| v1.9-2 | `signal_output.quad_alignment` + `quad_mult` columns + migration | ✅ Complete |
| v1.9-3 | `backend/routers/quad.py` — GET/POST `/api/quad/settings` | ✅ Complete |
| v1.9-4 | VIX Layer 3: asset-class gate (Domestic Equities only) | ✅ Complete |
| v1.9-5 | Slope boost 1.17 → 1.20; QUAD_ALIGNMENT dict + helpers | ✅ Complete |
| v1.9-6 | Quad Layer 4 wired into `compute_output()` in `conviction_engine.py` | ✅ Complete |
| v1.9-7 | `signals.py`: quad_settings fetch, sector_map, pass to compute_output | ✅ Complete |
| v1.9-8 | `App.js`: quad header display, Asset Class/Sector removed from table, popup additions | ✅ Complete |
| v1.9-9 | `QuadSetup.js`: full admin quad settings form (fetch/save/display) | ✅ Complete |
| v1.9-10 | Deploy: Supabase migrations + Fly.io API + web | ✅ Complete |

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
- Volume surge icon on dashboard rows (deferred — opening bar always spikes; daily avg comparison unreliable intraday)
- Schwab order execution (permanently out of scope)
- Quad Tracker dashboard (Phase QT)
- Quad alignment column in Signal Matrix table (Phase QT)
- Tier 2 auto-surfacing based on conviction threshold
- MA20/50/100 display in dashboard UI
- Signal history UI (table exists, endpoint exists — frontend consumption is future scope)
- Intraday alert log UI — `intraday_alert_log` table exists; no dashboard view yet (future scope)

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
