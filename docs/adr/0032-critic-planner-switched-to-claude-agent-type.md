# Planner switches from Plan agent type to claude for Agent tool access

Both the planner (GENERATE_STEP) and critic (REVIEW_STEP) sub-agents are invoked as `subagent_type: "claude"` rather than `subagent_type: "Plan"`, to gain access to the Agent tool needed for nested spawning.

## Context

The `Plan` agent type is defined with "all tools except Agent" — it cannot call the Agent tool and therefore cannot spawn sub-agents. This blocks nested spawning for the planner.

The default `claude` agent type has `*` tools, which includes Agent, enabling nested sub-agent spawning.

The `Plan` type's benefit is that it is purpose-built for structured plan output. Switching to `claude` loses that affordance and requires explicit planning instructions in the prompt.

## Decision

Switch both GENERATE_STEP and REVIEW_STEP to `subagent_type: "claude"`. Add explicit role instructions to each prompt ("You are a software implementation planner…" / "You are a parallel critic coordinator…") to compensate for the loss of the Plan type's built-in planning affordance.

## Consequences

- Both sub-agents now have Agent tool access and can spawn sub-sub-agents.
- Plan-specific affordances from the `Plan` type are no longer available; prompt engineering carries the load.
- If the `claude` type's general-purpose framing degrades plan quality vs. the `Plan` type, the fix is prompt refinement rather than reverting the type.
