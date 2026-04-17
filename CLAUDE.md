# Signal Matrix Platform — Project Context

## Important Note for Neo
The `.docx` spec files in `Docs/` cannot be read by Claude Code.
Readable `.txt` copies exist:
- `Docs/SignalMatrix_Spec_v1.7.txt` — **current** full platform spec (v1.7 — BB LRR/HRR framework, Trend/Tail Levels, proximity conviction, ENTRY prox threshold, EXTENDED redesign)
- `Docs/SignalMatrix_Spec_v1.6.txt` — **superseded** by v1.7 (Phases 1–5 complete, OBV, VIX gauge, futures — retained for reference)
- `Docs/SignalMatrix_Spec_v1.5.txt` — prior version (Phase 4 era — superseded by v1.6)
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
  - Schwab portal status: ✅ Approved — callback URL modification confirmed 2026-03-25
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
- **Fixed:** `closes.index.date <= date.today()` — use `.date` attribute for comparison; use `<=` (not `<`) to include today's confirmed EOD close (see EOD Bar Inclusion Fix below)

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

### FORMING State Removed — EXTENDED Removed from structural_state (`pivot_engine.py`, `conviction_engine.py`) — v1.7 / post-v1.7
- **FORMING eliminated:** "Pullback from D, no new C yet" is now simply `UPTREND_VALID` / `DOWNTREND_VALID` — the trend is confirmed, the pullback is normal operation, no special state needed
- **EXTENDED removed from `structural_state`** — EXTENDED is now a dedicated boolean field `d_extended` in `signal_pivots` and `signal_output`. `structural_state` never contains "EXTENDED". The five valid `structural_state` values are: `UPTREND_VALID`, `DOWNTREND_VALID`, `BREAK_OF_TRADE`, `BREAK_OF_TREND`, `BREAK_CONFIRMED`, `NO_STRUCTURE` — nothing else.
- **WARNING removed from `structural_state`** — WARNING was a conviction-engine concept that conflicted with pivot-engine states (e.g. both BREAK_OF_TRADE and WARNING active simultaneously). The `warning` boolean flag on LRR/HRR cells already communicates it. Never set `state = "WARNING"` in `conviction_engine.py`.
- **`d_extended` boolean (dedicated field):** D has pushed more than one full BC range beyond B → `d_extended = True`; B becomes the break level (persistent until new C forms)
  ```python
  bc_range = abs(B - C)
  d_extended = (D > B + bc_range)   # uptrend
  d_extended = (D < B - bc_range)   # downtrend
  ```
  Reversion: when new C forms (D becomes new B, new C established) → `d_extended` resets to False; break level returns to new C
- **`d_extended` drives:** (1) B vs C selection in `_compute_warn_flags` and `is_warning`; (2) popup `*` asterisk on active break level (B when True, C when False); (3) the B-based break state machine in `compute_d_and_state` when extension threshold is crossed
- **`d_extended` is independent of `structural_state`** — when extension fires and price subsequently breaks B, state = `BREAK_OF_TRADE` / `BREAK_CONFIRMED` AND `d_extended = True`. The B/C context survives the state transition.
- **Daily overshoot flag (separate, tactical):** `signals.py` reads existing `signal_output.hrr` / `signal_output.lrr` before overwriting them; passes as `prior_ranges` to `compute_output`; conviction_engine compares today's close against those prior values → sets `lrr_extended` / `hrr_extended` Boolean fields. This is NOT `d_extended` — three independent concepts.
- **Daily overshoot display:** ↑ flag appears on HRR cell (bullish overshoot) or ↓ flag on LRR cell (bearish overshoot) with "do not chase" tooltip; state cell still shows UPTREND_VALID / DOWNTREND_VALID
- **BREAK_OF_TRADE does NOT change direction** — direction holds on the first close through the break level (provisional break, first-day forgiveness). Only `BREAK_CONFIRMED` (2+ consecutive closes) changes direction to Neutral.
- **BREAK_OF_TRADE = amber state cell; BREAK_CONFIRMED = red state cell** — visual distinction in `stateColor()`
- **States that force Neutral:** `BREAK_CONFIRMED` and `NO_STRUCTURE` only
- **UPTREND_VALID, DOWNTREND_VALID, BREAK_OF_TRADE, BREAK_OF_TREND** all allow Bullish/Bearish direction

### ABC Pivot Search — All A Candidates Tried (`pivot_engine.py`)
- Old behavior: `_find_uptrend_abc` / `_find_downtrend_abc` used only the single nearest pivot low/high before B as A
- When the nearest A is above C (uptrend) or below C (downtrend), a valid ABC exists with an older A — but the engine was moving to the next C candidate instead
- **Fixed:** For each (C, B) pair, iterate all A candidates newest-first and stop at the first satisfying `C > A` (uptrend) or `C < A` (downtrend)
- **Example:** SPX trend — engine was finding A=10/10/25 (6552.51) which is above C=11/20/25 (6538.76), causing the uptrend check to fail; correct A is 04/08/25 (4982.77); old engine fell back to a stale ABC (C=10/10/25, 111 trading days) and fired NO_STRUCTURE
- **Rule:** Never assume the nearest A before B is the correct A — always scan all candidates

### Yahoo Finance `auto_adjust=False` — Actual Close Prices (`yahoo_finance.py`)
- Old behavior: `yf.Ticker().history()` uses `auto_adjust=True` by default — silently adjusts all historical closes for dividends, making stored prices diverge from actual traded prices
- **Problem:** SPY Aug 1 2025 showed $616.49 in cache vs $621.72 on Yahoo/ThinkorSwim — gap grows for older bars and any dividend-paying ticker
- **Fixed:** `auto_adjust=False` on both `history(period="5y")` and `history(period="5d")` calls in `yahoo_finance.py`
- This only affects Yahoo fallback path — Schwab always returns actual prices
- **After deploying this fix:** wipe local SQLite history (`UPDATE price_cache SET history_json=NULL, ... cache_date='1970-01-01'`) and run REFRESH DATA + CALCULATE SIGNALS to replace adjusted history with actual prices
- **Production:** safe — Schwab is primary for all equity/ETF tickers; Yahoo fallback only serves indices (SPX, VIX, etc.) and futures which pay no dividends, so `auto_adjust` has no effect on them
- **Do not** revert to default `auto_adjust=True`

