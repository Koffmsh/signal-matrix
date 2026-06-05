# CLAUDE.md Maintenance Protocol

**Status:** v1.0 — locked
**Owner:** Shannon (decisions) · Neo / Claude Code (execution)
**Purpose:** Define what lives where, how each change is recorded, and the exact
instruction that routes a change to the right document. Keeps CLAUDE.md lean and
current while preserving the *why* behind every non-obvious decision.

---

## 1. Why this exists

CLAUDE.md grew to ~2,500 lines by absorbing three different kinds of content:
operating rules, historical rationale, and a verbatim change ledger. A single
monolith that is read in full every session raises two real costs:

1. **Contradiction risk** — superseded formulas (v1.6–v1.9) sit alongside the
   current one (v2.0), so an agent can hold both at once.
2. **Signal dilution** — the rules that must never be violated are buried in
   795 lines of narrative.

The fix is not just trimming. It is **separating content by purpose** across a
small set of files, each with one job.

---

## 2. The document architecture

| File | Job | Auto-loaded by Claude Code? | Tone |
|---|---|---|---|
| **CLAUDE.md** | Operating manual — current rules, constraints, active state, architecture | **Yes** (every session) | Terse, imperative |
| **DECISIONS.md** | The *why* — rationale behind non-obvious choices (ADR-lite) | **No** — pointer in CLAUDE.md; read before methodology/architecture changes | Human-readable, explanatory |
| **Docs/ archive** | Full superseded specs (v1.6 / v1.7 / v1.8 math, retired build sequences) | No | As written |
| **git log** | The *what / when* — chronological change ledger | N/A | Commit messages |

> **The auto-load rule that makes this work:** Claude Code loads CLAUDE.md
> automatically but **not** DECISIONS.md. So the top of CLAUDE.md must carry a
> standing instruction — *"Before any methodology or architecture change, read
> DECISIONS.md"* — exactly like the existing "read the spec .txt first" rule.
> Without that pointer, the rationale is invisible to Neo at work time.

### What does NOT belong in CLAUDE.md
- Verbatim git commit hashes (`git log` reproduces these on demand).
- Full math of superseded formulas (→ Docs/ archive; one-line "superseded by vX"
  reference stays).
- Step-by-step build sequences for completed phases (→ collapse to one
  "Phase N — COMPLETE" line).
- "Old behavior → fixed" narratives where the cause is obvious (→ a single
  `never do X` rule; no story).

---

## 3. The routing rule (the one test that decides everything)

For any change, fix, or new functionality, ask:

> **"Will an agent take a wrong action without this line?"**

| Answer | Destination |
|---|---|
| **Yes — and the reason is obvious** | CLAUDE.md, as a terse imperative rule (`never downgrade yfinance below 1.2.0`) |
| **Yes — but the reason is non-obvious** | CLAUDE.md rule **+** a DECISIONS.md entry holding the *why* |
| **No** | git commit message only (the *what*); nothing in CLAUDE.md |

**Regression guard:** if dropping the narrative would let someone re-introduce a
bug or re-litigate a settled trade-off, the *why* is non-obvious — it goes to
DECISIONS.md. Example: *"STD20 lags because spike bars persist in the rolling
window; IV is forward-looking"* is a regression guard, not a story. Keep it.

---

## 4. The standing instruction to Neo

Replace *"update claude.md with changes"* with:

> ### "Log this change."

On that trigger, Neo runs this sequence:

1. Apply the **routing rule** (§3) to the change.
2. State the proposed routing in one line — e.g.
   *"Rule → CLAUDE.md #75; why → DECISIONS.md ADR-014; what → commit msg."*
3. Make the edits (terse rule in CLAUDE.md, ADR entry in DECISIONS.md).
4. Write a clear commit message for the *what*.
5. **Show Shannon the diff** before considering it done.

**Override variants** (when you want to force a destination):
- *"Log this — rule only"* → CLAUDE.md, no ADR.
- *"Log this — rationale only"* → DECISIONS.md, no rule change.
- *"Log this — archive"* → move superseded detail to Docs/, leave a reference.

Default ("Log this change") = Neo decides routing, you review.

---

## 5. DECISIONS.md entry format (ADR-lite)

Append-only. Newest at top. Never edit a closed decision — supersede it with a
new entry and flip the old one's status.

```
## ADR-014 — IV30 as primary trade-RR volatility source
Date: 2026-06-04
Status: Active            (Active | Superseded by ADR-NNN | Reversed)
Component: Trade LRR/HRR (conviction_engine.py)

Context:
  STD20 was the band-width input. Large spike bars persist in the 20-day
  rolling window, so the band stays wide after vol has actually recovered.

Decision:
  Drive band width from IV30 percentile rank; HV30 fallback when IV missing.

Why (regression guard):
  IV is forward-looking and regime-adjusted; STD20 lags by up to ~20 bars.
  Do not revert to STD20 without re-checking against Hedgeye reference charts.

Linked rule: CLAUDE.md "Trade LRR/HRR — v1.9.1"
```

Keep entries short. The goal is that anyone — including future-you — can read
*why* in under 60 seconds.

---

## 6. CLAUDE.md hygiene rules

- **One rule per line**, imperative voice. The numbered "do not revert to X"
  list (current rules 53–74) is the gold-standard format — extend it, don't
  prepend prose to it.
- **Target length: 600–900 lines.** If it grows past that, something belongs in
  DECISIONS.md or Docs/.
- **Top-of-file pointer block** (read order for Neo):
  1. Read CLAUDE.md (this file) — authoritative rules + state.
  2. Before methodology/architecture changes → read DECISIONS.md.
  3. Before touching a superseded component → check Docs/ archive.
- **Superseded references stay; superseded detail leaves.** Keep
  *"v1.9 → superseded by v2.0 (see Docs/)"*; delete the v1.9 math.
- **No commit hashes.** Ever.

---

## 7. Guardrails (process discipline)

- **Commit before any cleanup edit** so the prior version is recoverable.
- **Archive, never hard-delete.** Cut content moves to DECISIONS.md or Docs/ —
  a future "wait, why did we…" must remain answerable.
- **One concept at a time.** A full rewrite of the source of truth in a single
  pass is the exact "change everything at once" failure mode the project forbids.
  Edit section-by-section.
- **Shannon reviews the diff.** Neo proposes routing and edits; Shannon approves.

---

## 8. Migration of the existing file (one-time, separate effort)

The one-time cleanup that gets CLAUDE.md from ~2,479 lines to the 600–900 line
target is delivered as a standalone Neo-executable spec:
**`SignalMatrix_CLAUDEmd_Migration_Spec_v1_0.txt`**.

Shape: Neo runs a **read-only triage pass** (classifies every Known Fixes entry
into keep-as-rule / split-to-ADR / delete / archive-to-Docs), outputs a TRIAGE
table, and **stops for Shannon's approval**. Only the approved table is executed,
section-by-section. See the migration spec for the full sequence.

---

## Decision log for this protocol
- **Resolved:** No CHANGELOG.md — `git log` + disciplined commit messages are the *what*.
- **Resolved:** DECISIONS.md at repo root, ADR-lite format.
- **Resolved:** Top-of-CLAUDE.md pointer baked in — *"Read DECISIONS.md before any methodology/architecture change."*
- **Resolved:** Migration delivered as a standalone Neo spec with a triage-and-approve gate (`SignalMatrix_CLAUDEmd_Migration_Spec_v1_0.txt`).
