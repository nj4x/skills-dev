---
name: mark
description: Plant a session anchor so /repeat can later iterate everything that follows this point.
argument-hint: "[optional focus note]"
disable-model-invocation: true
---

<!-- Note: `arguments`/`argument-hint` are supported by the Claude Code CLI. Any VS Code agent-linter warning is cosmetic and accepted. -->

# The mark skill

`/mark` plants an **anchor** at the current point in the session. It summarizes nothing — it only records *where* in the session transcript the interesting dialog begins, plus an optional focus note. Later, `/repeat` (no args) recovers the dialog span that came **after** the anchor and iterates it.

```
1) past conversation        → ignored
2) /mark                    → plant anchor (records transcript line count)
3) … conversation continues → THIS span is what matters
4) /repeat                  → recover span 2→4, synthesize a task, run the loop
```

Discovery at repeat time is deterministic (session-id keyed file + transcript line slice), so it survives context-window truncation and never depends on scanning the live conversation.

---

## Steps when `/mark [note]` is invoked

**1. Session id**

```bash
echo $CLAUDE_CODE_SESSION_ID
```

Store as `SESSION_ID`. If empty, hard abort with: `CLAUDE_CODE_SESSION_ID is unset; cannot anchor this session.`

**2. Locate the transcript**

```bash
find ~/.claude/projects -name "$SESSION_ID.jsonl" -print -quit
```

Store as `TRANSCRIPT`. If empty/not found, hard abort with: `Session transcript not found; cannot anchor.`

**3. Record the anchor**

```bash
wc -l < "$TRANSCRIPT"
```

Store the integer as `ANCHOR_LINE`. This is the current line count — everything up to and including the `/mark` turn. The span to iterate is whatever is appended *after* this line. (Treat it as a lower bound: the extractor at repeat time also strips the `/mark` confirmation turn if it landed just after the anchor.)

**4. Timestamp**

```bash
date -u +%Y-%m-%dT%H:%M:%SZ
```

Store as `MARKED_AT`.

**5. Optional note**

The skill argument text (everything the user typed after `/mark`), trimmed. If empty, use the literal `none`. This is a free-text focus hint that biases the later synthesis (e.g. `/mark focus on the parser`).

**6. Ensure the marks directory exists**

```bash
mkdir -p ~/.claude/marks
```

**7. Write the mark file**

Use the Write tool to write `~/.claude/marks/<SESSION_ID>.md` (a subsequent `/mark` in the same session overwrites it — re-anchoring to the new point):

```markdown
# Mark — session <SESSION_ID>
<!-- anchor written by /mark; repeat reads transcript lines after anchor_line -->

transcript: <TRANSCRIPT>
anchor_line: <ANCHOR_LINE>
marked_at: <MARKED_AT>
note: <note or "none">
```

**8. Confirm**

Print exactly:

```
Anchored at transcript line <ANCHOR_LINE>.
  Mark file: ~/.claude/marks/<SESSION_ID>.md
  Note: <note or "(none)">
  Continue the dialog, then run /repeat (no args) to iterate everything after this point.
```

---

## Notes

- The mark file is keyed by session id, so it never leaks across sessions.
- No sentinel line is printed into the conversation — `/repeat` finds the mark by session-id file lookup, not by scanning context.
- Consumed by the `repeat` skill's MARK-REPLAY branch. See `repeat/SKILL.md`.
