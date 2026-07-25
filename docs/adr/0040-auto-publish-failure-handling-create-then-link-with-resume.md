# Auto-publish failure handling: create-then-link, stop-and-report on partial failure

(Filename retains the historical `with-resume` slug; the accurate title is above. The resume subsystem is descoped from this ADR and deferred to ADR-0041 — see "Scope" below.)

ADR-0034 auto-publishes an approved artifact to the configured tracker. For a real tracker (GitHub, Linear), `to-tickets` publishes **N issues plus cross-issue blocking links**, and any step can partially fail (network, auth, rate limit), potentially leaving created issues with dangling edges. This ADR defines the publish **ordering** and the **immediate failure response**. (`to-spec` publishes a single document, so its failure surface is small; the same principles apply.)

**Scope of this ADR (descoped):** this ADR now covers only (a) the two-phase create-then-link ordering and (b) a **stop-and-report** response to partial failure. A full **resume / idempotency-by-slug subsystem** (persisted publish map, skip-existing on re-run, link-pass resume) is a logically separable concern and is **deferred to a future publishing-reliability ADR** (see "Deferred to a future ADR" below and ADR-0041, proposed). Rollback remains rejected here on its own merits; the alternative is report-and-let-a-human-decide, not automated resume.

## Two-phase ordering: create all, then link

Publishing runs in two ordered passes so a link never references a not-yet-created issue:

1. **Create pass** — create every issue in dependency order, driven by the **manifest** (ADR-0034, "Publish is manifest-driven"), from the staged draft files. Record each ticket's stable **slug** (its staging filename `<NN>-<slug>`) alongside the returned tracker ID so the link pass can resolve `Blocked by` references.
2. **Link pass** — only after all issues exist, create the native blocking edges, resolving each `Blocked by` slug to its tracker ID.

This ordering is retained as the core decision: interleaving create+link per issue would let a link reference an issue that does not exist yet.

## Local-tracker publish: promotion, not API calls

For the local-file tracker, publishing performs the **promotion steps** defined in ADR-0034 with no create/link API passes:

- **to-spec:** `draft-spec.md` → `spec.md`, stripping the `artifact-type:` frontmatter.
- **to-tickets:** promote each manifest-listed `draft-issues/<NN>-<slug>.md` → `issues/<NN>-<slug>.md`, apply `ready-for-agent`, then remove the `draft-issues/` staging directory.

Local-file promotion is **ordered** — promote all files before removing staging — so a partial promotion failure (permission error, disk full) leaves the source `draft-issues/` directory intact alongside any partially-populated `issues/`. On partial local promotion failure, the skill **stops and reports** which files were promoted and which remain in `draft-issues/`, and does **not** remove the staging directory until all promotions succeed.

A **zero-slice** manifest aborts publish (ADR-0034) before any promotion or API call. A manifest whose `Blocked by` graph **cannot be topologically sorted** (a cycle or a self-block) likewise aborts *before any create call* — the create pass requires a dependency order to exist. In normal operation ADR-0038's post-edit assertion (d) already rejects a cyclic manifest at synthesis time, so this is a defence-in-depth guard for an externally-supplied or hand-edited manifest.

## On partial failure (real tracker): stop and report, do not roll back

Deleting already-created issues is destructive and often not permitted by the tracker, so **rollback is rejected**. This ADR's response is to **stop immediately and report** — it does not attempt automated recovery:

- **Create pass fails midway** — stop and report which slugs were created (slug → tracker ID) and which remain uncreated.
- **Link pass fails** — all issues exist; stop and report the specific `Blocked by` edges not yet created (the **dangling edges**).
- **Reporting** — on any partial failure the skill surfaces: created issues (slug → ID), missing issues, and dangling edges, and states that recovery is manual for now. In headless runs it writes this report to `.scratch/<feature-slug>/publish-report.md` and stops rather than retrying blindly.

Because publish only runs after critic approval (ADR-0034) and the drafts remain staged, a failed publish never loses the *authoring* work: the staged artifact is intact. What is **not** guaranteed by this ADR is automatic, duplicate-free continuation of a half-finished tracker write — that is the deferred subsystem.

## Deferred to a future ADR (publishing-reliability)

The following are explicitly **out of scope here** and deferred (ADR-0041, proposed):

- **Idempotency-by-slug resume:** a persisted slug→ID **publish map** (`.scratch/<feature-slug>/publish-map.json`) so a re-run skips slugs already present and creates only the missing issues, with no duplicates. **Note on the crash window:** the correct approach is a **write-ahead** map — append a slug→ID entry *before* (or atomically with) confirming the issue's creation — so a crash between "issue created" and "map persisted" cannot orphan an issue from its record. Full implementation is deferred.
- **Link-pass resume idempotency:** re-running only the link pass without duplicating edges requires either **querying the tracker for existing edges** or **tracking created edges** locally, so an already-existing link is a no-op. The mechanism is deferred.

Stating these here fixes the *intended* direction (write-ahead, slug-keyed, edge-tracked) without committing this ADR to implement it.

## Considered Options

- **Interleave create+link per issue**: a link would reference an issue that may not exist yet (forward `Blocked by`). Rejected — forces topological pre-ordering of links and still races on rate limits.
- **Rollback on failure (delete created issues)**: destructive, frequently disallowed by tracker permissions, and risks deleting issues a human already started acting on. Rejected in favour of stop-and-report (and, later, resume).
- **Build the full resume/idempotency subsystem in this ADR**: rejected as scope creep — resume is separable from critic integration, and folding it in here blocks the critic-first flow on a reliability subsystem it does not need to ship. Deferred to ADR-0041.
- **Retry the whole publish from scratch (no idempotency key)**: creates duplicate issues. Rejected; the deferred slug-keyed map is the idempotency key when resume is built.
