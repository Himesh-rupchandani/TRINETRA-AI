"""Officer profiles + uploaded CCTV video pipeline (demo/test only)."""
import sys
import time
from pathlib import Path

for p in [str(Path(__file__).resolve().parents[1])]:
    if p not in sys.path:
        sys.path.insert(0, p)

import pytest
import cv2
import numpy as np
from fastapi.testclient import TestClient
from sqlalchemy import func

from app.database.database import SessionLocal, get_db, init_db
from app.database.models import Camera, VehicleEvent


@pytest.fixture(scope="module")
def client():
    """Live app against the real DB session so the background worker thread
    sees the same rows as the endpoints. Created rows/files are cleaned up."""
    init_db()
    from contextlib import asynccontextmanager
    from app.main import app

    @asynccontextmanager
    async def noop_lifespan(app):
        yield

    original_lifespan = app.router.lifespan_context
    app.router.lifespan_context = noop_lifespan
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c
    app.router.lifespan_context = original_lifespan
    app.dependency_overrides.clear()
    db = SessionLocal()
    try:
        for cam_id in ("CAM9TEST", "CAMX"):
            db.query(VehicleEvent).filter(
                func.upper(VehicleEvent.camera_id) == cam_id
            ).delete(synchronize_session=False)
            db.query(Camera).filter(func.upper(Camera.camera_id) == cam_id).delete(
                synchronize_session=False
            )
        db.commit()
    finally:
        db.close()
    from app.services.uploaded_video_service import upload_dir

    for name in ("cam9test.mp4",):
        try:
            (upload_dir() / name).unlink(missing_ok=True)
        except OSError:
            pass


def _write_clip(path, frames=10, size=(160, 120)):
    w = cv2.VideoWriter(path, cv2.VideoWriter_fourcc(*"mp4v"), 10, size)
    for i in range(frames):
        f = np.zeros((size[1], size[0], 3), np.uint8)
        cv2.rectangle(f, (5 + i, 40), (60 + i, 90), (200, 200, 200), -1)
        w.write(f)
    w.release()


def test_officer_roster(client: TestClient):
    me = client.get("/api/officers/me")
    assert me.status_code == 200
    assert me.json()["officer_id"] == "OFF-02471"
    assert me.json()["police_id"] == "GJ-02471"

    roster = client.get("/api/officers")
    assert roster.status_code == 200
    assert len(roster.json()) == 6
    # Selection list shape: photo + name + rank only (no stats/plates here).
    for o in roster.json():
        assert o["photo_url"] and o["name"] and o["designation"]

    priya = client.get("/api/officers/OFF-03318").json()
    assert priya["name"] == "SI Priya Sharma"
    assert priya["police_id"] == "GJ-03318"
    assert priya["vehicles_caught"] == 6
    assert priya["total_challans"] == 8
    assert priya["total_challan_amount"] == 16500
    assert priya["total_amount_collected"] == 8500
    assert priya["net_revenue"] == 7500
    assert len(priya["plates"]) == 6

    assert client.get("/api/officers/OFF-99999").status_code == 404


def test_upload_registers_camera_and_processes(client: TestClient, tmp_path):
    nxt = client.get("/api/uploads/videos/next-camera-id")
    assert nxt.status_code == 200
    assert nxt.json()["camera_id"].startswith("CAM")

    cam_id = "CAM9TEST"
    clip = str(tmp_path / "cam9test.mp4")
    _write_clip(clip)
    with open(clip, "rb") as fh:
        r = client.post(
            "/api/uploads/videos",
            files={"file": ("cam9test.mp4", fh, "video/mp4")},
            data={"camera_id": cam_id},
        )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["camera_id"] == cam_id
    assert body["video_file"] == "cam9test.mp4"
    assert body["job_status"] in ("QUEUED", "PROCESSING", "DONE")

    # Camera grid picks the upload up as a playable file camera.
    cam = client.get(f"/api/cameras/{cam_id.lower()}")
    assert cam.status_code == 200
    assert cam.json()["stream_type"] == "FILE"
    assert cam.json()["status"] == "ONLINE"

    # Unsupported file types are rejected, not stored.
    bad = client.post(
        "/api/uploads/videos",
        files={"file": ("notes.txt", b"hello", "text/plain")},
        data={"camera_id": "CAMX"},
    )
    assert bad.status_code == 422

    # Background job finishes the 10-frame clip quickly.
    final = None
    for _ in range(60):
        time.sleep(0.5)
        final = client.get(f"/api/uploads/videos/{cam_id}").json()
        if final["job_status"] in ("DONE", "FAILED"):
            break
    assert final is not None and final["job_status"] == "DONE"
    assert final["frames_total"] == 10
    assert final["progress_pct"] == 100.0
    # Without the YOLO weights installed, no detections — but the job must
    # say so instead of silently producing nothing.
    assert "recent_plates" in final


def test_simple_tracker_ids_are_stable():
    from app.services.simple_tracker import SimpleTracker

    t = SimpleTracker(iou_threshold=0.25, max_misses=2)
    live, _ = t.update([(10, 10, 60, 60, "car", 0.9), (200, 10, 260, 60, "car", 0.8)])
    assert [b.track_id for b in live] == [1, 2]
    # Slight motion keeps the same ids; a newcomer gets id 3.
    live, _ = t.update(
        [(12, 10, 62, 60, "car", 0.9), (200, 12, 260, 62, "car", 0.8), (400, 10, 450, 60, "bus", 0.7)]
    )
    assert sorted(b.track_id for b in live) == [1, 2, 3]
    # Vanished tracks retire after max_misses and report back for flushing.
    all_retired = []
    for _ in range(4):
        _, retired = t.update([])
        all_retired.extend(retired)
    assert {b.track_id for b in all_retired} == {1, 2, 3}


def test_plate_normalizer_strips_format_noise():
    from app.utils.plate_normalizer import normalize_plate

    assert normalize_plate("GJ 01 AB 1234") == "GJ01AB1234"
    assert normalize_plate("mh-02 cd 5678") == "MH02CD5678"
