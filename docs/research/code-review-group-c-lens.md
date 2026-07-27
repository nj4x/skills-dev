# Research: Group C / Edge Cases lens — context-awareness for high-level artifacts

**Date:** 2026-07-27  
**Sessions analysed:**
- `553fae1b` (Jul 26 23:57) — to-tickets critic loop, 86 [C] findings
- `302f4e7e` (Jul 26 23:40) — to-spec critic loop, 48 [C] findings
- `60d680a5` (Jul 26 22:38) — grilling session, 54 [C] findings (applied to ADRs)
- `21ee2cb1` (Jul 26 18:48) — grill-with-docs, 168 [C] findings
- `e9de2fd7` (Jul 25 18:33) — tickets loop (12 passes, amon-watchlist-wiring)
- `70c800f8` (Jul 25 17:32) — forensic analysis of the above

---

## 1. Skill clarification

The "group C / edge cases" lens lives in the **critic skill**, not the code-review skill.

| Skill | Path | Groups / Finders |
|---|---|---|
| critic | `planning/critic/SKILL.md` | GROUP A/B/C/D/E/F — runs on plans, specs, tickets, design-review (ADRs) |
| code-review | `dev/code-review/docs/workflow.md` | Finder A/B/C/D — runs on committed git diffs |

The code-review skill's Finder C is "Quality & Standards" (`workflow.md:640`): Kotlin idioms, simplification, efficiency, testing standards, altitude cleanup (TODO comments, magic strings). It is applied to production code in the diff, not to architectural documents.

The critic skill's Group C is "Edge Cases & Robustness" (`planning/critic/SKILL.md:296`). This is the lens the user describes as too clerical for high-level artifacts.

---

## 2. Group C definition

`planning/critic/SKILL.md:296–301`:

```
GROUP C — Edge Cases & Robustness:
You are an adversarial reviewer focused on EDGE CASES and ROBUSTNESS. Evaluate ONLY:
- Missing edge cases: what inputs, states, conditions, or scenarios are not handled?
  Think: empty inputs, concurrent access, permission errors, network failures, boundary conditions.
[IF artifact_type == plan]
- Failure modes and rollback: what happens when each step fails? Is there a rollback path?
  Are there irreversible operations with no guard?
[END IF]
```

Active groups by artifact type (`planning/critic/SKILL.md:257`):

| Artifact type | Groups |
|---|---|
| `design-review` (ADRs) | A / B / C |
| `spec` | A / B / C / D (+ F on iteration 0) |
| `tickets` | A / B / C / D / E (+ F on iteration 0) |
| `plan` | A / B / C / D / E |

Group C is the **only** group that runs identically across every artifact type without an escape hatch or artifact-type-specific scope constraint. Group E for plans has "If this plan has no operational surface, approve immediately" — Group C has no equivalent.

---

## 3. Concrete examples from recent sessions

### 3a. ADRs (design-review) — Session `60d680a5`

```
[C][minor] No ADR addresses how lock loss is detected mid-run: TCP keepalive
prevents silent drops but the spec says 'lock lost mid-run' emits
propose_skipped_lock_contention yet no ADR describes the polling or
connection-health check that would detect the lock has been released before
Stage 3 completes.
```

```
[C][minor] ADR-0052 relies entirely on the fetch boundary to reject naive timestamps
but synthesizer itself has no guard; if a provider adapter passes a naive timestamp
through (bug in adapter), SetupIdea construction is the only safety net — ADR-0052
should explicitly state synthesizer raises ValueError on naive tzinfo.
```

Both findings ask an ADR to document **implementation-level guards** (lock polling frequency, synthesizer-level tzinfo validation) that belong in a ticket or implementation spec. An ADR documents the architectural *decision* (use advisory locking, use UTC-only timestamps) not every guard the implementation must add.

### 3b. Tickets — Session `553fae1b` (86 [C] findings)

Legitimate (catches genuine contract errors):
```
[C][major] Ticket 04 adds source VARCHAR(50) NOT NULL to an existing table without
a backfill step — ALTER TABLE will raise a NOT NULL constraint violation on any
database with existing rows.
```

```
[C][major] Ticket 03 bar_timestamp extraction raises KeyError (missing key) or
ValueError (naive tzinfo) inside synthesize(), but no catch is specified in the
per-bar loop — either exception propagates out and aborts the entire synthesize()
call.
```

Picky (language semantics, implementation internals):
```
[C][minor] Ticket 01: all_warmup on an empty series returns True (Python all([]) is
True) — a zero-length series is silently classified as warming-up rather than
surfaced as a compute error.
```