### EOD Bar Inclusion Fix (`yahoo_finance.py`)
- Old behavior: `closes.index.date < date.today()` excluded today's close from `history_prices`
- **Problem:** When the scheduler fetches data at 4 PM ET, today's close IS the confirmed EOD price. Excluding it meant the 5th post-pivot bar didn't count until the next trading day — a confirmed pivot on Mar 20 wouldn't be used in that day's signal calculation even though the data was fetched after close.
- **Fixed:** `closes.index.date <= date.today()` — include today's EOD bar
- **Rule:** Do not revert to `<` — today's bar at EOD fetch time is always a confirmed close, not an intraday bar

### Pivot Engine: Intact Structure Preference + BREAK_CONFIRMED Spanning (`pivot_engine.py`)
- **Problem 1 — Spanning a prior break:** When both uptrend and downtrend ABCs are valid and the most-recent-C tiebreak is used, the winner could span a BREAK_CONFIRMED of a prior same-direction structure. The engine was reaching back to an A that predated a structural break, producing a phantom ABC (e.g. IWM: uptrend A=Nov 20, C=Mar 20 — but the uptrend had a BREAK_CONFIRMED Mar 5-6 at C=$260.03).
- **Problem 2 — BREAK_CONFIRMED beating intact structure:** GLD, AAPL, NVDA, TLT all had a broken structure in one direction winning over an intact structure in the other direction, causing them to show BREAK_CONFIRMED when a valid directional structure existed.
- **Fixed:** `_has_prior_break_confirmed()` — scans intermediate pivots between A and C of the candidate ABC for any historical BREAK_CONFIRMED; if found, the ABC is rejected and the other direction is used.
- **Fixed:** `_price_on_correct_side()` — before applying the most-recent-C tiebreak, prefer the structure where current price is still on the valid side of C (structure intact). A broken structure only wins if both structures are broken or both are intact.
- **Problem 3 — Prior break check skipped on intact-only early return:** When one structure was intact and the other broken, the intact one was returned immediately (lines 277-280) without calling `_has_prior_break_confirmed`. The check only fired on the tiebreak path (both intact or both broken). FXB example: intact uptrend (A=Nov19, C=Mar30) was returned over a valid downtrend (A=Feb25, B=Mar13, C=Mar23) because the uptrend was price-intact. The uptrend spans the Feb 18-19 BREAK_CONFIRMED — should have been rejected.
- **Fixed (2026-04-11):** Both early-return cases (lines 277-280) now call `_has_prior_break_confirmed` on the intact winner before returning. If a prior break is found, the other (broken) structure is returned instead.
- **Selection priority in `find_abc_structure()`:**
  1. Only one direction found → use it
  2. Both found, only one intact (price on correct side of C) → use intact, UNLESS it spans a prior BREAK_CONFIRMED → use broken structure instead
  3. Both intact or both broken → most recent C wins, UNLESS:
     a. The newer structure has never established D (price never closed through B) → older structure governs. D is the confirmation event: a geometric ABC without D is not a confirmed reversal and cannot override an unbroken prior structure.
     b. The winner spans a prior BREAK_CONFIRMED of a same-direction structure → use other.
- **`_d_has_established(abc, prices)`** — returns True if price has ever closed through B (above B for uptrend, below B for downtrend). Guards the tiebreak: without D, the newer ABC is geometric only.
- **Rule:** Do not simplify `find_abc_structure()` back to "most recent C wins" — the priority logic is load-bearing

### LT Bar Window Reduced: 90 → 50 (`pivot_engine.py`)
- Old `TIMEFRAMES["lt"] = 90` required 180 bars of surrounding context — major reversals were invisible for ~9 months after they occurred
- **Problem:** GLD's $495 peak (Jan 2026) was undetectable at bw=90 as late as April 2026 (~50 bars old); showed NO_STRUCTURE despite a clear multi-year uptrend
- **Fixed:** `TIMEFRAMES["lt"] = 50` — pivots need ~2.5 months of context each side; 5x the trend window (bw=10), still clearly "structural"
- **Rule:** Do not increase LT bar_window above 50 without verifying that 3–4 month old major reversals still register

### Trend Bar Window Reduced: 20 → 10 (`pivot_engine.py`)
- Old `TIMEFRAMES["trend"] = 20` required 40 bars of surrounding context to confirm a pivot, making it nearly impossible for the trend engine to detect a new reversal within 40 trading days (~2 months)
- **Problem:** MSFT's Jan-Mar 2026 collapse was invisible to the trend engine at bw=20 — trend showed NO_STRUCTURE / Neutral despite a clear downtrend
- **Fixed:** `TIMEFRAMES["trend"] = 10` — still provides meaningful trend-scale pivots while detecting reversals within ~20 trading days
- **Rule:** Do not increase trend bar_window above 10 without verifying that recent reversals (< 6 weeks) still register

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

### VIX Regime Threshold — Green Cutoff is 19 (`App.js`, `conviction_engine.py`)
- Correct thresholds: `VIX < 19` → Green (Investable), `19 ≤ VIX < 30` → Amber (Choppy/Edgy), `VIX ≥ 30` → Red (Danger)
- VIX = 19 is choppy territory — Investable requires VIX strictly below 19
- **Do not** use 20 as the cutoff

### Vol Signal / Vol Direction — Popup Field Naming (`App.js`)
- Backend field `vol_signal` (Confirming/Diverging/Neutral) is computed from OBV pivot direction vs Trade Dir — stored for popup display only; no longer drives a conviction multiplier (v1.8+)
- Popup shows two fields:
  - **Vol Direction** — raw OBV pivot trend direction: Bullish / Bearish / Neutral (maps to `obv_direction`)
  - **Vol Signal vs Trade** — Confirming ✓ / Diverging ✗ / Neutral — (maps to `obv_confirming`; compared against Trade Dir)
