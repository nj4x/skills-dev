# refactor-tests reference: Review queue (Step 11)

Split from `patterns.md`, which holds the other schemas and conventions.

`reference/python/render_review_queue.py` turns the run's human-action items into `.scratch/refactor-tests/review-queue.md` and, with `--stage`, into `to-tickets` drafts. Decisions: ADR-0079, amended by ADR-0080.

**Items and keys.** Each item belongs to one category and has the key `<category>|<criterion>|<id>`:

| Category | Source | Criterion | Id | Label |
|---|---|---|---|---|
| review | plan `review_candidates` | `dead-test`, `coverage-subset`, `cost`, `pinning` | `<file>::<test_name>` | `ready-for-human` |
| fix | plan `review_candidates` | `order-dependent`, `flaky` | `<file>::<test_name>` | `ready-for-agent` |
| hotspot | plan `review_candidates` | `hotspot` | `<function>` | `ready-for-agent` |
| add | plan `seams.add_candidates` | `untested-seam` | `<module>::<seam>` | `ready-for-agent` |
| skipped | ledger `simplification.parametrizations` with `skipped` | `skipped-parametrization` | `<file>::<consolidated_name>` | `ready-for-human` |
| skipped | ledger `spring.skipped_clusters` | `skipped-spring-cluster` | `<cluster>` | `ready-for-human` |

**Grouping.** One ticket per category, criterion, and module. Dead-test and pinning items also split by `kind`: one ticket per criterion, kind, and module, with the kind in the title. A pinning `collaborator-double` ticket is labelled `ready-for-agent`; every other review ticket stays `ready-for-human`. Every pinning `boundary-double` item still becomes a `ready-for-human` ticket, although the double is allowed: the ticket carries the keep-the-double, do-not-delete text, so a reviewer who sees the flag knows no deletion is wanted. A dead-test `no-raise-contract` item is never ticketed: `render` leaves it out of the queue and counts it in its output under `report_only`. The helper accepts an item with any `kind` value, or none. Any string kind on a dead-test or pinning item splits the ticket, also one the helper has no text for. A kind on another criterion, or a non-string kind, shows in the item line and does not split the ticket. The module is the test file's directory, the source module for add candidates, the cluster for Spring clusters, and the function for a hotspot, so each hotspot gets its own ticket, titled `Fix cost hotspot <function> in the test tier`. A group over 25 ids splits into tickets titled `(part i of n)`. Tickets are numbered fix first, then hotspot, review, add, and skipped, so every hotspot ticket comes before every review ticket. Each ticket lists its ids with an evidence excerpt of at most two lines, plus `call_s` and `time_saved_s`, `note`, `failing_ids`, the skipped `tests`, or the Spring `classes` when the item has them; a hotspot item lists its `share`, profiled `tests`, `subprocess_spawns` per test, and `via`. Two blocking edges: a fix ticket blocks each review ticket that holds a test matching one of its ids (`order_gate.matches`); a hotspot ticket blocks each `cost` and `coverage-subset` ticket that holds a test in the directory of one of the hotspot's `tests`, because fixing the hotspot changes their `call_s` order (ADR-0080 Decision 2). A hotspot ticket's text (`WHAT["hotspot"]`) says: "Fix this in the test tier (a fixture or stub), never by deleting tests. Re-run the evidence pass after the fix, because `call_s` order changes." A review ticket's "What to build" text depends on its criterion (`WHAT["review"]`): coverage-subset, cost and pinning carry the mutation-gate caveat (see `patterns.md` → What each criterion proves). A known kind replaces that text (`review_what`): a dead-test ticket states its kind's disposition (no kind reads as `no-assertion`), and a pinning `collaborator-double` ticket says "Re-point the stub (deps injection or a checked patch); do not delete." with no mutation-gate caveat. Other pinning kinds keep the pinning text. A fix ticket ends its text with a `Reproduce:` command built from the ledger `runners.python` command, the `order_gate.plugin` install, and the seed, for example `uv run --with pytest-randomly pytest -p randomly --randomly-seed=<seed> <file>`. Every ticket body, and `spec.md`, carries the line `git_sha: <sha>`, read from the evidence file's `git_sha`, so a later agent can tell whether the list is stale; it reads `git_sha: unknown` when there is no evidence file or its `git_sha` is `null`.

