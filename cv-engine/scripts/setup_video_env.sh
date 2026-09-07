#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# Offline-friendly environment setup for the cv-engine recorded-video pipeline.
#
# Creates a Python environment with the CV stack and fetches the model weights
# used by scripts/analyze_video_file.py.
#
# Usage:
#   bash cv-engine/scripts/setup_video_env.sh [VENV_DIR]
#
# Notes
# -----
# * torch/ultralytics are installed from PyPI. On a CPU-only box you can use
#   the smaller CPU wheels instead (needs download.pytorch.org reachable):
#       pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu
# * opencv-python-headless is force-reinstalled LAST: ultralytics pulls the GUI
#   build which crashes headless servers with "libGL.so.1: cannot open ...".
# * Weights are downloaded to cv-engine/models_dev/ (git-ignored):
#     - yolo11n.pt                 stock Ultralytics YOLO11-nano (COCO vehicles)
#     - license_plate_detector.pt  single-class licence-plate detector
#   Both are verified by SHA-256 so a corrupted/substituted file is rejected.
# ---------------------------------------------------------------------------
set -euo pipefail

VENV_DIR="${1:-$HOME/pyenv}"
CV_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MODELS="${TRINETRA_MODELS_DIR:-$HOME/models}"

echo "==> python env: $VENV_DIR"
if [ ! -x "$VENV_DIR/bin/python" ]; then
  python3 -m venv "$VENV_DIR"
fi
"$VENV_DIR/bin/pip" install --no-cache-dir -q --upgrade pip
"$VENV_DIR/bin/pip" install --no-cache-dir -q ultralytics rapidocr-onnxruntime psutil pytest httpx
"$VENV_DIR/bin/pip" uninstall -y -q opencv-python 2>/dev/null || true
"$VENV_DIR/bin/pip" install --no-cache-dir -q --force-reinstall "opencv-python-headless>=4.9"

echo "==> model weights: $MODELS"
mkdir -p "$MODELS"

# sha256 of the official Ultralytics yolo11n.pt (v8.3.0 assets release) and of
# the licence-plate detector used by this pipeline.
YOLO_SHA="0ebbc80d4a7680d14987a577cd21342b65ecfd94632bd9a8da63ae6417644ee1"
PLATE_SHA="8ec3b254a6c87610f037a90957462cafa11a9c03224e33a28c6a1d1ac2ac51b0"

fetch() { # fetch <dest> <sha256> <primary-url> [gh-repo] [gh-path]
  local dest="$1" sha="$2" url="$3" repo="${4:-}" path="${5:-}"
  if [ -f "$dest" ] && [ "$(sha256sum "$dest" | cut -d' ' -f1)" = "$sha" ]; then
    echo "    ok (cached): $(basename "$dest")"; return 0
  fi
  echo "    downloading $(basename "$dest") ..."
  if curl -fsSL --max-time 300 -o "$dest" "$url" 2>/dev/null; then :;
  elif [ -n "$repo" ] && command -v gh >/dev/null; then
    # Fallback for networks where release-asset CDNs are blocked but the
    # GitHub API is reachable.
    gh api -H "Accept: application/vnd.github.raw" "/repos/$repo/contents/$path" > "$dest"
  else
    echo "    FAILED to download $(basename "$dest")" >&2; return 1
  fi
  local got; got="$(sha256sum "$dest" | cut -d' ' -f1)"
  if [ "$got" != "$sha" ]; then
    echo "    SHA MISMATCH for $(basename "$dest"): $got != $sha" >&2
    rm -f "$dest"; return 1
  fi
  echo "    ok: $(basename "$dest")"
}

fetch "$MODELS/yolo11n.pt" "$YOLO_SHA" \
  "https://github.com/ultralytics/assets/releases/download/v8.3.0/yolo11n.pt" \
  "Vedant363/Vehicle-Detection-and-Traffic-Assessment" "yolo11n.pt"

fetch "$MODELS/license_plate_detector.pt" "$PLATE_SHA" \
  "https://github.com/DHANA-TEJA/vehicle-plate-detection-yolo11/raw/main/best.pt" \
  "DHANA-TEJA/vehicle-plate-detection-yolo11" "best.pt"

echo "==> done. Run the pipeline with:"
echo "    $VENV_DIR/bin/python $CV_ROOT/scripts/analyze_video_file.py <video.mp4> --location \"Faculty Parking\""
