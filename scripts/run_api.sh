#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
PROJECT_DIR=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)

cd "$PROJECT_DIR"
exec "${HERMES_PYTHON:-$PROJECT_DIR/.venv/bin/python}" -m uvicorn app.main:app --host "${API_BIND_ADDRESS:-0.0.0.0}" --port "${API_PORT:-8000}"
