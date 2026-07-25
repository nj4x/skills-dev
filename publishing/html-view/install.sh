#!/usr/bin/env bash
# Wrap in a subshell so set options don't leak into the parent shell when sourced
(
  set -euo pipefail

  SKILL_NAME="html-view"
  DEST="$HOME/.claude/skills/$SKILL_NAME"
  SRC="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"

  mkdir -p "$HOME/.claude/skills"

  # rm -rf cleanly replaces a prior symlink or directory at DEST
  if [ -L "$DEST" ] || [ -e "$DEST" ]; then
    echo "Replacing existing install at $DEST"
    rm -rf "$DEST"
  fi

  ln -s "$SRC" "$DEST"
  echo "Installed: $DEST -> $SRC"
  echo "Open a new Claude Code session to use /html-view"
)
