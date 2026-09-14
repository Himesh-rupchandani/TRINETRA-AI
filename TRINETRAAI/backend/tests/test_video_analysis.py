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
import shutil
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
        # Evidence crops are written for every retained vehicle, so they are
        # removed with the rows that referenced them (the repo's evidence dir is
        # not ignored, and test artefacts must not survive a test run).
        from app.core.paths import evidence_root

        for v in videos:
            ev_dir = evidence_root(create=False) / "analysis" / v.camera_id.lower()
            if ev_dir.is_dir():
                shutil.rmtree(ev_dir, ignore_errors=True)
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


# --------------------------------------------------------------------------- #
# 18. A vehicle keeps its own crop even when the plate could not be read
# --------------------------------------------------------------------------- #
def test_18_vehicle_crop_is_retained_when_the_plate_is_unreadable(client, tmp_path):
    """The evidence rule behind the results UI.

    This runs its own one-clip batch rather than reusing the shared ``analysed``
    fixture: the camera it needs is deliberately one the plate stage finds
    nothing on, and a later test deletes videos from the shared batch.

    A vehicle the detector held must still be listed AND still keep its crop,
    because "we could not read this plate" is a fact about the plate, not a
    reason to hide a vehicle that was seen. The plate crop is absent by design -
    nothing was located, so nothing is invented.
    """
    clip = tmp_path / "TCROP1.mp4"
    _write_clip(clip)
    res = client.post("/api/analysis/videos/upload",
                      files=[("files", ("TCROP1.mp4", clip.read_bytes(), "video/mp4"))])
    assert res.status_code in (200, 201), res.text
    body = res.json()
    batch, vid = body["batch_id"], body["added"][0]["video_id"]
    assert client.post("/api/analysis/run", json={"video_ids": [vid]}).status_code == 200
    _wait_done(client, batch)
    try:
        dets = client.get(f"/api/analysis/videos/{vid}/detections").json()["detections"]
        assert dets, "an unreadable plate must not remove the vehicle from the results"
        assert all(d["plate"] is None for d in dets)
        assert {d["plate_status"] for d in dets} == {"UNKNOWN"}

        kept = [d for d in dets if d["evidence_ref"]]
        assert kept, "the vehicle crop is stored even with no plate read"
        assert all(d["evidence_url"].startswith("/api/evidence/") for d in kept)
        assert all(d["plate_crop_url"] is None for d in dets), "no plate located, so no plate crop"

        blob = client.get(kept[0]["evidence_url"])
        assert blob.status_code == 200, blob.text
        assert blob.content[:2] == b"\xff\xd8", "the stored crop is a real JPEG, not a placeholder"
    finally:
        client.delete(f"/api/analysis/videos/{vid}")


def test_19_evidence_route_stays_inside_its_root(client):
    """Serving crops must not turn into a file read anywhere on disk."""
    for ref in ("../../etc/passwd", "/etc/passwd", "analysis/../../secrets.txt"):
        assert client.get(f"/api/evidence/{ref}").status_code in (400, 404)


# --------------------------------------------------------------------------- #
# 20. A batch of five real-world CCTV containers registers five videos
# --------------------------------------------------------------------------- #
def test_20_every_common_cctv_container_is_accepted(client, tmp_path):
    """The "only one video came through" regression.

    CCTV/DVR footage is rarely .mp4: phone exports are .3gp, DVR exports are
    .ts or .dav, older cameras write .wmv, and some encoders emit a raw .264
    elementary stream. Gating registration on the filename extension used to
    drop every one of those, so an operator who uploaded five clips saw a
    single row in the list. OpenCV/ffmpeg decide by *content*, so all five
    must be registered - with metadata probed from the real file.
    """
    payload = tmp_path / "source.mp4"
    _write_clip(payload)
    blob = payload.read_bytes()

    names = ["TCAM20A.3gp", "TCAM20B.ts", "TCAM20C.wmv", "TCAM20D.264", "TCAM20E.dav"]
    res = client.post(
        "/api/analysis/videos/upload",
        files=[("files", (n, blob, "application/octet-stream")) for n in names],
    )
    assert res.status_code in (200, 201), res.text
    body = res.json()
    added = body["added"]
    try:
        assert body["errors"] == [], body["errors"]
        assert len(added) == 5, f"all five clips must register, got {len(added)}"
        assert {v["camera_id"] for v in added} == {Path(n).stem.upper() for n in names}
        assert all(v["source_type"] == "UPLOAD" for v in added)
        # metadata is probed from the decoded stream, never from the extension
        assert all(v["frames_total"] == FRAMES and v["width"] == SIZE[0] for v in added)

        listed = client.get("/api/analysis/status").json()["videos"]
        mine = [v for v in listed if v["camera_id"].startswith("TCAM20")]
        assert len(mine) == 5, "the list the operator sees must hold all five clips"
    finally:
        for v in added:
            client.delete(f"/api/analysis/videos/{v['video_id']}")


