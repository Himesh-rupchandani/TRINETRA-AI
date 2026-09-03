#!/usr/bin/env bash
# One-shot dev environment bootstrap for the Trinetra CV engine.
# Idempotent. Usage:
#   bash scripts/install_dev_env.sh                 # CPU torch (recommended)
#   TRINETRA_TORCH_INDEX="" bash scripts/install_dev_env.sh   # plain PyPI wheel
#   TRINETRA_CUDA=1 bash scripts/install_dev_env.sh           # CUDA wheels
set -uo pipefail
cd "$(dirname "$0")/.."

VENV="${VENV:-../.venv}"
PIP="$VENV/bin/pip"
TORCH_INDEX="${TRINETRA_TORCH_INDEX-https://download.pytorch.org/whl/cpu}"

echo "== [1/4] core (numpy, opencv, requests, pytest, psutil) =="
$PIP install -q numpy "opencv-python-headless>=4.9" requests pytest pytest-timeout psutil || exit 1

echo "== [2/4] torch =="
if [ -n "$TORCH_INDEX" ]; then
  $PIP install -q --index-url "$TORCH_INDEX" torch torchvision || exit 1
else
  # PyPI's Linux wheel is a CUDA build; it imports fine without a GPU.
  $PIP install -q torch torchvision || exit 1
fi

echo "== [3/4] detector + tracker (YOLO11, ByteTrack) =="
$PIP install -q "ultralytics>=8.3" || exit 1

echo "== [4/4] OCR =="
# rapidocr ships the PP-OCR models inside the wheel: no CDN download, fast on CPU.
$PIP install -q onnxruntime rapidocr-onnxruntime || echo "WARN: rapidocr install failed"
# easyocr is the alternative engine; its weights come from GitHub on first use.
$PIP install -q easyocr || echo "WARN: easyocr install failed (rapidocr still available)"

echo "== import check =="
"$VENV/bin/python" - <<'PY'
import importlib
for m in ("numpy", "cv2", "torch", "ultralytics", "onnxruntime", "rapidocr_onnxruntime", "easyocr", "psutil", "pytest"):
    try:
        mod = importlib.import_module(m)
        extra = f" cuda_available={mod.cuda.is_available()}" if m == "torch" else ""
        print(f"OK   {m} {getattr(mod, '__version__', '')}{extra}")
    except Exception as e:
        print(f"MISS {m}: {type(e).__name__}: {e}")
PY
echo "DONE"
