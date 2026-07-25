# Wire up cross-process Report Build Claim via SQLite CAS

The `reports_claimed_build_id` and `reports_claim_lease_seconds` columns were written by
`community_orchestrator._run_reports_attempt` unconditionally — providing in-process
single-flight via `_reports_tasks` but no real cross-process exclusivity (the lease value
was written but never read). A second process could begin report generation while the
first was mid-flight. We decided to make the Report Build Claim a genuine cross-process
mutex by implementing `claim_report_build` as a SQLite CAS:

1. `BEGIN IMMEDIATE` + `_write_lock` (matches `claim_community_build` exactly)
2. Read `reports_claimed_build_id`, `reports_claim_expires_at`, `reports_claim_token`,
   and `reports_committed_build_id` from `meta` inside the transaction
3. Return `None` if: reports are already committed for this `build_id`, OR a live claim
   exists **for this same `build_id`** (`claimed_build_id == build_id AND
   claim_expires_at > now`). A claim for a *different* `build_id` is from a prior
   generation and is superseded unconditionally — this prevents a stale
   prior-generation claim from blocking a genuinely new detection build.
4. Mint a fresh UUID token; write `claimed_build_id = build_id`,
   `claim_expires_at = now + lease_seconds`, `claim_token = token`; commit
5. Return the token to the caller; the caller stores it for use with
   `clear_report_claim(root_id, token)` on the failure/cancellation path

On a successful `commit_report_build` that same transaction also nulls out
`claimed_build_id`, `claim_token`, and `claim_expires_at`, clearing the slot so it
cannot block the next generation during the remaining lease window. `commit_report_build`
is itself ownership-checked (ADR-0022): it applies only when `claimed_build_id` and
`claim_token` still match the committing process, so a superseded prior-generation
commit is a no-op rather than clobbering the current generation's committed ID and live
claim.

`claim_report_build` returning `None` is handled by fail-fast: `_run_reports_attempt`
returns immediately with no retry. The in-process single-flight (`_reports_tasks`)
prevents unnecessary CAS contention; the SQLite CAS is the second line of defence for
separate processes sharing the same `GRAPH_DB_DIR`.

## build_id determinism: convergent output vs. claim identity

Report `build_id` is deterministic: `community_orchestrator.py` sets
`build_id = committed_build_id` — detection's already-committed ID, never a fresh
`uuid4()`. Two properties follow from this, which must be kept separate:

**Property 1 — Convergent output (used to justify tolerating duplicate builds).**
Because both processes work with the *same* `build_id`, `commit_report_build` is an
idempotent write of the same value (ADR-0022). Duplicate builds waste LLM
calls but cannot diverge or corrupt committed state. The LLM-generated report *payloads*
are themselves non-deterministic and may differ between the two racing processes; the
convergence guarantee is over committed *state*, not payload bytes. Report rows are keyed
by `(community_id, build_id)` and written as idempotent upserts, so a duplicate build
overwrites rather than interleaves, and only the owner's ownership-checked
`commit_report_build` finalizes Report Coverage. This convergence argument applies to
same-`build_id` races. Cross-generation overlap (a stale build from a prior generation
finishing late) is bounded separately: the commit ownership check makes the stale commit
a no-op, and Report Coverage is gated on the current `build_id`, so a late
prior-generation build cannot satisfy coverage for the new generation — the current
generation re-runs and self-heals.

**Property 2 — `build_id` is NOT a per-claim identity token.**
Since two processes competing for the same generation share the `build_id`, keying
`clear_report_claim` on `build_id` would allow the losing process's failure path to wipe
the winner's live claim. We therefore use a per-claim UUID token (ADR-0022,
`reports_claim_token`) as the ownership discriminant for release — minted fresh on each
successful claim call, unique per claim instance rather than per generation.

## Lease duration and the duplicate-build risk

The claim uses a **fixed lease with no renewal/heartbeat**, identical to
`claim_community_build`. This admits one failure mode: if a report build outlives
`lease_seconds`, the claim expires and a second process can acquire the slot and redo
the whole LLM build. We accept this risk explicitly rather than adding heartbeat renewal,
for three reasons:

1. **Bounded, self-healing waste, never corruption.** By Property 1 above, both processes
   converge on identical output. A duplicated build wastes LLM calls but cannot corrupt
   committed state.
2. **The lease is sized to dominate worst-case build time.** `reports_claim_lease_seconds`
   defaults to comfortably exceed the observed p99 report-build wall-clock for the largest
   supported corpus. Operators indexing unusually large roots are expected to raise it.
   Because the lease guards a coarse-grained, minutes-scale operation, a generous fixed
   lease is cheap.
3. **Consistency with `claim_community_build`.** That claim already makes the same
   fixed-lease trade-off. Introducing heartbeat renewal for reports alone would add a
   background timer, renewal-failure handling, and a divergent lifecycle for no
   proportional benefit. If lease overruns are ever observed in practice, adding renewal
   symmetrically to both claims is a contained follow-up.

**Release is owner-checked via token.** On failure or cancellation the orchestrator calls
`clear_report_claim(root_id, claim_token)` (ADR-0022), which clears only when
`reports_claim_token` matches. After a lease overrun and re-claim by a second process,
the second process's fresh token differs from the first process's stale token, so the
first process's `clear_report_claim` is a safe no-op.

## Assumptions

**Single-host clock.** Absolute-epoch leases (`reports_claim_expires_at =
now + lease_seconds`, read back as `expires_at > now`) assume all competing processes
share a coherent clock. This holds for same-host processes on a shared local
`GRAPH_DB_DIR` — the only supported topology, matching `claim_community_build`. A
networked or multi-host `GRAPH_DB_DIR` (e.g. SQLite over NFS) is unsupported and would
break both the lease TTL and SQLite's own locking.

## Considered Options

**Best-effort write (overwrite unconditionally):** Rejected — the cross-process guard
would be advisory.

**Retry on CAS failure:** Rejected in favour of fail-fast: the next consumer trigger (or
startup sweep) will re-evaluate.

**Key `clear_report_claim` on `build_id` instead of a token:** Rejected because `build_id`
is deterministic (same across processes for the same generation), so a stale process's
release would match the new owner's live claim and wipe it — the exact hazard the
ownership check is meant to prevent.
