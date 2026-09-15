#!/usr/bin/env bash
# Smoke test: start the mock partner API, run the sync, run it again to
# prove idempotency, then clean up. Run from the repo root.
set -euo pipefail

VENV=.venv
if [ ! -d "$VENV" ]; then
  python3 -m venv "$VENV"
  "$VENV/bin/pip" install -q -r requirements.txt
fi
PY="$VENV/bin/python"

"$PY" -m uvicorn mock_partner_api.server:app --host 127.0.0.1 --port 8000 &
API_PID=$!
trap 'kill $API_PID' EXIT
sleep 2

echo "=== First sync ==="
PYTHONPATH=. "$PY" -m pipeline.sync --base-url http://127.0.0.1:8000 --db demo.db

echo
echo "=== Second sync (should add zero new rows) ==="
PYTHONPATH=. "$PY" -m pipeline.sync --base-url http://127.0.0.1:8000 --db demo.db

echo
echo "=== Tests ==="
PYTHONPATH=. "$PY" -m pytest -q tests/
