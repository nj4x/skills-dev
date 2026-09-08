---
name: mute
description: Silence audio cue reminder notifications.
disable-model-invocation: true
arguments: [scope] [minutes]
argument-hint: "[session|project|all] [minutes]"
---

Parse the user's arguments to extract an optional scope keyword and an optional
number of minutes, then run:

```bash
~/.claude/hooks/say-mute.sh ${scope:-} ${minutes:-}
```

Where:
- `scope` is one of `session` (default), `project`, or `all`
- `minutes` is a positive integer, or empty for indefinite

Print the command output to the user. Nothing else is needed. Do not add commentary.
