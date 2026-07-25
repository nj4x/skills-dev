#!/bin/sh
# say-cue-lib.sh — Audio cue helpers for multi-turn Claude Code skills.
#
# Source this file from Bash snippets inside a skill's SKILL.md:
#
#   [ -f ~/.claude/hooks/say-cue-lib.sh ] && . ~/.claude/hooks/say-cue-lib.sh
#
# Then call:
#   say_skill_start               — at skill start; suppresses per-turn Stop chatter
#   say_skill_done "Message."     — at every exit path; emits one cue and clears marker
#
# The marker is per-session: ~/.claude/hooks/say-cue.sh checks it in the `stop`
# event handler and stays silent while it exists. say_skill_done removes it so
# normal Stop cues resume after the skill completes.
#
# Both functions degrade silently if CLAUDE_CODE_SESSION_ID is empty or `say`
# is unavailable — they never abort a skill.

say_skill_start() {
  _ss_id="${CLAUDE_CODE_SESSION_ID:-}"
  [ -n "$_ss_id" ] && : > "${TMPDIR:-/tmp}/claude-say-skill-${_ss_id}.lock" 2>/dev/null || true
}

# say_skill_done <message>
# Emits one spoken cue then clears the suppression marker.
# Respects CLAUDE_SAY_VOICE if set.
say_skill_done() {
  _sd_msg="${1:-Done.}"
  _sd_id="${CLAUDE_CODE_SESSION_ID:-}"
  if [ -n "${CLAUDE_SAY_VOICE:-}" ]; then
    ( printf '%s' "$_sd_msg" | say -v "$CLAUDE_SAY_VOICE" || true ) &
  else
    ( printf '%s' "$_sd_msg" | say || true ) &
  fi
  disown 2>/dev/null || true
  [ -n "$_sd_id" ] && rm -f "${TMPDIR:-/tmp}/claude-say-skill-${_sd_id}.lock" 2>/dev/null || true
}

# say_skill_cancel
# Clears the suppression marker silently — no speech.
# Use on hard-abort paths where speaking a cue is inappropriate.
say_skill_cancel() {
  _sc_id="${CLAUDE_CODE_SESSION_ID:-}"
  [ -n "$_sc_id" ] && rm -f "${TMPDIR:-/tmp}/claude-say-skill-${_sc_id}.lock" 2>/dev/null || true
}
