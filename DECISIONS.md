# DECISIONS.md — Signal Matrix Architecture Decision Record

**Purpose:** Hold the *why* behind non-obvious decisions — the rationale and
regression guards that keep CLAUDE.md lean without losing the reasoning. CLAUDE.md
tells you the rule; this file tells you why it exists and what NOT to revert to.

**Governed by:** `Docs/CLAUDE_md_Maintenance_Protocol.md`

---

## How to use this file

- **Read before any methodology or architecture change.** CLAUDE.md is auto-loaded
  every session; this file is not — its top-of-file pointer in CLAUDE.md is your cue
  to come here first.
- **Append-only, newest at top.** Never edit a closed decision. To change one,
  write a new ADR and flip the old entry's `Status` to `Superseded by ADR-NNN`.
- **Each ADR is linked both ways:** the entry names its `Linked rule:` in CLAUDE.md;
  the CLAUDE.md rule cites `see ADR-NNN`.
- **Keep entries short** — anyone, including future-you, should grasp the *why* in
  under 60 seconds.

---

## Entry format (ADR-lite)

```
## ADR-NNN — <short decision title>
Date: YYYY-MM-DD
Status: Active            (Active | Superseded by ADR-NNN | Reversed)
Component: <file / subsystem>

Context:
  <what situation / problem prompted the decision>

Decision:
  <what was chosen>

Why (regression guard):
  <the non-obvious reasoning; what NOT to revert to and why>

Linked rule: CLAUDE.md "<rule heading or number>"
```

---

## Decisions

<!-- Newest at top (highest ADR number first). New entries via "Log this change." -->

## ADR-022 — Macro-vol index history: append fetch uses MONTH/daily, not DAY/daily
Date: 2026-06-23
Status: Active
Component: `schwab_market_data.py` (`_schwab_fetch_index_histories`)

Context:
  The macro-vol index append path (gap 1–5 days) fetched `periodType=day` +
  `frequencyType=daily`. Schwab REJECTS that combination with HTTP 400:
  *"When periodType=day valid values for frequencyType are: minute."* So the
  append fetch 400'd on every normal trading day and fell through to Yahoo —
  silently, since the broad except caught it. This defeated ADR-010 (VXN/RVX/
  GVZ/OVX/MOVE are meant to live on Schwab) and FROZE RVX: its Yahoo fallback
  `^RVX` is delisted ("no price data found"), so when Schwab append 400'd there
  was nothing to recover from. The other four were masked because their `^`
  Yahoo symbols still resolve. The DAY choice was originally made in ADR-010 to
  dodge a "1-month endpoint mis-scales MOVE" bug that no longer reproduces.

Decision:
  `append` fetches `periodType=month` + `period=ONE_MONTH` + `frequencyType=daily`
  (the valid combo) and routes through the merge `_upsert` — not the single-bar
  `_append_bar` — so a multi-day gap (holiday + stale ticker) fills every missing
  bar, not just the latest. MAs are computed from the MERGED series so ma50/ma100
  don't null out on the ~20-candle fetch.

Why (regression guard):
  Schwab's `periodType=day` ONLY allows `frequencyType=minute` — never pair
  `day`+`daily` (it always 400s). Do not revert the append fetch to `DAY`/`TEN_DAYS`.
  The MONTH/ONE_MONTH endpoint is NOT mis-scaled — verified 2026-06-23 against
  stored history for all five incl. MOVE (overlap matched exactly; the only diffs
  were the newest two MOVE bars, Schwab-vs-Yahoo source disagreement at correct
  scale). RVX has no Yahoo fallback (`^RVX` delisted), so Schwab is its sole
  source: a >7-day refresh-token outage will freeze RVX — accepted per ADR-010's
  stale-but-correct stance. If Schwab ever changes the price-history contract,
  re-verify MONTH scaling against stored history before trusting it.

