#!/bin/bash
# Watchdog per ADR-0068 point 3: restarts the Cline task if the worker heartbeat goes stale.
set -u
STALENESS_THRESHOLD=300
BOOT_GRACE=120
CHECK_INTERVAL=30

# Must resolve to the same root as bridge.queue.default_root(), tilde expansion included.
BRIDGE_DIR="${CLINE_BRIDGE_DIR:-$HOME/.cline-bridge}"
ROOT="${BRIDGE_DIR/#\~/$HOME}"
HEARTBEAT="$ROOT/worker.alive"
WATCHDOG_HEARTBEAT="$ROOT/watchdog.alive"
PROMPT_FILE="$ROOT/worker-prompt.txt"

mkdir -p "$ROOT"
cp "$(dirname "$0")/worker-prompt.txt" "$PROMPT_FILE"

is_stale() {
  if [ ! -f "$HEARTBEAT" ]; then return 0; fi
  local mtime=$(stat -f%m "$HEARTBEAT" 2>/dev/null || echo 0)
  local now=$(date +%s)
  [ $((now - mtime)) -gt "$STALENESS_THRESHOLD" ]
}

url_encode() {
  python3 -c "import urllib.parse, sys; print(urllib.parse.quote(sys.stdin.read()))" "$@"
}

restart_task() {
  local encoded=$(cat "$PROMPT_FILE" | url_encode)
  open "vscode://cline-sr.cline-sr/task?prompt=$encoded"
  echo "[watchdog] $(date): task restarted"
  sleep "$BOOT_GRACE"
}

echo "[watchdog] $(date): monitoring heartbeat at $HEARTBEAT"
echo "[watchdog] staleness threshold: ${STALENESS_THRESHOLD}s, boot grace: ${BOOT_GRACE}s, check interval: ${CHECK_INTERVAL}s"

touch "$WATCHDOG_HEARTBEAT"
if is_stale; then
  restart_task
else
  echo "[watchdog] $(date): worker already alive, not starting a second one"
fi

while true; do
  sleep "$CHECK_INTERVAL"
  touch "$WATCHDOG_HEARTBEAT"
  if is_stale; then
    echo "[watchdog] $(date): heartbeat stale, restarting"
    restart_task
  fi
done
