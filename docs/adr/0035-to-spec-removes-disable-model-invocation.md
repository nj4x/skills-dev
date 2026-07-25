# to-spec removes disable-model-invocation

**Status: accepted; flag removal pending implementation.** As of this ADR, `to-spec/SKILL.md` still carries `disable-model-invocation: true` (line 4). This ADR records the decision to remove it; the SKILL edit lands with the critic-flow implementation (ADR-0034, ADR-0039).

`to-spec` is currently a directive-only skill (`disable-model-invocation: true`), meaning it gives instructions to the running model without actively orchestrating sub-agents. The critic-first flow (ADR-0034) requires the skill to spawn a critic agent, drive a synthesizer-revision loop, and then publish — that is active orchestration, incompatible with the directive-only constraint. The flag will therefore be removed.

We remove the flag rather than keeping `to-spec` directive and chaining a separate skill invocation, because splitting artifact creation and critic review across two slash-commands would break the auto-proceed guarantee: the user would have to manually invoke `/critic` after `to-spec` finished drafting. The cleaner boundary is one skill that produces a vetted, published artifact.

Removing the flag also makes `to-spec` **headless-capable**: it can be invoked by another agent with no interactive user. The headless behaviour is defined in ADR-0034 ("Cap exhaustion and headless behaviour") — publish only on true critic approval, otherwise stage the draft and stop.

`to-tickets` is already model-invocable (no flag), so no frontmatter change is needed there; only its process steps change (ADR-0034).

## Considered Options

- **Keep directive, instruct running model to call critic**: makes "auto-proceed" depend on the running model cooperating with the instructions; not reliable, and cannot orchestrate the revision loop.
- **Separate `to-spec-with-critic` wrapper skill**: clean but proliferates skills; two entry points for the same operation confuse discoverability.
