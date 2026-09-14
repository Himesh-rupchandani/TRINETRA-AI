"""End-to-end DB persistence check for the Video Analysis dashboard path.

Registers a short clip, runs the real worker, then verifies:
  * VehicleEvent rows store frame_number / plate / evidence refs consistently,
  * plate_matching.search finds the plate.
"""
import os
import sys
import time
from pathlib import Path

BACKEND = Path("/home/user/hack/TRINETRAAI/backend")
sys.path.insert(0, str(BACKEND))
os.chdir(BACKEND)

# Build a short clip from the first 60 frames of the demo video.
import cv2  # noqa: E402

src = BACKEND / "demo_cam04.mp4"
cap = cv2.VideoCapture(str(src))
w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
fps = cap.get(cv2.CAP_PROP_FPS)
short = Path("/tmp/demo_short.mp4")
wr = cv2.VideoWriter(str(short), cv2.VideoWriter_fourcc(*"mp4v"), fps, (w, h))
for i in range(60):
    ok, f = cap.read()
    if not ok:
        break
    wr.write(f)
wr.release()
cap.release()
print("short clip:", short, short.stat().st_size, "bytes")

from app.database.database import SessionLocal, init_db  # noqa: E402
from app.database.models import VehicleEvent  # noqa: E402
from app.services import video_analysis_service as vas  # noqa: E402
from app.services import plate_matching  # noqa: E402

init_db()
db = SessionLocal()
video = vas.register_upload(db, "demo_short.mp4", short.read_bytes(), "e2e-check")
db.close()
print("registered video_id=", video.video_id, "camera=", video.camera_id)

db = SessionLocal()
vas.start_analysis(db, [video.video_id])
db.close()

deadline = time.time() + 600
status = None
while time.time() < deadline:
    db = SessionLocal()
    st = vas.batch_status(db, "e2e-check")
    db.close()
    status = st["videos"][0]["status"]
    print("status:", status, flush=True)
    if status in ("DONE", "FAILED"):
        break
    time.sleep(5)

db = SessionLocal()
rows = db.query(VehicleEvent).filter(VehicleEvent.video_id == video.video_id).all()
print(f"\n{len(rows)} VehicleEvent rows:")
for r in rows:
    print(f"  track={r.vehicle_track_id} frame={r.frame_number} off={r.video_offset_sec} "
          f"cls={r.vehicle_class} plate={r.plate_number!r} raw={r.plate_raw!r} "
          f"pconf={r.plate_confidence} status={r.plate_status} "
          f"bbox={r.bbox} ev={r.evidence_ref} pev={r.plate_evidence_ref} "
          f"lat={r.latitude} lng={r.longitude}")

# Search
for plate in sorted({r.plate_number for r in rows if r.plate_number}):
    res = plate_matching.search(db, plate)
    print(f"search {plate}: found={res['found']} type={res['match_type']} "
          f"videos={res['vehicle']['video_count']} seq={res['vehicle']['sequence']}")
db.close()
print("DONE")
