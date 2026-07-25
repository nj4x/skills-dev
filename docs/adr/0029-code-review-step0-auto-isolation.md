# Reversed: Code-review Step 0 auto-isolation removed as dead code

## Status: Superseded

The Step 0 auto-isolation check described in this ADR was implemented but subsequently removed as non-functional dead code.

## Context

Code-review's Step 0 auto-isolation attempted to detect an active plan artifact by checking for a file at `~/.claude/plans/$CLAUDE_CODE_SESSION_ID.md`. The detection logic was:

```bash
if [ -n "$CLAUDE_CODE_SESSION_ID" ] && [ -f ~/.claude/plans/"$CLAUDE_CODE_SESSION_ID".md ]; then
  # Active plan artifact detected (grilling, planning, etc.)
  # Re-invoke in a fresh subagent
fi
```

However, the plans directory uses **descriptive slug filenames** (e.g., `community-readiness-deepening.md`, `refactor-claude-md-skill-critic-manifest.md`), not session-ID filenames. The detection never matched any actual plan file, so the re-invocation never fired. Step 0 became inert dead code.

## Decision

Remove Step 0 from `code-review/skill.md` and `workflow.md`.

The isolation concern it was meant to address remains valid: code-review's orchestration (builds, PR intake, document discovery, temp files) is stateful and can pollute a parent skill's context. However, isolation is now achieved by the caller: skills that need it (like `engineering/implement`) explicitly spawn a subagent and invoke `/code-review` inside it. The manual approach is explicit and reliable, whereas the automatic Step 0 detection was broken.

## Consequences

- No automatic isolation at the code-review skill level; callers must wrap code-review in a subagent if isolation is required.
- `engineering/implement` already demonstrates the correct pattern and continues to work unchanged.
- Removal of dead code reduces bloat and eliminates false claims about auto-isolation guarantees.