- The old duplicate "Vol Signal" row that appeared above OBV Direction was removed — it was a leftover from the price-momentum proxy era
- **Do not rename** `vol_signal` → `obv_signal` in the DB — "Vol Signal" is the correct trader-facing name

### Warning Tooltip — C Pivot Price Injected Inline (`App.js`)
- LRR/HRR ⚠ tooltips now include the C pivot value inline: e.g. `"LRR is below C ($448.20) — approaching trade invalidation level"`
- `warnTip(dir, which, cVal, bVal, isExtended)` helper builds the tooltip string — formats price as `$X,XXX.XX`; when `isExtended=true` tooltip says "B replaces C" as the break level
- All call sites (table rows + popup) pass `row.tradeExtended` / `row.trendExtended` as the `isExtended` param — **not** `row.tradeState === "EXTENDED"`
- C and B pivot values flow from `signal_output.pivot_c` / `signal_output.pivot_b` via `mergeSignalData()` → `tradeC`, `tradeB`, `trendC`, `trendB`

### EXTENDED Architectural Cleanup — `d_extended` Boolean (`pivot_engine.py`, `conviction_engine.py`, `App.js`)
- **Problem:** EXTENDED was stored in `structural_state`, conflicting with other states (e.g. BREAK_OF_TRADE could not coexist with the "came from EXTENDED" context needed to keep B as break level) and lingering as a misleading label after SPX retraced from its March 2026 extreme.
- **Fix:** `d_extended` Boolean added to `signal_pivots` and `signal_output`. `structural_state` no longer contains "EXTENDED" or "WARNING" — clean set of six values only.
- **`d_extended`** turns ON when `D > B + abs(B-C)` (uptrend) / `D < B - abs(B-C)` (downtrend). Turns OFF when new C forms.
- **`is_warning` and `_compute_warn_flags`** now accept `d_extended: bool` param instead of `orig_state` — `break_level = b if d_extended else c`
- **`_compute_direction`** simplified — no EXTENDED case; pivot engine pre-handles B-based break state machine when d_extended is True
- **`compute_output`** no longer sets `state = "WARNING"` — `warning` is a boolean flag only; `structural_state` is never overridden
- **BREAK_OF_TRADE does NOT change direction** — `_compute_direction` returns Bullish/Bearish for BREAK_OF_TRADE/BREAK_OF_TREND; only BREAK_CONFIRMED returns Neutral
- **`stateColor()`** in `App.js` — BREAK_OF_TRADE/BREAK_OF_TREND → amber; BREAK_CONFIRMED → red; removed EXTENDED and WARN cases
- **`tradeBreakIsB` / `trendBreakIsB`** in popup — driven by `row.tradeExtended` / `row.trendExtended` (not state string check)
- **Alembic migration:** `e2f4a6b8c1d0` — adds `d_extended` to `signal_pivots` and `signal_output`
- **Verified:** SPX `state=BREAK_OF_TRADE`, `d_extended=True`, `hrr_warn=True` (HRR 6825 > B 6798), popup `*` on Trade B

### Filter UX — Dropdown Multi-Select (`App.js`)
- Asset Class button row replaced with `MultiSelectDropdown` component — compact, multi-select, count badge, click-outside-to-close
- New Sector dropdown added alongside Asset Class — same `MultiSelectDropdown` component
- Both dropdowns populate dynamically from the active ticker universe (no hardcoded values)
- Viewpoint, ALIGNED ONLY, and ALERTS filters unchanged (remain as buttons)
- Filters apply instantly on selection — no submit button

### ENTRY Signal Column — Proximity-Based (v1.7) (`App.js`)
- `entrySignal` is computed in the `ALL_DATA` useMemo pipeline: `"BUY"` | `"SELL"` | `null`
- **BUY conditions:** Viewpoint = Bullish AND Trade Dir = Bullish AND Trend Dir = Bullish AND `prox_bullish > 0.85`
  - `prox_bullish = 1 - (close - tradeLRR) / (tradeHRR - tradeLRR)` — peaks at 1.0 when close = LRR
- **SELL conditions:** Viewpoint = Bearish AND Trade Dir = Bearish AND Trend Dir = Bearish AND `prox_bearish > 0.85`
  - `prox_bearish = (close - tradeLRR) / (tradeHRR - tradeLRR)` — peaks at 1.0 when close = HRR
- **Replaces:** 2%-of-price absolute threshold — not normalized to instrument volatility
- **Why prox > 0.85 works:** HRR - LRR is derived from STD20 → already volatility-scaled per instrument. prox > 0.85 = within bottom 15% of the range (from entry side) for any ticker
- Neutral viewpoint never triggers ENTRY signal regardless of price proximity
- Sort comparator must handle `null` — `typeof null === "object"` causes NaN on subtraction
- **Fix:** Null values explicitly sorted to bottom before string/numeric comparison in the sort function
- `ENTRY` count shown in header summary row alongside BULLISH / BEARISH / ALIGNED / ALERTS

### Schwab IV — ATM Option Contracts, IV Rank Formula (`schwab_options.py`)
- **DO NOT** read the top-level `volatility` field from `get_option_chain()` response — it is historical/realized vol, not implied vol
- **Correct source:** `_extract_atm_iv(data)` — parses `callExpDateMap` / `putExpDateMap`, interpolates to 30-day constant-maturity IV matching TOS methodology
- **30-day interpolation:** finds the two expirations bracketing 30 DTE (near < 30, far ≥ 30), computes ATM IV at each (average call + put), linearly interpolates → `IV_near × (far_dte - 30) / span + IV_far × (30 - near_dte) / span`; falls back to nearest available if only one side of 30 DTE exists
- Individual option `volatility` is a decimal (e.g. `0.318` for 31.8%) — no ÷100 needed; guard: if value > 2.0 it's percentage format, divide by 100
- **IV Rank formula** (matches TOS "IV Percentile"): `(current_iv - min_252) / (max_252 - min_252) * 100` — range-based, NOT `percentileofscore` frequency-based
- Cold start: returns `50` when fewer than 5 observations in `iv_history`
- Updates `price_cache.rel_iv` (replaces Yahoo proxy) + sets `price_cache.iv_source = 'schwab'`
- **Per-ticker fallback:** on any per-ticker error, leaves Yahoo proxy `rel_iv` intact and tags `iv_source = 'proxy'`
- **No-tokens fallback:** if Schwab token missing/expired, entire batch tagged `'proxy'` immediately — no options calls made
- `iv_source` exposed in `serialize_cache_row()` in `market_data.py` — popup label shows `IV% — schwab` or `IV% — proxy`
- **Production reset required after this fix:** run `DELETE FROM iv_history;` in Supabase SQL editor — old rows used wrong source field and will corrupt IV Rank if left in