**Volume gate** (ADR-0080 Decision 3). `render` counts the tickets it would stage after dedupe, hotspot tickets included, before any triage, and prints `volume: { tickets, threshold: 50, over, action, choice, chosen_by }`. With `--tracker local|real`, `action` is `publish` (`tickets` at most 50), `ask` (interactive), `triage` (`--unattended` on the local tracker; `render` then stages option (b) itself and prints `triage: true`), or `drafted` (`--unattended` on a real tracker); without `--tracker` it is `null`. The gate's answer is recorded in `choice` and `chosen_by`:

| Gate | `action` | `choice` | `chosen_by` |
|---|---|---|---|
| 50 tickets or fewer, no answer | `publish` | `null` | `null` |
| interactive, not yet answered | `ask` | `null` | `null` |
| unattended, local tracker, no answer | `triage` | `b` | `unattended-default` |
| unattended, real tracker, no answer | `drafted` | `null` | `unattended-default` |
| any count, any attendance, `--choice a` | `publish` | `a` | `asked` |
| any count, any attendance, `--choice b` (or `--triage`) | `triage` | `b` | `asked` |
| any count, any attendance, `--choice c` | `declined` | `c` | `asked` |

An explicit answer wins over the gate's default, at 50 tickets or fewer and in an unattended run too, and the staging follows the recorded action: `triage` stages option (b), `publish` and `declined` stage every ticket (under `declined` Step 11 publishes none of them). Without `--choice`, `render` reuses the `choice` recorded in ledger `publish.volume` only when its `chosen_by` is `asked`, as if it were passed again, so a resumed run does not ask again and an unattended resume keeps the human answer. The recorded answer decides only the staging: Step 11 item 3 still records `publish.status: drafted` on an unattended real-tracker run, so `volume.action` may be `publish` or `triage` while `publish.status` is `drafted`. A recorded `unattended-default` is never reused: the gate is computed again, so an interactive resume still asks. `--triage` is an alias of `--choice b`; the two flags are mutually exclusive. Option (b) stages:

| Staged under (b) | Ticket |
|---|---|
| fix, hotspot, add | Unchanged, with their `key:` lines. |
| review (dead-test, coverage-subset, cost, pinning) | One triage ticket per review criterion with at least one review ticket, in the review tickets' place. |
| skipped (parametrization, Spring cluster) | Not staged; listed in `review-queue.md` only. |

A triage ticket is titled `Triage <n> <criterion> tests from the review queue` (`test` when `<n>` is 1), labelled `ready-for-human`, and numbered where the review tickets were (after hotspot, before add). Its body says to triage by module and hotspot before per-test review, links `.scratch/refactor-tests/review-queue.md` and `.scratch/refactor-tests/run-summary.json`, and lists its tests per module (`- <module>: <n> tests`), with no `key:` line; its `tickets.json` entry has `keys: []` and `criterion: <criterion>`. Its items stay out of the cross-run index and queue again next run (ADR-0080 Consequences). It takes the blocking edges of the review tickets it replaced: a fix ticket blocks it when it holds a matching test, and a hotspot ticket blocks the `cost` and `coverage-subset` triage tickets of its directories. A hotspot edge to a criterion with no triage ticket is dropped. `review-queue.md` lists every per-test ticket in either mode.

**Run summary** `.scratch/refactor-tests/run-summary.json`: every `render` call writes it, `--rekey-only` included, so every Step 11 path leaves one. It is small enough to commit.

