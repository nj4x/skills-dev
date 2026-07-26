# Critic: evidence-gated major severity

Every `major`-severity finding in the critic skill must be backed by explicit evidence — an artifact quote, a `file:line` citation, or a scenario articulation with stated impact. Speculative findings without evidence are capped at `minor`.

## Context

During the amon-watchlist-wiring tickets review loop (12 passes, no convergence), a significant share of `major`-severity findings were later found to be speculative: the critic flagged concerns that were plausible but not grounded in the artifact or the codebase. Because the synthesizer was obligated to address all `major` items, it added machinery to resolve uncertain findings. The added machinery was then attacked by the next critic pass, keeping issue count flat while the actual artifact drifted from its original design.

Two enforcement strategies were considered:

- **Orchestrator enforcement**: after parsing the critic's JSON, scan each `top_issue` string for evidence signals; downgrade items lacking them from `major` to `minor` before further processing.
- **Prompt enforcement**: add an evidence rule to each GROUP prompt so sub-agents self-classify correctly before returning.

## Decision

Enforce via sub-agent prompts. Each GROUP prompt (A/B/C/D/E for plan; A/B/C/D for spec; A/B/C/D/E for tickets — E=Cross-Artifact Contract Consistency; A/B/C for design-review; F=Codebase Grounding for spec and tickets on iteration 0 only — see ADR-0050) gains a single line:

> "Every `major`-severity issue must cite evidence: an artifact quote, a `file:line` citation (for codebase findings), or a scenario articulation explaining which specific part of the artifact is affected. Speculative concerns without evidence are capped at `minor`."

The orchestrator does not post-process or re-classify severity. Evidence checking remains in the sub-agent's hands, which already own the prompt scope. This is intentionally a prompt-level review convention, not a parser-enforced invariant; adding parser heuristics would be brittle and would add machinery to the critic loop.

Evidence definitions by artifact type:

- **Spec / tickets / plan**: a direct quote from the artifact text, or reference to a specific section/ticket.
- **Codebase (Group F)**: `file:line` citation mandatory. Group F sub-agents receive the standard phrasing — search source code conceptually and cross-file, search docs and requirements as a document corpus, and for architecture-level questions start with a global search before reading individual files.
- **Consistency contradictions (Group B)**: one quote per side of the contradiction.
- **Edge-case / scenario (Group C)**: articulate the specific scenario and identify which part of the artifact fails to handle it.

## Consequences

- Speculative noise that previously consumed `major` slots is systematically reduced; synthesizer is no longer obligated to address ungrounded concerns.
- Real `major` findings become more trustworthy — each one carries a traceable claim.
- False negatives are possible: a sub-agent may rate a genuine issue `major` without citing evidence, or omit evidence and self-downgrade when the issue was real. Mitigation: Group F's codebase access makes evidence cheap for codebase findings; artifact-grounded groups already have the text in context.
- Prompt size increases modestly (one line per group).
