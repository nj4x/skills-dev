#!/bin/bash
# Symlink this extension into ~/.vscode/extensions/ for the dev loop
# (design #71: no vsix pipeline — rebuild + reload window).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VERSION="$(node -p "require('$ROOT/package.json').version")"
PUBLISHER="$(node -p "require('$ROOT/package.json').publisher")"
NAME="$(node -p "require('$ROOT/package.json').name")"
LINK="$HOME/.vscode/extensions/$PUBLISHER.$NAME-$VERSION"

if [ ! -f "$ROOT/out/extension.js" ]; then
  echo "out/extension.js missing — run 'npm run compile' first" >&2
  exit 1
fi

ln -sfn "$ROOT" "$LINK"
echo "linked: $LINK -> $ROOT"
echo "reload the VS Code window to pick it up"
