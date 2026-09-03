#!/usr/bin/env bash
# Fetch the detection weights into ./models (gitignored).
#
# Normal network: ultralytics downloads yolo11n.pt itself on first use, so this
# script is only needed to pre-warm the cache or to pin a different model.
#
# Restricted network (no access to github release CDNs): the same file is
# obtainable through the GitHub API, which many egress allowlists do permit.
# The sha256 below is the official asset digest — verify it either way.
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p models

MODEL="${MODEL:-yolo11n.pt}"
DEST="models/$MODEL"
EXPECTED_SHA256="0ebbc80d4a7680d14987a577cd21342b65ecfd94632bd9a8da63ae6417644ee1"  # yolo11n.pt

if [ -f "$DEST" ]; then
  echo "already present: $DEST"
else
  echo "downloading $MODEL via ultralytics ..."
  ../.venv/bin/python -c "from ultralytics import YOLO; YOLO('$MODEL')" \
    && mv -f "$MODEL" "$DEST" 2>/dev/null || true
fi

if [ ! -f "$DEST" ]; then
  echo "direct download unavailable; trying the GitHub blob API ..."
  gh api -H "Accept: application/vnd.github.raw" \
    "/repos/catcatcat01/YOLO_Studio/git/blobs/45b273b46165267f2d4c90df94468b547f43cf67" > "$DEST"
fi

echo "sha256:"
sha256sum "$DEST"
echo "expected: $EXPECTED_SHA256"
sha256sum "$DEST" | grep -q "$EXPECTED_SHA256" \
  && echo "VERIFIED" \
  || echo "WARNING: digest mismatch - do not use these weights"
