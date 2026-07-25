#!/bin/sh
# say-cue.sh <event-class>   — event JSON arrives on stdin.
# Audio cue dispatcher for Claude Code. Global install (~/.claude/hooks/).

EVENT="$1"
RAW="$(cat)"                         # consume hook stdin JSON once
SAY_DIR="$HOME/.claude/say"

# Ensure working directory exists (attended markers, PID files).
mkdir -p "$SAY_DIR" 2>/dev/null || true

# ---- R5: /repeat suppression marker -------------------------------------
# A marker created at LOOP START silences per-turn Stop chatter.
SID="$(printf '%s' "$RAW" | jq -r '.session_id // empty' 2>/dev/null)"
[ -z "$SID" ] && SID="${CLAUDE_CODE_SESSION_ID:-}"
MARKER="${TMPDIR:-/tmp}/claude-say-skill-${SID}.lock"
MARKER_COMPAT="${TMPDIR:-/tmp}/claude-say-repeat-${SID}.lock"  # backward compat

# ---- Mute flag helper ----------------------------------------------------
# _mute_active <file> <now>
# Returns 0 (active) or 1 (inactive/expired). Auto-removes expired flags.
_mute_active() {
  _ma_file="$1"; _ma_now="$2"
  [ -f "$_ma_file" ] || return 1
  _ma_exp="$(cat "$_ma_file" 2>/dev/null)"
  if printf '%s' "$_ma_exp" | grep -qE '^[0-9]+$'; then
    if [ "$_ma_exp" -gt "$_ma_now" ]; then
      return 0  # time-bounded, still active
    else
      rm -f "$_ma_file" 2>/dev/null || true
      return 1  # expired
    fi
  fi
  return 0  # indefinite (empty file)
}

# ---- R3 / R4: per-event default gating ----------------------------------
case "$EVENT" in
  idle|permission)
    # R3: ON by default. Honor explicit opt-out.
    [ "${CLAUDE_SAY_IDLE:-1}" = "0" ] && [ "$EVENT" = "idle" ] && exit 0
    [ "${CLAUDE_SAY_PERMISSION:-1}" = "0" ] && [ "$EVENT" = "permission" ] && exit 0
    ;;
  stop)
    # R4: general Stop is OFF by default; explicit opt-in only.
    [ "${CLAUDE_SAY_STOP:-0}" = "1" ] || exit 0
    # R5: when /repeat is running, suppress per-turn Stop chatter entirely;
    # the single completion cue comes from FINALIZE_STEP, not from Stop.
    [ -n "$SID" ] && { [ -f "$MARKER" ] || [ -f "$MARKER_COMPAT" ]; } && exit 0
    ;;
  attend)
    # UserPromptSubmit: user is back — clear all mute scopes for this context,
    # update attended marker, and kill any reminder loop for this session.
    ATTEND_CWD="$(printf '%s' "$RAW" | jq -r '.cwd // empty' 2>/dev/null)"
    [ -z "$ATTEND_CWD" ] && ATTEND_CWD="${CLAUDE_PROJECT_DIR:-}"
    ATTEND_PROJ=""
    if [ -n "$ATTEND_CWD" ] && [ "$ATTEND_CWD" != "." ] && [ "$ATTEND_CWD" != "/" ]; then
      ATTEND_PROJ="$(basename "$ATTEND_CWD")"
      [ "$ATTEND_PROJ" = "." ] || [ "$ATTEND_PROJ" = "/" ] && ATTEND_PROJ=""
    fi
    rm -f "$SAY_DIR/muted" 2>/dev/null || true
    [ -n "$SID" ]          && rm -f "$SAY_DIR/muted-$SID" 2>/dev/null || true
    [ -n "$ATTEND_PROJ" ]  && rm -f "$SAY_DIR/muted-proj-$ATTEND_PROJ" 2>/dev/null || true
    if [ -n "$SID" ]; then
      : > "$SAY_DIR/attended-$SID" 2>/dev/null || true
      PID_FILE="$SAY_DIR/reminder-pid-$SID"
      if [ -f "$PID_FILE" ]; then
        OLD_PID="$(cat "$PID_FILE" 2>/dev/null)"
        [ -n "$OLD_PID" ] && kill "$OLD_PID" 2>/dev/null || true
        rm -f "$PID_FILE" 2>/dev/null || true
      fi
    fi
    exit 0
    ;;
  *) exit 0 ;;
esac

# ---- Project name (needed for mute flag lookup before speaking) ----------
CWD="$(printf '%s' "$RAW" | jq -r '.cwd // empty' 2>/dev/null)"
[ -z "$CWD" ] && CWD="${CLAUDE_PROJECT_DIR:-}"
PROJ_RAW=""
if [ -n "$CWD" ] && [ "$CWD" != "." ] && [ "$CWD" != "/" ]; then
  PROJ_RAW="$(basename "$CWD")"
  [ "$PROJ_RAW" = "." ] || [ "$PROJ_RAW" = "/" ] && PROJ_RAW=""