```json
{
  "schema_version": 1,
  "started_at": "2026-10-16T19-26-00",
  "stopped_at": null,
  "git_sha": "3f2c9a1e0b7d4c6a8e5f1b2d3c4a5e6f7a8b9c0d",
  "dirty": false,
  "runner": { "python": "uv run pytest" },
  "seed": 1234567,
  "evidence_status": "ok",
  "counts": { "coverage-subset": 412, "cost": 41, "dead-test": 33, "pinning": 1813, "hotspot": 1 },
  "kinds": { "dead-test/no-raise-contract": 31, "dead-test/no-assertion": 2, "pinning/collaborator-double": 577 },
  "report_only": { "dead-test/no-raise-contract": 31 },
  "excluded": { "failed": 2, "skipped": 14, "no-coverage": 1 },
  "evidence_tests": 3120,
  "shares": { "coverage-subset": 0.132, "cost": 0.0131, "dead-test": 0.0006, "pinning": 0.5811 },
  "warnings": ["pinning flags 58% of evidence tests: criterion is not discriminating on this suite; triage by module and hotspot before per-test review"],
  "concentration": {
    "by_candidates": [ { "module": "tests/protrading/db", "candidates": 640 } ],
    "by_call_s": [ { "module": "tests/protrading/db", "call_s": 812.4 } ]
  },
  "hotspots": [ { "criterion": "hotspot", "function": "src/protrading/db/connection.py:connect", "share": 0.84, "tests": ["…"], "subprocess_spawns": {}, "via": [] } ],
  "call_time": { "before_s": 861.7, "after_s": 858.2 },
  "volume": { "tickets": 765, "threshold": 50, "over": true, "action": "triage", "choice": "b", "chosen_by": "asked" },
  "notes": []
}
```

- `git_sha`, `dirty`: from the evidence file, the same source as the ticket bodies; `null` when there is no evidence file or it holds `null`. `runner` is ledger `runners`. `seed` is ledger `order_gate.seed`, `null` when the gate did not run. `stopped_at` is the `--stopped-at` value.
- `counts` per plan `review_candidates` criterion and `kinds` per `<criterion>/<kind>`, both counted before `no-raise-contract` items are dropped; `report_only` as in the `render` output. `null` with no plan.
- `excluded`: evidence `excluded` entries per outcome, all languages; `null` with no evidence file.
- `shares`: per review criterion, distinct flagged tests divided by `evidence_tests` (the entries of the `ok` language blocks). `warnings` holds one line per criterion whose share is above 0.5. Both need evidence `ok`: otherwise `shares` is `null` and `warnings` is empty. A dead-test `no-raise-contract` test is never ticketed, so it counts in no share and raises no warning; a criterion whose only candidates are report-only has no `shares` key.
- `concentration`: top 15 modules (test file directories) by review candidate count, and by the summed `call_s` of their review candidates, a test flagged both coverage-subset and cost counted once. Dead-test `no-raise-contract` candidates are left out, as in `shares`. `null` with no plan.
- `hotspots`: the plan's hotspot entries; `[]` when the probe found none or did not run.
- `call_time`: ledger `simplification.call_time` `before_s` and `after_s`; `null` when evidence is not `ok`.
- `volume`: the volume gate as `render` printed it, `choice` and `chosen_by` included (see Volume gate); `null` after `--rekey-only`. The last render wins, so after the user answers the gate the file holds the answer.
- `notes`: one line per field left `null` (or `[]`) and why: no evidence file, evidence not `ok` with each language's reason, no plan, no seed, no hotspot, no call-time totals.

**Staged files** under `.scratch/<slug>/`, where the slug is `refactor-tests-review-<started_at>` lowercased (the `to-tickets` slug rule applied to the title `refactor-tests review <started_at>`):
- `spec.md`: that title as H1, `Project: <name>`, item counts, already-tracked items, and a "Proposed tickets" table (NN, title, label, blocked by).
- `draft-issues/<NN>-<slug>.md`: the `to-tickets` spec-linked template with `label:` in its frontmatter and the same value under `## Status`.
- `manifest.md`: `artifact-type: tickets` frontmatter, then the draft paths in order.
- `tickets.json`: `{ slug, tickets: [ { nn, slug, keys } ] }`, which `record` reads. A triage ticket's entry is `{ nn, slug, keys: [], criterion }`; `record` builds the triage sentence it looks for from `criterion`, never from the slug. An entry with no `criterion` is credited by name only.

