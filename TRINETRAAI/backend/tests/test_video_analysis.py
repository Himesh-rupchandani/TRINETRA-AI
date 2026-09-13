"""
Multi-video vehicle / number-plate analysis — the 17 required scenarios.

The video decoding, tracking, storage, matching, API and error handling are all
exercised for real. Only the two *model* stages (YOLO vehicle detection and the
OCR engine) are stubbed, so the suite is deterministic and runs on a CPU-only
box in seconds instead of depending on downloadable weights.

Nothing here writes fabricated plates into the product database: the tests use
their own camera ids (``TCAM*``) and delete every row and file they create.
"""
import sys
import time
from contextlib import asynccontextmanager
from pathlib import Path

for _p in [str(Path(__file__).resolve().parents[1])]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func

from app.database.database import SessionLocal, init_db
from app.database.models import Camera, VehicleEvent, VideoSource
from app.services import video_analysis_service as vas
from app.services.anpr_pipeline import PlateRead
from app.services.ocr_service import ocr_service
from app.services.vehicle_detection_service import VehicleDetection, vehicle_detection_service

TEST_PREFIX = "TCAM"
FRAMES = 30
SIZE = (320, 240)

# camera id -> (plate, ocr confidence, indian format) the stub "reads".
# Chosen so the suite covers: same plate in two videos, a camera that never saw
# it, a single-video vehicle, a low-confidence read and an unreadable vehicle.
SCRIPT = {
    "TCAM1": ("GJ01AB1234", 0.95, True),
    "TCAM2": ("MH12XY4567", 0.93, True),
    "TCAM3": ("GJ01AB1234", 0.91, True),
    "TCAM4": ("GJ05CD6789", 0.62, True),   # below OCR_LOW_CONFIDENCE_MARK
    "TCAM5": (None, 0.0, False),           # vehicle present, plate unreadable
    "TCAM6": ("GJ01AB1Z34", 0.75, True),   # 1 confusable char vs TCAM1's plate, not trusted
}


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #
def _write_clip(path: Path, frames: int = FRAMES) -> None:
    w = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), 10, SIZE)
    for i in range(frames):
        frame = np.full((SIZE[1], SIZE[0], 3), 40, dtype=np.uint8)
        cv2.rectangle(frame, (40 + i, 60), (200 + i, 180), (200, 200, 200), -1)
        w.write(frame)
    w.release()


def _camera_of(video_path: str) -> str:
    return Path(video_path).stem.upper()


def _fake_detect(frame, conf=None, imgsz=None):
    """One steadily moving vehicle — enough for the tracker to hold one id.

    `conf`/`imgsz` are the offline-analysis overrides the pipeline passes to the
    detector; the stub accepts and ignores them.
    """
    h, w = frame.shape[:2]
    x1 = 40
    return [VehicleDetection(x1=x1, y1=60, x2=min(w - 1, x1 + 180), y2=min(h - 1, 180),
                             class_name="car", confidence=0.92)]


_TLS = __import__("threading").local()


