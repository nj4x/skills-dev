#!/bin/bash
# Watchdog per ADR-0068 point 3: restarts the Cline task if the worker heartbeat goes stale.
set -u
PROMPT_FILE="$HOME/.cline-bridge/worker-prompt.txt"
STALENESS_THRESHOLD=300
BOOT_GRACE=120
CHECK_INTERVAL=30

mkdir -p "$HOME/.cline-bridge"
cp "$(dirname "$0")/worker-prompt.txt" "$PROMPT_FILE"

is_stale() {
  local heartbeat="$HOME/.mcp-bridge/worker.alive"
  if [ ! -f "$heartbeat" ]; then return 0; fi
  local mtime=$(stat -f%m "$heartbeat" 2>/dev/null || echo 0)
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

echo "[watchdog] $(date): monitoring heartbeat at $HOME/.mcp-bridge/worker.alive"
echo "[watchdog] staleness threshold: ${STALENESS_THRESHOLD}s, boot grace: ${BOOT_GRACE}s, check interval: ${CHECK_INTERVAL}s"

# Fire first task
restart_task

while true; do
  sleep "$CHECK_INTERVAL"
  if is_stale; then
    echo "[watchdog] $(date): heartbeat stale, restarting"
    restart_task
  fi
done
