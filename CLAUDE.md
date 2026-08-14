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
- **Database:** Supabase (managed Postgres) in production — isolated local **Postgres 17 container** (`db` service in docker-compose, matches prod Supabase 17.6) for local dev. SQLite is no longer used for dev. See "Local Dev Environment" + **ADR-025**.
- **yfinance:** v1.2.0 — do not downgrade (v0.2.x has persistent 429 block)
- **SMS:** Telnyx (v2 REST, `services/sms.py`); credentials in `.env` (TELNYX_API_KEY, TELNYX_FROM, TELNYX_TO). **Globally disabled** via `sms.SMS_DISABLED = True` pending 10DLC carrier registration — `send_sms`/`send_sms_to` no-op until lifted. (Superseded Twilio.)
- **Email:** Gmail SMTP (`services/email_alert.py`); env `EMAIL_FROM` / `EMAIL_TO` / `EMAIL_APP_PASSWORD`. `send_email_to(recipient, …)` for per-recipient sends. No kill switch — email is live.
- **FRED:** `services/fred.py` — REST client for St. Louis Fed economic data API; `FRED_API_KEY` in `.env`/`.env.dev`/Fly secrets. Series: `DGS2` → `TWO` (2-Year Treasury yield, replaces degraded Yahoo `2YY=F`), `BAMLH0A0HYM2` → `HY_OAS` (HY credit spread in bps). **Persisted in `price_cache`** via `fred_fetch_and_store()` in `schwab_market_data.py` — same fetch→store→serve pattern as Schwab/Yahoo. Runs in EOD scheduler (after prices, before IV) and manual REFRESH DATA. Endpoints read from `price_cache` with FRED live as fallback. `FRED_SERIES_MAP` in `schwab_market_data.py` maps tickers to FRED series IDs. 120 req/min limit; daily data, ~1-day lag.
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
- **Cloudflare:** Active — DNS management, DDoS protection, free SSL. No hosting. Account id `1cc54ccce957ce25a79ac27cbdf1e760`. `signal.suttonmc.com` is **Proxied** (orange cloud); `api.signal.suttonmc.com` is **DNS only** (grey cloud) — do not flip either (rule #97, **ADR-021**). Fly cert for the proxied `signal` host renews via DNS-01 records that must stay in place. Bot Fight Mode: **on**.
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
- **429 fallback** (`market_data.py`): on 429 the batch endpoint serves the cached DB rows (never returns empty) so all tickers stay visible.
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
- **OBV direction** (`conviction_engine.py`) — current method is a **21-bar lookback** (`_OBV_LOOKBACK = 21`): current OBV vs OBV 21 bars ago — higher → Bullish, lower → Bearish, equal → Neutral. Prior z-score regression (ADR-017), single-window slope÷std (ADR-005), ABCD-pivot / HH+HL / price-momentum methods are superseded. Vol Signal is a **two-layer** verdict: MA20 slope AND 21-bar lookback must BOTH confirm consensus direction for Confirming; BOTH oppose for Diverging; mixed = Neutral. Consensus direction = Trade OR Trend (whichever is directional; opposing → no consensus). `obv_direction`/`obv_confirming` stored in `signal_output`.
- **VIX regime cutoff is strictly `< 19`** (Green/Investable) — never use 20. `19 ≤ VIX < 30` amber, `≥ 30` red.
- **Vol popup naming** (`App.js`) — never rename DB field `vol_signal` → `obv_signal`. Popup shows "Vol Direction" (`obv_direction`) + "Vol Signal vs Trade" (`obv_confirming`, vs Trade Dir).
- **EXTENDED architectural cleanup** — `d_extended` boolean replaced the EXTENDED/WARNING `structural_state` values; `is_warning`/`_compute_warn_flags` take `d_extended` (`break_level = b if d_extended else c`); `compute_output` never sets `state="WARNING"`. See **ADR-002** (migration `e2f4a6b8c1d0`).
- **Q FIT arrows** — embedded in each quad column cell (no standalone column). Each column computes its own fit: `quad_fit` (current month), `quad_fit_next` (next month), `quad_fit_qtr` (quarterly) — all viewpoint-INDEPENDENT (Best/Neutral/Worst via `get_quad_alignment`); **never** `quad_alignment` (viewpoint-dependent). International Equities use country quarterly quad for all columns; US uses the respective monthly/quarterly quad per column.

### Schwab IV & volatility metrics (`schwab_options.py`)
- **IV source** — never read the option chain's top-level `volatility` (that's realized vol). IV30 = 30-day constant-maturity ATM IV via `_extract_atm_iv` (interpolate the two expirations bracketing 30 DTE). IV Rank is **range-based** `(cur-min_252)/(max_252-min_252)×100`, not frequency percentile. `iv_source` ∈ schwab | proxy | price_rank; per-ticker/no-token errors fall back to the Yahoo proxy. See **ADR-006**.
- **25Δ skew / risk reversal** — `_extract_25d_skew` uses a **strike-based Black-Scholes approximation** (compute K_call/K_put_25d from S and ATM IV, read nearest strike's IV), **never the delta field** (Schwab omits OTM delta → would land on ATM, near-zero RR). `risk_reversal = call_iv_25d − put_iv_25d` (positive = bullish forward skew). `strike_count = 20`. See **ADR-006**.
- **HV / VRP** — `hv30`/`hv90` = std of last 21/63 log returns × √252 (from `history_json`, no API call); `vrp = IV30 − HV30`. Skew Rank / VRP Rank / HV Rank each = 252-day range rank (`_RANK_MIN_HISTORY = 30`). P/C ratio = total put OI ÷ call OI (`>1.2` fear, `<0.6` complacency).
- **`vol_history`** holds all vol metrics; `implied_vol` nullable. `accumulate_hv_only(db)` writes HV-only rows for Yahoo-only tickers (SPX, NDX, RUT, VIX, $DJI, USD, JPY, /CL, /ZN, /GC, /HG, VVIX) and must stamp `price_cache.hv30/hv90/hv_rank` too. Idempotency checked against `vol_history` (clear rows to force re-fetch).
- **HV Rank label** — `iv_source='proxy'` shows "HV Rank" (realized-vol rank, never implied); `'schwab'` → "IV Rank — schwab"; `'price_rank'` → "VVIX Rank — price".

### Trade LRR/HRR — v1.9.2 BB+Snap Formula (Dynamic-N BB + Snap)
- **Spec:** `Docs/SignalMatrix_RR_v1_9_1.txt` (authoritative — full Steps 1–8, 8-bucket N lookup, computation). Supersedes v1.8 fixed-N BB + ATR buffer + MA20-regime (ATR/MA20/STD20/`ma20_regime` columns remain on `price_cache` but no longer drive the band).
- **Constants** (TOS-validated, hardcoded in `conviction_engine.py` — **code is source of truth**, see **ADR-013**): `k_wide=2.0, k_extend=2.2, k_max=1.0, k_min=0.0, k_decay=0.5`; `rank_lookback=252, hv_period_bars=21, snap_window=22, proximity_smooth=3`. Do not revert to spec defaults without re-validating bands against Hedgeye in ToS.
- **Framework:** dynamic-N BB (N 8→15 by IV30 percentile rank, HV30 fallback) + a stateful snap that compresses the trailing band toward MA during impulses. σ is **price-derived** `std(closes[-N:], ddof=0)`; IV/HV only drives N selection. Directional proximity `prox_lrr=(close−maN)/sdN` (signed, EMA-3) lets per-side k expand toward k_wide when price crosses MA — eliminates LRR inversion. Snap trigger = **today's close** vs prior 22 closes; releases via merge (k→k_wide) or breach (intraday extreme crosses yesterday's snap line); LRR wins coincidence.
- **State & contract:** snap state persists in `signal_output.hrr_snapped`/`lrr_snapped` (+`signal_history`; migration `q2r3s4t5u6v7`); cold start `len(closes) < 273` → `(None,None,False,False)`. `compute_trade_lrr_hrr(closes, vol_series, prior_hrr_snapped, prior_lrr_snapped)` is **pure**; caller (`compute_output`) handles vol-series lookup (`get_trade_rr_vol_series`: IV-primary → stored-HV → HV-from-closes fallback, ADR-024) + snap I/O. EOD-batch (today's close is confirmed, no forward displacement). See rule #77.

### Trend Level and Tail Level — Single MA (v1.7)
- One level per timeframe (replaces dual Trend/LT LRR/HRR). **Trend Level** = break pivot (C; B when `d_extended=True`), shown when Trend Dir ≠ Neutral — MA100 slope check removed; always shows the active invalidation level (uptrend green floor / downtrend red ceiling). **Tail Level** = MA200, shown only when LT Dir ≠ Neutral AND 20-day slope confirms. Code/DB key stays `"lt"`; display label is "Tail". Trend HRR removed from table/popup.

### MA20_TP Center Dropped (historical)
- MA20_TP / typical-price center was dropped (migration `13fb636fe76a`); v1.9.1 replaced the BB center with dynamic-N MA per-run from `closes[-N:]`. `price_cache.ma20` still populates for legacy only. **Never re-add MA20_TP.** See **ADR-007**.

### Infra & data-source guardrails
- **H/L history alignment** — when adding OHLC-based columns, verify `len(history_high_json) == len(history_json)` after the first data run (a legacy bootstrap once left H/L 3 bars short of close, inflating ATR).
- **Supabase from Docker (PROD migrations only)** — when migrating **production**, alembic must use `SUPABASE_POOLED_CONNECTION_STRING` (IPv4, port 6543) or the pre-encoded `DATABASE_URL`; the direct `:5432` host is IPv6-only and Docker Desktop on Windows can't route it (`alembic current` against it fails `Network is unreachable`). `alembic/env.py` does **NOT** auto-fall-back to pooled — it picks the first of `DATABASE_URL` → `SUPABASE_CONNECTION_STRING` → `SUPABASE_POOLED_CONNECTION_STRING` that is set, so never leave the IPv6 direct string as the only one set. Local dev no longer touches prod at all — it uses the `db` container via `.env.dev` (see "Local Dev Environment" + rule #89).
- **Supabase runtime = psycopg2 sync** — all routers are synchronous SQLAlchemy; `database.py` `_make_sync_url()` converts the asyncpg URL → psycopg2 and URL-encodes the password (`@ # /`). Do not introduce `create_async_engine`/`AsyncSession` without a planned full-router migration.
- **Fly secrets** — pre-encode passwords containing `# $ @ , /` (Fly mangles `#`/`$`); `database.py` checks the pre-encoded `DATABASE_URL` secret first, then `SUPABASE_POOLED_CONNECTION_STRING`.
- **Fly web deploy** — multi-stage build → `nginx:alpine` static (CRA `npm start` dies headless on Firecracker); `.dockerignore` MUST exclude `node_modules` (Windows binaries crash Linux); nginx needs `try_files $uri $uri/ /index.html` for React routes; all web deploys via `./deploy-web.sh` (never bare `fly deploy`). See **ADR-008**.
- **yfinance asset class** — `ASSET_CLASS_OVERRIDES` (`tickers.py`) is checked first before inference; verify asset class on new ETFs (rule #37 + Task 4.7 § hold the dict).
- **Futures = 3-file checklist** — new futures (`/XX`) need `YAHOO_SYMBOL_MAP` (`"/XX":"XX=F"`) + `SCHWAB_UNSUPPORTED` + `IV_INELIGIBLE`; for consistency also add to `_NON_NYSE_CALENDAR` (CME calendar) and `_HV_ONLY_TICKERS` (HV accumulation) — every list `/CL`,`/ZN`,`/GC` occupy. Current: /CL, /ZN, /GC, /HG (`HG=F`, COMEX copper). Symbol stored with slash; endpoints use `{symbol:path}`.
- **Indices / FX / futures permanently route to Yahoo** — Schwab API is equity/ETF-only (batch quotes silently drop indices; no FX endpoint; futures are contract-specific). `SCHWAB_UNSUPPORTED = {USD, JPY, /CL, /ZN, /GC, /HG, SPX, NDX, $DJI, VIX, RUT, VVIX, VXN, RVX, GVZ, OVX, MOVE, PALL, PPLT}`; run `_yahoo_fetch_subset` even on the fresh-cache early return so these get `updated_at` stamped. See **ADR-009**.
- **Restructured ETF history check** — some ETFs (currently PALL, PPLT) were restructured and Schwab's history API returns pre-restructuring prices, creating a discontinuity vs current quotes. Add these to `SCHWAB_UNSUPPORTED` so Yahoo supplies the history. Before adding new precious metals or commodity ETFs, verify Schwab history is continuous with the current price scale. See **ADR-015**.

### UI & dashboards guardrails
- **Sidebar** (`Sidebar.js`) — must stay `position: fixed` (sticky re-introduces Recharts `ResponsiveContainer` ResizeObserver stutter). Add dashboards by appending to `NAV_ITEMS` — no other files change. Admin is NOT in the sidebar (direct URL only). **VOL** is a collapsible parent with four children: SPX VOL (`/vol`), MACRO VOL (`/vol/macro`), BOND VOL (`/vol/bond`), HY CREDIT (`/vol/hy-credit`). Clicking VOL toggles the submenu open/closed (no navigation); only child items navigate. Collapsed sidebar: clicking VOL icon navigates to SPX VOL (default). Sub-items auto-expand when on any `/vol/*` route. See **ADR-011**.
- **Macro Vol dashboard** (`/vol/macro`) — charts VIX/VXN/RVX/GVZ/OVX; MOVE is collected & stored separately. **Speedometer regime gauges** above the chart show at-a-glance Investable/Choppy/Danger for all 5 indices using per-index thresholds from `VOL_INDEX_THRESHOLDS`. Frontend polls every 15 min during market hours (matches intraday quote cadence). Gauges: `VolGauge`/`VolGauges` components in `MacroVolChart.js`. **Needle animation:** needles sweep from left (-90°) to final position on mount with a 1.2s cubic-bezier bounce (`0.34, 1.56, 0.64, 1`); `animate` state flips via `requestAnimationFrame` after first paint. **Timestamp** top-right: contextual `LIVE` (9:30 AM–4 PM ET weekdays) or `EOD` (after hours/weekends) — derived from ET market hours check, not a flag. **OVX right-axis note** uses grey TEXT color with only the `▶` arrow in amber (avoids pulling attention).
- **Bond Vol dashboard** (`/vol/bond`) — charts MOVE index (ICE BofA Treasury implied volatility) with Investable (85) and Danger (120) threshold reference lines. Same layout as Macro Vol (chart + stats table + context note). Data from `GET /api/vol/bond-history` (single ticker, same response shape). MOVE is Schwab-only (`$MOVE`) — no Yahoo fallback; blank in dev.
- **HY Credit dashboard** (`/vol/hy-credit`) — dual-axis chart: HY OAS (FRED `BAMLH0A0HYM2`, blue `#4e8fde`, left axis in bps) + HYG price (white `#c8d8e8`, right axis in $). Inverse relationship: spreads widen → HYG drops. Regime badge: TIGHT <300 bps (green) · NORMAL 300–500 (amber) · STRESS ≥500 (red). OAS fetched live from FRED on each page load (daily data, ~1-day lag). HYG from `price_cache`. Stats table with bps formatting (OAS) and price formatting (HYG). OAS delta colors inverted vs price (widening = red, tightening = green). Union-date alignment (FRED + NYSE calendars differ); `connectNulls={true}` on both lines. Data from `GET /api/vol/hy-credit-history`.
- **Macro Vol data source** — VIX from Yahoo (`^VIX`); VXN/RVX/GVZ/OVX/MOVE from Schwab `$`-symbols (`SCHWAB_INDEX_HISTORY_MAP`, fetched via `_schwab_fetch_index_histories`); `_yahoo_fallback` **excludes** these so token expiry keeps stale-correct Schwab data instead of Yahoo garbage. The `append` fetch uses `MONTH`/`ONE_MONTH` + daily — **never** `periodType=day` + `frequencyType=daily` (Schwab 400s: `day` only allows `minute`), and routes through the merge `_upsert` so multi-day gaps fill. RVX has no Yahoo fallback (`^RVX` delisted) — Schwab is its only source. See **ADR-010** + **ADR-022** + rule #98.
- **Macro Vol chart uses union dates** (`vol.py` `/api/vol/macro-history`) — date axis is UNION of all ticker date arrays; each series fills `None` for missing dates (`connectNulls={false}` in chart). Previously strict intersection cut the chart back to the most stale ticker. Stats anchor `last` to `price_cache.close`; `prev` is **value-anchored** (`closes[-2]` when `close == closes[-1]`, else `closes[-1]`) — **never** gated on wall-clock `dates[-1] >= today_et`, which collapsed `prev→last` (DoD=0 for every ticker) when viewed any day after the last bar.
- **`_schwab_fetch_index_histories` per-ticker Yahoo fallback** — if Schwab `$VXN/$RVX/$GVZ/$OVX` history call fails individually, falls back to `_yahoo_fetch_subset` for that ticker. Previously failure was silent and the data gap was unrecoverable until Schwab was fixed.
- **MACRO sidebar parent** — collapsible parent at the bottom of sidebar navigation (below SECTOR PERF). Icon: M + baseline stroke SVG (`MacroIcon`). Children: YIELD CURVE (`/macro/yield-curve`), KEY CORRELATIONS (`/macro/correlations`). Houses economic regime indicators (yield curve, credit, correlations, growth/inflation/liquidity — distinct from VOL which covers direct market volatility). Sidebar now uses generic `openMenus` state for all collapsible parents (VOL, MACRO) — replaces the old hardcoded `volOpen`.
- **Yield Curve dashboard** (`/macro/yield-curve`) — dual-axis ComposedChart: TWO (2Y, `#c8d8e8`) + TNX (10Y, `#8899aa`) yields on left axis; computed 2-10 spread (TNX−TWO, `#4e8fde`) as Area on right axis in bps. Header badge: "NORMAL · XX bps" (green) or "INVERTED · XX bps" (red). Stats table with yield formatting (2Y/10Y) and bps formatting (spread). Zero reference line on spread axis. 480px chart height, vertical+horizontal gridlines, 2Y/MAX toggle. **TWO sourced from FRED `DGS2`** (Yahoo `2YY=F` delivers degraded stale data — same value for weeks, step-function spikes); TNX from `price_cache` (Yahoo `^TNX` is clean daily). Union-date alignment (FRED + NYSE calendars differ); `connectNulls={true}` on all lines. Data from `GET /api/vol/yield-curve-history` (value-anchored stats, same pattern as macro-vol). Spread delta colors inverted (green = steepening, red = flattening).
- **Key Correlations dashboard** (`/macro/correlations`) — rolling Pearson **price-level** correlations vs DXY across 5 timeframes (15D, 30D, 90D, 120D, 180D trading days) + 52-week rolling 30D stats (High, Low, % Time Pos, % Time Neg). Rows: SPX (S&P 500), /CL (Crude Oil), DBC (Commodities), /GC (Gold), IBIT (Bitcoin) — spot/futures tickers, not ETF proxies (matches Hedgeye methodology). Data from `GET /api/macro/correlations` (`backend/routers/macro.py`). **Cell highlighting:** strong (≥0.70) solid backgrounds `#00e5a0`/`#ff4d6d`; moderate (0.50–0.70) solid backgrounds `#66eebb`/`#ff8da6`; both with dark bold text (`#0a1628`, weight 700). Right-side rolling columns use colored font only (no background): `corrColor` green/red strong, light green/pink moderate. Sub-headers fontSize 9 (exception to standard 8 on this page only). DXY ticker renamed from USD across all backend config (`YAHOO_SYMBOL_MAP`: `DXY → DX-Y.NYB`). **DXY context section** below the correlation grid: 1-year price chart (dual Y-axis, tight domain) with header showing close, Viewpoint, Trend, Conviction, Quad badge (ℹ tooltip with Security Analysis-style quad detail text), and blue VIEW DETAIL → link to `/security/DXY`. Data returned inline from the correlations endpoint (signal_output + quad_settings + ticker metadata).
- **Sector Performance** (`/sector`) — SPX shown without `$` prefix (index); sector ETFs with `$`.

### Signals, ops & auth guardrails
- **No per-ticker query loops in read paths** — always `.filter(PriceCache.ticker.in_(tickers))` with `load_only` (skip the `history_json`/`volume_history_json` blobs).
- **Gap-detection fetch modes** (`schwab_market_data.py`, both Schwab & Yahoo paths) — per-ticker `skip`/`append`/`short`/`bootstrap`; `append` adds today's bar from the batch quote (no history API call); the 0.5s rate-limit sleep fires only on a real history call. See **ADR-012**.
- **`_schwab_fetch` requires `today` defined at top** — `today = datetime.now(_ET).strftime("%Y-%m-%d")` must be the first line after `PH = ...` in `_schwab_fetch`. It is used at multiple points in the loop (`_history_fetch_mode`, `_update_quote_only`, `_append_bar`). Missing it raises `NameError: name 'today' is not defined` which silently kills the entire Schwab fetch (caught by the outer try/except → Yahoo fallback) on every run. Do not remove or move this line.
- **Schwab refresh token has a hard 7-day expiry from login** — `get_status()` measures token age from **`created_at`** (stamped ONLY on a full OAuth exchange via `is_full_oauth=True`; never touched by access-token refreshes). This is the true refresh-token age: Schwab's 7-day life runs from login and is NOT extended by access-token refreshes. `state='aging'` fires at day 5 (amber dot); `state='expired'` at day 7+ (red dot, re-auth required). **Do NOT revert the clock to `updated_at`** — it is re-stamped on every successful access-token refresh (~every 30 min during market hours), so it never ages while the token is healthy: the age sits at 0–1 days right up until the 7-day wall, then only climbs AFTER the token already died (false-green, no advance warning — this is the recurring-weekly-death bug, see **ADR-026**). **Do NOT use `expires_at`** either — that is the 30-min access-token lifetime and would show red overnight (the original ADR-016 bug). `created_at` is the only field that is both refresh-stable and OAuth-anchored. An expired access token auto-recovers on the next schwab-py API call; red must only mean "refresh token is dead, re-auth required." See **ADR-016** (superseded clock) + **ADR-026** (correct clock). Daily 9 AM scheduler job (`_schwab_token_age_alert_job`, runs every day incl. weekends) sends email at day 5 (warning) and day 6+ (urgent) — now fires BEFORE the death. Immediate email sent on `invalid_grant`. Re-auth URL: `https://api.signal.suttonmc.com/api/auth/schwab/login`. **NOTE: weekly interactive re-auth is unavoidable — Schwab provides no API-only way to renew the refresh token; the fix makes the death *predicted*, not *prevented*.**
- **CALCULATE SIGNALS skip** — on repeat **manual** runs, Hurst+Pivots skip when `calculated_at` is today (output stage still runs); `trigger="scheduled"` ALWAYS recomputes everything. Never apply the skip to scheduled.
- **IV idempotent on manual REFRESH** — `market_data.py` calls `schwab_fetch_iv(force=False)` (never `force=True`); the scheduler relies on the same idempotency check (IV unfetched at 4 PM → always fetches).
- **Button freshness** — REFRESH DATA amber when past 4:15 PM ET weekday AND cache stale; CALCULATE SIGNALS amber when its timestamp is older than the data timestamp. Both admin-only (UI `isAdmin` + backend `require_admin_user`).
- **Auth & user management** (JWT httpOnly cookie + RBAC) — full spec in `Docs/Auth_User_Management_Spec_v1.0.md`; operating guards live in rules #80–#91; recovery in `Docs/RUNBOOK_AUTH_RECOVERY.md`.

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
│   │   │   ├── AdminPanel.js              ← admin shell: JWT auth (login redirect) + header + tab nav + nested Routes
│   │   │   ├── TickerList.js              ← ticker CRUD tab (/admin/tickers) — extracted from AdminPanel
│   │   │   ├── QuadSetup.js              ← quad config tab (/admin/quad) — US monthly NTM grid (12 rows, auto-save) + country quarterly table (16 countries × 4 quarters)
│   │   │   ├── UserList.js               ← user management tab (/admin/users) — role/status/reset-pw
│   │   │   └── AlertSettings.js          ← alert delivery tab (/admin/alerts) — per-user email/phone channels + per-alert on/off (Phase 1 Alert Creator)
│   │   ├── Analysis/
│   │   │   └── TickerAnalysis.js          ← stub — /ticker/:symbol route; full page future scope
│   │   ├── Dashboard/                     ← placeholder, logic still in App.js
│   │   ├── Security/
│   │   │   └── SecurityAnalysis.js        ← /security/:ticker deep-dive — pillars, price+RR chart, AI summary, profile
│   │   ├── Macro/
│   │   │   ├── SectorPerformance.js       ← /sector route; absolute + relative sector perf tables (1D/MTD/QTD/YTD vs SPX)
│   │   │   └── KeyCorrelations.js        ← /macro/correlations route; rolling Pearson vs DXY + 52-wk rolling stats
│   │   ├── Vol/
│   │   │   ├── SpxVolChart.js             ← SPX realized vol chart (HV30/HV90 lines + daily % change bars); 2Y/MAX toggle
│   │   │   ├── BondVolChart.js            ← MOVE bond vol chart (threshold lines at 85/120); stats table; 2Y/MAX toggle
│   │   │   ├── HyCreditChart.js           ← /vol/hy-credit — HY OAS (FRED) + HYG dual-axis chart; regime badge; 2Y/MAX toggle
│   │   │   └── YieldCurveChart.js         ← /macro/yield-curve — 2Y/10Y yields + 2-10 spread dual-axis chart; 2Y/MAX toggle
│   │   └── shared/
│   │       ├── Header.js                  ← global top bar (48px fixed); brand left, user profile right
│   │       ├── Sidebar.js                 ← collapsible left sidebar (48px→180px); lock toggle; position: fixed; generic collapsible parents (VOL, MACRO); MacroIcon SVG
│   │       └── SystemStatus.js            ← ADR-020 — header CONNECTION/DATA (admin) + STATUS (user) dots; reads /api/system/status
│   ├── data/
│   │   └── tickers.js                     ← SEED DATA ONLY — source of truth is the Postgres tickers table
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
│   │   ├── intraday_alert_log.py          ← Intraday monitor alert dedup log
│   │   ├── user.py                        ← Auth — users (+ phone/alert_email_enabled/alert_sms_enabled for Alert Creator)
│   │   ├── user_alert_subscription.py     ← Per-user, per-alert on/off (Phase 1 Alert Creator)
│   │   └── ai_summary.py                 ← AI-generated summaries cache (ticker+date keyed, Anthropic Haiku)
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
│   │       ├── u6v7w8x9y0z1_spx_impact_add_label_weights.py                      ← added snapshot_label + weights_json (intraday snapshot support)
│   │       ├── y0z1a2b3c4d5_add_alert_delivery_settings.py                       ← users.phone/alert_email_enabled/alert_sms_enabled + user_alert_subscriptions table (Phase 1 Alert Creator)
│   │       ├── z1a2b3c4d5e6_price_cache_unique_ticker.py                          ← dedup + enforce UNIQUE(ticker) on price_cache (ADR-027; fixes the ROBO duplicate-row bug)
│   │       ├── a2b3c4d5e6f7_signal_output_add_pillar_scores.py                    ← structural_score/volume_score/vix_score on signal_output + signal_history (+ quad_score on signal_history)
│   │       ├── b3c4d5e6f7g8_add_ai_summaries_table.py                             ← ai_summaries table (on-demand AI summary cache, ADR-030)
│   │       └── c4d5e6f7g8h9_tickers_add_profile_summary.py                        ← tickers.profile_summary (company profile text from Schwab/yfinance backfill)
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
│   │   ├── spx_constituents.py            ← SPX constituent impact — SSGA SPY XLSX weights + Schwab batch quotes ✅
│   │   ├── sms.py                         ← Telnyx SMS wrapper (globally disabled — SMS_DISABLED, pending 10DLC) ✅
│   │   ├── email_alert.py                 ← Gmail SMTP email wrapper (send_email / send_email_to) ✅
│   │   ├── fred.py                        ← FRED API client (HY OAS + future macro series) ✅
│   │   ├── alert_catalog.py               ← canonical alert list (keys/labels/tooltips) — Alert Creator ✅
│   │   ├── system_status.py               ← ADR-020 — computes connection/data/status axes + standing integrity scan ✅
│   │   └── ai_summary.py                 ← On-demand AI summary generation (Anthropic Haiku); called from security router, NOT scheduler (ADR-030)
│   └── routers/
│       ├── market_data.py
│       ├── signals.py                     ← Task 3.3/3.4/4.3 — Signal endpoints + history ✅
│       ├── scheduler.py                   ← Task 4.2 — Scheduler status endpoint ✅
│       ├── auth.py                        ← Task 5.3 — Schwab OAuth endpoints ✅
│       ├── tickers.py                     ← Task 4.6/4.7 — Ticker CRUD + yfinance lookup ✅
│       ├── spx_impact.py                  ← GET /api/spx-impact — returns eod + intraday snapshots ✅
│       ├── sector_performance.py          ← GET /api/sector-performance(?live=true) — 1D/MTD/QTD/YTD absolute + relative; live mode fetches fresh Schwab quotes for 12 sector tickers
│       ├── system.py                       ← ADR-020 — GET /api/system/status (admin: connection+data+status; user: status only)
│       ├── alerts.py                       ← GET/PUT /api/alerts/my-settings — per-user alert delivery settings (Phase 1 Alert Creator)
│       ├── security.py                    ← GET /api/security/{ticker}/detail — aggregated deep-dive; GET /{ticker}/summary — async on-demand AI summary; POST /{ticker}/summary — admin regen (ADR-030)
│       └── macro.py                       ← GET /api/macro/correlations — rolling Pearson correlations vs DXY + 52-wk rolling stats
├── .env                                   ← NOT in Git — backend secrets (Supabase, Schwab, JWT_SECRET, admin seed creds, email)
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

### Build sequences — Phases 3–5 (all ✅ Complete)
Per-task build detail lives in git history. Phase 4.4 (Fly.io deploy) was absorbed into Phase 5. Shipped: signal engine (`signal_engine.py` Hurst/DFA, `pivot_engine.py` ABC, `conviction_engine.py` LRR/HRR+conviction, dashboard wiring); EOD scheduler; signal-history snapshots; tickers table + dynamic backend; yfinance lookup; Supabase migration; Fly.io deploy; Schwab OAuth + quote polling + IV; OBV source swap.

### New Button — CALCULATE SIGNALS
- Added to dashboard header alongside REFRESH DATA
- Manual trigger only — never auto-calculates on page load
- Must be run AFTER REFRESH DATA (price history must be current)
- Calls: `GET /api/signals/calculate` — runs full pipeline (hurst → pivots → output → snapshot) in one call
- Signal engine reads from the `price_cache` DB table (Postgres) — NEVER calls yfinance directly

---

## Phase 4 — Task 4.2: EOD Scheduler ✅

### Scheduler Overview
- APScheduler `AsyncIOScheduler` inside FastAPI lifespan
- **Four registered jobs:**
  1. `schwab_data_job` — CronTrigger 4:00 PM ET NYSE trading days (prices → IV → signals)
  2. `intraday_monitor` — CronTrigger mon–fri 9:30 AM–3:45 PM ET at :00/:15/:30/:45
  3. `spx_impact_11am` / `spx_impact_1pm` — CronTrigger 11 AM / 1 PM ET Mon-Fri
  4. `schwab_token_age_alert` — CronTrigger 9:00 AM ET daily
- On startup: catch-up check — if past 4:00 PM ET, trading day, and no successful run today → runs immediately
- All dates use **ET timezone** — never UTC (see UTC vs ET fix above)
- **No proactive Schwab token refresh job** — schwab-py `client_from_access_functions` auto-refreshes the access token during API calls. A separate scheduler job causes `invalid_grant` races. See **ADR-015**.

### EOD Flow (4:00 PM ET, NYSE trading days) — single chained job
```
APScheduler (schwab_data_job)
    → schwab_fetch_all()                writes → price_cache (Schwab primary, Yahoo fallback)
    → fred_fetch_and_store()            writes → price_cache (FRED: DGS2→TWO, BAMLH0A0HYM2→HY_OAS) — non-fatal
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
    → Read weights_json from most recent EOD row in spx_impact_cache — no SPY fetch
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
    → /api/system/status        connection·data·integrity → header dots (ADR-020)
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

### Dashboard Header — System Status Indicators (ADR-020)
Dots next to the data timestamp, fed by `GET /api/system/status` (fetched once on load, no polling).
Logic in `services/system_status.py`; `components/shared/SystemStatus.js` only renders. Supersedes
the old single `● SCHED` + `● SCHWAB` dots.
- **CONNECTION** (admin only) — Schwab auth: green `fresh` / amber `aging` / red `expired`|`disconnected`. Click (amber/red) → re-auth.
- **DATA** (admin only) — source · freshness · EOD-run · integrity. Precedence: `integrity > run_failed > run_incomplete > run_missed > stale > yahoo`(amber)` > good`(green). Green is the all-day normal state with an adaptive tooltip (live prices → EOD complete → markets closed); there is **no "pending" amber**. Click (red) → REFRESH DATA.
- **STATUS** (users only) — plain-language roll-up of DATA: green `normal` / amber `degraded` / red `issue`.
- `scan_integrity` is a **standing** NaN/Inf check — green means *verified good*, not "didn't throw."

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
live price against it. Fires email/SMS alerts when triggers are met.

**Delivery is per-user (Alert Creator Phase 1).** Recipients are resolved each run from
`user_alert_subscriptions` joined to `users` channel prefs via `_load_alert_recipients(db)` →
`{alert_type: {emails, phones}}` (active users only). An alert fires only if it has subscribers
with an enabled channel — delivery is **opt-in, default off** (this replaced the hardcoded
`_RETRACEMENT_50_SEND` kill switch). `_dispatch()` fans out: email via `send_email_to` per
recipient; SMS via `send_sms_to` (still globally gated by `SMS_DISABLED`). The old single
env-recipient `send_email`/`send_sms` path is gone from the monitor.

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

**BREAK_OF_TRADE** — intraday price crosses through the break level (early warning before EOD confirmation):
```
Gate: structural_state must be UPTREND_VALID or DOWNTREND_VALID
Break level: pivot_c normally; pivot_b when d_extended=True
Uptrend:   fires when close < break_level
Downtrend: fires when close > break_level
```
- Fires once per ticker per day (pivot_c = NULL in dedup key, like PROXIMITY)
- Arrow matches break direction: `🔻` uptrend breaking down through support; `🔺` downtrend breaking up through resistance
- Message: ticker, viewpoint, price, "support"/"resistance" + break level (C or B extended), conviction
- Notes that EOD confirmation is required (intraday crossing ≠ confirmed break)
- Does NOT recalculate signals — purely observational (rule #75)

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
3. _load_alert_recipients(db)            — per-user subscriptions → {alert_type: {emails, phones}}; early-return if none
4. Load signal_pivots                    — trade tf, matching tickers (read-only)
5. Load price_cache                      — current close after step 1
6. For each ticker (only for alert types that have recipients):
   a. PROXIMITY check → _dispatch(email/SMS) + log if prox >= 0.85 and not already fired today
   b. RETRACEMENT_50 check → _dispatch + log if at/past 50% level and not already fired today
   c. BREAK_OF_TRADE check → _dispatch + log if price crosses break level and not already fired today
7. db.commit()
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

### SMS Service (`sms.py`) — Telnyx
- `send_sms(message)` → env `TELNYX_TO` recipients · `send_sms_to(numbers, message)` → explicit list (per-user delivery). Both → True/False, share `_post_message()` (Telnyx v2 REST POST).
- Reads from env: `TELNYX_API_KEY`, `TELNYX_FROM`, `TELNYX_TO`
- **`SMS_DISABLED = True`** (module-level, public) — both functions no-op + log "SMS disabled" until 10DLC clears. The Alert Settings UI reads this (`sms_globally_disabled`) to show the "pending carrier registration" note and disable the SMS checkbox.
- No-ops silently (warning log) if credentials missing — safe in dev.

### Why Volume Surge Was Excluded
The first 15-minute bar always has elevated volume relative to the daily average (opening spike) —
any volume pace comparison in the first 1–2 bars would fire false positives on nearly every ticker.
Dropped entirely. OBV direction already computed in EOD signals and displayed in the popup.

---

## Alert Settings — Per-User Alert Delivery (Phase 1 Alert Creator) ✅

Admin → **ALERTS** tab (`/admin/alerts`, `components/Admin/AlertSettings.js`). Lets a user choose
which intraday alerts they receive and on which channels. Operates on the **logged-in user's own
row** (`request.state.user`, set by the session middleware) — not admin-gated; any active user
manages their own alerts. Generalizes to a user-facing settings page later with no schema change.

**Layout (ThinkorSwim-style):**
- **DELIVERY** — account email (read-only) + "Send email" checkbox; single phone field + "Send SMS"
  checkbox (disabled with "SMS pending carrier registration" note while `SMS_DISABLED`).
- **ALERTS** — per-alert checkbox + description (Proximity to Entry, 50% Retracement) from the
  `alert_catalog`. One **Apply Settings** button.

**Description detail level (convention, not the exact strings):** each alert's `description` states
its firing **criteria** as `field operator threshold` conditions joined by boolean operators, plus
the dedup window — e.g. `viewpoint ∈ {Bullish, Bearish} AND prox ≥ 0.85. Once per day.` Thresholds
only, no formula expansions. Rationale: the criteria must be self-documenting so a user never has to
ask "what makes this fire?". Keep this granularity when adding alerts; the wording itself is owned by
`alert_catalog.py`, not CLAUDE.md.

**Phase 2 trajectory (not built):** the two catalog entries are hardcoded alerts. The real Alert
Creator is a user-facing builder where each alert holds **multiple criteria** (field · boolean
operator · value threshold) AND/OR-composed against platform metrics (viewpoint, prox, conviction,
vol-diff, etc.). The point is **flexibility**, not a fixed shape — the user decides the granularity:
"Proximity to Entry" could be one alert `(viewpoint = Bullish OR viewpoint = Bearish) AND prox ≥ 0.85`,
or split into separate per-viewpoint alerts; the builder supports either. Implies a conditions schema
(per-alert rows of field/operator/value + a group/connector for AND/OR) replacing the flat
`alert_catalog.py` keys.

**Data model:**
- `users` += `phone`, `alert_email_enabled`, `alert_sms_enabled` (the shared delivery destinations —
  one email + one phone apply to ALL of that user's alerts).
- `user_alert_subscriptions` (id, user_id FK, alert_type, enabled, updated_at; `UNIQUE(user_id, alert_type)`)
  — the per-alert on/off toggles.
- `services/alert_catalog.py` — `ALERT_CATALOG` (key/label/description) is the single source of truth
  for alert keys; keys MUST match what the intraday monitor fires (`PROXIMITY`, `RETRACEMENT_50`, `BREAK_OF_TRADE`).

**Endpoints (`routers/alerts.py`):**
- `GET /api/alerts/my-settings` — user's channels + per-alert state + catalog + `sms_globally_disabled`.
- `PUT /api/alerts/my-settings` — Apply button; validates phone (E.164-ish) and rejects "SMS on without
  phone" and unknown alert keys; upserts subscriptions.

**Endpoints (`routers/security.py`):**
- `GET /api/security/{ticker}/detail` — aggregated deep-dive: price_cache + signal_output (all 3 tfs) + signal_history (trade RR history) + cached ai_summary (most recent, no generation) + ticker profile. Single call for the Security Analysis page.
- `GET /api/security/{ticker}/summary` — async on-demand AI summary: returns cached today's summary or generates one; falls back to most recent cached on failure. Frontend fetches independently (non-blocking page load).
- `POST /api/security/{ticker}/summary` — admin-only: force-regenerate AI summary for a ticker.

**Guardrails:**
- Migration `y0z1a2b3c4d5` is idempotent (guarded `add_column` + `create_table`) — required because
  `Base.metadata.create_all()` at startup pre-creates the **table** but never the **users columns**.
  ⚠ The local container auto-reloads against **production** Supabase (rule #89): saving the new model
  triggered `create_all` to create `user_alert_subscriptions` in prod while the `users` columns were
  still missing — a half-migrated state that crashed local startup. Completing the additive migration
  (safe for the live Fly app) is the recovery. Lesson: when adding a model + columns, expect the
  reload to force the migration immediately.
- Deliver opt-in/default-off — a fresh user has no subscriptions, so nothing sends until they opt in.

---

## Phase 4 — Tasks 4.3 / 4.5 / 4.6 / 4.7 (Signal History · Cache Load · Tickers · Lookup) ✅

**Signal History (4.3):** `calculate_signals()` writes a `signal_history` snapshot of all `signal_output` rows on every run — idempotent (one per ticker/timeframe per ET day, checked in Python — no UNIQUE constraint), non-fatal on failure, `trigger` ∈ manual|scheduled|catchup. `GET /api/signals/history` (params ticker/timeframe/start_date/end_date/limit≤500, newest-first) — not yet wired to UI (future backtesting).
- **CALCULATE SIGNALS:** `GET /api/signals/calculate` runs the full pipeline + snapshot; its response holds only raw `compute_output` — the frontend must re-fetch `GET /api/signals/stored` as the source of truth (`h_trade_delta`, `vix_regime`, etc. are written separately in the signal loop).

**Page-load cache (4.5):** page load reads the warm DB cache (local Postgres / prod Supabase; instant, no external call). Auto-loading from the local DB is allowed; auto-fetching Yahoo/Schwab on load is prohibited. See rule #17.

**Tickers table (4.6):** the Postgres `tickers` table is the source of truth (replaces `tickers.js`, which is seed-only via `seed_tickers_if_empty`); `get_active_tickers(db)` is the only retrieval path — no hardcoded lists (rules #35–#36). Columns: id, ticker (UNIQUE), description, asset_class, sector, tier, parent_ticker, active, display_order, created_at, updated_at. API: `GET/POST /api/tickers`, `PUT/DELETE /api/tickers/{symbol}` (DELETE = soft-delete, never hard — rule #3), `GET /api/tickers/lookup/{symbol}` (registered before `/{symbol}`). Admin panel adds/edits/soft-deletes; ticker locked after creation; Asset Class is a fixed-vocabulary dropdown.

**yfinance lookup (4.7):** `GET /api/tickers/lookup/{symbol}` returns suggested description/asset_class/sector (never auto-saves; fills empty fields only; graceful on missing data). `ASSET_CLASS_OVERRIDES` (`tickers.py`) is checked first before yfinance inference — see rule #37.

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
- Token refresh: handled automatically by schwab-py `client_from_access_functions` during API calls — no separate scheduler job (see **ADR-015**)
- Fallback: all Schwab calls fall back to Yahoo Finance on token expiry or API error
- Data source tagged in `price_cache.data_source` — visible in dashboard header

### EOD Scheduler: Updated Flow (Phase 5+)
```
4:00 PM ET — single chained job (prices → IV → signals)
    schwab_fetch_all()       Schwab primary / Yahoo fallback — writes price_cache
    fred_fetch_and_store()   FRED economic series (DGS2→TWO, HY OAS) — writes price_cache (non-fatal)
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
                 → floor(0) → cap(105)

Structural (−5 to 55, base 0/25/50 ±5 adjustments):
  Both aligned (Bullish+Bullish or Bearish+Bearish) → 50
  One direction, one Neutral → 25
  Both Neutral OR opposing (Bullish+Bearish) → 0
  +5 NATH boost: Viewpoint=Bullish AND trade HRR > ATH
  −5 target-side warn: BB target can't reach structural reference (hrr_warn uptrend / lrr_warn downtrend)
  Quad gate uses structural_base (0/25/50) not adjusted score

Quad (−15 / −11 / 0 / +15 / +20):
  Gate: structural_score==0 AND Viewpoint=Neutral → 0 (both timeframes Neutral/opposing).
        structural_score==25 (one timeframe confirmed) → quad CONTRIBUTES (not gated).
  Aligned = (Bullish viewpoint + Best quad) OR (Bearish viewpoint + Worst quad)
  Aligned, prob≥0.45 → +20; Aligned, prob<0.45 → +15
  Neutral alignment → 0
  Misaligned (Bearish+Best or Bullish+Worst), prob≥0.45 → −15; prob<0.45 → −11

Volume (0 / 5 / 10 / 15):
  obv_direction: two-layer consensus — MA20 slope + 21-bar lookback must agree:
    Both Bullish → "Bullish"; Both Bearish → "Bearish"
    One directional + one Neutral → "Leaning Bullish" / "Leaning Bearish"
    Opposing → "Neutral"; Both Neutral → "Neutral"
  Mirrors Structure pillar: opposing OBV layers = 0 (not partial credit).
  Directional bias: Trade OR Trend (whichever is directional; opposing → no bias → 0)
  Scoring: obv_direction checked against structure's directional bias:
    Full alignment (Bullish/Bearish) matching structure → 10
    Leaning matching structure → 5
    Opposing structure or Neutral obv_direction → 0
    Acceleration bonus (+5, total 15) only on full alignment AND obv_slope_trend accelerating
  vol_signal no longer computed — obv_direction replaces both fields.

  OBV signals:
    obv_slope: sign of 3-bar ROC on OBV MA20: 'rising' | 'falling' | 'flat'
    obv_slope_trend: acceleration: slope_now vs slope_prev: 'increasing' | 'decreasing' | 'flat'

Vol (−10 to +15 — routed per vol index; flat +15 when no index applies):
  Direction-aware: elevated vol is a tailwind for shorts, headwind for longs.
  Routed via `_resolve_vol_index()`: VOL_INDEX_TICKER_MAP → Domestic Equities→VIX → None (flat +15).
  Per-index thresholds (investable_ceiling, danger_floor):
    VIX (19,30), VXN (22,32), RVX (21,31), GVZ (22,32), OVX (38,60), MOVE (85,120)

  Bullish / Neutral (three tiers — Edgy eliminated):
    close < ceiling AND HRR < ceiling → +15  (Investable+)
    close < ceiling                   → +10  (Investable)
    ceiling ≤ close < danger_floor    → +0   (Choppy)
    close ≥ danger_floor              → −10  (Danger)

  Bearish (asymmetric — +5 floor):
    close ≥ danger_floor              → +15  (Danger — vol confirms short thesis)
    ceiling ≤ close < danger_floor    → +10  (Choppy — elevated vol supports shorts)
    close < ceiling                   → +5   (floor — structure is primary filter)

  Vol HRR sourced from signal_output where ticker=vol_index, timeframe='trade'
  Missing vol index row → +15 (default full credit)

Range: 0–105 (v2.1 additive formula; NATH/warn baked into structural pillar)
  Base max:  Structural 55 (50+5 NATH) + Quad 20 + Volume 15 + VIX 15 = 105
  Floor: 0 (quad misalignment absorbed by floor)

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
**Conviction always calculates (v2.1)** — blank (None) only when score < 45. Neutral viewpoint displays score in grey; it does not suppress calculation. Conviction color follows viewpoint: green (Bullish), red (Bearish), grey (Neutral) — never score-based.

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
                structural_score,           ← Integer — pillar: 0/25/50 (trade tf only; NULL on trend/lt)
                volume_score,               ← Integer — pillar: 0/10/15 (trade tf only)
                vix_score,                  ← Integer — pillar: 0/5/10/15 (trade tf only)
                calculated_at
                UNIQUE(ticker, timeframe)

ai_summaries:   id (INTEGER PRIMARY KEY),
                ticker          (STRING NOT NULL, indexed)
                summary_date    (STRING(10) NOT NULL)   -- ET YYYY-MM-DD
                headline        (TEXT)                   -- one-line AI-generated headline
                bullets_json    (TEXT)                   -- JSON array of 2-5 bullet strings
                model           (STRING(50))             -- e.g. 'claude-haiku-4-5-20251001'
                created_at      (STRING)                 -- UTC timestamp
                UNIQUE(ticker, summary_date)

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
                -- GET /api/quad/current → {monthly, next_monthly, quarterly} for current + next ET month + current quarter
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
                UNIQUE(ticker)              ← ENFORCED via unique index ix_price_cache_ticker (migration z1a2b3c4d5e6, ADR-027). Prod lacked this until 2026-06-30 (model had only index=True; create_all never ALTERs an existing table) → a duplicate ROBO row poisoned reads. Model now declares unique=True.
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
GET /api/system/status            ← ADR-020 ✅  (connection+data for admin, status-only for users)
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
- Auto-loading from the DB cache (Postgres) on page load is allowed — it is a local DB read, not a Yahoo call

### Ticker Universe — Source of Truth
- **Postgres `tickers` table** is the source of truth as of Task 4.6
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
| OBV Direction | **Frequentist** | 21-bar lookback: current OBV vs OBV 21 bars ago (Bullish/Bearish/Neutral) |
| Quad Probability Distribution | **Bayesian** | Continuously updated belief across 4 quads |
| Forward Quarter Projections Q2-Q4 | **Bayesian** | Prior decay without new confirming evidence |
| Policy Signal Modifiers | **Bayesian** | Discrete evidence updates to forward projections |

---

## Dashboard — Current State
- React app running at localhost:3000 via Docker
- Close prices: real — auto-loaded from the DB cache on page load
- Sparklines: real — 60-day price history
- Rel IV: real — Schwab IV Percentile from options chain (`iv_source = 'schwab'`); falls back to Yahoo proxy (`iv_source = 'proxy'`) on token expiry or per-ticker error
- Volume: real — daily volume from Yahoo Finance
- Signal columns: **live** — populated from `/api/signals/stored` on page load; recalculated on CALCULATE SIGNALS
- REFRESH DATA: manual fetch only — forces fresh Yahoo Finance fetch outside scheduler window
- CALCULATE SIGNALS: manual trigger only, reads from price_cache
- Admin panel at localhost:3000/admin — JWT cookie auth + live DB admin-role check (rule #81)
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
| [Quad Now] | Current month US quad box + probability + Q FIT arrow (▲/—/▼) — fit computed against current month's quad |
| [Quad Next] | Next month US quad box + probability + Q FIT arrow — fit computed against next month's quad |
| [Quad Qtr] | Current quarter US quad box + probability + Q FIT arrow — fit computed against quarterly quad; International Equities show country quarterly quad |

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
- Key commits / change ledger: see `git log` — not duplicated here (the *why* behind decisions lives in DECISIONS.md).
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
- **Access:** JWT httpOnly cookie + live DB role check (`require_admin_user`, rule #81); login at `/login`. The old `REACT_APP_ADMIN_PASSWORD` build-arg gate was **removed** (replaced by JWT cookie auth) — never re-add it; a `REACT_APP_*` value bakes into the public JS bundle.
- **Tab nav:** Horizontal tabs below the header — [TICKERS] [QUAD SETUP] — add new tabs by extending `TABS` array in `AdminPanel.js`
- **Sub-routes:** `/admin/tickers` → `TickerList.js` · `/admin/quad` → `QuadSetup.js` · unknown paths redirect to tickers
- **App.js route:** `/admin/*` (wildcard required for nested routing)
- **Sidebar:** Hidden on all `/admin/*` paths via `showSidebar` check in `AppLayout`
- **After changing `.env`/`.env.dev`:** Must restart the backend container
- **Never hardcode secrets in source code** — use `.env` (local) / Fly secrets (prod); never a `REACT_APP_*` secret (client-bundle exposure)
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
25. **Conviction always calculates (v2.1)** — displayed when score ≥ 45 regardless of Viewpoint. Neutral viewpoint shows conviction in grey (`#8899aa`); Bullish shows green, Bearish shows red. Blank only when score < 45 (tooltip: "No score — conviction below 45%"). Alert still requires non-Neutral viewpoint AND conviction ≥ 80.
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
41. **OBV direction is a two-layer consensus** — `_obv_direction(slope_dir, lookback_dir)` combines both OBV layers (MA20 slope + 21-bar lookback) into a single directional assessment, mirroring Structure pillar logic: both aligned → Bullish/Bearish, one directional + one Neutral → Leaning Bullish/Leaning Bearish, opposing → Neutral, both Neutral → Neutral. `_obv_lookback_direction()` handles the raw 21-bar comparison (`_OBV_LOOKBACK = 21`). **Volume scoring mirrors Structure:** `obv_direction` checked against structure's directional bias (Trade OR Trend — whichever is directional; opposing = no bias = 0). Full alignment matching structure = 10 (+5 acceleration = 15). Leaning matching structure = 5. Opposing or Neutral = 0. **`vol_signal` is no longer computed** — `obv_direction` (Bullish/Bearish/Leaning/Neutral) replaces both `vol_signal` and the old single-layer `obv_direction`. DB column `vol_signal` retained (no migration) but written as None.
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
61. **Vol score tiers (v2.3 — asset-specific vol indices, direction-aware, Edgy eliminated)** — Each ticker routes to its relevant volatility index via `_resolve_vol_index(ticker, asset_class)`: ticker-level map (`VOL_INDEX_TICKER_MAP`) → Domestic Equities default to VIX → None (flat +15). **Vol indices:** VIX (broad SPX equities), VXN (Nasdaq-heavy: QQQ/NDX/XLK/SMH/SOXX/CIBR/QTUM/GRID/AAPL/MSFT/NVDA/AVGO/GOOGL/META/NFLX), RVX (Russell: IWM/RUT), GVZ (Gold: GLD/SGOL//GC), OVX (Oil: USO//CL/XOP/OIH), MOVE (Fixed Income: TLT//ZN/SHY/IEF/VGIT/LQD/MBB/PFF/TIP). **Per-index thresholds** `(investable_ceiling, danger_floor)` in `VOL_INDEX_THRESHOLDS`: VIX (19,30), VXN (22,32), RVX (21,31), GVZ (22,32), OVX (38,60), MOVE (85,120). **Three tiers (Edgy eliminated → folded into Choppy):** Bullish/Neutral: Investable+ (close < ceiling AND HRR < ceiling) +15 · Investable (close < ceiling) +10 · Choppy (ceiling–danger) +0 · Danger (≥ danger) −10. Bearish (asymmetric, +5 floor): Danger +15 · Choppy +10 · Tradable +5 (label is "Tradable" not "Investable" — low vol doesn't help a short thesis; frontend also maps stale "Investable"/"Calm" → "Tradable" when structural lean is Bearish). **Vol scorer uses `_struct_bias` (structural lean), not `viewpoint`** — same variable as Volume and Quad pillars; a Neutral viewpoint with a Bearish lean gets the asymmetric Bearish scoring (+5 Tradable floor), not the Bullish/Neutral scoring (+10/+15). `get_vol_score(vol_close, vol_hrr, thresholds, viewpoint)` is the generic scorer (the `viewpoint` parameter receives `_struct_bias` from the caller); `get_vix_score()` wraps it with index routing. Security detail endpoint resolves vol index per ticker and returns `vol_index` field. Popup label: "Vol Regime" (not "VIX Regime"). **NATH Boost (+5 structural):** Viewpoint=Bullish AND trade HRR > `price_cache.ath` → structural_score += 5 (was ×1.05 on final score pre-v2.1). **Target-side warn (−5 structural):** hrr_warn (Bullish) or lrr_warn (Bearish) → structural_score −= 5 (was ×0.92 on final score pre-v2.1). Both baked into the structural pillar.
66. **Quad score uses structural lean (`_struct_bias`), not viewpoint (v2.0)** — `alignment = get_quad_alignment(asset_class, sector, current_quad)` → +1.0/0.0/-1.0. `_struct_bias` = directional lean from Trade or Trend (whichever is non-Neutral; opposing = Neutral) — same variable the Volume pillar uses. Gate: `_struct_bias == "Neutral"` AND `structural_base == 0` (raw 0/25/50 alignment, before ±5 adjustments) → quad_score=0. **Aligned = (Bullish lean + Best) OR (Bearish lean + Worst)** — the structural lean must agree with the quad tailwind direction. A Neutral viewpoint with a Leaning Bearish structure (structural_score=25) in a Worst quad scores **Aligned** (+20), not Misaligned. Previously used `viewpoint` which required full Bullish/Bearish alignment — Neutral viewpoints always scored Misaligned even when the lean matched. Aligned: +20 (prob≥0.45) or +15 (prob<0.45). Misaligned: -15 (prob≥0.45) or -11 (prob<0.45). Neutral alignment: 0. `quad_score` (Integer) is stored in `signal_output` and shown in popup (green/red/grey). `quad_mult` still written to `signal_output` for debug only — not in v2.0 formula and not shown in popup. Index sectors always return 0. **Quad alignment LABEL is separate from quad SCORE (ADR-034):** when the structural gate fires (score=0, no direction), `quad_align_label` shows the raw macro stance — "Best" (+1.0), "Worst" (−1.0), or "Neutral" (0.0) — so users see whether the macro environment favors/opposes the security even without directional structure. When structure exists, label shows "Aligned"/"Misaligned" as before. Popup: "Best ▲" green / "Worst ▼" red. Never re-merge label and score.
67. **Quad settings use upsert semantics** — POST to `/api/quad/settings` checks `UNIQUE(country, forecast_month, quad_type)`: updates existing row if found, inserts new row otherwise. `forecast_month` replaces the old `effective_date` key. Conviction reads the US monthly row whose `forecast_month` = conviction month (see rule #102). Admin Panel → QUAD SETUP manages this.
102. **Conviction engine early quad shift on the 24th** — `run_output()` in `signals.py` shifts to the **next month's** US monthly quad on or after the 24th of the current ET month (`now_et.day >= 24`). Markets are forward-looking; the next month's quad is already influencing security moves by that point. The **visual** quad columns (Quad Now / Quad Next / Quad Qtr) are unaffected — they always show the calendar month. Only the conviction score calculation shifts early. Uses `_next_calendar_month()` helper. If the next month's quad row is not yet configured in QUAD SETUP, conviction falls back to no quad (`quad_current=None`, `quad_prob=0.0`).
68. **Quad alignment uses sector-first priority** — `get_quad_alignment()` checks `sector` key first, then `asset_class`. This correctly handles USD (sector="USD"), GLD/SGOL//GC (sector="Gold"), JPY/FXY (sector="Yen"), FXB (sector="British Pound"), FXE (sector="Euro"), IBIT (sector="Cryptocurrency"). Foreign Exchange asset_class is the fallback for any unlisted FX ticker.
118. **Equities asset class quad mapping: Best Q1/Q2, Neutral Q3, Worst Q4** — `Domestic Equities` and `International Equities` are in `QUAD_ALIGNMENT` best asset_class for Q1 (Goldilocks) and Q2 (Reflation), worst for Q4 (Deflation), and **NOT listed** in Q3 (Stagflation) — making them Neutral at the asset_class level. Hedgeye backtest data shows SPY EV is +6.6% (Q1), +4.6% (Q2), −0.1% (Q3), −0.8% (Q4); Q3 is essentially flat because sector winners (Utilities, Energy, Tech, Health Care) and losers (Financials, Comm Services, Consumer Disc, Industrials) cancel out for broad indices. Individual equity sectors still score Best/Worst in Q3 via sector-level matching — this only affects tickers that fall through to asset_class (e.g. SPY/QQQ/IWM with sector="Broad Market"). Do not re-add equities to Q3 worst asset_class.
71. **International Equities route to country quarterly quads** — `signals.py` `run_output()` routes tickers with `asset_class = "International Equities"` to their country's current-quarter quad (e.g. EWJ sector="Japan" → "JP" → `YYYY-QN` quarterly row) instead of the US monthly quad. `_SECTOR_TO_CODE` dict in `signals.py` maps sector labels to ISO country codes. If no country quarterly quad is set, falls back to no quad (multiplier = 1.00). Dashboard columns for international rows show the country quarterly quad (no probability — quarterly rows always store 1.0); US monthly quad + probability shown for all other rows. Quarterly data fetched in `App.js` from `/api/quad/settings?country=ALL&type=quarterly` on page load, mapped via `CODE_TO_SECTOR` to build `countryQuads` state `{sector: {cur, next}}`.
72. **Quad UI colors (dashboard + QuadSetup)** — Q1: `#007a55` (dark green, white text) · Q2: `#00e5a0` (system green) · Q3: `#f0b429` (system amber) · Q4: `#ff4d6d` (system red). Box style: `background: color + "55"` (33% opacity) + `border: 1px solid color` + white text — matches QuadBtn active style. Do not introduce new quad color values.
73. **Conviction tooltip — 2-line format (v2.1)** — Line 1: formula `Structural (−5 to 55) + Quad (±20) + Volume (15) + Vol (−10 to +15) → floor(0) → cap 105`. Line 2: display rules `Show ≥ 45 · Green (Bullish) · Red (Bearish) · Grey (Neutral) · ⚡ ≥ 80`. Security page: when conviction is blank, tooltip reads "No score — conviction below 45%". Conviction color always follows viewpoint (green/red/grey), never score-based. Do not revert to proximity/multiplier descriptions.
69. **Slope boost changed to × 1.20 in v1.9** (was × 1.17 in v1.8). Do not revert to 1.17.
62. **H_eff (asymmetric Hurst) asset class scope (Phase 6)** — asymmetric H (H_trend_up / H_trend_down) applies to Commodities and Foreign Exchange ONLY. All other asset classes use symmetric H_trend. `/ZN` (10-Year Treasury futures) is EXCLUDED from asymmetric H despite being a futures ticker — its price series is driven by rate policy, not directional commodity flows; always uses symmetric H_trend.
63. **ΔH (delta-H) threshold for display color** — `h_trade_delta >= 0` → green (momentum improving or stable); `h_trade_delta < -0.05` → red (meaningful deterioration); between -0.05 and 0 → neutral grey. Stored in `signal_output.h_trade_delta`; display only — NOT in conviction formula.
64. **VoV rank computed from existing VIX price history** — no separate accumulation period needed. `compute_vov_with_rank()` computes 30-day rolling std of VIX log returns (VoV series) from 5-year history in `price_cache`, then ranks current VoV within its own 252-day trailing window. Returns `(vov_30d, vov_rank)` tuple. Stored in `price_cache.vov_30d` and `price_cache.vov_rank`. Updated on every REFRESH DATA when VIX history is fetched. Not currently displayed — retained for future VVIX vs realized VoV spread signal.
**VVIX price rank** — computed in `refresh_data()` in `market_data.py` after VoV. Ranks VVIX close within its own 252-day price history (0–100). Stored in `price_cache.rel_iv` for the VVIX row (VVIX has no options chain so rel_iv is otherwise unused). `iv_source` set to `"price_rank"`. Displayed in VIX gauge header as `VVIX 85.3 · 42nd pct`. Popup shows `IV Rank — price_rank`. Do not replace with the Yahoo realized-vol proxy — price rank answers the correct question (is VVIX elevated vs history?).
65. **Proactive spec review** — when reading a spec or reviewing methodology, flag any inconsistencies with existing code or other parts of the spec before implementing. Do not implement silently when something looks wrong or contradictory.
70. **UI text contrast + table typography (LOCKED)** — Never use `#445566` or darker for readable text. Three color levels: (1) `#e8f4ff` for page titles; (2) `#c8d8e8` (LABEL) for data values, row labels, bold footer labels; (3) `#8899aa` (TEXT) for column headers, sub-headers, subtitles, timestamps, footer text, inactive controls. Reserve `#445566` and darker for decorative borders only. **Stats table typography (Vol/Macro pages):** Page title: 18/700/`#e8f4ff`/0.06em/left · Subtitle: 11/400/`#8899aa`/0.05em/left · Timestamp: 10/400/`#8899aa`/right · Column headers: 9/700/`#8899aa`/0.1em/center · Sub-headers: 8/700/`#8899aa`/0.1em/center · Data values: 11/400/`#c8d8e8`/center · Row labels (col 1): 11/600/`#c8d8e8`/left · Footer text: 10/400/`#8899aa`/0.03em/left · Footer bold label: 10/600/`#c8d8e8`/0.03em/left. Format: size/weight/color/letterSpacing/align. Multi-column headers (DoD, WoW, MoM) use `colSpan={2}` — never two separate `<th>` cells. Do not deviate without explicit instruction.
74. **Intraday monitor uses `schwab_fetch_intraday_quotes` — never `schwab_fetch_all`** — `schwab_fetch_all(force=False)` has an idempotency check that skips when all Schwab tickers have `cache_date == today`; the scheduled EOD job passes `force=True` to bypass it (see rule #120 / **ADR-033**). `schwab_fetch_intraday_quotes()` always calls `get_quotes()`, uses `lastPrice` only, and does not update `cache_date` or `history_json`. Swapping them silently breaks the 15-minute price refresh.
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
89. **Local Docker uses an isolated DEV Postgres container — NOT prod (ADR-025)** — `.env.dev` (gitignored) sets `DATABASE_URL` to the `db` service (postgres:17) and blanks the prod `SUPABASE_*` strings, so the local backend reads/writes the dev DB only and cannot reach prod even if `DATABASE_URL` is dropped. Confirm via the admin header **DB badge** (DEV grey / PROD **green** on the production server / PROD **red** when a non-production process is on Supabase — see ADR-025 badge note) and the startup log line (`DB CONNECTION → host=… [DEV|PROD-SUPABASE]`). Prod Supabase is reached only by Fly — or locally if `.env.dev` is absent (env_file `required:false` fallback to `.env`); if the badge ever reads PROD **red** locally, `.env.dev` is missing. **History:** before ADR-025 local hit prod directly (the 2026-04-25 `env_file` accident) — that is what this fixes. Schwab in dev runs on Yahoo fallback (empty `schwab_tokens`); never copy the prod token into dev (refresh-token rotation race, ADR-015/018).
90. **Idempotent migrations for new tables** — `Base.metadata.create_all()` runs at startup and creates any new tables from SQLAlchemy models, BEFORE alembic gets a chance to run on a fresh deploy. New `op.create_table` migrations must guard with `if "table_name" not in inspector.get_table_names(): ...` (see `add_users_table.py` / `add_password_reset_tokens_table.py` for the pattern). Otherwise `alembic upgrade head` after deploy fails with "table already exists".
91. **`REFRESH DATA` and `CALCULATE SIGNALS` are admin-only** — both UI buttons (gated by `isAdmin` in App.js) and backend endpoints (`/api/market-data/batch`, `/api/signals/calculate` use `require_admin_user`). Viewers see cached data via `/api/market-data/cached` and `/api/signals/stored`; they cannot trigger expensive recalcs.
92. **Never add a proactive Schwab token refresh scheduler job** — schwab-py `client_from_access_functions` handles all access-token refreshes internally during API calls. A separate APScheduler job that calls the Schwab token endpoint concurrently races with schwab-py's internal refresh: both use the same refresh token; Schwab rotates it on first use, so the second caller gets `invalid_grant` and kills the session. See **ADR-015**.
93. **`get_status()` clock source is `created_at` — NOT `updated_at`, NOT `expires_at` (ADR-026)** — `created_at` is stamped only on a full OAuth exchange (`is_full_oauth=True`) and never by access-token refreshes, so it tracks the real age of the Schwab refresh token (hard 7-day life from login, not extended by refresh). `state='aging'` at day 5, `state='expired'` at day 7. **Never revert to `updated_at`**: `_store_tokens` re-stamps it on every successful access-token refresh (~every 30 min during market hours), so it never ages while healthy → false-green, the day-5/6 warning emails can never fire before the token dies, and the connection silently dies at the 7-day wall (the recurring weekly-death symptom). **Never use `expires_at`** (30-min access token → false-red overnight, the original ADR-016 bug). See **ADR-016** (the superseded `updated_at` clock and why `expires_at` was wrong) + **ADR-026** (why `created_at` is the only correct clock).
94. **schwab-py/authlib callbacks must accept `*args, **kwargs`; keep `authlib` pinned** — `get_schwab_client._write(token_dict, *args, **kwargs)` (and `_read`) must accept forwarded args. authlib (transitive dep of schwab-py) passes `refresh_token=` to the token-write callback on every access-token refresh; a fixed `_write(token_dict)` signature raises TypeError on each refresh → the token never persists → `updated_at` freezes → total Schwab outage (EOD + 15-min intraday) → silent Yahoo fallback. `authlib` is **pinned** in `requirements.txt` (`==1.6.12`) — an unpinned bump caused the 2026-06-18 outage; never unpin it or any schwab-py transitive without re-testing a token refresh. **The green SCHWAB dot only proves the refresh token is < 7 days old (rule #93), NOT that refresh works** — verify Schwab health via `price_cache.data_source` counts or a live quote, never the dot alone. See **ADR-018**.
95. **Lightweight Yahoo fetches must drop NaN closes** — `fetch_ticker_close` (and any "last bar" Yahoo fetch) must `hist = hist[hist["Close"].notna()]` before `.iloc[-1]`, mirroring `fetch_ticker_data`'s `dropna()`; return None if no valid close remains. Yahoo serves a NaN close for the current day on **weekday holidays / data glitches** (e.g. ^GSPC on Juneteenth); unguarded, that NaN lands in `price_cache.close/ma200/std20`, serializes as an invalid JSON token, and breaks the dashboard read → "LIVE DATA UNAVAILABLE / DISPLAYING MOCK DATA". Normal weekends don't expose it (no Yahoo weekend row). Note: pandas `.mean()` skips NaN (ma20/50/100 survive) but `np.mean` does not (ma200/std20 go NaN) — that asymmetry is the diagnostic tell. See **ADR-019**.
96. **Header status = three axes via `/api/system/status` (`services/system_status.py`)** — **CONNECTION** (Schwab auth) + **DATA** (source·freshness·EOD-run·integrity) are **admin-only**; **STATUS** (plain roll-up) is **users-only**. `compute_data` precedence: `integrity > history_gaps > run_failed > run_incomplete > run_missed > stale > yahoo > good`; green is the all-day normal with an adaptive tooltip — never add a "pending" amber. `scan_integrity` is a **standing** NaN/Inf check on serialized fields — green means *verified-good*, never "didn't throw" (the 6/18 blind spot). CONNECTION and DATA remain **distinct axes** — DATA stays green/amber on good Yahoo data even when Schwab is down (a dead token still yields good data; don't make DATA red for a Schwab outage). **CONNECTION is a real health signal, not token-age alone (ADR-026):** `compute_connection` starts from `get_status()` (token age, rule #93) but then **cross-checks `_yahoo_degraded(db)`** — if the token age looks OK yet Schwab-eligible tickers fell back to Yahoo (`data_source='yahoo_fallback'`), CONNECTION goes RED `failing`, because a silently-broken refresh (premature revocation/authlib break) can't be caught by age (rule #94 / ADR-018). Exception: a token issued today (age 0) is trusted (the OAuth exchange just proved it) until the next fetch tags `data_source`. So GREEN `fresh` = token valid AND Schwab verified serving data; this is NOT "token AGE implies data health" — it's the reverse (actual Schwab call-success informs the auth dot). `scheduler.py` writes a `'started'` scheduler_log row (status is TEXT — no migration) flipped to success/failure at the end → a stuck `'started'` = DATA `run_incomplete`. Frontend `SystemStatus.js` is dumb (backend computes color/tooltip/clickable). See **ADR-020**.
97. **`signal.suttonmc.com` is Cloudflare-Proxied → Fly cert renews via DNS-01, never HTTP-01** — two DNS-only records on the suttonmc.com zone keep renewal automatic: `CNAME _acme-challenge.signal → signal.suttonmc.com.13y0odn.flydns.net` + `TXT _fly-ownership.signal → app-13y0odn` (values from `fly certs setup signal.suttonmc.com --app signal-matrix-web`). **Never delete the `_acme-challenge` CNAME** — without it the cert expires behind the proxy and the site throws Cloudflare 525. **Keep `api.signal` grey-cloud (DNS only); never proxy it** — proxying needs its own renewal records AND would 524 the long REFRESH DATA / CALCULATE SIGNALS fetches (CF free-plan 100s origin timeout). The "Exposed RDP" Critical insights on `api.signal` are **false positives** (Fly anycast edge accepts handshakes on arbitrary ports; `fly.api.toml` exposes only `[http_service]` 8000→443). No Cloudflare API token on the dev machine — DNS edits are dashboard-only. See **ADR-021**.
98. **Schwab price history: `periodType=day` only allows `frequencyType=minute`** — never pair `day` + `daily` (Schwab returns HTTP 400 `"valid values for frequencyType are: minute"`). The macro-vol index `append` path (`_schwab_fetch_index_histories`) must use `MONTH`/`ONE_MONTH` + daily and route through the merge `_upsert` (not single-bar `_append_bar`) so multi-day gaps fill and ma50/ma100 compute from the merged series. The MONTH endpoint is **not** mis-scaled (verified incl. MOVE 2026-06-23 — the old ADR-010 "1-month mis-scales MOVE" claim is wrong). RVX has no Yahoo fallback (`^RVX` delisted) — a >7-day token outage freezes it (accepted per ADR-010). See **ADR-022**.
99. **Never append a `today`-stamped history bar on a non-trading day** — the append path dates bars with wall-clock `today`; on a manual REFRESH during a holiday/weekend the quote APIs return the prior close, which would otherwise be stored as a phantom bar (the 2026-06-19 Juneteenth + 2026-05-23 Saturday phantoms across 93 tickers → 1-day notches on the union-date macro-vol chart). `_history_fetch_mode` downgrades `append`→`skip` when `today` is not an NYSE session (covers Schwab + Yahoo paths). FX (USD/JPY) + futures (/CL,/ZN,/GC) are exempt via `_NON_NYSE_CALENDAR` (non-NYSE calendars). The scheduler's holiday guard is NOT sufficient — manual REFRESH bypasses it. `short`/`bootstrap` merges stay unguarded (real source dates self-heal stored phantoms). Cleanup of existing phantoms = remove non-NYSE-session dates from history + recompute ma/std20/ATH/spark; idempotent. See **ADR-023**.
100. **Trade-RR vol series falls back to HV-from-closes for newly-activated tickers (ADR-024)** — `get_trade_rr_vol_series` resolves in order: stored IV30 (≥256 rows) → stored HV30 (≥256 rows) → **HV30 reconstructed on the fly from `price_cache.history_json`** (`_hv30_series_from_closes`; same formula as `accumulate_hv_only`: `std(log-rets[-21:], ddof=0)·√252`; source tag `hv_computed`) → None. Needed because the 252-day rank window requires ≥256 vol rows, but `vol_history` is forward-accumulated only (no vol bootstrap), so a freshly-activated ticker (e.g. UUP, and the macro-vol indices VXN/RVX/GVZ/OVX/MOVE) would otherwise show a blank trade LRR/HRR for ~1 year. Never raise the ≥256 gate or remove the fallback (it re-blanks new tickers). IV30 is **not** reconstructable (Schwab serves no historical option chains) — never try to backfill IV; HV-only fallback is correct. Self-heals to stored `iv`/`hv` as rows accumulate; existing long-history tickers (VIX `hv`, GLD `iv`) are unchanged. A DB-only recompute is futile until the code deploys — live deployed code overwrites `signal_output` on the next REFRESH/CALCULATE/EOD run. See **ADR-024**.
101. **`price_cache.ticker` is UNIQUE — enforced in the DB, not just the model (ADR-027)** — the unique index `ix_price_cache_ticker` (migration `z1a2b3c4d5e6`) is the real guard; the model declares `Column(String, index=True, unique=True)` so fresh DBs get it via `create_all`. **Why both are required:** `create_all` only ever CREATES missing tables — it never ALTERs an existing one to add a constraint, so adding `unique=True` to the model alone does nothing to a live DB (prod ran ~unconstrained until 2026-06-30, which let a duplicate ROBO row — a stale `yahoo_fallback`/`1970-01-01` orphan — persist; `_upsert`'s `.filter(ticker==…).first()` updated one row while the read path served both, non-deterministically showing stale data). Any schema-vs-prod "this column is UNIQUE" claim must be **verified against the live DB** (`inspect(engine).get_unique_constraints/get_indexes`), never assumed from the model or CLAUDE.md. When a ticker shows frozen/`1970-01-01`/empty-history despite a live quote, **suspect a duplicate `price_cache` row first** (`GROUP BY ticker HAVING count()>1`), not the data source. See **ADR-027**.
103. **AI summaries are async and on-demand — never in the scheduler (ADR-030)** — the detail endpoint (`GET /api/security/{ticker}/detail`) returns only the most recent cached summary (no generation). A separate `GET /api/security/{ticker}/summary` endpoint generates on-demand if no cached summary exists for today, falling back to the most recent cached summary on failure. The frontend fetches this independently after page load (non-blocking — page renders immediately, summary shows "Analyzing..." until ready). `generate_summary` strips markdown code fences from Haiku responses before JSON parsing. Cached per day in `ai_summaries` table (`UNIQUE(ticker, summary_date)`). Model: `claude-haiku-4-5-20251001`. Do not wire into `schwab_data_job` or any scheduler job — generates for all ~51 tickers daily regardless of views (wasteful API spend).
104. **Ticker cell click → `/security/:ticker`; row click → popup** — `<Link>` on ticker cell uses `onClick={e => e.stopPropagation()}` to prevent the row click handler from firing. Hover-only blue (`#2196F3` + underline on hover, original color on leave). Do not remove `stopPropagation` — it separates the two navigation paths.
105. **Profile backfill: Schwab Instruments primary, yfinance fallback** — `POST /api/tickers/backfill-profiles` (admin-only). Schwab `get_instruments(symbols, Projection.FUNDAMENTAL)` batch for equity/ETF descriptions; yfinance `longBusinessSummary` per-ticker with 15s thread timeout for indices/futures/FX (`SCHWAB_UNSUPPORTED_PROFILES`). Stored in `tickers.profile_summary`. Backfill is manual, not scheduled. **Auto-populate on creation:** `_auto_populate_profile()` in `tickers.py` runs after `create_ticker` — Schwab Instruments primary, yfinance fallback. No manual backfill needed for new tickers.
106. **VRP regime labels (Security Analysis page)** — computed from IV Rank + VRP (percentage points). Priority order: **Falling Knife** (red, IV Rank > 80, VRP < −15) · **Gamma Trap** (amber, IV Rank > 50, VRP < −10) · **Yield Harvest** (green, IV Rank > 50, VRP > 5) · **Upside Panic** (amber, IV Rank < 30, VRP > 5) · **Quiet Accumulation** (light green `#66eebb`, IV Rank < 20, −2 < VRP < 5) · **Neutral** (grey, everything else). Displayed inline next to VRP percentage in the vol metrics row. Source: ToS VRP Matrix script.
107. **Sector Performance LIVE mode** — `GET /api/sector-performance?live=true` fetches fresh Schwab quotes for the 12 sector tickers + SPX only (not all ~107 tickers), computes perf from live prices, returns with `refreshed_at` timestamp. Frontend: EOD/LIVE toggle tabs with `sessionStorage` persistence (navigating away and back restores LIVE tab if previously fetched). Re-clicking LIVE always re-fetches. LIVE button disabled after 4 PM ET weekdays and on weekends (EOD data is current). No DB table — browser-only caching.
108. **Security detail endpoint NaN guard (`_safe()`)** — `security.py` wraps all float fields with `_safe(v)` (NaN/Inf → None) before returning. FastAPI's `JSONResponse` uses `allow_nan=False`, so any NaN in the response dict crashes serialization AFTER the CORS middleware passes — the error response lacks CORS headers → browser sees "Failed to fetch" (not a JSON error). Index tickers (SPX, NDX, RUT) had NaN in `signal_history.lrr/hrr` rows which propagated into `rr_history`. The `is not None` check does not catch NaN (`float('nan') is not None` → True). Always use `_safe()` or `math.isnan()` when guarding against NaN in API responses.
109. **Security Analysis pillar boxes show raw scores** — STRUCTURE: 0/25/50, VOLUME: 0/5/10/15, VOLATILITY: 0/5/10/15, QUAD: -15 to +20. Labels derived from raw values: STRUCTURE (Bullish/Bearish/Leaning Bullish/Leaning Bearish/Neutral — viewpoint-aware, see rule 111), VOLUME (`obv_direction`: Bullish/Bearish/Leaning Bullish/Leaning Bearish/Neutral — two-layer consensus), QUAD (Aligned/Misaligned/Neutral/Best/Worst — Best/Worst shown when structural gate fires, see rule #66 + ADR-034). **VOLATILITY label uses `vix_regime` from backend** (not derived from score); "N/A" regime shows "Full Credit" (+15 flat, no applicable vol index). VOLATILITY detail text shows the resolved vol index name (VIX/VXN/RVX/GVZ/OVX/MOVE). Colors: STRUCTURE green≥50/amber≥25/grey, VOLUME green≥10/amber≥5/grey, VOLATILITY green≥10/grey (no amber — Edgy eliminated), QUAD green>0/red<0/grey **+ green for Best or red for Worst when score=0 (raw macro stance, not directional alignment)**.
110. **Security Analysis chart price bubbles** — `PriceBubble` SVG component renders colored bubbles at the right end of each `ReferenceLine`: LRR (green `#00e5a0`), HRR (red `#ff4d6d`), current price (white `#ffffff` with dark text). Smart overlap avoidance: when price is within 18px of HRR or LRR, the price bubble offsets vertically. Render order: LRR → HRR → Price (price on top). Current price `ReferenceLine` uses `stroke="transparent"` (no visible line, bubble only). Chart grid stroke `#3a4f65` (brighter than default `#1a2a3a` for readability). Chart margins `{ top: 20, right: 55, bottom: 10, left: 10 }` — top/bottom provide bubble room outside the grid (no phantom grid lines); right accommodates bubble width. Y-axis `domain: ["auto", "auto"]` — no padding (avoids odd tick values). Legend labels: "LRR (Buy/Add)" and "HRR (Sell/Reduce)".
111. **STRUCTURE pillar label is viewpoint-aware** — `pillarLabel("STRUCTURE", raw, data)` returns the actual viewpoint for score ≥ 50 (`data.viewpoint` — "Bullish"/"Bearish"), "Leaning {direction}" for score = 25 (uses whichever of Trade/Trend direction is non-Neutral), and "Neutral" for score = 0. This is a frontend-only translation — backend `structural_score` values (0/25/50) are unchanged; the AI summary prompt reads raw backend fields directly (`structural_score`, `viewpoint`, `trade_direction`) and never sees these labels.
112. **VRP regime is a separate labeled field with hover tooltips** — the Security Analysis vol metrics row shows VRP as a percentage only; the regime label (Falling Knife / Gamma Trap / Yield Harvest / Upside Panic / Quiet Accumulation / Neutral) appears in its own "VOLATILITY REGIME" field with independent header and color. Each regime label has a `title` tooltip explaining the condition and how to apply it (e.g. Yield Harvest → sell premium; Falling Knife → avoid selling premium). Vol metrics headers: "IV30" and "HV30" (not "IMPLIED VOL 30D" / "HISTORICAL VOL (HV30)"). Regime computation unchanged (rule 106).
113. **Security Analysis tab content scrolls at maxHeight 115px** — tab content container uses `maxHeight: 115` + `overflowY: auto` so the block height stays fixed across tabs (Risk Range, AI Analysis, Profile). Content taller than 115px scrolls within the tab; shorter content fits without scrollbar. The outer block never stretches.
114. **Security Analysis timestamp formatting** — `updated_at` (raw UTC string from backend) is converted to readable ET via `toLocaleString("en-US", { timeZone: "America/New_York" })` + " ET" suffix. Fallback to raw string on parse failure.
115. **Security Analysis layout spacing** — VIEWPOINT/CONVICTION labels use `marginBottom: 8` for label-to-value gap. Conviction value is centered under its label (`textAlign: "center"`). Vol metrics row labels use `marginBottom: 6`; row has `marginBottom: 24` for breathing room before tabs.
117. **Security Analysis pillar detail text — two-line format** — VOLATILITY: description uses vol index name + level + positioning guidance. QUAD: two-line format — line 1 describes how the macro environment treats the security's sector/style ("X historically perform well/poorly in the current macro environment"), line 2 explains alignment with price structure ("The macro environment supports current price structure" or "Currently working against {direction} price structure"). **"perform well" vs "perform poorly" is direction-aware:** "Best" or (Aligned+Bullish) or (Misaligned+Bearish) → "perform well" (quad is favorable for the sector); "Worst" or (Aligned+Bearish) or (Misaligned+Bullish) → "perform poorly" (quad is unfavorable). Previously "Aligned" was always treated as "Best" — wrong for Bearish tickers where Aligned means Worst-for-sector (good for the short thesis). Uses `structDir` (Trade or Trend lean) not `viewpoint` for determining quad direction, consistent with rule #66. Generic sectors (Index, Broad Market, Equities) fall through to `asset_class` for the label. Neutral quad shows single line: "No strong historical edge for X in the current macro environment."
118. **Security Analysis ticker search validates before navigating** — `handleNav` in `SecurityAnalysis.js` checks `tickerList.some(t => t.ticker === s)` before calling `navigate()`. If the user types a non-existent ticker and presses Enter, nothing happens (no broken page navigation). The dropdown filter already shows "no results" — this guards the form submit path.
119. **Volume pillar text says "volume signals" not "OBV layers"** — pillar detail text in `SecurityAnalysis.js` uses "both volume signals aligned" (full direction) and "one volume signal directional" (leaning direction). The OBV implementation detail is hidden from the user-facing label.
120. **Scheduled EOD job bypasses `schwab_fetch_all` idempotency check (ADR-033)** — `schwab_fetch_all(db, force=True)` from the scheduler; manual REFRESH DATA uses `force=False` (default). The idempotency check (`cache_date == today` for all Schwab tickers) prevents redundant API calls on double-clicks, but previously also blocked the 4 PM scheduled run when REFRESH DATA was clicked earlier that day — the actual EOD close was never captured, producing stale `price_cache.close` (from the intraday monitor) and stale `history_json` (from the earlier manual fetch). See **ADR-033**.
121. **`compute_output` uses `history_json[-1]` for price, not `price_cache.close` (ADR-033)** — the pivot engine computes `structural_state` from `history_json[-1]`; the conviction engine must use the same price for `_compute_direction` so direction and state always agree. `price_cache.close` can diverge when the intraday monitor updates it between REFRESH DATA runs. Fallback to `cache_row.close` only when `history_json` is empty.
122. **Break-of-trade alert arrows match break direction** — `🔻` for bullish uptrend breaking down through support; `🔺` for bearish downtrend breaking up through resistance. Message body uses "support C" / "resistance B" labels. See **ADR-033**.
123. **`_update_quote_only` must sync `history_json[-1]` to EOD close (ADR-035)** — when `_history_fetch_mode` returns `skip` (today's bar already in history), `_update_quote_only` now syncs `prices[-1]`, `vols[-1]`, H/L, and spark to the EOD quote. Previously only `price_cache.close` was updated, leaving `history_json[-1]` at the stale intraday value from an earlier append. The conviction engine reads `history_json[-1]` (rule #121), so OBV and direction computed with the wrong price. The 2026-08-13 incident: WOOD showed Bearish volume (score 0) because `history_json[-1]=72.36` (intraday) vs `close=72.98` (EOD up day) — OBV subtracted 140K volume instead of adding it; affected 67 tickers. Never remove the history sync from `_update_quote_only`.
124. **Security Analysis Risk Range — Trade Level column** — shows the break level: `pivot_c` normally, `pivot_b` when `d_extended=True`. Trend Level = `lrr` (MA100-based from signal_output). Tail Level = `lrr` (MA200-based). Trade previously showed "—" — now shows the active invalidation pivot, matching the popup's Trade B/C display.
116. **History gap detection and auto-backfill (`schwab_market_data.py`)** — `_history_fetch_mode` now detects missing NYSE trading days and escalates `skip`→`short` or `append`→`short` to trigger a full history fetch that fills gaps via `_upsert` merge. Two checks: (1) **Internal gap scan** (calendar_gap==0 / skip path): scans last 30 stored dates against NYSE calendar; any missing sessions → `short`. (2) **Forward gap prevention** (calendar_gap 2–5 / append path): checks for missed NYSE sessions between last stored date and today; any found → `short` (previously `_append_bar` only added today's bar, permanently losing intermediate trading days). Non-NYSE tickers (`_NON_NYSE_CALENDAR`: USD, JPY, /CL, /ZN, /GC, /HG) are exempt from both checks. **`scan_history_gaps()` in `system_status.py`** is the standing health check — scans all tickers for missing NYSE days in the last ~20 sessions; wired into `compute_data()` as amber `history_gaps` state (precedence: after integrity red, before run checks). The 2026-08-10 incident: 4 trading days (7/23, 7/30, 7/31, 8/06) missing across ALL ~50 tickers due to `_append_bar` silently dropping intermediate bars — corrupted OBV accumulation, MA20 slope, and downstream conviction scores (SPY volume_score 0→10, conviction updated after fix). REFRESH DATA self-heals via the `short` escalation.

---

## Local Dev Environment (ADR-025)

Local dev runs against an **isolated Postgres 17 container** (`db` service in docker-compose) — not
production Supabase, and not SQLite. It mirrors prod's engine (Supabase = managed PG 17.6) so
migrations rehearse faithfully, while keeping every local write (registrations, CALCULATE SIGNALS,
test fixtures) out of production.

- **Wiring:** `.env.dev` (gitignored) sets `DATABASE_URL` → the `db` container and blanks the prod
  `SUPABASE_*` strings (so local can't reach prod even if `DATABASE_URL` is dropped). Layered after
  `.env` in compose with `required:false` — a missing `.env.dev` boots against prod via `.env`.
- **Which DB am I on?** Admin header **DB badge** — `compute_db_env()` in `system_status.py`, derived
  from the live engine host (not an env flag) **plus** `ENVIRONMENT`: **DEV** grey · **PROD green** on
  the production server (`ENVIRONMENT=production` + Supabase = normal/healthy) · **PROD red** when a
  *non-production* process is connected to Supabase (missing `.env.dev` — the ADR-025 hazard; screams
  only when genuinely dangerous). Amber-on-PROD was retired 2026-07-16 (it false-alarmed on the normal
  production state). Also see startup log line `DB CONNECTION → host=… [DEV|PROD-SUPABASE]`.
- **Schwab in dev:** empty `schwab_tokens` → all Schwab calls fall back to Yahoo (intentional — kills
  the shared refresh-token rotation race). The 5 Schwab-only macro-vol `$`-indices
  (MOVE/VXN/RVX/GVZ/OVX) have no Yahoo source → blank in dev (expected). Never copy the prod token in.
- **Bootstrap a fresh dev DB:** `docker compose up -d db` → `docker compose run --rm backend alembic
  upgrade head` → `docker compose up -d` (seeds tickers + admin from `.env`). Optionally mirror the
  live universe by copying the prod `tickers` table (safe — no PII; never copy `users`).
- **Rollback:** remove `.env.dev` → back to prod; `docker compose down -v` → wipe dev data. Prod is
  never in the blast radius.

---

## Session-Start Checklist — Run at the Start of Every Backend Session

Neo must run these steps at the start of any session that touches backend code, signals, or schema.
Do not skip. Do not assume the environment is already in sync.

```
1. Confirm Docker is running
   docker ps | grep signal-matrix

2. Sync the local DEV Postgres schema (isolated container — NOT prod; see "Local Dev Environment")
   docker compose up -d db                                  # postgres:17 dev container
   docker compose run --rm backend alembic upgrade head     # builds/updates dev schema on PG17

3. Confirm Fly.io auth is valid (only needed before deploys)
   fly auth whoami

4. Confirm production API is alive (only needed before deploys)
   curl https://api.signal.suttonmc.com/health
```

If step 2 fails, stop and diagnose before making any code changes. A schema mismatch between
the local DEV Postgres and the Alembic migration history means local test results are unreliable.

---

## Pre-Migration Checklist — Run Before Every Alembic Migration

Every schema change must follow this sequence exactly. Do not skip steps, do not reorder.

### Step 1 — Write and review the migration file
- Generate: `docker exec signal-matrix-backend-1 alembic revision --autogenerate -m "description"`
- Review the generated file in `backend/alembic/versions/` before running it
- Confirm upgrade() and downgrade() are correct
- Confirm no unexpected table drops or column renames

### Step 2 — Dry-run the migration against the local DEV Postgres first
```bash
docker compose run --rm backend alembic upgrade head
```
- Targets the isolated `db` container (postgres:17, **same engine as prod Supabase 17.6**) via the
  `DATABASE_URL` in `.env.dev` — a faithful Postgres rehearsal, not a SQLite approximation. This is
  the dry-run that catches engine-level migration issues before they reach prod.
- If this fails, fix the migration file before touching production.
- (The `sqlite:////app/signal_matrix.db` fallback in `alembic/env.py` still exists for the
  no-env-vars case, but local dev now uses the Postgres container — see "Local Dev Environment".)

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
./deploy-web.sh                    # builds web; REACT_APP_API_URL baked via fly.web.toml [build.args]
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

The live ticker universe is managed via the Postgres `tickers` table and admin panel.
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
