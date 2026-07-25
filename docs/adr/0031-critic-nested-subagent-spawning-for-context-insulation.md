# Nested sub-agent spawning for context insulation in critic

Use nested sub-agent spawning (sub-agents that spawn their own sub-agents) rather than orchestrator-level fan-out when parallelising the critic and planner, to keep the orchestrator context window clean.

## Context

The critic skill's plan/review loop runs a serial chain: orchestrator spawns one Plan agent (planner), then one critic agent, collects their full output into its context, and loops. As plan complexity grows, the orchestrator accumulates large plan texts and long critic responses, degrading reasoning quality across iterations.

Two approaches exist to parallelize review work:

- **Orchestrator-level fan-out**: the orchestrator spawns N review sub-agents simultaneously, collects all N responses, and merges them. Simpler to implement but every sub-agent response lands directly in the orchestrator's context window, making context pollution proportional to N.

- **Nested sub-agent spawning**: the planner or critic sub-agents themselves spawn further sub-agents to delegate parallel work. The orchestrator sees only one compact result per step regardless of how much parallel work happened inside.

## Decision

Implement nested sub-agent spawning for the parallel critic redesign. The orchestrator's REVIEW_STEP dispatches a single "critic coordinator" agent; that coordinator spawns 4–5 parallel sub-agents (one per lens group), collects their verdicts, merges them, and returns a single merged JSON verdict to the orchestrator.

The planner (GENERATE_STEP) may also opportunistically spawn sub-agents for major revision work, but this is advisory and unconstrained — the orchestrator's API is unchanged (planner returns one coherent revised plan).

## Consequences

- Orchestrator context grows only by one compact verdict per REVIEW_STEP — insulated from N×(critic reasoning) accumulation.
- The critic coordinator (a `claude` agent) must be trusted to spawn sub-agents correctly, merge results, and return valid JSON — more failure surface than a single agent.
- If nested sub-agent spawning fails or is unreliable in practice, the fallback is orchestrator-level fan-out (ADR to be written if rollback occurs).
- Testing requires verifying the sub-agent spawn → JSON merge pipeline end-to-end with a synthetic plan.
