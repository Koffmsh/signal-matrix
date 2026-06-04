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

<!-- Newest at top. First ADRs land here during the CLAUDE.md migration (M2). -->

_No entries yet — populated during migration Phase M2 and ongoing via "Log this change."_
