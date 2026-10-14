#!/usr/bin/env bash
#
# Tests the shell functions of skills/engineering/wizard/template.sh.
#
# The template has no source guard (it ends with `run_wizard "$@"; exit`), so
# this test extracts the library's function definitions and evaluates them
# instead of sourcing the file. Each case runs in a temp directory and asserts
# file state and return codes, not internal variables.
#
# Run: bash tests/wizard/template_test.sh

# Mirror the template's runtime options except -e (failed cases are counted,
# not fatal); _existing relies on pipefail to fail on a missing key.
set -uo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
TEMPLATE="$ROOT/skills/engineering/wizard/template.sh"

# Every top-level `name() {` … `}` block above the STAGES marker.
FUNCS=$(awk '
  /^# STAGES:/ { exit }
  /^[A-Za-z_][A-Za-z0-9_]*\(\) *\{/ { infn = 1 }
  infn { print }
  infn && /^}/ { infn = 0 }
' "$TEMPLATE")
[[ -n "$FUNCS" ]] || { echo "FAIL: no functions extracted from $TEMPLATE"; exit 1; }
eval "$FUNCS"
for fn in _existing write_env ask; do
  declare -F "$fn" >/dev/null || { echo "FAIL: $fn not extracted"; exit 1; }
done

# Globals the functions read; colours off.
BOLD=""; DIM=""; RESET=""; BLUE=""; GREEN=""; YELLOW=""
WRITTEN_ENV=(); WRITTEN_SECRET=(); SKIPPED=()

PASS=0; FAIL=0
pass() { PASS=$((PASS + 1)); printf 'ok   %s\n' "$1"; }
fail() { FAIL=$((FAIL + 1)); printf 'FAIL %s: %s\n' "$1" "$2"; }

# mode PATH prints the octal permission bits (macOS and GNU stat).
mode() { stat -c '%a' "$1" 2>/dev/null || stat -f '%Lp' "$1"; }

TMP_ROOT=$(mktemp -d)
trap 'rm -rf "$TMP_ROOT"' EXIT

# fresh: new empty case directory; sets ENV_FILE inside it.
fresh() {
  CASE_DIR="$TMP_ROOT/$1"
  mkdir -p "$CASE_DIR"
  ENV_FILE="$CASE_DIR/.env"
}

# roundtrip NAME VALUE: write_env then _existing returns VALUE unchanged.
roundtrip() {
  local name="$1" value="$2" got
  fresh "$name"
  write_env KEY "$value" >/dev/null
  if got=$(_existing KEY); then
    [[ "$got" == "$value" ]] && pass "$name" || fail "$name" "got [$got], want [$value]"
  else
    fail "$name" "_existing returned non-zero"
  fi
}

roundtrip roundtrip_plain 'sk_test_123'
roundtrip roundtrip_spaces 'hello big world'
roundtrip roundtrip_single_quotes "it's a 'quoted' value"
roundtrip roundtrip_dollar_backslash_dquote 'a$HOME\b"c'

# Overwrite keeps one line per key and returns the latest value.
fresh upsert_replaces
write_env KEY first >/dev/null
write_env OTHER x >/dev/null
write_env KEY second >/dev/null
n=$(grep -c '^KEY=' "$ENV_FILE")
got=$(_existing KEY)
[[ "$n" == 1 && "$got" == second && "$(_existing OTHER)" == x ]] \
  && pass upsert_replaces || fail upsert_replaces "lines=$n value=[$got]"

# Env file mode is 0600 after creation.
fresh mode_0600_on_create
write_env KEY v >/dev/null
m=$(mode "$ENV_FILE")
[[ "$m" == 600 ]] && pass mode_0600_on_create || fail mode_0600_on_create "mode $m"

# Symlink with an existing target: target updated, its mode kept, link stays.
fresh symlink_existing_target
printf 'OLD=1\n' > "$CASE_DIR/target.env"
chmod 640 "$CASE_DIR/target.env"
ln -s target.env "$ENV_FILE"
write_env KEY v >/dev/null
m=$(mode "$CASE_DIR/target.env")
if [[ -L "$ENV_FILE" && "$m" == 640 ]] && grep -qx "KEY='v'" "$CASE_DIR/target.env" \
   && grep -qx 'OLD=1' "$CASE_DIR/target.env"; then
  pass symlink_existing_target
else
  fail symlink_existing_target "link=$([[ -L $ENV_FILE ]] && echo yes || echo no) mode=$m"
fi

# Symlink with a missing target: target created at mode 0600.
fresh symlink_missing_target
ln -s target.env "$ENV_FILE"
write_env KEY v >/dev/null
if [[ -L "$ENV_FILE" && -f "$CASE_DIR/target.env" ]]; then
  m=$(mode "$CASE_DIR/target.env")
  [[ "$m" == 600 ]] && grep -qx "KEY='v'" "$CASE_DIR/target.env" \
    && pass symlink_missing_target || fail symlink_missing_target "mode=$m"
else
  fail symlink_missing_target "target not created or link replaced"
fi

# _existing refuses a double-quoted value containing \, $ or ".
for v in 'a\nb' 'a\b' 'a$b' 'a\"b' 'a"b'; do
  fresh "refuse_dquoted_${#v}_$RANDOM"
  printf 'KEY="%s"\n' "$v" > "$ENV_FILE"
  if _existing KEY >/dev/null; then
    fail "refuse_dquoted [$v]" "_existing returned 0"
  else
    pass "refuse_dquoted [$v]"
  fi
done

# A plain double-quoted value still decodes.
fresh dquoted_plain
printf 'KEY="hello world"\n' > "$ENV_FILE"
got=$(_existing KEY) && [[ "$got" == 'hello world' ]] \
  && pass dquoted_plain || fail dquoted_plain "got [${got:-}]"

# Old-style unquoted KEY=VALUE line still reads.
fresh unquoted_legacy
printf 'KEY=plain_value\n' > "$ENV_FILE"
got=$(_existing KEY) && [[ "$got" == plain_value ]] \
  && pass unquoted_legacy || fail unquoted_legacy "got [${got:-}]"

# _existing on a missing file or key returns non-zero.
fresh missing_file
_existing KEY >/dev/null && fail missing_file "returned 0" || pass missing_file
printf 'OTHER=1\n' > "$ENV_FILE"
_existing KEY >/dev/null && fail missing_key "returned 0" || pass missing_key

# ask with stdin at EOF exits non-zero instead of looping. A watchdog kills it
# after 5s so a regression fails rather than hangs.
fresh ask_eof
( ask KEY "Prompt:" </dev/null >/dev/null 2>&1 ) &
pid=$!
( sleep 5; kill -9 "$pid" ) 2>/dev/null &
watchdog=$!
wait "$pid"; rc=$?
pkill -P "$watchdog" 2>/dev/null; kill "$watchdog" 2>/dev/null; wait "$watchdog" 2>/dev/null
if (( rc == 137 )); then
  fail ask_eof "timed out (looping at EOF)"
elif (( rc == 1 )); then
  pass ask_eof
else
  fail ask_eof "rc=$rc, want 1"
fi

printf '\n%d passed, %d failed\n' "$PASS" "$FAIL"
(( FAIL == 0 ))