def _fake_read_factory():
    """Thread-local: each analysis worker reads *its own* video's script."""
    def _fake_read(frame, bbox, vehicle_class="car"):
        plate, conf, indian = SCRIPT.get(getattr(_TLS, "camera", ""), (None, 0.0, False))
        if not plate:
            return None
        return PlateRead(raw=plate, normalized=plate, confidence=conf,
                         ocr_confidence=conf, indian_format=indian, plate_box=None)
    return _fake_read


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    init_db()
    from app.main import app

    @asynccontextmanager
    async def noop_lifespan(app):  # skip camera threads
        yield

    original_lifespan = app.router.lifespan_context
    app.router.lifespan_context = noop_lifespan

    # --- stub the two model stages -----------------------------------------
    original_detect = vehicle_detection_service.detect
    original_ensure = vehicle_detection_service._ensure_model
    original_model = vehicle_detection_service._model
    original_read = vas.read_plate_for_vehicle
    original_engine = ocr_service._engine
    original_attempted = ocr_service._attempted
    original_run = vas._run_video

    vehicle_detection_service.detect = _fake_detect
    vehicle_detection_service._ensure_model = lambda: object()
    vehicle_detection_service._model = object()
    vas.read_plate_for_vehicle = _fake_read_factory()
    ocr_service._engine, ocr_service._attempted = object(), True

    def _run_with_camera(video_id: str):
        """Runs inside the worker thread: tag it with the video it is reading."""
        db = SessionLocal()
        try:
            v = db.query(VideoSource).filter(VideoSource.video_id == video_id).first()
            _TLS.camera = v.camera_id if v else ""
        finally:
            db.close()
        return original_run(video_id)

    vas._run_video = _run_with_camera

    with TestClient(app, raise_server_exceptions=True) as c:
        yield c

    # --- restore + clean up -------------------------------------------------
    app.router.lifespan_context = original_lifespan
    app.dependency_overrides.clear()
    vehicle_detection_service.detect = original_detect
    vehicle_detection_service._ensure_model = original_ensure
    vehicle_detection_service._model = original_model
    vas.read_plate_for_vehicle = original_read
    vas._run_video = original_run
    ocr_service._engine, ocr_service._attempted = original_engine, original_attempted

    db = SessionLocal()
    try:
        videos = db.query(VideoSource).filter(
            VideoSource.camera_id.like(f"{TEST_PREFIX}%")
        ).all()
        for v in videos:
            try:
                if v.file_path:
                    Path(v.file_path).unlink(missing_ok=True)
            except OSError:
                pass
        db.query(VideoSource).filter(
            VideoSource.camera_id.like(f"{TEST_PREFIX}%")
        ).delete(synchronize_session=False)
        db.query(VehicleEvent).filter(
            VehicleEvent.camera_id.like(f"{TEST_PREFIX}%")
        ).delete(synchronize_session=False)
        db.query(Camera).filter(
            Camera.camera_id.like(f"{TEST_PREFIX}%")
        ).delete(synchronize_session=False)
        db.commit()
    finally:
        db.close()


@pytest.fixture(scope="module")
def clips(tmp_path_factory):
    d = tmp_path_factory.mktemp("analysis_clips")
    paths = {}
    for cam in SCRIPT:
        p = d / f"{cam}.mp4"
        _write_clip(p)
        paths[cam] = p
    return paths


def _upload(client, clips, cams):
    files = [("files", (f"{c}.mp4", clips[c].read_bytes(), "video/mp4")) for c in cams]
    return client.post("/api/analysis/videos/upload", files=files)


