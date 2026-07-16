#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

PYTHON_BIN="${PYTHON_BIN:-python3}"
VENV_DIR="${VENV_DIR:-.venv}"

if [[ "${ALLOW_DIRTY_BUILD:-0}" != "1" && -n "$(git status --porcelain)" ]]; then
  echo "Refusing to build from a dirty worktree." >&2
  echo "Commit, stash, or set ALLOW_DIRTY_BUILD=1 for a local-only build." >&2
  git status --short >&2
  exit 2
fi

if [[ ! -x "$VENV_DIR/bin/python" ]]; then
  "$PYTHON_BIN" -m venv "$VENV_DIR"
fi

PYTHON="$VENV_DIR/bin/python"

"$PYTHON" -m pip install --upgrade pip 'setuptools>=83,<84' build twine

rm -rf dist build ./*.egg-info

"$PYTHON" setup.py check --metadata --strict
"$PYTHON" -m build
"$PYTHON" -m twine check dist/*

echo "Package build completed successfully."
echo "Artifacts are available in $ROOT_DIR/dist."
