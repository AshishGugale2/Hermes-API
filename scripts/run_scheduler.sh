#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
PROJECT_DIR=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)
cd "$PROJECT_DIR" || exit 1
exec "${HERMES_PYTHON:-$PROJECT_DIR/.venv/bin/python}" -m app.jobs.scheduler