def _wait_done(client, batch_id, timeout=120.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        # Scoped to this batch: other videos in the product database (e.g. a
        # real operator's upload still being analysed) must not block the test.
        body = client.get("/api/analysis/status", params={"batch_id": batch_id}).json()
        if body["status"] in ("DONE", "EMPTY") and body["total_videos"]:
            if all(v["status"] in ("DONE", "FAILED") for v in body["videos"]):
                return body
        time.sleep(0.4)
    raise AssertionError("analysis did not finish in time")


@pytest.fixture(scope="module")
def analysed(client, clips):
    """Upload all six clips, run the pipeline once, reuse the result."""
    res = _upload(client, clips, list(SCRIPT))
    assert res.status_code in (200, 201), res.text
    assert res.json()["errors"] == []
    batch = res.json()
    # Run ONLY this batch's videos — never pull unrelated uploads into the
    # stubbed test pipeline.
    run = client.post(
        "/api/analysis/run",
        json={"video_ids": [v["video_id"] for v in batch["added"]]},
    )
    assert run.status_code == 200, run.text
    status = _wait_done(client, batch["batch_id"])
    results = client.get(
        "/api/analysis/results", params={"batch_id": batch["batch_id"]}
    ).json()
    return {"status": status, "results": results}


def _record(results, plate):
    for v in results["vehicles"]:
        if v["plate"] == plate:
            return v
    return None


# --------------------------------------------------------------------------- #
# 1. Multiple local videos can be added in one request
# --------------------------------------------------------------------------- #
def test_01_multiple_local_videos_are_registered(analysed, client):
    videos = client.get("/api/analysis/videos").json()["videos"]
    mine = [v for v in videos if v["camera_id"].startswith(TEST_PREFIX)]
    assert len(mine) == len(SCRIPT)
    assert {v["camera_id"] for v in mine} == set(SCRIPT)
    assert all(v["source_type"] == "UPLOAD" for v in mine)
    # metadata is probed from the real file, not guessed
    assert all(v["frames_total"] == FRAMES and v["width"] == SIZE[0] for v in mine)


# --------------------------------------------------------------------------- #
# 2. The camera id is derived from the file name (CAM1.mp4 -> CAM1)
# --------------------------------------------------------------------------- #
def test_02_camera_id_from_filename_and_collisions(client, clips):
    assert vas.camera_id_from_filename("CAM1.mp4") == "CAM1"
    assert vas.camera_id_from_filename("junction 7 - east.MOV") == "JUNCTION_7_EAST"
    db = SessionLocal()
    try:
        taken = vas.unique_camera_id(db, "TCAM1")
        assert taken == "TCAM1_2", "a second video must not silently overwrite a camera"
    finally:
        db.close()


# --------------------------------------------------------------------------- #
# 3. A non-video / oversized upload is rejected with a clear reason
# --------------------------------------------------------------------------- #
def test_03_invalid_upload_is_rejected_clearly(client, clips):
    res = client.post(
        "/api/analysis/videos/upload",
        files=[("files", ("notes.txt", b"not a video", "text/plain"))],
    )
    # every file rejected -> 422 with the reason, and nothing is registered
    assert res.status_code == 422
    assert "unsupported video type" in res.json()["detail"].lower()
    db = SessionLocal()
    try:
        assert db.query(VideoSource).filter(VideoSource.source_name == "notes.txt").count() == 0
    finally:
        db.close()

    # a mixed batch keeps the good file and reports the bad one per-file
    mixed = client.post(
        "/api/analysis/videos/upload",
        files=[
            ("files", ("TCAM7.mp4", clips["TCAM1"].read_bytes(), "video/mp4")),
            ("files", ("broken.txt", b"nope", "text/plain")),
        ],
    )
    assert mixed.status_code in (200, 201)
    body = mixed.json()
    assert [v["camera_id"] for v in body["added"]] == ["TCAM7"]
    assert len(body["errors"]) == 1
    assert body["errors"][0]["source_name"] == "broken.txt"


# --------------------------------------------------------------------------- #
# 4. Google Drive: a malformed link is rejected before any download
# --------------------------------------------------------------------------- #
def test_04_gdrive_invalid_link(client):
    res = client.post(
        "/api/analysis/videos/gdrive/validate",
        json={"url": "https://example.com/some/file.mp4"},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["valid"] is False
    assert body["accessible"] is False
    assert "google drive" in (body["reason"] or "").lower()


# --------------------------------------------------------------------------- #
# 5. Google Drive: a well-formed but unreachable/private link fails gracefully
# --------------------------------------------------------------------------- #
def test_05_gdrive_private_or_unreachable_link(client):
    url = "https://drive.google.com/file/d/1AbCdEfGhIjKlMnOpQrStUvWxYz012345/view?usp=sharing"
    res = client.post("/api/analysis/videos/gdrive/validate", json={"url": url})
    assert res.status_code == 200
    body = res.json()
    assert body["valid"] is True          # the URL itself parses
    assert body["file_id"] == "1AbCdEfGhIjKlMnOpQrStUvWxYz012345"
    if not body["accessible"]:            # normal case: no network / not public
        assert body["reason"], "an inaccessible link must explain why"
        # adding it must fail with the same human-readable reason, not a 500
        add = client.post("/api/analysis/videos/gdrive", json={"url": url})
        assert add.status_code in (400, 422, 502)
        assert add.json()["detail"]


# --------------------------------------------------------------------------- #
# 6. Every video is actually processed and reports real per-video counters
# --------------------------------------------------------------------------- #
def test_06_all_videos_processed(analysed):
    videos = [v for v in analysed["status"]["videos"] if v["camera_id"].startswith(TEST_PREFIX)]
    assert len(videos) == len(SCRIPT)
    assert all(v["status"] == "DONE" for v in videos)
    assert all(v["progress_pct"] == 100.0 for v in videos)
    assert all(v["frames_read"] == FRAMES for v in videos)
    assert all(v["vehicles_detected"] >= 1 for v in videos)


# --------------------------------------------------------------------------- #
# 7. De-duplication: one record per tracked vehicle, not one per frame
# --------------------------------------------------------------------------- #
def test_07_detections_are_deduplicated_per_track(analysed):
    db = SessionLocal()
    try:
        rows = db.query(VehicleEvent).filter(
            VehicleEvent.camera_id.like(f"{TEST_PREFIX}%")
        ).all()
        assert rows, "no sighting was stored"
        # FRAMES frames were decoded per video but each video yields ONE record
        per_cam = {}
        for r in rows:
            per_cam.setdefault(r.camera_id, []).append(r)
        for cam, recs in per_cam.items():
            assert len(recs) == 1, f"{cam} stored {len(recs)} rows for one vehicle"
        # and every stored record carries full provenance
        r = rows[0]
        assert r.video_id and r.frame_number is not None
        assert r.vehicle_class == "car" and r.vehicle_confidence
        assert r.bbox and len(r.bbox) == 4
        assert r.video_offset_sec is not None and r.event_time is not None
    finally:
        db.close()


# --------------------------------------------------------------------------- #
# 8. The same plate seen in two videos is matched across them
# --------------------------------------------------------------------------- #
def test_08_same_plate_matched_across_videos(analysed):
    rec = _record(analysed["results"], "GJ01AB1234")
    assert rec is not None
    assert rec["video_count"] == 2
    assert set(rec["cameras"]) == {"TCAM1", "TCAM3"}
    assert rec["seen_in_multiple"] is True


# --------------------------------------------------------------------------- #
# 9. The camera sequence contains only cameras that really saw the vehicle
# --------------------------------------------------------------------------- #
def test_09_sequence_skips_cameras_that_never_saw_it(analysed):
    rec = _record(analysed["results"], "GJ01AB1234")
    assert rec["sequence"] == ["TCAM1", "TCAM3"]
    assert rec["sequence_label"] == "TCAM1 → TCAM3"
    assert "TCAM2" not in rec["sequence"], "TCAM2 never saw this plate"


# --------------------------------------------------------------------------- #
# 10. A vehicle seen in one video only is reported as such
# --------------------------------------------------------------------------- #
def test_10_single_video_vehicle(analysed):
    rec = _record(analysed["results"], "MH12XY4567")
    assert rec is not None
    assert rec["video_count"] == 1
    assert rec["sequence"] == ["TCAM2"]
    assert rec["seen_in_multiple"] is False
    multi = [v["plate"] for v in analysed["results"]["multi_video_vehicles"]]
    assert "MH12XY4567" not in multi


# --------------------------------------------------------------------------- #
# 11. Vehicle history is ordered and timestamped per camera
# --------------------------------------------------------------------------- #
def test_11_vehicle_history_is_ordered_and_timestamped(analysed, client):
    res = client.get("/api/analysis/vehicles/GJ01AB1234")
    assert res.status_code == 200
    hist = res.json()["history"]
    assert [h["step"] for h in hist] == [1, 2]
    assert [h["camera_id"] for h in hist] == ["TCAM1", "TCAM3"]
    for h in hist:
        assert h["timestamp"].count(":") == 2      # HH:MM:SS offset in the video
        assert h["event_time"]                     # absolute time
        assert h["source_name"].endswith(".mp4")
        assert 0.0 <= h["ocr_confidence"] <= 1.0


# --------------------------------------------------------------------------- #
# 12. Low-confidence OCR is marked, never presented as a confirmed plate
# --------------------------------------------------------------------------- #
def test_12_low_confidence_is_marked(analysed):
    rec = _record(analysed["results"], "GJ05CD6789")
    assert rec is not None, "a low-confidence read is still reported, but flagged"
    assert rec["plate_status"] == "LOW_CONFIDENCE"
    assert rec["best_ocr_confidence"] < 0.80
    db = SessionLocal()
    try:
        row = db.query(VehicleEvent).filter(VehicleEvent.camera_id == "TCAM4").first()
        assert row.plate_status == "LOW_CONFIDENCE"
        assert row.watchlist_match is False, "a low-confidence read must not raise an alert"
    finally:
        db.close()


# --------------------------------------------------------------------------- #
# 13. An unreadable plate becomes Unknown — never invented
# --------------------------------------------------------------------------- #
def test_13_unreadable_plate_is_unknown(analysed):
    db = SessionLocal()
    try:
        row = db.query(VehicleEvent).filter(VehicleEvent.camera_id == "TCAM5").first()
        assert row is not None, "the vehicle is still counted as a sighting"
        assert row.plate_number is None
        assert row.plate_raw is None
        assert row.plate_status == "UNKNOWN"
    finally:
        db.close()
    assert analysed["results"]["unreadable_sightings"] >= 1
    plates = {v["plate"] for v in analysed["results"]["vehicles"]}
    assert None not in plates and "" not in plates


# --------------------------------------------------------------------------- #
# 14. Near-miss plates are surfaced as *possible* matches, never merged
# --------------------------------------------------------------------------- #
def test_14_fuzzy_matches_are_flagged_not_merged(analysed):
    plates = {v["plate"] for v in analysed["results"]["vehicles"]}
    assert {"GJ01AB1234", "GJ01AB1Z34"} <= plates, "similar plates stay separate records"
    pairs = {
        frozenset((m["plate_a"], m["plate_b"])): m
        for m in analysed["results"]["possible_matches"]
    }
    key = frozenset(("GJ01AB1234", "GJ01AB1Z34"))
    assert key in pairs, "a 1-character confusable difference must be surfaced"
    m = pairs[key]
    assert m["differing_characters"] == 1
    assert "POSSIBLE" in m["note"].upper() or "not confirmed" in m["note"].lower()
    # a genuinely different plate is not proposed
    assert frozenset(("GJ01AB1234", "MH12XY4567")) not in pairs


# --------------------------------------------------------------------------- #
# 15. Plate search: found, normalised, and not-found are all handled
# --------------------------------------------------------------------------- #
def test_15_plate_search(client, analysed):
    hit = client.get("/api/analysis/search", params={"plate": "gj 01 ab-1234"}).json()
    assert hit["found"] is True
    assert hit["normalized_query"] == "GJ01AB1234"
    assert hit["vehicle"]["sequence"] == ["TCAM1", "TCAM3"]
    assert any(p["plate"] == "GJ01AB1Z34" for p in hit["possible_matches"])

    miss = client.get("/api/analysis/search", params={"plate": "DL09ZZ0000"}).json()
    assert miss["found"] is False
    assert miss["vehicle"] is None
    assert miss["possible_matches"] == []


# --------------------------------------------------------------------------- #
# 16. Summary statistics are derived from the stored rows
# --------------------------------------------------------------------------- #
def test_16_summary_statistics(analysed):
    r = analysed["results"]
    assert r["total_videos"] == len(SCRIPT)
    assert r["total_sightings"] == r["readable_sightings"] + r["unreadable_sightings"]
    assert r["unique_plates"] == len(r["vehicles"])
    assert r["plates_in_multiple_videos"] == len(r["multi_video_vehicles"]) == 1
    db = SessionLocal()
    try:
        stored = db.query(func.count(VehicleEvent.id)).filter(
            VehicleEvent.camera_id.like(f"{TEST_PREFIX}%")
        ).scalar()
        assert r["total_sightings"] == stored
    finally:
        db.close()


# --------------------------------------------------------------------------- #
# 17. Removing a video removes its sightings; existing endpoints still work
# --------------------------------------------------------------------------- #
def test_17_delete_video_and_no_regression(client, analysed, clips):
    # existing, unrelated endpoints must be unaffected by this feature
    assert client.get("/api/health").status_code == 200
    assert client.get("/api/cameras").status_code == 200
    assert client.get("/api/stats/kpis").status_code == 200

    before = client.get("/api/analysis/results").json()["total_videos"]
    videos = [v for v in client.get("/api/analysis/videos").json()["videos"]
              if v["camera_id"] == "TCAM5"]
    assert videos, "TCAM5 should exist before deletion"
    vid = videos[0]["video_id"]
    stored_path = None
    db = SessionLocal()
    try:
        row = db.query(VideoSource).filter(VideoSource.video_id == vid).first()
        stored_path = row.file_path
    finally:
        db.close()

    assert client.delete(f"/api/analysis/videos/{vid}").status_code == 200
    assert client.delete(f"/api/analysis/videos/{vid}").status_code == 404

    db = SessionLocal()
    try:
        assert db.query(VideoSource).filter(VideoSource.video_id == vid).first() is None
        assert db.query(VehicleEvent).filter(VehicleEvent.video_id == vid).count() == 0
    finally:
        db.close()
    if stored_path:
        assert not Path(stored_path).exists(), "the stored video file must be removed too"

    after = client.get("/api/analysis/results").json()
    assert after["total_videos"] == before - 1
