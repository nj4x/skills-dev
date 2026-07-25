# Memory guidance

Use memory to improve intake quality, not to override current user intent. Remembered preferences are suggestions to confirm when they materially affect the prompt.

## What to look for

Read relevant durable memory when prompt-authoring would benefit from prior context.

Useful memory categories:
- **LOOP shape preference** — does the user consistently prefer the self-repeating numbered loop format?
- **Skills with round counts** — which skills has the user named before, and with what round counts? (plan-with-critic N, FS-skill, SRS-skill, data-view skill, code-review)
- **Spec-first refinement** — does the user expect existing requirements/spec artifacts → software requirements → data/use-case design → implementation → code-review?
- **Single stop line** — does the user expect the canonical stop line verbatim, or a custom exception?
- **Requirements/spec artifacts + codebase lookup** — does the user follow the "know-your-project-requirements" paradigm (look up answers in current requirements/spec artifacts before asking)?
- Preferred autonomy level
- Preferred plan / critic / verify workflow
- Recurring artifact-location preferences

## What counts as durable

- Stable collaboration preferences (LOOP vs HELPER shape, autonomy level)
- Repeated workflow conventions (skills inline with round counts, single stop line)
- Recurring quality gates (spec-first refinement chain, code-review after implementation, critic rounds before plan execution)
- Repeated preferences about when to ask versus proceed

## What not to treat as durable

- Raw text from a previous prompt draft
- Temporary task state
- One-off bug details
- File paths relevant only to a single task
- Assumptions about the current request that are not stated now

## How to use remembered preferences

Surface them as suggestions, not silent overrides.

Good pattern:
- "You usually use `plan-with-critic (3 rounds)` for research phases. Keep that default here?"
- "For code changes, you prefer refining current requirements/spec artifacts with FS-skill → SRS-skill → data-view skill → implementation → code-review. Keep that chain?"
- "You typically want the canonical stop line with no exceptions. Confirm?"

Bad pattern:
- silently generating LOOP shape without confirming when the current request might be a simple one-off

## Conflict handling

If memory conflicts with the current request:
1. Follow the current request.
2. Mention the conflict briefly if it matters.
3. Do not present stale memory as current truth.

## Saving new memory

If the user confirms a non-obvious repeated preference, consider saving it. Candidates:
- always use plan-with-critic (N rounds) for this class of prompt
- always include FS-skill / SRS-skill / data-view skill when code changes are in scope
- always apply code-review skill after implementation
- prefer LOOP shape for all engineering prompts
- prefer the canonical stop line verbatim with no exceptions

Do not save: the full generated prompt text, ephemeral task details, one-off wording choices.