```
[C][minor] Ticket 06: pg_advisory_unlock is called unconditionally in finally — on
the contention path, pg_try_advisory_lock returned False, so unlocking a never-held
lock is semantically incorrect and may confuse lock-monitoring tooling.
```

The last two are implementation choices that belong in the code itself, not the ticket spec. The ticket doesn't need to enumerate every Python stdlib subtlety or every SQL lock-monitoring edge case.

### 3c. Spec — Speculative DST finding (Session `e9de2fd7`, amon-watchlist-wiring tickets loop)

Group C raised as major:
```
NOT NULL backfill undefined for `session_date` when legacy `scored_at` is NULL,
naive, or lands outside a session window (pre-open, weekend, DST fall-back
duplicated hour). Survivor selection ('latest scored_at') is undefined when
`scored_at` is NULL in a duplicate group.
```

The DST part was later found to be unreachable — `scored_at` is a `TIMESTAMPTZ` column (absolute UTC instant), so there is no "DST fall-back duplicated hour" state. The spec was revised to add an explicit sentence: "There is no DST-ambiguity sub-case. Callers pass `TIMESTAMPTZ`-derived values — absolute UTC instants with no timezone ambiguity" (`442e22d5`, `4dea04ae`). The finding forced prose into the spec to address a non-problem.

The `70c800f8` forensic session (`Line 71`) catalogued the full failure:
> "Group C is unbounded. Only Group E has an escape hatch. Late-pass C findings drift
> speculative (DST fall-back duplicate hour, `US..SPX`, `HK.0700`, tie-order on
> identical timestamps) while still counting as major."

---

## 4. Why Group C is appropriate for code but picky for ADRs and specs

| Artifact | What Group C asks | Problem |
|---|---|---|
| Implementation code | "Does this function handle null input / off-by-one / concurrent writes?" | Concrete and verifiable against the call sites. |
| ADR (design-review) | "Does this architectural decision document every implementation guard?" | ADRs intentionally delegate implementation details to tickets. Asking them to enumerate guards is out of scope and generates speculative findings. |
| Spec | "Does this interface spec handle every boundary state?" | Partially appropriate — a spec *should* define its interface contract at boundaries. But Group C generates findings beyond the spec's stated scope (DST case, Python all([]) subtlety). |
| Ticket | "Does this work-item description enumerate every implementation edge case?" | Tickets describe *what* to build and *how to verify* it. The *how* of internal guards is the implementer's job. Over-specified tickets resist refactoring. |

The core mismatch: Group C's prompt ("empty inputs, concurrent access, permission errors, network failures, boundary conditions") is written for **runnable software**. Applied to a **decision document**, it maps to implementation-level details the document is not meant to capture. Applied to a **ticket**, it maps to internal implementation choices the implementer should own.

---

## 5. Existing mitigations (currently in SKILL.md)

`planning/critic/SKILL.md`:

| Line | Mitigation | Effectiveness |
|---|---|---|
| 272 | "Speculative concerns are capped at minor" | Prevents speculative findings from being major, but minors are still fed to the revision prompt and cause churn |
| 39–51 | Ledger with stable IDs and `status: fixed/accepted` | Prevents re-litigation of the same issue across passes |
| 51 | Convergence guard: `halt = true` when `major_count >= prior_pass` | Prevents infinite loops but doesn't prevent minor-heavy stalls |
| 275–278 | Critic-induced constructs capped at minor after pass 2 | Prevents the spiral where the critic attacks its own induced machinery |

Group C still has **no artifact-type-specific scope constraint** for `design-review`. For ADRs, Group C runs the same prompt it runs for implementation plans.

---

## 6. Recommended improvements

### 6a. Scope Group C differently per artifact type

Specific edit to `planning/critic/SKILL.md:296–301` — replace Group C block with:

