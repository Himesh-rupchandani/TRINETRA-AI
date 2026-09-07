#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# Faculty Parking demo loop (Phases 2, 12-18 of the brief):
#
#     short sample run  ->  eyeball detections  ->  full run  ->  target report
#
# Usage:
#   bash cv-engine/scripts/run_faculty_parking.sh /path/to/faculty_parking.mp4
#   bash cv-engine/scripts/run_faculty_parking.sh --drive-url "<public drive link>"
#
# Environment:
#   PY       python interpreter (default: $HOME/pyenv/bin/python, else python3)
#   SAMPLE   seconds analysed in the sample pass (default 25)
#   EXTRA    extra flags forwarded to analyze_video_file.py (e.g. "--frame-skip 3")
# ---------------------------------------------------------------------------
set -euo pipefail

CV_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REPO_ROOT="$(cd "$CV_ROOT/.." && pwd)"
PY="${PY:-$([ -x "$HOME/pyenv/bin/python" ] && echo "$HOME/pyenv/bin/python" || echo python3)}"
SAMPLE="${SAMPLE:-25}"
EXTRA="${EXTRA:-}"
export YOLO_CONFIG_DIR="${YOLO_CONFIG_DIR:-/tmp/Ultralytics}"

if [ $# -lt 1 ]; then
  echo "usage: $0 <video.mp4> | --drive-url <link>" >&2
  exit 2
fi

if [ "$1" = "--drive-url" ]; then
  SOURCE=(--drive-url "$2")
else
  SOURCE=("$1")
fi

COMMON=(--location "Faculty Parking" --camera-id faculty_parking
        --video-id faculty_parking_01 --target-sightings 5)

echo "=============================================================="
echo "PASS 1/2 — ${SAMPLE}s SAMPLE (verify vehicles are detected)"
echo "=============================================================="
"$PY" "$CV_ROOT/scripts/analyze_video_file.py" "${SOURCE[@]}" "${COMMON[@]}" \
  --sample "$SAMPLE" \
  --output-dir "$REPO_ROOT/outputs/faculty_parking_sample" $EXTRA

echo
read -r -p "Sample looks correct? Continue with the FULL video? [y/N] " reply
case "$reply" in
  [yY]*) ;;
  *) echo "stopped after the sample pass."; exit 0 ;;
esac

echo "=============================================================="
echo "PASS 2/2 — FULL VIDEO"
echo "=============================================================="
"$PY" "$CV_ROOT/scripts/analyze_video_file.py" "${SOURCE[@]}" "${COMMON[@]}" \
  --output-dir "$REPO_ROOT/outputs/faculty_parking" $EXTRA

echo
echo "Backend handoff (dry run):"
"$PY" "$CV_ROOT/scripts/post_sightings.py" \
  "$REPO_ROOT/outputs/faculty_parking/events.json" --dry-run | head -5
echo
echo "Deliverables in $REPO_ROOT/outputs/faculty_parking/"