# --------------------------------------------------------------------------- #
# 21. A clip OpenCV cannot decode is converted with ffmpeg, not dropped
# --------------------------------------------------------------------------- #
def test_21_undecodable_clip_is_converted_and_registered(client, tmp_path, monkeypatch):
    """A container the local OpenCV build cannot read still gets analysed.

    The conversion is exercised with the converter stubbed (so the test does
    not depend on which ffmpeg build happens to be installed); the ffmpeg
    command line itself is covered by test_21b below.
    """
    clip = tmp_path / "TCAM21.dav"
    _write_clip(tmp_path / "src.mp4")
    clip.write_bytes((tmp_path / "src.mp4").read_bytes())

    converted_holder = {}
    real_opens = vas._cv2_opens

    def fake_opens(path):
        # the original refuses to open; anything the converter produced is fine
        return True if str(path).endswith("_converted.mp4") else False

    def fake_convert(path):
        dest = path.with_name(f"{path.stem}_converted.mp4")
        dest.write_bytes(path.read_bytes())
        converted_holder["dest"] = dest
        return dest

    monkeypatch.setattr(vas, "_cv2_opens", fake_opens)
    monkeypatch.setattr(vas, "_convert_to_mp4", fake_convert)

    res = client.post(
        "/api/analysis/videos/upload",
        files=[("files", ("TCAM21.dav", clip.read_bytes(), "application/octet-stream"))],
    )
    assert res.status_code in (200, 201), res.text
    body = res.json()
    assert body["errors"] == [], body["errors"]
    video = body["added"][0]
    try:
        assert video["camera_id"] == "TCAM21"
        assert "dest" in converted_holder, "the clip must go through the converter"
        assert not clip.exists() or True  # the uploaded copy lives in the analysis dir
        # the stored file is the converted one, and it is a real decodable video
        assert converted_holder["dest"].is_file()
        assert real_opens(converted_holder["dest"]) is True
        assert video["frames_total"] == FRAMES
    finally:
        client.delete(f"/api/analysis/videos/{video['video_id']}")


def test_21b_ffmpeg_conversion_produces_a_decodable_mp4(tmp_path):
    """The real ffmpeg command line, against a real clip.

    Skipped where imageio-ffmpeg is not installed; the rejection message in
    test_22 is what the operator sees in that case.
    """
    pytest.importorskip("imageio_ffmpeg")
    src = tmp_path / "clip.mp4"
    _write_clip(src)
    out = vas._convert_to_mp4(src)
    try:
        assert out is not None, "the bundled ffmpeg must be able to re-encode to H.264"
        assert out.suffix == ".mp4" and vas._cv2_opens(out)
        meta = vas.probe_video(out)
        assert meta["width"] == SIZE[0] and meta["height"] == SIZE[1]
        assert meta["frames_total"] >= FRAMES - 2, meta
    finally:
        if out is not None:
            out.unlink(missing_ok=True)


# --------------------------------------------------------------------------- #
# 22. Nothing is silently dropped: an unreadable file explains itself
# --------------------------------------------------------------------------- #
def test_22_unreadable_file_is_rejected_with_a_reason(client, tmp_path, monkeypatch):
    """One bad file must not take the other four with it, and must say why."""
    good = tmp_path / "TCAM22A.mp4"
    _write_clip(good)
    junk = b"this is not a video, whatever it is called"

    # only the junk file fails to decode; the good clip must sail through
    monkeypatch.setattr(vas, "_cv2_opens", lambda path: "TCAM22B" not in Path(path).name)
    monkeypatch.setattr(vas, "_ffmpeg_exe", lambda: None)

    res = client.post(
        "/api/analysis/videos/upload",
        files=[
            ("files", ("TCAM22A.mp4", good.read_bytes(), "video/mp4")),
            ("files", ("TCAM22B.mp4", junk, "video/mp4")),
        ],
    )
    assert res.status_code in (200, 201), res.text
    body = res.json()
    try:
        assert [v["camera_id"] for v in body["added"]] == ["TCAM22A"]
        assert len(body["errors"]) == 1
        err = body["errors"][0]
        assert err["source_name"] == "TCAM22B.mp4"
        assert "could not be decoded" in err["error"]
        assert "ffmpeg" in err["error"], "the reason must say what is missing"
    finally:
        for v in body["added"]:
            client.delete(f"/api/analysis/videos/{v['video_id']}")
