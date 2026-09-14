"""One-shot: process the real demo video through the dashboard pipeline + DB.

Resets the local SQLite dev DB, registers the full demo_cam04.mp4, runs the
analysis worker to completion, then prints a full ledger of what was stored.
"""
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

os.chdir(str(Path(__file__).resolve().parent))

DB = Path("trinetra.db")

# Clean slate for the demo DB (it is gitignored dev state).
if DB.exists():
    DB.unlink()

from app.database.database import SessionLocal, init_db  # noqa: E402
from app.database.models import VehicleEvent, VideoSource, Camera  # noqa: E402
from app.services import video_analysis_service as vas  # noqa: E402

init_db()
db = SessionLocal()
data = Path("demo_cam04.mp4").read_bytes()
video = vas.register_upload(db, "demo_cam04.mp4", data, "demo", camera_id="DEMO_CAM04")
db.close()
print(f"registered video_id={video.video_id} camera={video.camera_id}")

db = SessionLocal()
vas.start_analysis(db, [video.video_id])
db.close()

deadline = time.time() + 900
status = None
while time.time() < deadline:
    db = SessionLocal()
    st = vas.batch_status(db, "demo")
    db.close()
    v = st["videos"][0]
    status = v["status"]
    print(f"status={status} progress={v['progress_pct']}% frames={v['frames_read']} "
          f"vehicles={v['vehicles_detected']} plates={v['plates_read']}", flush=True)
    if status in ("DONE", "FAILED"):
        break
    time.sleep(10)

db = SessionLocal()
rows = db.query(VehicleEvent).filter(VehicleEvent.video_id == video.video_id).all()
print(f"=== {len(rows)} sightings stored ===", flush=True)
for r in rows:
    print(f"track={r.vehicle_track_id} frame={r.frame_number} off={r.video_offset_sec} "
          f"cls={r.vehicle_class} vconf={r.vehicle_confidence} "
          f"plate={r.plate_number!r} pconf={r.plate_confidence} status={r.plate_status} "
          f"ev={r.evidence_ref} pev={r.plate_evidence_ref}", flush=True)
db.close()
print("DONE", flush=True)
