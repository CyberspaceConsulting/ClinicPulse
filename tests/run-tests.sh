#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../backend"
VENV="${VENV:-.venv}"
[ -d "$VENV" ] || python3 -m venv "$VENV"
"$VENV/bin/pip" -q install -r requirements.txt
exec "$VENV/bin/python" -m pytest -q ../tests/backend "$@"