### Conviction Score — Base 50 + Proximity + OBV Alignment + Slope Boost (v1.8+)
- **H completely removed from conviction formula** — H is still calculated and stored for regime classification display only (H < 0.45 → oscillators; H > 0.55 → trend-following). H does NOT affect conviction score.
- **Current formula:**
  ```
  base             = 50   (viewpoint alignment is the gate — trade+trend both agree)
  conviction_raw   = base × (0.70 + 0.30 × prox)        → range 35–50
  conviction_align = conviction_raw × alignment_mult      → 1.20 / 0.85 / 1.00
  conviction_final = conviction_align × slope_boost       → 1.17 / 1.00
                   = min(conviction_final, 100.0)
  ```
  where `prox` peaks at 1.0 when close is at the entry zone (LRR for Bullish, HRR for Bearish)

- **OBV Alignment multiplier (Layer 1)** — OBV pivot direction + OBV slope_trend agree with viewpoint:
  - Aligned:    OBV pivot = Bullish AND slope_trend = increasing (Bullish viewpoint)
                OBV pivot = Bearish AND slope_trend = decreasing (Bearish viewpoint) → **× 1.20**
  - Misaligned: OBV pivot AND slope_trend both oppose viewpoint → **× 0.85**
  - Neutral:    anything else → **× 1.00**

- **Slope boost multiplier (Layer 2)** — only fires when Layer 1 aligned AND slope direction confirms:
  - Bullish + aligned + obv_slope = rising  → **× 1.17**
  - Bearish + aligned + obv_slope = falling → **× 1.17**
  - Otherwise → **× 1.00**

- **OBV signals computed:**
  - `obv_dir`: pivot-based OBV direction (bar_window=9) — existing, drives vol_signal display
  - `obv_ma20`: 20-period SMA of OBV series
  - `obv_slope`: sign of 3-bar rate of change on OBV MA20 — `rising` | `falling` | `flat`
    `slope_now = obv_ma20[-1] - obv_ma20[-4]`
  - `obv_slope_trend`: acceleration — `increasing` | `decreasing` | `flat`
    `slope_prev = obv_ma20[-2] - obv_ma20[-5]`; compare slope_now vs slope_prev

- **Range: ~30 (floor) – ~70 (ceiling)** — current phase
  - Floor: `50 × 0.70 × 0.85 × 1.00 = 29.75`
  - Ceiling: `50 × 1.00 × 1.20 × 1.17 = 70.2`

- **Alert threshold: conviction ≥ 65** (≈ 93% of ceiling; H condition removed)

- **Deferred to later phases:** VIX regime multiplier, IV vs realized vol / option skew (per asset class), quad outlook
- **`vol_signal`** (Confirming/Diverging/Neutral) still computed and stored for popup display — no longer drives a multiplier
- Old weights history: v1.6: H_trade×0.65 + H_trend×0.35; v1.7: H_eff×100 + prox boost + OBV mult + VIX mult — all superseded

### Bollinger Band LRR/HRR — v1.8 Formula (MA20 close center + close STD + ATR buffer)
- **Supersedes:** v1.7 H-modulated k_tight formula and v1.8-interim TP-center formula. All prior sigma/anchor/bc_range/MA20_TP formulas obsolete.
- **Two k coefficients — fixed, not H-modulated:**
  ```
  k_wide  = 2.0    # target side — standard 2σ BB; never changes
  k_tight = 0.0    # entry side — MA20(close) exactly; H removed from band width
  ```
  H is still calculated and stored in `signal_hurst` for indicator regime classification
  (H < 0.45 → oscillators; H > 0.55 → trend-following). H does NOT influence band width.

- **Center: MA20(close) — standard 20-day simple moving average of close prices**
  Stored in `price_cache.ma20`. MA20_TP was tried as an interim center but the improvement
  over MA20(close) was negligible (±7 pts on SPX) and `ma20_tp` / `std20_tp` columns have
  been dropped (migration `13fb636fe76a`). MA20(close) is the permanent center.

- **STD20: close-based always**
  `std20 = std(prices[-20:], ddof=0)` — standard Bollinger Band price-level std.
  Stored in `price_cache.std20` (close-based).

- **ATR: 14-day simple MA of True Range**
  `TR[i] = max(H-L, |H-C_prev|, |L-C_prev|)`. Stored in `price_cache.atr`.
  Added by migration `j7e5f3g1h2i0`. Used in downtrend + normal case HRR to ensure
  a meaningful ceiling above close when price approaches MA20 from below.

- **Full formula by pivot direction + MA20 regime:**
  ```
  center = MA20(close)
  vol    = STD20(close)

  Structural uptrend + above MA20 (normal):
    LRR = center                                   # MA20 — tight entry floor (k_tight = 0)
    HRR = center + k_wide × vol                    # BB upper — target

  Structural uptrend + below MA20 (counter-trend):
    LRR = center - k_wide × vol                    # BB lower — widens to full band
    HRR = center + k_wide × vol                    # BB upper — target

  Structural downtrend + below MA20 (normal):
    LRR = center - k_wide × vol                    # BB lower — target
    HRR = max(center, close + 0.5 × ATR)           # ATR buffer: ensures HRR sits at least
                                                   # 0.5×ATR above close; collapses to MA20
                                                   # when price is far below (buffer inactive)

  Structural downtrend + above MA20 (counter-trend flip):
    LRR = center - k_wide × vol                    # BB lower — target
    HRR = center + k_wide × vol                    # BB upper — widens to full band
  ```

