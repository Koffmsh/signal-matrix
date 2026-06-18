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
Status: Active
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
  Letting Yahoo fall back for these corrupts the macro-vol series. Use the 10-day DAY
  fetch for `append`, 5-year YEAR fetch for `short`/`bootstrap` (the 1-month endpoint
  mis-scales MOVE).

Linked rule: CLAUDE.md "Macro Vol — Data Source Architecture"

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
Status: Active
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
