---
name: hs
description: Show recent user prompts for the current project with pagination.
argument-hint: "[more | <prompt-number>]"
disable-model-invocation: true
---

# hs — prompt history

Paginated view of user prompts for the current project's Claude Code sessions.

## Modes

| Invocation | Behaviour |
|---|---|
| `/hs` | Show latest 10 prompts; resets pagination |
| `/hs more` | Show the next 10 older prompts |
| `/hs N` | Show prompt #N in full |

## On invocation

1. Pass the argument (empty, `more`, or a number) directly to the script:

```bash
python3 "$HOME/.claude/skills/hs/show-history.py" [ARGUMENT]
```

2. Display the output verbatim. No additional commentary.
