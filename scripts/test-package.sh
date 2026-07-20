#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

PYTHON_BIN="${PYTHON_BIN:-python3}"
VENV_DIR="${VENV_DIR:-.venv}"

if [[ ! -x "$VENV_DIR/bin/python" ]]; then
  "$PYTHON_BIN" -m venv "$VENV_DIR"
fi

PYTHON="$VENV_DIR/bin/python"

"$PYTHON" -m pip install --upgrade pip 'setuptools>=83,<84'
"$PYTHON" -m pip install -e '.[dev,test]'

"$PYTHON" -m unittest discover -s tests
"$PYTHON" -m ruff check src tests
"$PYTHON" -m compileall -q src tests

echo "Idelium CLI local test suite completed successfully."
