---
lineage-rules: exempt
---

# ADR-0080: refactor-tests triages its review queue before publishing (amends ADR-0079)

**Status**: Accepted  
**Date:** 2026-10-17  
**Source SRS**: none (lineage exempt; requirements corpus does not exist yet, retrofit tracked in ADR-0065)  
**Amends**: ADR-0079 Decisions 3, 10 and 13

## Context

The first large run of `refactor-tests` (nj4x/pro-trading, 2026-10-16) finished healthy but left a review queue nobody could act on: 9,358 items in 765 staged drafts. The user declined to publish them and built a 10-ticket execution map by hand instead (https://github.com/nj4x/pro-trading/issues/836). Findings and sources: `docs/research/refactor-tests-pro-trading-followups.md`.

Two of the problems are in the ADR-0079 contract itself:

- The slowest tests were slow for one shared reason: a macOS keychain subprocess behind every database connection, about 84% of the slowest test's time. A test-tier stub cut the integration tier from 861.7 s to 89.4 s with no test deleted. ADR-0079 has no category for a shared cost cause, so the run queued 251 per-test cost reviews whose `time_saved_s` read as deletion savings.
- The `publish.status` table has no value for "the user chose not to publish". The run recorded `local-only`, which ADR-0079 defines as "no tracker, or a gate regressed", plus an ad hoc `note`.

## Decision

1. **New `hotspot` category** (amends Decision 3). Step 8 profiles the top 5 cost candidates serially with cProfile. A function that holds at least 50% of call time in at least half of the profiled tests is a hotspot. Each hotspot becomes one item `{ criterion: "hotspot", function, share, tests }` in a fifth category, **hotspot candidates**, labelled `ready-for-agent`. A hotspot is fixed in the test tier (a fixture or stub), never by deleting tests. Python only.
2. **New blocking edge** (amends Decision 10). A hotspot ticket blocks every `cost` and `coverage-subset` ticket whose tests share a test directory with the hotspot's profiled tests, because `call_s` order changes once the hotspot is fixed. The fix → review edge stays. Hotspot tickets are numbered before every review ticket.
3. **Volume gate.** When Step 11 would stage more than 50 tickets, an interactive run asks before it publishes:
   - (a) publish all;
   - (b) publish only fix, hotspot and add tickets, plus one triage ticket per review criterion that links `review-queue.md` and `run-summary.json`;
   - (c) queue file only, recorded as `declined`.

   An unattended run takes (b) on the local tracker and stays `drafted` on a real tracker, as before.
4. **New `declined` status** (amends Decision 13): "The user chose not to publish. The queue file and drafts are kept." Final. A resume never retries it.

   | `publish.status` | Meaning | Final |
   |---|---|---|
   | `declined` | The user chose (c) at the volume gate. Queue file and drafts kept; nothing published. | yes |

   All other rows of the ADR-0079 table stay as they are.

## Consequences

- `render_review_queue.py`, its tests, `reference/patterns.md` (Review queue tables) and `SKILL.md` Steps 8 and 11 change together.
- The volume gate adds a mid-run question. It sits inside the audio-suppression window like the Step 7b seam round, so no new cue is needed.
- A triage ticket under option (b) carries no `key:` lines for the items it summarizes. Those items do not enter the cross-run index and are queued again on the next run, which is the intended effect: the next run, after hotspot fixes, has fresher evidence.
- Profiling adds about five serial test runs to Phase B, also under `--dry-run`. Its output is written only under `.scratch/refactor-tests/`.
- The `to-tickets` contract is unchanged: hotspot tickets use the existing `label:` field and `Blocked by` edges.