fi

# ---- Mute check (idle/permission only) -----------------------------------
# Check all three scopes before speaking or starting a loop.
# Stop events are not suppressed by mute (they fire once and are low-volume).
case "$EVENT" in
  idle|permission)
    INTERVAL="${CLAUDE_SAY_REPEAT_INTERVAL:-300}"
    NOW="$(date +%s)"

    # Kill any prior reminder loop for this session first.
    if [ -n "$SID" ]; then
      PID_FILE="$SAY_DIR/reminder-pid-$SID"
      if [ -f "$PID_FILE" ]; then
        OLD_PID="$(cat "$PID_FILE" 2>/dev/null)"
        [ -n "$OLD_PID" ] && kill "$OLD_PID" 2>/dev/null || true
        rm -f "$PID_FILE" 2>/dev/null || true
      fi
    fi

    # Mute flags suppress both the immediate cue and the reminder loop.
    _mute_active "$SAY_DIR/muted"                "$NOW" && exit 0
    _mute_active "$SAY_DIR/muted-proj-$PROJ_RAW" "$NOW" && exit 0
    _mute_active "$SAY_DIR/muted-$SID"           "$NOW" && exit 0

    # Per-session cooldown: skip if user attended within INTERVAL seconds.
    ATTENDED_FILE="$SAY_DIR/attended-$SID"
    if [ -f "$ATTENDED_FILE" ]; then
      MTIME="$(stat -f %m "$ATTENDED_FILE" 2>/dev/null || stat -c %Y "$ATTENDED_FILE" 2>/dev/null || echo 0)"
      AGE=$((NOW - MTIME))
      if [ "$AGE" -lt "$INTERVAL" ]; then
        exit 0
      fi
    fi
    ;;
esac

# ---- R6: spoken text = stdin .message, else fixed per-event fallback -----
MSG="$(printf '%s' "$RAW" | jq -r '.message // empty' 2>/dev/null)"
if [ -z "$MSG" ]; then
  case "$EVENT" in
    idle)       MSG="Claude is waiting for you." ;;
    permission) MSG="Claude needs your permission." ;;
    stop)       MSG="Claude is done." ;;
  esac
fi

# ---- Project name suffix (speech-friendly version) -----------------------
if [ -n "$PROJ_RAW" ]; then
  PROJ_SPEECH="$(printf '%s' "$PROJ_RAW" | tr '_-' '  ')"
  MSG="${MSG%[.!?]}"
  MSG="$MSG in $PROJ_SPEECH."
fi

# ---- R8(d) fallback: whitelist-sanitize if say-reads-stdin is unproven ---
if [ -f "$HOME/.claude/hooks/.say-stdin-ok" ]; then
  STDIN_OK=1
else
  STDIN_OK=0
  MSG="$(printf '%s' "$MSG" | LC_ALL=C tr -cd "A-Za-z0-9 .,'!?-")"
fi

# ---- R7: system default voice unless CLAUDE_SAY_VOICE overrides ----------
if [ -n "${CLAUDE_SAY_VOICE:-}" ]; then
  set -- -v "$CLAUDE_SAY_VOICE"
else
  set --
fi

# ---- R8(a,b,c): speak immediately ----------------------------------------
if [ "$STDIN_OK" = "1" ]; then
  ( printf '%s' "$MSG" | say "$@" || true ) &
else
  ( say "$@" "$MSG" || true ) &
fi
disown 2>/dev/null || true

# ---- Reminder loop (idle/permission only) --------------------------------
# Mute and cooldown checks already passed above. Start the loop.
case "$EVENT" in
  idle|permission)
    MAX="${CLAUDE_SAY_REPEAT_MAX:-100}"

    # Clear attended state and start reminder cycle.
    rm -f "$SAY_DIR/attended-$SID" 2>/dev/null || true

    (
      i=0
      while [ "$i" -lt "$MAX" ]; do
        sleep "$INTERVAL"
        [ -f "$SAY_DIR/attended-$SID" ] && break
        if [ -n "${CLAUDE_SAY_VOICE:-}" ]; then
          printf '%s' "$MSG" | say -v "$CLAUDE_SAY_VOICE" || true
        else
          printf '%s' "$MSG" | say || true
        fi
        i=$((i+1))
      done
      # Clean up PID file on natural exit.
      [ -n "$SID" ] && rm -f "$SAY_DIR/reminder-pid-$SID" 2>/dev/null || true
    ) &
    LOOP_PID=$!
    disown 2>/dev/null || true

    # Record PID so attend handler and future idle events can kill this loop.
    [ -n "$SID" ] && printf '%s\n' "$LOOP_PID" > "$SAY_DIR/reminder-pid-$SID" 2>/dev/null || true
    ;;
esac

exit 0
