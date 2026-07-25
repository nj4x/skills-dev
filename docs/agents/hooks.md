# hooks/ directory

`hooks/` contains the macOS `say` hook system and is **not** organized as a skill. Instead, it is symlinked directly into `~/.claude/hooks/` and wired in `~/.claude/settings.json`. See `hooks/README.md` for the full setup procedure (symlink, stdin probe, four hook entries).

## Audio cues in multi-turn skills

Multi-turn skills that run several agent turns should call `say_skill_start` at entry and `say_skill_done`/`say_skill_cancel` at every exit path via `say-cue-lib.sh`. Single-turn skills need nothing — the global Stop hook handles them.
