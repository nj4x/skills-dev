# hooks/

macOS audio cue hooks for Claude Code. Speaks a notification when Claude is
waiting for you, then repeats every 5 minutes until you respond.

## Files

| File | Purpose |
|------|---------|
| `say-cue.sh` | Main dispatcher — receives hook events, plays cues, manages reminder loops |
| `say-cue-lib.sh` | Shell helper for skills: `say_skill_start`, `say_skill_done`, `say_skill_cancel` |
| `say-mute.sh` | Backing script for `/mute` — kills all loops, sets global mute flag |
| `.say-stdin-ok` | Proof file written at install time; confirms `say` accepts text on stdin |

## Prerequisites

- macOS (uses the built-in `say` command)
- `jq` — used to parse hook JSON (`brew install jq`)

## Setup in a new environment

### 1. Symlink the files into `~/.claude/hooks/`

```sh
mkdir -p ~/.claude/hooks
REPO="$(pwd)"   # run from the skills-dev root

ln -s "$REPO/hooks/say-cue.sh"     ~/.claude/hooks/say-cue.sh
ln -s "$REPO/hooks/say-cue-lib.sh" ~/.claude/hooks/say-cue-lib.sh
ln -s "$REPO/hooks/say-mute.sh"    ~/.claude/hooks/say-mute.sh
chmod +x ~/.claude/hooks/say-cue.sh ~/.claude/hooks/say-mute.sh
```

### 2. Run the stdin precondition test

`say-cue.sh` pipes text to `say` over stdin (injection-proof). Confirm this
works on your machine and write the proof file:

```sh
AIFF="$(mktemp /tmp/say-probe.XXXXXX.aiff)"
printf 'probe' | say -o "$AIFF" && touch ~/.claude/hooks/.say-stdin-ok
rm -f "$AIFF"
```

If the command fails, `say-cue.sh` falls back to a whitelist-sanitized argument
path automatically — the proof file is optional but recommended.

### 3. Wire the hooks in `~/.claude/settings.json`

Add the four entries below to your `hooks` object. If the key already has
entries, append the new group to the existing array — do not replace it.

```json
{
  "hooks": {
    "Notification": [
      {
        "matcher": "",
        "hooks": [
          {
            "type": "command",
            "command": "/Users/YOU/.claude/hooks/say-cue.sh idle  # claude-say-hook"
          }
        ]
      }
    ],
    "PermissionRequest": [
      {
        "matcher": "",
        "hooks": [
          {
            "type": "command",
            "command": "/Users/YOU/.claude/hooks/say-cue.sh permission  # claude-say-hook"
          }
        ]
      }
    ],
    "Stop": [
      {
        "matcher": "",
        "hooks": [
          {
            "type": "command",
            "command": "/Users/YOU/.claude/hooks/say-cue.sh stop  # claude-say-hook"
          }
        ]
      }
    ],
    "UserPromptSubmit": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "/Users/YOU/.claude/hooks/say-cue.sh attend  # claude-say-hook"
          }
        ]
      }
    ]
  }
}
```

Replace `/Users/YOU` with your actual home directory (`echo $HOME`).

> **Note:** `Stop` cues are off by default — set `CLAUDE_SAY_STOP=1` to enable.

### 4. Install the `/mute` skill

```sh
ln -s "$REPO/mute" ~/.claude/skills/mute
```

## Behaviour

| Event | What happens |
|-------|-------------|
| Claude goes idle / needs attention | Speaks immediately; starts a reminder loop (every 5 min, up to 100 times) |
| Claude needs permission | Same as idle |
| Claude finishes a task | Speaks once (opt-in: `CLAUDE_SAY_STOP=1`) |
| User submits a message | Kills the reminder loop, clears the global mute flag |
| `/mute` | Kills all loops; suppresses new ones for this session until user sends a message |
| `/mute project` | Same, scoped to all sessions in the current project |
| `/mute all` | Same, scoped globally across every session |
| `/mute 30` / `/mute project 30` / `/mute all 30` | Time-bounded variants (self-expire after N minutes) |

## Environment variables

| Variable | Default | Effect |
|----------|---------|--------|
| `CLAUDE_SAY_IDLE` | `1` | Set to `0` to disable idle cues |
| `CLAUDE_SAY_PERMISSION` | `1` | Set to `0` to disable permission cues |
| `CLAUDE_SAY_STOP` | `0` | Set to `1` to enable task-completion cues |
| `CLAUDE_SAY_VOICE` | system default | Override with any `say -v` voice name |
| `CLAUDE_SAY_REPEAT_INTERVAL` | `300` | Seconds between reminder repeats |
| `CLAUDE_SAY_REPEAT_MAX` | `100` | Maximum number of reminders per cycle |

## Opting a skill into named completion cues

Single-turn skills need nothing — the global idle cue handles them. For
multi-turn skills (like `repeat`/`critic`) that run several agent turns:

```sh
# At skill start — suppresses per-turn Stop chatter:
[ -f ~/.claude/hooks/say-cue-lib.sh ] && . ~/.claude/hooks/say-cue-lib.sh && say_skill_start || true

# At every exit path (normal finish):
proj="$(basename "${CLAUDE_PROJECT_DIR:-$PWD}")"
proj_say="$(printf '%s' "$proj" | tr '_-' '  ')"
msg="My skill finished${proj_say:+ in ${proj_say}}."
[ -f ~/.claude/hooks/say-cue-lib.sh ] && . ~/.claude/hooks/say-cue-lib.sh && say_skill_done "$msg" || true

# At hard-abort paths (no speech, just clear the marker):
[ -f ~/.claude/hooks/say-cue-lib.sh ] && . ~/.claude/hooks/say-cue-lib.sh && say_skill_cancel || true
```

## Runtime state files

All state is stored in `~/.claude/say/`:

| File | Purpose |
|------|---------|
| `reminder-pid-<sid>` | PID of the active reminder loop for a session |
| `attended-<sid>` | Timestamp of last user activity for a session (cooldown) |
| `muted` | Global mute flag (`/mute all`); empty = indefinite, number = epoch expiry |
| `muted-<sid>` | Per-session mute flag (`/mute` or `/mute session`) |
| `muted-proj-<name>` | Per-project mute flag (`/mute project`) |
