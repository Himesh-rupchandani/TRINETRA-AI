#!/usr/bin/env bash
# Native Python Render service: Root Directory MUST be blank (repository root).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="${PYTHON_BIN:-python}"
cd "$ROOT"
case "${TRINETRA_API_ONLY:-0}" in
  1|true|TRUE|yes|YES|on|ON)
    echo "ERROR: Unset TRINETRA_API_ONLY (or set it to 0) for the Render ML backend." >&2
    exit 1 ;;
esac
# Avoid downloading a CUDA stack onto a CPU web-service instance.
"$PYTHON" -m pip install --upgrade pip
"$PYTHON" -m pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu
"$PYTHON" -m pip install -r TRINETRAAI/backend/requirements-ml.txt
"$PYTHON" scripts/ensure_headless_opencv.py
"$PYTHON" scripts/render_preflight.py --imports-only