- **MA20 regime switch (2-consecutive-close rule):** independent of ABC pivot direction.
  1 close on wrong side forgiven; day 2 flips regime. Stored in `price_cache.ma20_regime`.
  Regime check uses close vs MA20(close).

- **Rel IV completely removed from LRR/HRR** — informational display in popup only
- **MA20 / STD20 / ATR stored in price_cache** — written on every price fetch

### Trend Level and Tail Level — Single MA (v1.7, replaces dual LRR/HRR for Trend and LT)
- **Supersedes:** Dual Trend LRR/HRR and LT LRR/HRR bands — only one level per timeframe now
- **Trend Level:** Break pivot (C normally; B when `d_extended=True`), shown when Trend Dir ≠ Neutral. MA100 slope check removed — always shows the active invalidation level.
  - Uptrend: green floor (buy/add zone); Downtrend: red ceiling (sell/short zone)
- **Tail Level:** MA200, shown only when LT Dir ≠ Neutral AND 20-day slope confirms direction
- **Code/DB key unchanged:** still `"lt"` everywhere in models and DB; display label only is "Tail"
- **Trend HRR removed from table and popup** — only one level per Trend/Tail timeframe

### MA20_TP Center Dropped — MA20(close) Is Permanent Center (`conviction_engine.py`, `schwab_market_data.py`)
- **MA20_TP (typical price center)** was added as a v1.8 interim: TP = (H+L+C)/3 resists downward movement during sell days
- **Removed (migration `13fb636fe76a`):** TP center improvement over MA20(close) was negligible (±7 pts on SPX). Not worth the schema complexity.
- `price_cache.ma20_tp` and `price_cache.std20_tp` columns dropped; `conviction_engine.compute_trade_lrr_hrr()` uses `ma20` directly
- `schwab_market_data._compute_tp_metrics()` function removed; no TP writes anywhere
- **Rule:** Do not re-add MA20_TP. MA20(close) is the permanent center for the BB LRR/HRR formula.

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
- `_append_bar()` — appends close/volume from batch quote to existing `history_json`; recomputes MA20/50/100/200, STD20, spark, ma20_regime from merged history; no API call
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

### IV Fetch — Idempotent on Manual REFRESH DATA (`market_data.py`, `schwab_options.py`)
- **Root problem:** `market_data.py` called `schwab_fetch_iv(db, force=True)` — bypassed the built-in idempotency check on every manual REFRESH DATA press, running ~65 Schwab options chain calls (~55 seconds) even when IV was already fresh
- **Fix:** Changed to `schwab_fetch_iv(db, force=False)` — the existing idempotency check now fires: if IV already fetched today, skip entirely
- **Scheduler path unchanged:** Scheduler calls `schwab_fetch_iv(db)` (default `force=False`) — since IV has never been fetched when the 4 PM job runs, the idempotency check never fires and IV always fetches fresh at EOD
- **First manual REFRESH DATA of the day:** IV fetches (~55 seconds) — unavoidable, 65 options chain calls
- **Subsequent REFRESH DATA same day:** IV skipped entirely → near-instant
- **Rule:** Never change back to `force=True` in `market_data.py` — it re-introduces the 55-second penalty on every button press

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
│   │       ├── aa2d62ea88e4_initial_schema.py
│   │       ├── b3f1c9d2e4a7_price_cache_add_ma_columns.py   ← v1.7 Phase A
│   │       ├── c9a4e1f2b8d3_signal_output_add_ma_levels.py  ← v1.7 Phase B
│   │       ├── d5e3f1a2c4b7_signal_output_add_extended_flags.py ← v1.7 Phase C
│   │       ├── e2f4a6b8c1d0_add_d_extended_to_pivots_and_output.py ← EXTENDED architectural cleanup
│   │       ├── f7a3b2c1d9e6_price_cache_add_ohlc_tp.py      ← added daily_high/low, history H/L, vov
│   │       ├── j7e5f3g1h2i0_price_cache_add_atr.py          ← added price_cache.atr (14-day ATR)
│   │       └── 13fb636fe76a_price_cache_drop_tp_columns.py  ← dropped ma20_tp, std20_tp (±7pt SPX, negligible)
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
- Single job fires at **4:00 PM ET** on NYSE trading days only (via `pandas_market_calendars`)
- On startup: catch-up check — if past 4:00 PM ET, trading day, and no successful run today → runs immediately
- All dates use **ET timezone** — never UTC (see UTC vs ET fix above)

### EOD Flow (4:00 PM ET, NYSE trading days) — single chained job
```
APScheduler (schwab_data_job)
    → schwab_fetch_all()    writes → price_cache (Schwab primary, Yahoo fallback)
    → schwab_fetch_iv()     writes → price_cache.rel_iv + iv_history
    → calculate_signals()   writes → signal_hurst
                                   → signal_pivots
                                   → signal_output
                                   → signal_history (snapshot)
    → scheduler_log         writes → success/failure entry
```
Previously two separate jobs (data at 4:00 PM, signals at 4:15 PM). Merged into one — signals run
immediately after data fetch, both buttons go green together by ~4:02 PM.

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

### EOD Scheduler: Updated Flow (Phase 5+)
```
4:00 PM ET — single chained job (prices → IV → signals)
    schwab_fetch_all()       Schwab primary / Yahoo fallback — writes price_cache
    schwab_fetch_iv()        ~65 requests (options-eligible only) — writes iv_history
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

### Conviction Score Formula — v1.8+ (Base 50 + Proximity + OBV Alignment + Slope Boost)
```
H completely removed from conviction formula.
H is still calculated and stored for regime classification display only:
  H < 0.45 → mean-reverting regime (use oscillators: RSI, Stochastics)
  H > 0.55 → trending regime (use trend-following: MA, momentum)

Base score:
  base = 50   (viewpoint alignment is the gate — trade+trend both agree)

Proximity boost (direction-aware — peaks at entry zone):
  Bullish: prox = 1 - (close - trade_lrr) / (trade_hrr - trade_lrr)   # 1.0 at LRR, 0.0 at HRR
  Bearish: prox = (close - trade_lrr) / (trade_hrr - trade_lrr)        # 1.0 at HRR, 0.0 at LRR
  Clamp:   prox = max(0.0, min(1.0, prox))

  conviction_raw = base × (0.70 + 0.30 × prox)   → range 35–50

