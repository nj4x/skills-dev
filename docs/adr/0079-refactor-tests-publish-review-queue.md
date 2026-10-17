---
lineage-rules: exempt
---

# ADR-0079: refactor-tests publishes its human-review queue as tickets (Step 11)

**Status**: Accepted  
**Date:** 2026-10-16  
**Source SRS**: none (lineage exempt; requirements corpus does not exist yet, retrofit tracked in ADR-0065)

## Context

`docs/research/refactor-tests-wayfinder-rearchitecture.md` asked whether `refactor-tests` should follow wayfinder: one tracking issue with a sub-issue per task. Wayfinder tickets are decisions resolved one per session. `refactor-tests` is a single-run, suite-gated executor whose moves, removals and parametrizations are only valid as a batch, whose ledger already resumes at a finer grain than issues could, and which never commits. The items it hands to a human (review candidates, add candidates, fix candidates, skipped parametrizations, AST warnings, skipped Spring clusters) are different: today they appear only in the Final report, and nothing tracks whether anyone acts on them.

## Decision

Keep the ledger as the source of truth for everything the skill executes. Add **Step 11**, which sends only the human-action items to the tracker.

1. **Rejected options.**
   - A full re-architecture around a map issue with a sub-issue per move, removal or cluster. It costs 1.5 to 3 weeks and loses the single-run, suite-gated, never-commits guarantees.
   - A default-off flag. The items would stay invisible on most runs, which is the problem this ADR fixes.
   - The local checklist alone. A file under `.scratch/` has no owner, no state and no visibility outside the working copy.
2. **Trigger.** Step 11 runs by default. `--no-publish-review` skips it and records `publish.status: skipped`.
3. **Items.** Four categories, each item in exactly one:
   - **Review candidates**: dead-test, coverage-subset, cost, pinning.
   - **Fix candidates**: order-dependent and flaky tests. These are only fix tickets, never review tickets.
   - **Add candidates**: confirmed seams that no interface test reaches.
   - **Skipped work**: parametrizations skipped with AST warnings, and skipped Spring clusters.
4. **Granularity.** One ticket per criterion and module. A group over 25 test ids splits into numbered tickets. Two exceptions:
   - Skipped parametrizations: one ticket per module, listing each skipped group with its AST warning.
   - Skipped Spring clusters: one ticket per cluster, listing its test classes and the reason it was skipped.

   Each ticket carries test ids, evidence excerpts of at most two lines, `call_s` and `time_saved_s`. Fix tickets also carry the seed and `failing_ids`. No raw coverage maps.
5. **Local queue file.** Unless `--no-publish-review` is given, Step 11 always writes `.scratch/refactor-tests/review-queue.md`. It publishes through `Skill("to-tickets")` only when `docs/agents/issue-tracker.md` exists.
6. **Staged artifacts.** A new helper, `reference/python/render_review_queue.py`, writes drafts, a manifest and `spec.md` under the per-run slug `refactor-tests-review-<ledger run timestamp>`. A second run never collides with the first run's published `issues/` directory. The `spec.md` H1 is `refactor-tests review <ledger run timestamp>`, so slugifying it with the `to-tickets` rule gives exactly the per-run slug. The project name goes on the first body line. `spec.md` holds item counts per criterion and a "Proposed tickets" section with the helper's grouping, labels and edges.
7. **Source model.** `to-tickets` always runs in its spec-linked subtype. What changes is whether a parent issue exists.
   - **Local tracker:** the source is `spec.md`. No parent issue; pass 3 never runs.
   - **Real tracker, interactive:** Step 11 creates one parent issue just before it calls `Skill("to-tickets")`. The parent's title is the `spec.md` H1 and its body is the whole `spec.md`, H1 included. Step 11 records the parent ID in `publish.parent` before the call. It then passes the parent as the source. `to-tickets` refreshes `spec.md` from the issue (identical content), and pass 3 makes every ticket a sub-issue of the parent.
   - **Real tracker, unattended:** no parent is created (Decision 8). Only the staged drafts, manifest and `spec.md` exist.
   - **Later manual publish of staged drafts:** the report gives two paths. First path: create the parent issue from `spec.md`, then run `/to-tickets` with that issue as the source; the tickets become its sub-issues. Second path: run `/to-tickets` on `spec.md` alone; the tickets publish with no parent. Both paths land in the same slug directory because the H1 slugifies to it.
   - **Parent left without tickets:** if the interactive `to-tickets` call ends without publishing (critic not approved and the user abandons, or pass 1 fails before any ticket exists), the parent stays open. The report names it so the user can close it or reuse it as the source for a later `/to-tickets`. Step 11 never deletes or closes issues.
