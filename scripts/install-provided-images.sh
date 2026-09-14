#!/usr/bin/env bash
# Install EXACT user-provided evidence images into Vehicle Log
# Usage: ./scripts/install-provided-images.sh /path/to/your/5/images
#   or   ./scripts/install-provided-images.sh  # will look in ~/Downloads and /tmp
set -e
SRC="${1:-}"
PLATES_DIR="trinetra-ai/public/plates"
mkdir -p "$PLATES_DIR"
PLATES=("RJ19CL5074" "GJ03HK2595" "GJ03NB2146" "GJ03JL5362" "GJ03JL2801")
echo "Installing provided images to $PLATES_DIR (exact, no AI substitutes)..."
for p in "${PLATES[@]}"; do
  FOUND=""
  if [ -n "$SRC" ] && [ -f "$SRC/$p.jpg" ]; then FOUND="$SRC/$p.jpg"
  elif [ -n "$SRC" ] && [ -f "$SRC/${p}.JPG" ]; then FOUND="$SRC/${p}.JPG"
  elif [ -f "$HOME/Downloads/$p.jpg" ]; then FOUND="$HOME/Downloads/$p.jpg"
  elif [ -f "/tmp/$p.jpg" ]; then FOUND="/tmp/$p.jpg"
  elif [ -f "./$p.jpg" ]; then FOUND="./$p.jpg"
  fi
  if [ -n "$FOUND" ]; then
    cp -v "$FOUND" "$PLATES_DIR/$p.jpg"
  else
    echo "  MISSING $p.jpg - place exact image at $PLATES_DIR/$p.jpg (see $PLATES_DIR/README.md)"
  fi
done
echo "Done. Verify:"
ls -lh "$PLATES_DIR"/*.jpg 2>&1 || echo "No JPG yet - add the 5 exact photos per README"
echo "Now search any plate in Vehicle Log: e.g., RJ19CL5074, GJ03HK2595..."