```
GROUP C — Edge Cases & Robustness:
[IF artifact_type == plan]
You are an adversarial reviewer focused on EDGE CASES and ROBUSTNESS. Evaluate ONLY:
- Missing edge cases: what inputs, states, conditions, or scenarios are not handled?
  Think: empty inputs, concurrent access, permission errors, network failures, boundary conditions.
- Failure modes and rollback: what happens when each step fails? Is there a rollback path?
  Are there irreversible operations with no guard?
[END IF]
[IF artifact_type IN {spec, tickets}]
You are an adversarial reviewer focused on EDGE CASES and ROBUSTNESS. Evaluate ONLY:
- Boundary conditions *within the artifact's stated interface contract*: cases the spec/ticket
  explicitly claims to handle but has a gap. Do NOT generate findings about internal implementation
  choices (choice of algorithm, internal guard placement, language-level subtleties like
  `all([]) == True`) — those are the implementer's domain.
- Undefined state transitions: are there states or transitions in the spec's own state machine
  that are unreachable or unspecified? Only if the spec's own language implies they exist.
- Concrete failure scenario required for any major finding: quote the spec/ticket section that
  implies the behavior should be handled; speculative "could happen" findings are minors.
[END IF]
[IF artifact_type == design-review]
You are an adversarial reviewer focused on DECISION-LEVEL OMISSIONS. Evaluate ONLY:
- Unspecified failure policy at the architectural level: what happens when the core mechanism
  this ADR introduces fails as a whole? (Not: what guards should the implementation add.)
- Missing scope boundary: does the ADR leave ambiguous whether a class of cases is in-scope
  or out-of-scope for this decision?
- If the decision document does not claim to specify algorithmic behavior, approve immediately
  with severity "none" for this group — do not invent implementation requirements.
[END IF]
```

### 6b. Gate auto-approval on major_count == 0, not on merged severity string

The repeat contract's approval condition appears to consume the merged `severity` string. Minors from Group C block approval even when no majors exist. The REVIEW_STEP should feed only `major_count` to the approval condition, not `severity`. Minor findings should be recorded in the ledger but not block the loop.

This change belongs in the repeat contract (`planning/repeat/SKILL.md`) rather than critic, but critic's REVIEW_STEP should enforce it: after REVIEW_STEP, set `halt_condition` only when `major_count > 0`. Minors accumulate in the ledger for the final report but do not trigger a revision pass.

### 6c. Do not feed minor findings to the revision prompt

Currently `top_issues` (which mixes majors and minors) is fed verbatim to the synthesizer. The synthesizer then adds machinery to address minor findings, which Group C then attacks in the next pass. Feed only major findings to the revision prompt; minors are reported but not revised.

---

## 7. Which current Group C checks are reasonable for each artifact type

| Group C check | Code | Spec | Tickets | ADRs |
|---|---|---|---|---|
| Empty/null input handling | Yes | Yes (if spec claims to handle it) | Minor at most | No |
| Concurrent access / race | Yes | Yes (if spec involves concurrency) | Minor at most | No |
| Permission / auth errors | Yes | Only for auth-facing specs | No | No |
| Network / DB failures | Yes | Yes (if spec defines error policy) | No | No |
| Boundary arithmetic (div-by-zero, off-by-one) | Yes | Yes | Yes | No |
| Missing migration backfill | N/A | Yes | Yes | No |
| Language-level subtleties (all([]) == True) | Yes | No | No | No |
| DST / timezone edge cases | Yes | Only if TIMESTAMPTZ not used | No | No |
| Lock semantics details | Yes | Only if lock policy is spec'd | No | No |
| Implementation guard placement | Yes | No | No | No |

---

## Source citations

| Claim | File | Location |
|---|---|---|
| Group C definition (current) | `planning/critic/SKILL.md` | Lines 296–301 |
| Active groups by artifact type | `planning/critic/SKILL.md` | Line 257 |
| Group E operational escape hatch | `planning/critic/SKILL.md` | Lines 309–312 |
| Speculative-cap rule | `planning/critic/SKILL.md` | Line 272 |
| Ledger implementation | `planning/critic/SKILL.md` | Lines 39–51 |
| Convergence guard | `planning/critic/SKILL.md` | Line 51 |
| Code-review Finder C (Quality & Standards) | `dev/code-review/docs/workflow.md` | Lines 640–651 |
| ADR lock-loss finding | Session `60d680a5` | Content search: `[C][minor] No ADR addresses how lock loss` |
| ADR naive-timestamp finding | Session `60d680a5` | Content search: `[C][minor] ADR-0052 relies entirely` |
| all_warmup/Python finding | Session `553fae1b` | Content search: `[C][minor] Ticket 01: all_warmup` |
| pg_advisory_unlock finding | Session `553fae1b` | Content search: `[C][minor] Ticket 06: pg_advisory_unlock` |
| DST fall-back speculative finding | Session `e9de2fd7` | Content search: `DST fall-back duplicated hour` |
| DST finding rebuttal in spec | Sessions `442e22d5`, `4dea04ae` | Content search: `no DST-ambiguity sub-case` |
| Group C unbounded assessment | Session `70c800f8` | Line 71 assistant message |