8. **Unattended runs** (no `AskUserQuestion`, no user present, or model-invoked). Step 11 puts the line `headless: true` in the `to-tickets` args, and `to-tickets` honours that as well as a missing `AskUserQuestion`, because a model-invoked run may still hold the tool. Against a real tracker, stage drafts only and report "drafts ready, publish with `/to-tickets`" with the two paths of Decision 7. Against the local tracker, publish. Interactive runs use the normal `to-tickets` quiz and critic loop. The quiz gets the helper's grouping and edges as its proposal; there is no bypass.
9. **Labels.** `to-tickets` gains an optional per-ticket `label:` field that defaults to `ready-for-agent`. No `wayfinder:*` labels.
   - `ready-for-human`: review candidates, skipped parametrizations (each needs a manual merge decision), and skipped Spring clusters (each needs a configuration judgment).
   - `ready-for-agent`: fix candidates and add candidates.
10. **Blocking.** The only edge: a fix ticket blocks any review ticket that shares test ids with it, because a test that fails in random order gives no stable evidence to review until it is fixed.
11. **When it runs.** After a healthy finish (Step 10 or Phase C) and after `--dry-run`. A dry-run then ends at `phase: done`, so the real run after it starts a fresh ledger with its own `started_at` and slug. After a gate regression it writes only `review-queue.md`, marked "run stopped at <phase>; candidates may be stale", and records `publish.status: local-only`.
12. **Cross-run dedupe.** Step 11 keeps a cross-run index at `.scratch/refactor-tests/review-index.json`. Each entry maps a key `(category, criterion, test id)` to the ticket reference and the run slug that published it.
    - **Before staging**, the helper drops every item whose key is already in the index. `review-queue.md` and the report list those items under "already tracked", each with its ticket reference.
    - **Moved tests**: the helper first maps index test ids through the current run's ledger move records (old id to new id). A dry-run followed by the real run therefore does not re-ticket a candidate whose test the real run moved.
    - **Re-keying**: after mapping, `render` writes the re-keyed entries back, so a moved test stays tracked in later runs whose ledgers no longer hold the move. A `--no-publish-review` run re-keys too. A layout regression (`failed-layout`) does not re-key, since the user may revert its moves; after a later regression the Phase A moves stay in the tree and are re-keyed.
    - **Write rule**: only published tickets enter the index, after `to-tickets` reports them. Unpublished drafts never enter it, so a later run re-stages those items.
    - **Re-ticketing**: an entry suppresses its item whatever the ticket's tracker state. To re-ticket, delete the entry. Step 11 does not query the tracker.
    - **Superseded drafts**: if an earlier `refactor-tests-review-*` slug has drafts but no published `issues/`, the report names it as superseded by the current slug.
13. **Ledger.** Add `publish: { status, slug, parent, tickets[], already_tracked[] }`. Each `tickets[]` entry holds the ticket reference and its keys. `failed` is reported with created and uncreated tickets and never changes the run's health result. Idempotent resume of a partial publish stays deferred under ADR-0041.

    | `publish.status` | Meaning | Final |
    |---|---|---|
    | `skipped` | `--no-publish-review` given. | yes |
    | `queued` | `review-queue.md` written; publish not yet attempted. A resume reruns the rest of Step 11. | no |
    | `publishing` | `to-tickets` called; it may have published some tickets. A resume goes straight to recording what was published. | no |
    | `local-only` | No `docs/agents/issue-tracker.md`, or the run stopped at a gate regression. Queue file only. | yes |
    | `empty` | Zero items after dedupe. Queue file says so; no `to-tickets` call, no parent. | yes |
    | `drafted` | Drafts staged, nothing published: unattended real-tracker run, or the critic did not approve and the user did not publish. | yes |
    | `published` | `to-tickets` finished without a pass 1 or 2 failure. Pass-3 fallbacks still count as published. Items no published ticket names (a slice dropped in the quiz) are reported as not ticketed and queue again next run. | yes |
    | `failed` | Real-tracker pass 1 or 2, or a local-tracker promotion, stopped partway. | yes |

    A resume never retries a final status.

## Consequences

- New helper and tests in `reference/python/`, new Step 11 and ledger schema in `SKILL.md` and `reference/patterns.md`, and an optional `label:` field in `to-tickets` (a shared contract change).
- New dependency edge `engineering/refactor-tests` to `engineering/to-tickets` in `docs/agents/skill-dependencies.md`, inheriting the `setup-skills` requirement. It is optional at runtime: no tracker means the queue file only.
- Default-on means a model-invoked run can reach the publish step. Decision 8 is the guard: an unattended run never creates issues, the parent included, on a real tracker.
- The cross-run index is local to one working copy. A run from another clone, or after `.scratch/` is deleted, can publish duplicates. A test renamed outside a refactor-tests run also escapes dedupe.
- Fix candidates come from the plan's demoted entries (`review_candidates` with `order-dependent` or `flaky`). A fix ticket therefore lists every test of a demoted change, and a gate-flagged test that no planned change touches gets no ticket; it stays in the Final report only.
- A skipped Spring cluster's id is built from its annotations and mocked types, so adding a mock gives the cluster a new key and a second ticket.
- An interactive run that ends without publishing can leave an open parent with no sub-issues.
- A partial real-tracker publish needs manual cleanup until ADR-0041 lands.
- Estimate: 1.5 to 2.5 days (the cross-run index adds about half a day).
