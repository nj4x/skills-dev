#!/bin/sh
# say-mute.sh [scope] [minutes]
# Silence audio cue reminder loops with optional scope and duration.
#
# Scope:
#   (none)    current session only  [default]
#   project   all sessions in the current project
#   all       every session globally
#
# Minutes:
#   (none)    indefinite — cleared only when user sends a real message
#   N         silence for N minutes regardless of user activity
#
# Examples:
#   say-mute.sh              # mute this session indefinitely
#   say-mute.sh 30           # mute this session for 30 minutes
#   say-mute.sh project      # mute current project indefinitely
#   say-mute.sh project 30   # mute current project for 30 minutes
#   say-mute.sh all          # mute all sessions indefinitely
#   say-mute.sh all 30       # mute all sessions for 30 minutes

SID="${CLAUDE_CODE_SESSION_ID:-}"
SAY_DIR="$HOME/.claude/say"

# Parse scope and minutes from args.
ARG1="${1:-}"
ARG2="${2:-}"
case "$ARG1" in
  all|project|session)
    SCOPE="$ARG1"
    MIN="$ARG2"
    ;;
  *)
    SCOPE="session"
    MIN="$ARG1"
    ;;
esac

# Validate minutes.
if [ -n "$MIN" ]; then
  case "$MIN" in
    *[!0-9]*|'') MIN="" ;;
  esac
fi

if [ -z "$SID" ] && [ "$SCOPE" != "all" ]; then
  echo "No session ID available — cannot mute by session or project." >&2
  exit 1
fi

mkdir -p "$SAY_DIR" 2>/dev/null || true

# Derive project name for project-scoped mute.
PROJ_RAW=""
if [ "$SCOPE" = "project" ]; then
  PROJECT_DIR="${CLAUDE_PROJECT_DIR:-$PWD}"
  PROJ_RAW="$(basename "$PROJECT_DIR")"
  [ "$PROJ_RAW" = "." ] || [ "$PROJ_RAW" = "/" ] && PROJ_RAW=""
  if [ -z "$PROJ_RAW" ]; then
    echo "Cannot determine project name." >&2
    exit 1
  fi
fi

# Kill ALL active reminder loops (regardless of scope — /mute always silences
# what is currently ringing; the flag then controls what can restart).
KILLED=0
for PID_FILE in "$SAY_DIR"/reminder-pid-*; do
  [ -f "$PID_FILE" ] || continue
  OLD_PID="$(cat "$PID_FILE" 2>/dev/null)"
  if [ -n "$OLD_PID" ]; then
    kill "$OLD_PID" 2>/dev/null && KILLED=$(( KILLED + 1 )) || true
  fi
  rm -f "$PID_FILE" 2>/dev/null || true
done

# Compute flag file and expiry.
case "$SCOPE" in
  all)     FLAG="$SAY_DIR/muted" ;;
  project) FLAG="$SAY_DIR/muted-proj-$PROJ_RAW" ;;
  session) FLAG="$SAY_DIR/muted-$SID" ;;
esac

if [ -n "$MIN" ] && [ "$MIN" -gt 0 ] 2>/dev/null; then
  EXPIRY=$(( $(date +%s) + MIN * 60 ))
  printf '%s\n' "$EXPIRY" > "$FLAG"
  DURATION="for ${MIN} minutes"
else
  : > "$FLAG"
  DURATION="until next message"
fi

case "$SCOPE" in
  all)     LABEL="all sessions" ;;
  project) LABEL="project '$PROJ_RAW'" ;;
  session) LABEL="this session" ;;
esac

echo "User attendance confirmed — ${LABEL} muted ${DURATION} (${KILLED} notification loop(s) stopped)."
