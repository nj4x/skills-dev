#!/bin/bash
# Watchdog per ADR-0068 point 3 and ADR-0074: restarts pooled workers whose heartbeats go stale.
set -u
STALENESS_THRESHOLD=300
CHECK_INTERVAL=30
RESTART_GAP=20      # spacing between restarts fired in one scan, so a restarted worker claims
                    # its slot before the next URI lands (ADR-0074 misdirected-restart risk)
RESTART_GRACE=300   # skip a slot this long after restarting it, so a worker that came back in a
                    # different slot does not cascade restarts off the old file (ADR-0074 risk 5)
MAX_POOL_SIZE=10

# Must resolve to the same root as bridge.queue.default_root(), tilde expansion included.
BRIDGE_DIR="${CLINE_BRIDGE_DIR:-$HOME/.cline-bridge}"
ROOT="${BRIDGE_DIR/#\~/$HOME}"
WATCHDOG_HEARTBEAT="$ROOT/watchdog.alive"
PROMPT_FILE="$ROOT/worker-prompt.txt"
POOL_CONF="$ROOT/pool.conf"

POOL_SIZE="${POOL_SIZE:-1}"
case "$POOL_SIZE" in
  ''|*[!0-9]*) POOL_SIZE=0 ;;
esac
if [ "$POOL_SIZE" -lt 1 ] || [ "$POOL_SIZE" -gt "$MAX_POOL_SIZE" ]; then
  echo "[watchdog] POOL_SIZE must be an integer 1..$MAX_POOL_SIZE" >&2
  exit 1
fi

mkdir -p "$ROOT"
cp "$(dirname "$0")/worker-prompt.txt" "$PROMPT_FILE"
echo "$POOL_SIZE" > "$POOL_CONF"

# Seconds since mtime; a missing file reads as infinitely old.
age() {
  local mtime
  mtime=$(stat -f%m "$1" 2>/dev/null) || { echo 999999999; return; }
  echo $(( $(date +%s) - mtime ))
}

url_encode() {
  python3 -c "import urllib.parse, sys; print(urllib.parse.quote(sys.stdin.read()))" "$@"
}

restart_slot() {
  local slot=$1
  local encoded
  encoded=$(url_encode < "$PROMPT_FILE")
  open "vscode://cline-sr.cline-sr/task?prompt=$encoded"
  touch "$ROOT/.restart-$slot"
  echo "[watchdog] $(date): worker-$slot heartbeat stale, task restarted"
}

# Restart every slot whose heartbeat file exists and has gone stale. A slot with no heartbeat
# file was never claimed, so there is nothing to restart (ADR-0074: POOL_SIZE is a ceiling,
# not a launch directive).
scan() {
  local fired=0 slot
  for slot in $(seq 1 "$POOL_SIZE"); do
    [ -e "$ROOT/worker-$slot.alive" ] || continue
    [ "$(age "$ROOT/worker-$slot.alive")" -gt "$STALENESS_THRESHOLD" ] || continue
    [ "$(age "$ROOT/.restart-$slot")" -gt "$RESTART_GRACE" ] || continue
    [ "$fired" -eq 0 ] || sleep "$RESTART_GAP"
    restart_slot "$slot"
    fired=$((fired + 1))
  done
}

echo "[watchdog] $(date): monitoring up to $POOL_SIZE worker slots under $ROOT"
echo "[watchdog] staleness: ${STALENESS_THRESHOLD}s, restart grace: ${RESTART_GRACE}s, restart gap: ${RESTART_GAP}s, check interval: ${CHECK_INTERVAL}s"

while true; do
  touch "$WATCHDOG_HEARTBEAT"
  scan
  sleep "$CHECK_INTERVAL"
done