**Cross-run index** `.scratch/refactor-tests/review-index.json`: `{ schema_version: 1, entries: { <key>: { ref, slug } } }`. `render` maps each entry's id through the ledger's `id_map`, or, when `id_map` has no entry, through its `moves` (old file to new file), before comparing keys. `render` then writes the re-keyed entries back, except after a layout regression (`--stopped-at failed-layout`, whose moves the user may revert; Phase A moves stay in the tree after a later regression), so a test moved in this run still matches its entry when a later ledger no longer holds the move. `render --rekey-only` does only the re-key, for a run with `--no-publish-review`; it needs no `--plan`. If two entries re-key to the same key, the first is kept. Only `record` adds entries, and only for published tickets. A ticket counts as published when `--ref` names it, when a manifest line reads `<tracker-ID> <name>` (`<name>` is `<NN>-<slug>`, any number of digits, `.md` optional), or when `issues/<name>.md` exists. Its body is `issues/<name>.md` or `draft-issues/<name>.md`. Each ticket item line ends with `` key: `<key>` ``. An item is credited to the published ticket whose body holds its full key in backticks, so a ticket `to-tickets` renamed, merged, or split still counts. A triage ticket (option (b); its `tickets.json` entry has `keys: []` and its `criterion`) has no key to credit: it counts as published when a published name is its `<NN>-<slug>`, or when a published body holds the triage sentence of its entry's `criterion` (`stands for every <criterion> test it flagged`), and it adds no index entry. `record` prints `{ status, tickets, unpublished, unmatched }`: `status` is `published` (every key and every triage ticket credited), `drafted` (none), or `partial` (some; Step 11 maps it to the ledger status); `tickets` holds one `{ ref, keys }` per credited ref, a triage ticket's with `keys: []`; `unpublished` lists every key no published body names, then the `<NN>-<slug>` of every triage ticket not published; `unmatched` lists published names with no body file. An entry suppresses its item whatever the ticket's tracker state; delete the entry to re-ticket the item. `render` reports an earlier `refactor-tests-review-*` directory as superseded when it has `draft-issues/`, no `issues/`, no manifest line with a tracker id, and no index entry.

**Ledger `publish`**: `{ status, slug, parent, volume, tickets: [ { ref, keys } ], already_tracked: [ { key, ref } ] }`. `volume` is the last `render` output's `volume`; `render` reuses its `choice` on resume only when `chosen_by` is `asked`. `tickets` is `record`'s `tickets`: a published triage ticket appears as `{ ref, keys: [] }`, so the report still has one line per ticket, while `entries` in the cross-run index never hold it.

| `status` | Meaning | Final |
|---|---|---|
| `skipped` | `--no-publish-review` given. | yes |
| `queued` | Queue file written; publish not yet attempted. A resume reruns Step 11 from item 2. | no |
| `publishing` | `to-tickets` called; it may have published some or all tickets. A resume goes to `record` (item 6). | no |
| `local-only` | No `docs/agents/issue-tracker.md`, or a gate regressed. Queue file only. | yes |
| `empty` | Zero items after dedupe. No parent, no `to-tickets` call. | yes |
| `drafted` | Drafts staged, nothing published. | yes |
| `declined` | The user chose (c) at the volume gate: not to publish. Queue file and drafts kept; nothing published. A resume never retries it. | yes |
| `published` | `to-tickets` finished without a pass 1 or 2 failure. Pass-3 sub-issue fallbacks count as published. Items no published body names are reported as not ticketed and queue again next run. | yes |
| `failed` | `to-tickets` real-tracker pass 1 or 2, or a local-tracker promotion, stopped partway. | yes |
