# refactor-tests reference: Mutation deletion gate

Split from `patterns.md`, which holds the other schemas and conventions.

Optional follow-up, per module; see `SKILL.md` → Follow-up: mutation deletion gate (optional). Coverage-subset is not redundancy: on one pro-trading module, deleting the flagged set would have dropped the mutation score from 26/28 to 11/28. A first summary also counted excluded `no-coverage` tests as non-killers, which turned "15 of 26" into "21 of 26". Neither mutmut nor Cosmic Ray records which test killed a mutant, so the gate compares two runs.

**Contract.** Delete test T only if every mutant T kills is also killed by some kept test. Tests listed under evidence `excluded` are kept tests: they count as killers, never as candidates.

**Recipe.**

1. Run mutmut twice on module M, scoped to M's covering tests: once as is, once with the candidate batch deselected. A mutant killed in the first run and surviving the second is a lost kill.
2. A timeout counts as killed in both runs. A mutant with a non-deterministic outcome counts as lost.
3. Re-run only the lost mutants without fail-fast, to build the restore list: the tests to keep.
4. Use batches of 25 candidates.
5. Leave migrations and generated code out of the count. mutmut reads `mutate_only_covered_lines` and `do_not_mutate` only from project config: rely on them if the project already sets them; otherwise drop mutants in those files from both runs when comparing.
6. Install mutmut ephemerally, as Step 7 does. Edit no project config.
7. Run the gate after the hotspot fixes. It is about 9.6x cheaper once a shared cost is gone.

The gate is advice, not a build dependency. It does not write the reserved `kill_set` key of the evidence file. Porting a helper waits until pro-trading #843 proves its tool.