Supersedes: the fetch-mode detail of ADR-010 only (the "use 10-day DAY fetch for
  append … the 1-month endpoint mis-scales MOVE" rationale). ADR-010's core
  decision — `_yahoo_fallback` EXCLUDES these tickers so token expiry keeps
  stale-but-correct Schwab data instead of Yahoo garbage — remains Active.

Linked rule: CLAUDE.md "Macro Vol data source" + rule #98

## ADR-021 — Fly custom-hostname cert renewal behind the Cloudflare proxy
Date: 2026-06-22
Status: Active
Component: Cloudflare DNS (suttonmc.com zone), Fly certs (signal-matrix-web / -api)

Context:
  signal.suttonmc.com is Proxied (orange cloud) in Cloudflare. Fly issues its
  Let's Encrypt cert via HTTP-01, which CANNOT complete behind the CDN — Fly
  detects the proxy and requires DNS-based ownership proof. The original cert
  issued ~3 months earlier but never renewed; it expired and the site threw
  Cloudflare Error 525 (CF reached the origin but Fly had no valid cert for the
  custom hostname — signal-matrix-web.fly.dev itself was HTTP 200 the whole time).
  api.signal.suttonmc.com was unaffected because it is grey-cloud (DNS only), so
  Fly validates HTTP-01 against the origin IP directly.

Decision:
  Keep signal proxied, but add two DNS-only records to the suttonmc.com zone so
  Fly renews via DNS-01 automatically (values from
  `fly certs setup signal.suttonmc.com --app signal-matrix-web`):
    • CNAME _acme-challenge.signal → signal.suttonmc.com.13y0odn.flydns.net
    • TXT   _fly-ownership.signal  → app-13y0odn
  Keep api.signal grey-cloud (DNS only) — do NOT proxy it.

Why (regression guard):
  The _acme-challenge CNAME makes all future renewals automatic; do not delete it.
  Do NOT proxy api.signal to "fix" the Unproxied-AAAA security finding: (1) it would
  hit the same renewal trap (needs its own _acme-challenge/_fly-ownership records),
  and (2) Cloudflare's free-plan 100s origin timeout would 524 the long REFRESH
  DATA / CALCULATE SIGNALS bulk Schwab fetches. CAA is fine — the zone already
  permits Let's Encrypt (0 issue "letsencrypt.org" alongside pki.goog). The
  "Exposed RDP" Critical insights on api.signal are FALSE POSITIVES: the Fly anycast
  edge completes TCP handshakes on arbitrary ports (3389 "open" on both the shared
  IPv4 and dedicated IPv6), but fly.api.toml exposes only [http_service] 8000→443 —
  no RDP. No Cloudflare API token on the dev machine; DNS edits are dashboard-only
  (account id 1cc54ccce957ce25a79ac27cbdf1e760).

Linked rule: CLAUDE.md rule #97

## ADR-020 — Header status split: CONNECTION + DATA + STATUS (own module)
Date: 2026-06-19
Status: Active
Component: `services/system_status.py`, `routers/system.py`,
           `components/shared/SystemStatus.js`, `services/scheduler.py`

Context:
  A single SCHWAB dot conflated two independent things — Schwab auth health and
  data health — and keyed off token AGE only. During the 2026-06-18 authlib
  outage (ADR-018) it stayed green while every fetch failed, data went stale, and
  NaN corrupted the cache (ADR-019). No indicator reflected actual fetch success
  or data integrity. The old ● SCHED dot also showed green because Yahoo fallback
  made the run "succeed."

Decision:
  Three indicators, two admin-only, computed in services/system_status.py:
    • CONNECTION (admin) — Schwab auth only: fresh / aging / expired / disconnected.
      expired (≥7d) and disconnected (missing/undecryptable, ANY age) are distinct.
    • DATA (admin) — source · freshness · EOD-run · integrity, by precedence:
      integrity > run_failed > run_incomplete > run_missed > stale > yahoo > good.
      Green stays green all day with an adaptive tooltip — NO "pending" amber.
    • STATUS (users) — plain roll-up of DATA: normal / degraded / issue.
  A STANDING integrity scan (scan_integrity) checks NaN/Inf over the fields the
  page-load endpoints serialize — the check that would have caught 6/19.
  GET /api/system/status → {connection, data, status} for admins, {status} only
  for everyone else. scheduler.py writes a 'started' scheduler_log marker (flipped
  to success/failure at end) so a mid-run crash = DATA run_incomplete (status is
  TEXT — no migration).

Why (regression guard):
  "Green" must mean VERIFIED-good, never "didn't throw" — keep the integrity scan
  in the green path. CONNECTION and DATA are INDEPENDENT axes (a dead token still
  yields good Yahoo data = amber, not red); do not re-merge them. Token AGE is a
  CONNECTION signal only — never let it imply data health (the 6/18 blind spot).
  The frontend is dumb: backend computes every color/tooltip/clickable. The old
  /schwab/status + /scheduler/status endpoints remain but the header now reads
  /api/system/status.

Linked rule: CLAUDE.md rule #96

## ADR-019 — fetch_ticker_close must drop NaN closes (Yahoo weekday-holiday NaN)
Date: 2026-06-19
Status: Active
Component: `yahoo_finance.py` (`fetch_ticker_close`)

Context:
  Yahoo returns a NaN close for the current day on weekday holidays / data
  glitches — reproduced: ^GSPC / ^NDX / ^RUT all returned NaN for the session on
  Juneteenth (2026-06-19). The lightweight append-path fetch took
  hist["Close"].iloc[-1] with no guard, writing NaN into
  price_cache.close / ma200 / std20 for Yahoo-only tickers (SPX, NDX, RUT, $DJI,
  PPLT, PALL). FastAPI serialized NaN as an invalid JSON token → the browser's
  JSON.parse threw → the frontend fell back to mock ("LIVE DATA UNAVAILABLE /
  DISPLAYING MOCK DATA"). ma20/50/100 survived (pandas .mean() skips NaN) but
  ma200 (np.mean) and std20 did not — that asymmetry was the tell.

Decision:
  Filter `hist = hist[hist["Close"].notna()]` before taking the last bar,
  mirroring the dropna() that fetch_ticker_data already uses. Return None
  (treated as a failed fetch, no write) if no valid close remains.

Why (regression guard):
  Any lightweight "last bar" Yahoo fetch MUST drop NaN — Yahoo is not a clean
  source on non-session days. Dormant for a month because normal weekends
  produce NO Yahoo weekend row (iloc[-1] is Friday's real close); only weekday
  holidays / Yahoo glitches expose it. The full path (fetch_ticker_data) was
  always guarded; the lightweight append path was not. Keep BOTH guarded.

Linked rule: CLAUDE.md rule #95

## ADR-018 — Schwab token-write callback must accept **kwargs; pin authlib
Date: 2026-06-18
Status: Active
Component: `schwab_client.py` (`get_schwab_client._write`); `backend/requirements.txt`

Context:
  authlib is an UNPINNED transitive dependency of schwab-py. A Docker rebuild
  pulled authlib 1.6.12, which began forwarding `refresh_token=` as a kwarg to
  the token_write_func on every access-token refresh. Our `_write(token_dict)`
  accepted one positional arg only → TypeError inside authlib's
  ensure_active_token on every refresh → the refreshed token was never persisted
  → `updated_at` froze → 100% Schwab failure (EOD job AND the 15-min intraday
  monitor) → silent Yahoo fallback for ~24h. It "worked for over a month"
  because the code never changed — the transitive dep silently upgraded on a
  rebuild. get_status() showed green throughout (per ADR-016 it measures
  refresh-token AGE, not whether refresh succeeds — a recent-but-broken token
  reads connected).

Decision:
  `_write(token_dict, *args, **kwargs)` — accept and ignore forwarded args;
  token_dict is the full new token and _store_tokens unwraps the
  {creation_timestamp, token} shape. PIN `authlib==1.6.12` in requirements.txt
  so a future rebuild cannot reintroduce a signature mismatch.

Why (regression guard):
  Never give a schwab-py / authlib callback (token_read_func / token_write_func)
  a fixed positional signature — always accept `*args, **kwargs`; the library
  adds kwargs across versions. Keep authlib pinned. Do NOT trust the green
  SCHWAB dot as proof Schwab works (it only proves the refresh token is < 7 days
  old) — confirm via price_cache.data_source counts or a live quote.

Linked rule: CLAUDE.md rule #94

## ADR-017 — OBV direction: rolling z-score oscillator → 40-bar regression (replaces slope÷std)
Date: 2026-06-18
Status: Active
Component: `conviction_engine.py` (`_obv_direction`, `_rolling_zscore`)

Context:
  Prior method (ADR-005) regressed raw OBV over 40 bars and divided the slope by
  std(OBV[-40:]). That is algebraically identical to a SINGLE-window z-score regression
  (subtracting the mean doesn't change a slope; dividing by positive std can't flip sign),
  so it never inverted — verified empirically: a 25× volume gap moved the normalized value
  only ~0.4% and never crossed the band. But it is a single static-window transform.

Decision:
  Build a ROLLING 20-bar z-score of OBV (each bar normalized by its OWN trailing 20-bar
  mean/std), then take the 40-bar linear-regression slope of that stationary oscillator.
  Sign-only classification (neutral band = 0, maximally responsive): slope > 0 → Bullish,
  < 0 → Bearish, == 0 → Neutral. Requires ≥ 59 OBV bars (zn + rn − 1 = 20 + 40 − 1).
  `obv_confirming` unchanged: z-score regression direction AND raw-OBV 20-SMA 3-bar slope
  must both confirm Trade Dir (+10 volume_score), plus acceleration (+5).

Why (regression guard):
  Adopted for RESPONSIVENESS, not to fix an inversion — the rolling z-score registered a
  post-gap trend turn ~3 trading days earlier than the single-window method, because recent
  bars are normalized by their own local (pre-shock) environment. Do NOT "simplify" back to
  slope÷std: that collapses the rolling per-bar σ_t into one scalar and loses the early turn.
  Do NOT confuse this with the broken ThinkScript `OBV/StDev` (level÷dispersion) study, which
  DOES invert — dividing the huge near-constant OBV level by a co-moving σ yields a 1/σ signal
  that sinks as the trend strengthens; the mean-subtraction in the z-score is what cures that.
  Band = 0 means `_obv_direction` almost never returns Neutral (only volumeless indices such
  as VIX, whose flat OBV gives an exact-zero slope) — accepted tradeoff for max responsiveness;
  expect more frequent Confirming/Diverging vol_signals. The raw-OBV 20-SMA slope/acceleration
  signals deliberately stay on raw OBV (sign-only, so scale is irrelevant).

Linked rule: CLAUDE.md rule #41

## ADR-016 — `get_status()` clock source: `updated_at`, not `expires_at`
Date: 2026-06-17
Status: Active
Component: `backend/services/schwab_client.py` — `get_status()`

Context:
  The SCHWAB header dot was showing red every morning (and every overnight period
  with no API calls), even though the system would auto-recover on the next
  schwab-py API call. Root cause: `get_status()` compared `expires_at` against
  now. `expires_at` is the 30-min access token lifetime — it always reads as
  expired after 30 minutes of inactivity.

Decision:
  Use `updated_at` as the clock for the 7-day expiry check. `updated_at` is
  stamped by `_store_tokens()` on every successful token write (both OAuth
  exchange and schwab-py auto-refresh during API calls). If `updated_at` is
  < 7 days old the refresh token is still valid; ≥ 7 days → the refresh token
  has likely expired → show red and require re-auth.

Why (regression guard):
  A 30-min access token expiring overnight is normal and recoverable — schwab-py
  auto-refreshes it on the next API call (9:30 AM intraday monitor or 4 PM EOD
  job). Showing red for this causes alarm and unnecessary re-auths. RED must
  exclusively mean "the refresh token is dead; the system cannot recover without
  user action." `expires_at` is the wrong signal for that. Do NOT revert to
  `expires_at` without first verifying that you're checking the refresh token's
  expiry — Schwab does not return a separate `refresh_token_expires_at` field,
  so `updated_at` + 7 days is the correct proxy.

Linked rule: CLAUDE.md rule #93 + "Schwab refresh token has a hard 7-day expiry"


## ADR-015 — Remove proactive Schwab token refresh scheduler job
Date: 2026-06-17
Status: Active
Component: `backend/services/scheduler.py`, `backend/services/schwab_client.py`

Context:
  A `schwab_refresh` APScheduler job fired every 25 minutes and called the
  Schwab token endpoint directly (via `refresh_access_token()` in
  `schwab_client.py`). This was added before schwab-py's `client_from_access_functions`
  was in use. Once the IV fetch was activated (commit `111f900` fixed a NameError
  that had silently suppressed it), the IV fetch ran 65+ option chain requests
  over several minutes. During that window schwab-py's internal auto-refresh and
  the 25-min scheduler both read the same refresh token from the DB and called
  Schwab simultaneously. Schwab rotates the refresh token on first use; the
  second caller got `invalid_grant`, killing the session.

Decision:
  Remove `_refresh_schwab_tokens_job` and its scheduler registration entirely.
  Let schwab-py's `client_from_access_functions` handle all token refreshes
  internally — it calls `_write()` (which calls `_store_tokens()`) on each
  successful refresh, keeping `updated_at` current. No separate refresh job.

Why (regression guard):
  schwab-py serializes token refresh internally — only one refresh happens per
  client instance per expired access token. A parallel httpx caller has no
  knowledge of schwab-py's in-flight refresh and will race on the refresh token.
  Schwab's single-use refresh token rotation means only one winner; the loser
  gets `invalid_grant`. Do NOT re-add any APScheduler job that calls the Schwab
  token endpoint directly. The only safe refresh path is through the schwab-py
  client. If future sessions need a keep-alive mechanism, it must go through
  schwab-py (e.g., a lightweight API call on a schedule — not a direct token POST).

Linked rule: CLAUDE.md rule #92 + Scheduler Overview section
<!-- ADR-001..013 seeded 2026-06-04 from the CLAUDE.md "Known Fixes & Learnings" migration (Phase M2). Dates reflect the recording pass, not original decision dates. -->

## ADR-015 — Restructured precious metals ETFs must use Yahoo history, not Schwab
Date: 2026-06-17
Status: Active
Component: schwab_market_data.py — SCHWAB_UNSUPPORTED set

Context:
  PALL (Aberdeen Physical Palladium) and PPLT (abrdn Physical Platinum Shares)
  underwent fund restructurings that changed the per-share commodity holding. After
  the restructuring, each share represents a smaller fraction of the underlying metal,
  so the post-restructuring price is ~5–10× lower than the pre-restructuring price.
  Schwab's get_price_history() returns unadjusted historical prices spanning both
  eras, creating a staircase discontinuity within the 60-bar sparkline window. Yahoo
  Finance returns only post-restructuring prices (consistent with current quotes).

Decision:
  Add PALL and PPLT to SCHWAB_UNSUPPORTED. Yahoo supplies their full price history;
  Schwab is not used for these tickers. The sparkline, pivot levels, and LRR/HRR all
  derive from Yahoo history and are internally consistent.

Why (regression guard):
  Schwab serves PALL and PPLT without error (they are valid US-listed ETFs), so the
  incompatibility is not obvious from a code-level audit. The symptom is a visual
  staircase in the spark chart and an anomalously large Trend Level (e.g. Bearish
  Trend Level $165 when current price is $15). Do not remove these from
  SCHWAB_UNSUPPORTED without first verifying Schwab's history matches current price
  scale for both tickers.

Linked rule: CLAUDE.md "Restructured ETF history check"

## ADR-014 — CLAUDE.md migration stops at ~1,510 lines; current ops content stays
Date: 2026-06-04
Status: Active
Component: CLAUDE.md / DECISIONS.md (documentation governance)

Context:
  The CLAUDE.md migration (governed by `Docs/CLAUDE_md_Maintenance_Protocol.md` +
  `Docs/SignalMatrix_CLAUDEmd_Migration_Spec_v1_0.txt`) set an aspirational target of
  600–900 lines. Section (a) "Known Fixes & Learnings" (796→73) and pass-2 targets
  (the 68-entry commit-hash list, Phase 3–5 build tables, Task 4.3–4.7 build
  narratives) were condensed. CLAUDE.md went 2,479 → 1,510 (−39%).

Decision:
  Stop at ~1,510. Pass-2 item (c) condensed only the *build-narrative framing*;
  live operational sections were kept intact: EOD Scheduler, Intraday Monitor,
  "Signal Engine Math — ALL DECISIONS LOCKED", dashboard column + popup-field
  tables, the numbered Project Rules, and the session/pre-migration checklists.

Why (regression guard):
  The 600–900 target was aspirational. This project carries an unusually large
  amount of *current* operational spec; cutting below ~1,500 means deleting live
  documentation, not trimming history. Do NOT "finish the job" in a future pass by
  gutting current ops sections — the remaining length is legitimate. Process note:
  pass-2 (c) was inline-approved (the assessment + a "go", not a separate written
  TRIAGE table); the execution record is git commits 426865c + 4ee089e. Future
  passes should still produce a triage table before cutting unless the scope is as
  unambiguous as the commit-hash delete.

Linked rule: CLAUDE.md "Read order (authoritative)" + Maintenance Protocol

## ADR-013 — Trade BB+Snap constants are TOS-tuned, not spec defaults
Date: 2026-06-04
Status: Active
Component: Trade LRR/HRR — `conviction_engine.py` (`_RR_K_*`)

Context:
  The v1.9.1/1.9.2 BB+Snap spec (`Docs/SignalMatrix_RR_v1_9_1.txt`) shipped with
  example defaults (k_extend=2.0, k_max=1.0, k_min=0.3). Visual validation against
  Hedgeye RRs on SPX/GOOGL/AMZN showed those defaults drifted.

Decision:
  Hardcode TOS-tuned constants in `conviction_engine.py`:
  k_wide=2.0, k_extend=2.2, k_max=1.0, k_min=0.0, k_decay=0.5.

Why (regression guard):
  These are the validated live values — the **code is the source of truth**, not the
  Docs spec (older defaults) and not any prose copy. A prior CLAUDE.md rule drifted to
  k_max=1.4/k_min=0.4, which never matched the code; do not trust stale inline copies.
  Do not revert to spec defaults without re-validating bands against Hedgeye in ToS.

Linked rule: CLAUDE.md "Trade LRR/HRR — v1.9.1 Formula" + rule #77

## ADR-012 — Gap-detection fetch modes (skip/append/short/bootstrap)
Date: 2026-06-04
Status: Active
Component: `schwab_market_data.py`, `yahoo_finance.py`

Context:
  Every REFRESH fetched full multi-month/5-year history per ticker even when the DB
  already had it and only one new bar was needed — slow (~60s on second hit).

Decision:
  Per-ticker `_history_fetch_mode(existing_row, today)` chooses: `skip` (cache==today,
  quote-only), `append` (1–5d gap, append today's bar from batch quote, no history
  API call), `short` (6–45d, targeted fetch), `bootstrap` (no/short history or >45d
  gap, full 5-year). Same four modes applied to the Yahoo-only path.

Why (regression guard):
  Removing the modes reintroduces full-history pulls on every refresh. The `append`
  path must recompute MAs/STD/spark from the merged history. The 0.5s rate-limit
  sleep must fire only when a history API call is actually made.

Linked rule: CLAUDE.md gap-detection rules

## ADR-011 — Sidebar must be `position: fixed` (Recharts ResizeObserver stutter)
Date: 2026-06-04
Status: Active
Component: `src/components/shared/Sidebar.js`, `AppLayout`

Context:
  On pages with Recharts `ResponsiveContainer`, a `position: sticky` sidebar caused
  visible stutter: the chart's ResizeObserver fired repeatedly as flex-layout content
  width changed during hover-expand transitions.

Decision:
  Sidebar is `position: fixed` at `top: 48px`; content uses a fixed `marginLeft` so
  its width never changes during sidebar expand/collapse.

Why (regression guard):
  Reverting to `position: sticky` re-introduces the ResizeObserver stutter on every
  Recharts page. Add dashboards via the `NAV_ITEMS` array — no layout change needed.

Linked rule: CLAUDE.md "Sidebar must remain position: fixed"

## ADR-010 — Macro-vol index history sourcing (Schwab $-symbols; Yahoo-fallback excluded)
Date: 2026-06-04
Status: Active — fetch-mode detail superseded by ADR-022 (Yahoo-exclusion core decision still Active)
Component: `schwab_market_data.py` (`SCHWAB_INDEX_HISTORY_MAP`, `_yahoo_fallback`)

Context:
  VXN/RVX/GVZ/OVX/MOVE are fetched via Schwab `$`-prefixed symbols. When Schwab
  tokens expire, the generic Yahoo fallback returned ~73 stale bars for e.g. `^RVX`
  that merged with `cut=0`, replacing good history with garbage.

Decision:
  Fetch these via `_schwab_fetch_index_histories()`; `_yahoo_fallback()` **excludes**
  all `SCHWAB_INDEX_HISTORY_MAP` tickers — on token expiry they keep stale-but-correct
  Schwab data rather than being overwritten by Yahoo.

Why (regression guard):
  Letting Yahoo fall back for these corrupts the macro-vol series — keep
  `_yahoo_fallback` excluding all `SCHWAB_INDEX_HISTORY_MAP` tickers.
  NOTE (superseded by ADR-022): the original "use 10-day DAY fetch for `append`
  because the 1-month endpoint mis-scales MOVE" rationale is wrong — `periodType=day`
  + `frequencyType=daily` always 400s, and MONTH/ONE_MONTH is not mis-scaled. The
  append path now uses MONTH/daily; `short`/`bootstrap` still use the 5-year YEAR fetch.

Linked rule: CLAUDE.md "Macro Vol data source"

## ADR-009 — Indices, FX, and futures permanently route to Yahoo
Date: 2026-06-04
Status: Active
Component: `schwab_market_data.py` (`SCHWAB_UNSUPPORTED`), `yahoo_finance.py`

Context:
  Schwab's API is equity/ETF-only. Batch quotes silently drop index symbols (no
  error, missing keys); there is no FX endpoint (DXY/spot don't exist there); futures
  use contract-specific symbols, not the continuous front-month abstraction we use.

Decision:
  Indices (SPX/NDX/$DJI/VIX/RUT/VVIX), FX (USD/JPY), and futures (/CL,/ZN,/GC) are
  permanently sourced from Yahoo. This is a deliberate architecture decision, not a gap.

Why (regression guard):
  Do not attempt to "upgrade" these to Schwab — replicating continuous-futures rolls
  or finding non-existent FX endpoints is complexity for zero EOD signal gain. New
  tickers in these classes go in `SCHWAB_UNSUPPORTED` + `YAHOO_SYMBOL_MAP` (+ futures
  also `IV_INELIGIBLE`).

Linked rule: CLAUDE.md "Schwab API — Instrument Type Limitations"

## ADR-008 — Fly.io web = multi-stage build → nginx static (not CRA dev server)
Date: 2026-06-04
Status: Active
Component: `Dockerfile.web.fly`, `deploy-web.sh`, `nginx.conf`

Context:
  `npm start` exited code 0 instantly on Fly Firecracker VMs (headless, no TTY). Two
  stacked bugs: no `.dockerignore` (so `COPY . .` overwrote Linux node_modules with
  Windows binaries → instant clean exit) and a 256MB VM too small for webpack.

Decision:
  Multi-stage build: `npm run build` on Depot's builder, then `nginx:alpine` serves
  static `build/`. `.dockerignore` excludes node_modules. nginx needs
  `try_files $uri $uri/ /index.html` for React Router. All web deploys via `deploy-web.sh`.

Why (regression guard):
  Never deploy CRA via `npm start` to Fly — it dies headless. `.dockerignore` must
  exclude node_modules or Windows binaries crash the Linux container. Bare `fly deploy`
  skips build-arg plumbing.

Linked rule: CLAUDE.md Fly web-deploy rules

## ADR-007 — MA20_TP (typical-price center) dropped
Date: 2026-06-04
Status: Active
Component: `conviction_engine.py`, `price_cache`

Context:
  A v1.8 interim used TP=(H+L+C)/3 as the BB center to resist downward drag on sell
  days. Measured improvement over MA20(close) was ±7 pts on SPX.

Decision:
  Removed (migration 13fb636fe76a): dropped `ma20_tp`/`std20_tp`, removed
  `_compute_tp_metrics()`. v1.9.1 later replaced the center entirely with dynamic-N MA.

Why (regression guard):
  Negligible gain (±7pt SPX) was not worth the schema complexity. Do not re-add
  MA20_TP / typical-price center.

Linked rule: CLAUDE.md "Never re-add MA20_TP"

## ADR-006 — Schwab IV30 + vol-metrics methodology (ATM, 25Δ BS-approx, VRP)
Date: 2026-06-04
Status: Active
Component: `schwab_options.py`

Context:
  The option chain's top-level `volatility` field is realized/historical vol, not
  implied. Schwab omits delta on OTM options, so delta-based 25Δ selection landed on
  ATM strikes (≈0.5 delta), producing near-zero risk reversals (~0.4% vs correct ~-6%).

Decision:
  IV30 = 30-day constant-maturity ATM IV via `_extract_atm_iv` (interpolate the two
  expirations bracketing 30 DTE). 25Δ skew via **strike-based Black-Scholes
  approximation** (compute K_call/K_put_25d from S and ATM IV, read nearest strike's
  IV) — never the delta field. IV Rank is range-based `(cur-min)/(max-min)×100`. HV30/90
  = 21/63-day annualized realized vol. VRP = IV30 − HV30.

Why (regression guard):
  Do NOT read top-level `volatility` (it's realized vol). Do NOT revert 25Δ to
  delta-based selection (Schwab's OTM delta is unreliable). IV Rank is range-based,
  not frequency percentile.

Linked rule: CLAUDE.md Schwab IV / vol-metrics rules

## ADR-005 — OBV direction method evolution (why 40-bar regression won)
Date: 2026-06-04
Status: Superseded by ADR-017 (regression now runs on a rolling z-score oscillator, band 0)
Component: `conviction_engine.py` (`_obv_direction`)

Context:
  OBV direction went through three methods: (1) 5/20-day price-momentum proxy (not real
  volume); (2) HH+HL comparison of the last-2 vs prior-2 pivot highs (needed 4 confirmed
  pivots, lagged V-recoveries by weeks, could signal before D established); (3) ABCD
  pivot logic on OBV.

Decision:
  Current method (v2.0) = 40-bar linear regression slope on the OBV series, normalized
  by std(OBV[-40:]); |norm| ≤ 0.02 → Neutral. `obv_confirming` is strict: regression
  direction AND OBV MA20 3-bar ROC both confirm Trade Dir.

Why (regression guard):
  Do not revert to the price-momentum proxy (not volume) or the HH+HL/ABCD pivot
  methods (4-pivot lag, pre-D false signals). The regression is scale-invariant and
  responds without waiting for confirmed pivots.

Linked rule: CLAUDE.md rule #41

## ADR-004 — Yahoo `auto_adjust=False` (store actual traded prices)
Date: 2026-06-04
Status: Active
Component: `yahoo_finance.py`

Context:
  yfinance defaults `auto_adjust=True`, silently dividend-adjusting all historical
  closes. SPY Aug 1 2025 showed $616.49 cached vs $621.72 actual — divergence grows
  for older bars and any dividend payer.

Decision:
  `auto_adjust=False` on all `history()` calls. Yahoo fallback only serves
  no-dividend instruments (indices/FX/futures) in production, so impact is dev-only.

Why (regression guard):
  Reverting to `auto_adjust=True` makes stored prices diverge from actual traded
  prices, corrupting pivots and bands. Do not revert.

Linked rule: CLAUDE.md "Yahoo auto_adjust=False"

## ADR-003 — ABC pivot selection & dynamic update (load-bearing)
Date: 2026-06-04
Status: Active
Component: `pivot_engine.py`

Context:
  Several real failures: anchoring A at a sub-extreme pivot (XLV), V-recoveries that
  never re-established trend, a stale fixed B making the d_extended threshold wrong,
  and phantom ABCs that span a prior BREAK_CONFIRMED (IWM/GLD/AAPL/NVDA/TLT/FXB).

Decision:
  (1) A anchors at the most extreme confirmed pivot in the lookback window
  (`_MAX_A_LOOKBACK` trade=60 / trend=150 / lt=none), forward-walk, with most-extreme→
  least-extreme A-candidate iteration for V-recoveries. (2) B advances to the most
  recent confirmed pivot after C is finalized (`update_b_dynamically`, run AFTER
  `update_c_dynamically`). (3) `find_abc_structure()` selection priority prefers the
  price-intact structure and rejects any ABC spanning a prior BREAK_CONFIRMED
  (`_has_prior_break_confirmed`, `_price_on_correct_side`, `_d_has_established`).

Why (regression guard):
  Do not retreat A to a less-extreme pivot; do not raise `_MAX_A_LOOKBACK["trade"]`
  above 60; do not remove/ reorder `update_b_dynamically` (C must finalize first); do
  not simplify `find_abc_structure()` to "most-recent-C-wins" — the priority logic
  prevents phantom structures spanning confirmed breaks.

Linked rule: CLAUDE.md pivot-engine rules

## ADR-002 — structural_state is exactly 6 values; d_extended is a boolean
Date: 2026-06-04
Status: Active
Component: `pivot_engine.py`, `conviction_engine.py`

Context:
  FORMING, EXTENDED, and WARNING were once stored in `structural_state`, conflicting
  with each other (e.g. BREAK_OF_TRADE could not coexist with "came-from-EXTENDED"
  context) and lingering as misleading labels after price retraced.

Decision:
  `structural_state` ∈ {UPTREND_VALID, DOWNTREND_VALID, BREAK_OF_TRADE, BREAK_OF_TREND,
  BREAK_CONFIRMED, NO_STRUCTURE} — nothing else. FORMING eliminated (a pullback is just
  *_VALID). EXTENDED became the boolean `d_extended` (D > B + abs(B-C)). WARNING became
  the boolean `warning` flag. BREAK_OF_TRADE/TREND hold direction; only BREAK_CONFIRMED
  → Neutral.

Why (regression guard):
  Never add EXTENDED/WARNING/FORMING back to `structural_state`. `d_extended` is the
  sole source of truth for B-vs-C break level (warn flags, popup asterisk). Three
  independent "extended" concepts (d_extended / lrr_extended+hrr_extended / the dead
  EXTENDED string) must never be conflated.

Linked rule: CLAUDE.md rules #53–#60

## ADR-001 — All trading-day dates use ET, never UTC
Date: 2026-06-04
Status: Active
Component: `market_data.py`, `services/scheduler.py`, `routers/scheduler.py`

Context:
  Docker runs UTC. After ~8 PM ET (midnight UTC) the UTC date rolls to the next day
  while the ET trading date has not — breaking three things: `cache_date` (cache miss),
  `run_date` in `scheduler_log` (`today_complete` false), and the NYSE trading-day check.

Decision:
  Use ET everywhere a date represents a trading day or cache key:
  `datetime.now(ZoneInfo("America/New_York"))`. Store UTC-naive timestamps for display
  fields, but convert to ET at display time.

Why (regression guard):
  Never use `date.today()`, `str(date.today())`, or `datetime.utcnow().date()` for any
  trading-day/cache-key date — they return UTC and silently break after 8 PM ET.

Linked rule: CLAUDE.md rule #34
