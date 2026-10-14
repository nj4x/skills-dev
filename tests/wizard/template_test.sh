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

# Every top-level `name() {` … `}` block above the STAGES marker. A one-line
# definition (`say() { …; }`) closes on its own line. Exits 2 when the marker
# is missing, so a renamed marker fails here instead of extracting the stages.
FUNCS=$(awk '
  /^# STAGES:/ { found = 1; exit }
  /^[A-Za-z_][A-Za-z0-9_]*\(\) *\{/ { print; infn = !/\} *$/; next }
  infn { print }
  infn && /^}/ { infn = 0 }
  END { if (!found) exit 2 }
' "$TEMPLATE") || { echo "FAIL: no '# STAGES:' marker in $TEMPLATE"; exit 1; }
[[ -n "$FUNCS" ]] || { echo "FAIL: no functions extracted from $TEMPLATE"; exit 1; }
eval "$FUNCS"

# Every function the template defines above the marker must now be declared.
NAMES=$(awk '
  /^# STAGES:/ { exit }
  match($0, /^[A-Za-z_][A-Za-z0-9_]*\(\)/) { print substr($0, 1, RLENGTH - 2) }
' "$TEMPLATE")
for fn in $NAMES; do
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

# contents PATH prints the file on one line for a failure message.
contents() {
  if [[ -e "$1" ]]; then printf 'file [%s]' "$(tr '\n' '|' < "$1")"; else printf 'file missing'; fi
}

TMP_ROOT=$(mktemp -d)
trap 'rm -rf "$TMP_ROOT"' EXIT

# fresh: new empty case directory; sets ENV_FILE inside it.
fresh() {
  CASE_DIR="$TMP_ROOT/$1"
  mkdir -p "$CASE_DIR"
  ENV_FILE="$CASE_DIR/.env"
}

# expect_existing NAME WANT: _existing KEY returns 0 and prints WANT.
expect_existing() {
  local name="$1" want="$2" got
  if got=$(_existing KEY); then
    [[ "$got" == "$want" ]] && pass "$name" \
      || fail "$name" "got [$got], want [$want]; $(contents "$ENV_FILE")"
  else
    fail "$name" "_existing returned non-zero; $(contents "$ENV_FILE")"
  fi
}

# expect_refused NAME: _existing KEY returns non-zero.
expect_refused() {
  if _existing KEY >/dev/null; then
    fail "$1" "_existing returned 0; $(contents "$ENV_FILE")"
  else
    pass "$1"
  fi
}

# has_line PATH LINE: PATH holds LINE as a whole line.
has_line() { grep -qxF -- "$2" "$1"; }

# roundtrip NAME VALUE: write_env then _existing returns VALUE unchanged.
roundtrip() {
  fresh "$1"
  write_env KEY "$2" >/dev/null
  expect_existing "$1" "$2"
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
if [[ "$n" == 1 ]]; then
  expect_existing upsert_replaces second
else
  fail upsert_replaces "$n KEY lines; $(contents "$ENV_FILE")"
fi
[[ "$(_existing OTHER)" == x ]] && pass upsert_keeps_other \
  || fail upsert_keeps_other "$(contents "$ENV_FILE")"

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
if [[ -L "$ENV_FILE" && "$m" == 640 ]] && has_line "$CASE_DIR/target.env" "KEY='v'" \
   && has_line "$CASE_DIR/target.env" 'OLD=1'; then
  pass symlink_existing_target
else
  fail symlink_existing_target "link=$([[ -L $ENV_FILE ]] && echo yes || echo no) mode=$m; $(contents "$CASE_DIR/target.env")"
fi

# Symlink with a missing target: target created at mode 0600.
fresh symlink_missing_target
ln -s target.env "$ENV_FILE"
write_env KEY v >/dev/null
if [[ -L "$ENV_FILE" && -f "$CASE_DIR/target.env" ]]; then
  m=$(mode "$CASE_DIR/target.env")
  [[ "$m" == 600 ]] && has_line "$CASE_DIR/target.env" "KEY='v'" \
    && pass symlink_missing_target \
    || fail symlink_missing_target "mode=$m; $(contents "$CASE_DIR/target.env")"
else
  fail symlink_missing_target "target not created or link replaced"
fi

# _existing refuses a double-quoted value containing \, $ or ".
i=0
for v in 'a\nb' 'a\b' 'a$b' 'a\"b' 'a"b'; do
  i=$((i + 1))
  fresh "refuse_dquoted_$i"
  printf 'KEY="%s"\n' "$v" > "$ENV_FILE"
  expect_refused "refuse_dquoted [$v]"
done

# A plain double-quoted value still decodes.
fresh dquoted_plain
printf 'KEY="hello world"\n' > "$ENV_FILE"
expect_existing dquoted_plain 'hello world'

# Old-style unquoted KEY=VALUE line still reads.
fresh unquoted_legacy
printf 'KEY=plain_value\n' > "$ENV_FILE"
expect_existing unquoted_legacy plain_value

# _existing on a missing file or key returns non-zero.
fresh missing_file
expect_refused missing_file
printf 'OTHER=1\n' > "$ENV_FILE"
expect_refused missing_key

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