OBV Signals:
  obv_ma20        = 20-period SMA of the OBV series
  obv_slope       = sign of 3-bar ROC: obv_ma20[-1] - obv_ma20[-4]
                    'rising' | 'falling' | 'flat'
  obv_slope_trend = acceleration: slope_now vs slope_prev (obv_ma20[-2] - obv_ma20[-5])
                    'increasing' | 'decreasing' | 'flat'

OBV Alignment Multiplier (Layer 1):
  Aligned:    OBV pivot=Bullish AND slope_trend=increasing  (Bullish viewpoint)
              OBV pivot=Bearish AND slope_trend=decreasing  (Bearish viewpoint) → × 1.20
  Misaligned: both oppose viewpoint → × 0.85
  Neutral:    anything else → × 1.00

  conviction_align = conviction_raw × alignment_mult

Slope Boost Multiplier (Layer 2 — only when Layer 1 aligned):
  Bullish + aligned + obv_slope=rising  → × 1.17
  Bearish + aligned + obv_slope=falling → × 1.17
  Otherwise → × 1.00

  conviction_final = conviction_align × slope_boost
                   = min(conviction_final, 100.0)   # hard cap

Range: ~30 (floor) – ~70 (ceiling, current phase)
  Floor:   50 × 0.70 × 0.85 × 1.00 = 29.75
  Ceiling: 50 × 1.00 × 1.20 × 1.17 = 70.2

Alert threshold: conviction >= 65 (H condition removed)

CRITICAL: Conviction is BLANK (not calculated) when Viewpoint = Neutral

Deferred to later phases: VIX regime multiplier, IV vs realized vol / option skew
(per asset class), quad outlook — these will push ceiling toward 100.

vol_signal (Confirming/Diverging/Neutral) still computed and stored for popup display.
It no longer drives a conviction multiplier.
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
| **Bullish** | Trade Bullish + Trend Bullish | Calculated normally |
| **Bearish** | Trade Bearish + Trend Bearish | Calculated normally |
| **Neutral** | Any other combination — including one Neutral, one Bullish/Bearish, or opposite directions | BLANK |

**No Diverging state.** Three states only: Bullish, Bearish, Neutral.

### Alert Flag ⚡ Trigger (ALL THREE must be true)
1. H_eff > 0.55 (effective H — asymmetric for Commodities/FX, symmetric H_trend for all others)
2. Viewpoint = Bullish OR Bearish (never fires on Neutral)
3. Final Conviction ≥ 70% (after all multipliers including VIX regime)

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

### LRR / HRR Formula — Bollinger Band Framework v1.8 (`conviction_engine.py`)

**SUPERSEDES:** v1.7 H-modulated formula. All prior sigma/anchor/bc_range formulas obsolete. Do not use.

#### Inputs
```python
MA20        = 20-day simple MA of close prices                 # stored in price_cache.ma20 (center + regime check)
STD20       = std(prices[-20:], ddof=0)                        # close-based std
ATR         = 14-day simple MA of True Range                   # stored in price_cache.atr
pivot_dir   = 'uptrend' | 'downtrend' | None                   # from ABC pivot structure
ma20_regime = 'uptrend' | 'downtrend'                          # stored in price_cache.ma20_regime
# Note: H_trend still computed and stored but NOT used in band formula (v1.8 change)
# Note: ma20_tp / std20_tp were dropped (migration 13fb636fe76a) — improvement was negligible
```

#### k Coefficients — Fixed (v1.8: H removed from band width)
```python
k_wide  = 2.0    # standard 2σ BB — target side, never changes
k_tight = 0.0    # entry side — MA20 exactly; H does not modulate this

# H is still computed + stored (signal_hurst.h_trade / h_trend) for:
#   H < 0.45 → mean-reverting regime → use oscillators (RSI, Stochastics)
#   H > 0.55 → trending regime → use trend-following indicators (MA, momentum)
# H does NOT affect LRR, HRR, or band width.
```

#### Center: MA20(close)
```python
center = ma20   # 20-day simple MA of close prices; stored in price_cache.ma20
vol    = std20  # close-based std: std(prices[-20:], ddof=0)
```

#### MA20 Price Regime Switch — 2-Consecutive-Close Rule
```
regime = "uptrend"   if 2+ consecutive closes ABOVE MA20(close)
regime = "downtrend" if 2+ consecutive closes BELOW MA20(close)
```
- Independent of ABC pivot structural direction. Pivots say "what is the structural trend." Regime says "where is price vs MA20 right now."
- 1 close on wrong side of MA20 is forgiven. Day 2 flips regime.
- Stored in `price_cache.ma20_regime` — written on every price fetch

#### LRR/HRR Formulas — Pivot Direction + Regime Switch (v1.8)
```python
# Structural uptrend + above MA20 (normal):
LRR = center                               # MA20 — tight entry floor (k_tight = 0)
HRR = center + k_wide × vol               # BB upper — target

# Structural uptrend + below MA20 (counter-trend):
LRR = center - k_wide × vol               # BB lower — widens to full band
HRR = center + k_wide × vol               # BB upper — target

# Structural downtrend + below MA20 (normal):
LRR = center - k_wide × vol               # BB lower — target
HRR = max(center, close + 0.5 × atr)     # ATR buffer: meaningful ceiling above close;
                                           # collapses to MA20 when close is far below

# Structural downtrend + above MA20 (counter-trend flip):
LRR = center - k_wide × vol               # BB lower — target
HRR = center + k_wide × vol               # BB upper — widens to full band
```

#### Role Summary
```
Uptrend + above MA20 (normal):          LRR = MA20 (tight entry, k_tight=0), HRR = BB upper (target)
Uptrend + below MA20 (counter-trend):   LRR = BB lower (wide),               HRR = BB upper (target)
Downtrend + below MA20 (normal):        LRR = BB lower (target),              HRR = max(MA20, close+0.5×ATR)
Downtrend + above MA20 (counter-trend): LRR = BB lower (target),              HRR = BB upper (wide)
```
k_wide always defines the target/exit side. Entry side collapses to MA20 (k_tight = 0).

