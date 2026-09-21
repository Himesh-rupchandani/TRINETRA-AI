#!/usr/bin/env bash
# Existing Render Web Service -> Start Command: bash scripts/render_start.sh
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="${PYTHON_BIN:-python}"
export OMP_NUM_THREADS="${OMP_NUM_THREADS:-2}"
export MKL_NUM_THREADS="${MKL_NUM_THREADS:-2}"
export OPENBLAS_NUM_THREADS="${OPENBLAS_NUM_THREADS:-2}"
cd "$ROOT/TRINETRAAI/backend"
"$PYTHON" "$ROOT/scripts/render_preflight.py"
# One process owns the frame scheduler, preview photos, source leases and SSE.
# PORT is injected by Render. Do not start another API-only process here.
exec "$PYTHON" -m uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-10000}" --workers 1