#### ATR Buffer Behavior
- When close is far below MA20 (2×ATR or more): `close + 0.5×ATR` < MA20 → HRR = MA20
- When close approaches MA20 (within 0.5×ATR): buffer kicks in → HRR = close + 0.5×ATR
- This ensures HRR always provides a meaningful ceiling, even when close has recovered near MA20
- ATR = 14-day simple MA of True Range; stored in `price_cache.atr`

#### Self-Correction Property
When close drops below LRR → tomorrow's MA20 falls → LRR follows MA20 downward automatically. Formula self-heals within 1–3 sessions.

#### Daily Overshoot Flag (Tactical — Separate from Structural EXTENDED)
```python
# uptrend:   if today_close > prior_hrr → hrr_extended = True  (↑ flag, "do not chase" tooltip)
# downtrend: if today_close < prior_lrr → lrr_extended = True  (↓ flag, "do not chase" tooltip)
# Stored in signal_output.lrr_extended / hrr_extended (Boolean)
# State cell still shows UPTREND_VALID / DOWNTREND_VALID — NOT the structural EXTENDED state
```

#### STD20
`std(prices[-20:], ddof=0)` — standard Bollinger Band price-level std. Written to `price_cache.std20` on every price fetch.

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
                calculated_at
                UNIQUE(ticker, timeframe)

price_cache:    ticker, close, volume, ma20, ma50, ma100, ma200, std20, ma20_regime,
                rel_iv, iv_source, data_source, cache_date,
                history_json, volume_history_json,
                history_dates_json, history_high_json, history_low_json,
                daily_high, daily_low,
                spark_json, updated_at,
                atr,                        ← 14-day simple MA of True Range (migration j7e5f3g1h2i0)
                vov_30d,                    ← Phase 6: 30-day VIX volatility-of-volatility (decimal, e.g. 0.15)
                vov_rank,                   ← Phase 6: VoV rank within its own 252-day rolling history (0–100)
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
5. **Volume Signal (OBV)** — Confirming / Diverging / Neutral. Applied as multiplier to conviction score.

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
| Conviction Score | **Frequentist** | H_eff × proximity boost × OBV mult × VIX regime mult (Phase 6) |
| Trend / Tail Level | **Frequentist** | MA100 / MA200 slope-confirmed floor or ceiling (v1.7) |
| OBV Pivot Direction | **Frequentist** | Structural pivot logic applied to OBV series |
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
- **VoV line** — `VoV 15.3% · 72nd pct` displayed in grey below scale labels; from `price_cache.vov_30d` + `vov_rank`; hidden when null

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
| Conviction % | 0-100% — blank when Neutral; green ≥70%, amber 50-69%, grey <50% |
| ENTRY | ▲ BUY (green) or ▼ SELL (red) badge — prox > 0.85 at entry zone, all timeframes aligned; blank when conditions not met; sortable |
| Trade Dir | Short-term direction |
| Trade LRR | BB lower band (MA20 - k_lrr×STD20) — color = trade direction; ⚠ when LRR < C (uptrend) or LRR > B (downtrend); ↑↓ overshoot flag |
| Trade HRR | BB upper band (MA20 + k_hrr×STD20) — color = trade direction; ⚠ when HRR < B (uptrend) or HRR > C (downtrend); ↑↓ overshoot flag |
| Trend Dir | Medium-term direction |
| Trend Level | MA100 — floor (uptrend, green) or ceiling (downtrend, red); hidden when Neutral or slope contradicts direction |
| Asset Class | Classification — tightened badge, far right |
| Sector | GICS sector / type — tightened badge, far right |

## Popup Fields (click any row) — Phase 6
| Field | Notes |
|---|---|
| Close | Live price |
| Viewpoint | Bullish / Bearish / Neutral |
| Aligned Since | ET timestamp — when current Bullish/Bearish viewpoint began. Hidden when Neutral |
| Conviction | % or — when Neutral |
| ΔH (20d) | Change in H_trade (63-day DFA, Trade timeframe) over ~20 trading days — green when rising, red when falling; from `h_trade_delta` in `signal_output` |
| VIX Regime | Investable / Edgy / Choppy / Danger — regime at time of signal calculation; from `vix_regime` in `signal_output` |
| Vol Direction | Bullish / Bearish / Neutral — OBV pivot trend direction (`obv_direction`) |
| Vol Signal vs Trade | Confirming ✓ / Diverging ✗ / Neutral — compared against Trade Dir (`obv_confirming`) |
| Trade Dir | Direction + icon |
| Trade LRR | BB lower band; color = trade dir; ⚠ + hover tooltip when warn; ↑↓ overshoot flag |
| Trade HRR | BB upper band; color = trade dir; ⚠ + hover tooltip when warn; ↑↓ overshoot flag |
| Trade C | C pivot — trade invalidation level (or B when structural EXTENDED) |
| Trade B | B pivot — prior swing high/low |
| Trade State | Structural state string |
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
| Rel IV% | IV Rank — schwab or proxy source tagged; informational only (not in conviction formula) |
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

| Timeframe | LRR/Level ⚠ condition | HRR ⚠ condition |
|---|---|---|
| **Trade** | Bullish: `lrr < c` · Bearish: `lrr > b` | Bullish: `hrr < b` · Bearish: `hrr > c` |
| **Trend** | Bullish: `level < c` only (MA100 below C pivot) | Bearish: `level > c` only |
| **Tail** | Never | Never (no HRR column) |

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
25. **Conviction is blank when Viewpoint = Neutral**
26. **Direction determined by pivots only** — H has no role in direction or viewpoint
27. **LRR/HRR always show** — grey when Neutral, green when Bullish, red when Bearish
28. **Viewpoint has three states only** — Bullish, Bearish, Neutral (no Diverging)
29. **Direction check uses C normally; B when d_extended=True** — `price > c` for Bullish, `price < c` for Bearish; LRR is not part of the direction check. When `d_extended=True`, pivot engine pre-handles B-based breaks before `_compute_direction` is called — no EXTENDED case needed in direction logic.
30. **LRR/HRR always compute for BREAK states** — `_infer_pivot_direction` infers underlying direction even for BREAK_OF_TRADE/BREAK_OF_TREND/BREAK_CONFIRMED so LRR/HRR render grey
31. **LRR/HRR cell color = timeframe direction** — use `dirRangeColor(dir, isWarn)`, NOT viewpoint color
32. **Per-cell ⚠ warn flags are price-based** — separate from IV-driven `warning` structural state
33. **Warning scope is timeframe-specific** — Trade: full (C+B); Trend: C-based only; LT: none
34. **All cache_date and run_date writes use ET date** — never UTC date for trading day keys
35. **`get_active_tickers(db)`** is the only way to retrieve the ticker list in backend — no hardcoded arrays
36. **tickers.js is seed data only** — never import it for the live ticker universe; use `/api/tickers`
37. **Asset class overrides checked first** — add new entries to `ASSET_CLASS_OVERRIDES` in `tickers.py` when yfinance returns wrong asset class
38. **Neo cannot read .docx files** — CLAUDE.md is the primary spec source for Neo; keep it current
39. **One close through break level = BREAK_OF_TRADE immediately** — break level = C normally; B when `d_extended=True`. Direction HOLDS during BREAK_OF_TRADE (not Neutral). Forgiveness: recovery on day 1 restores prior state; 2+ consecutive closes = BREAK_CONFIRMED → direction → Neutral. Recovery from BREAK_CONFIRMED requires close above B.
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
51. **MA20 regime (`'uptrend'`/`'downtrend'`) is independent of ABC pivot direction** — do not conflate. Pivots say "what is the structural trend." MA20 regime says "where is price vs MA20 right now." They can disagree.
52. **LT timeframe code/DB key stays `"lt"` everywhere** — display label only changes to "Tail" (UI, popup headers, table header). Never rename in models, DB columns, or backend API responses.
53. **Three independent "extended" concepts — never conflate:**
    - `d_extended` (Boolean field) — D > B + abs(B-C); B becomes break level; drives warn flags and popup `*`; NOT in structural_state
    - `lrr_extended` / `hrr_extended` (Boolean fields) — daily overshoot: today's close vs prior LRR/HRR; drives ↑↓ flags on LRR/HRR cells
    - "EXTENDED" string — **no longer exists** in structural_state or anywhere in the system
54. **Trend Level and Tail Level display `None` when direction is Neutral** — no level shown; also hidden when MA slope contradicts Trend/Tail direction
55. **ENTRY prox threshold = 0.85** — do not revert to 2%-of-price absolute threshold; prox is range-normalized via HRR-LRR (STD20-derived, automatically volatility-scaled)
56. **Proximity in conviction formula is direction-aware** — peaks at 1.0 when close is at the entry zone: LRR for Bullish (floor entry), HRR for Bearish (ceiling short entry)
57. **`structural_state` has exactly six valid values** — `UPTREND_VALID`, `DOWNTREND_VALID`, `BREAK_OF_TRADE`, `BREAK_OF_TREND`, `BREAK_CONFIRMED`, `NO_STRUCTURE`. Never add EXTENDED, WARNING, or any other value.
58. **BREAK_OF_TRADE / BREAK_OF_TREND do NOT change direction to Neutral** — direction holds (Bullish/Bearish) during provisional break; only BREAK_CONFIRMED flips direction to Neutral
59. **WARNING is a boolean flag only** — `signal_output.warning`; never override `structural_state` to "WARNING" in `conviction_engine.py`
60. **`d_extended` is the sole source of truth for B vs C break level** — `is_warning`, `_compute_warn_flags`, popup `tradeBreakIsB`/`trendBreakIsB`, and `warnTip` all read `d_extended` directly; never derive from state string comparison
61. **VIX regime multiplier tiers are locked (Phase 6)** — Investable (VIX < 19) × 1.10 · Edgy (19–23) × 1.00 · Choppy (24–29) × 0.90 · Danger (≥ 30) × 0.80. Applied last in conviction chain after OBV multiplier. Final conviction capped at 100. Do not change these thresholds without explicit instruction.
62. **H_eff (asymmetric Hurst) asset class scope (Phase 6)** — asymmetric H (H_trend_up / H_trend_down) applies to Commodities and Foreign Exchange ONLY. All other asset classes use symmetric H_trend. `/ZN` (10-Year Treasury futures) is EXCLUDED from asymmetric H despite being a futures ticker — its price series is driven by rate policy, not directional commodity flows; always uses symmetric H_trend.
63. **ΔH (delta-H) threshold for display color** — `h_trade_delta >= 0` → green (momentum improving or stable); `h_trade_delta < -0.05` → red (meaningful deterioration); between -0.05 and 0 → neutral grey. Stored in `signal_output.h_trade_delta`; display only — NOT in conviction formula.
64. **VoV rank computed from existing VIX price history** — no separate accumulation period needed. `compute_vov_with_rank()` computes 30-day rolling std of VIX log returns (VoV series) from 5-year history in `price_cache`, then ranks current VoV within its own 252-day trailing window. Returns `(vov_30d, vov_rank)` tuple. Stored in `price_cache.vov_30d` and `price_cache.vov_rank`. Updated on every REFRESH DATA when VIX history is fetched.
65. **Proactive spec review** — when reading a spec or reviewing methodology, flag any inconsistencies with existing code or other parts of the spec before implementing. Do not implement silently when something looks wrong or contradictory.

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

### Phase 6 Build Sequence

| Task | Deliverable | Status |
|---|---|---|
| 6.1 | Delta-H (ΔH) — 20-day change in H_trade; display in popup | ✅ Complete |
| 6.2a | VoV percentile rank — 30-day VIX volatility-of-volatility + 252-day rank | ✅ Complete |
| 6.2b | VIX regime multiplier — Investable/Edgy/Choppy/Danger tiers applied to conviction | ✅ Complete |
| 6.3 | Asymmetric H (H_eff) — directional Hurst for Commodities/FX; symmetric for all others | ✅ Complete |

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