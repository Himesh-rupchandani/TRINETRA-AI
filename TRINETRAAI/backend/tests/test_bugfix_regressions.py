"""Regression tests for the confirmed bug fixes (items 1, 2, 4, 5, 6, 17).

Each test names the bug it pins so a future refactor cannot silently reintroduce
it:

* item 1  — ``app/api/bandwidth.py`` shadowed the engine functions it imported,
            turning ``/stats/scaling`` and ``/stats/federation`` into unbounded
            recursion (HTTP 500).
* item 2  — ``uploaded_video_service`` used ``timedelta`` without importing it:
            every uploaded-video sighting raised NameError inside the worker and
            the job died as FAILED.
* item 4  — two handlers were registered for ``GET /api/events/{id}``; the second
            shadowed the first.
* item 5  — naive local timestamps on the wire; every timestamp must now be UTC
            with a ``Z`` suffix.
* item 6  — ``EVIDENCE_ROOT`` was resolved against the CWD by the API and against
            the backend root by the pipelines, so evidence 404'd.
* item 17 — alert ``status`` query param shadowing, resolve-note separation,
            single WS payload key, thread-safe broadcast, unknown-camera 404 on
            ``/cameras/{id}/live`` and streaming upload size enforcement.
"""
import asyncio
import json
import os
import re
import sys
import threading
import time
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

backend_root = Path(__file__).resolve().parents[1]
if str(backend_root) not in sys.path:
    sys.path.insert(0, str(backend_root))

import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func

from app.core.config import settings
from app.core import paths as core_paths
from app.database.database import SessionLocal, init_db
from app.database.models import Alert, Camera, VehicleEvent
from app.services import uploaded_video_service as uvs
from app.services.ws_manager import ws_manager

ISO_TS = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}")


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #
@pytest.fixture(scope="module")
def client():
    """Live app against the real DB (the workers use SessionLocal directly)."""
    init_db()
    from app.main import app

    @asynccontextmanager
    async def noop_lifespan(_app):
        yield

    original_lifespan = app.router.lifespan_context
    app.router.lifespan_context = noop_lifespan
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c, app
    app.router.lifespan_context = original_lifespan
    app.dependency_overrides.clear()


def _write_clip(path: str, frames: int = 12, size=(200, 150)) -> None:
    """Tiny real MP4 so the pipeline decodes actual frames."""
    writer = cv2.VideoWriter(path, cv2.VideoWriter_fourcc(*"mp4v"), 10, size)
    for i in range(frames):
        frame = np.full((size[1], size[0], 3), 30 + i * 4, dtype=np.uint8)
        cv2.rectangle(frame, (40 + i * 3, 60), (160 + i * 3, 130), (200, 200, 200), -1)
        writer.write(frame)
    writer.release()


@pytest.fixture(scope="module")
def upload_env(tmp_path_factory):
    """Upload pipeline with the model stages stubbed (no YOLO/OCR weights here).

    The point is item 2: with detections present, ``finalize_track`` runs and
    must compute ``started_at + timedelta(seconds=offset)`` — the NameError that
    used to kill every uploaded-video job.
    """
    from app.services.ocr_service import PlateReading, ocr_service
    from app.services.vehicle_detection_service import (
        VehicleDetection,
        vehicle_detection_service,
    )

    init_db()
    from app.main import app

    @asynccontextmanager
    async def noop_lifespan(_app):
        yield

    original_lifespan = app.router.lifespan_context
    app.router.lifespan_context = noop_lifespan

    saved_detector = (
        vehicle_detection_service.detect,
        vehicle_detection_service._ensure_model,
        vehicle_detection_service._model,
    )
    saved_ocr = (ocr_service.read_plate, ocr_service._engine, ocr_service._attempted)

    def fake_detect(frame, conf=None, imgsz=None):
        h, w = frame.shape[:2]
        return [
            VehicleDetection(
                x1=30, y1=50, x2=min(w - 1, 190), y2=min(h - 1, 140),
                class_name="car", confidence=0.93,
            )
        ]

    def fake_read_plate(frame, bbox, vehicle_class="car"):
        return PlateReading(
            raw="GJ 01 AB-1234", normalized="GJ01AB1234",
            confidence=0.95, indian_format=True,
        )

    vehicle_detection_service.detect = fake_detect
    vehicle_detection_service._ensure_model = lambda: object()
    vehicle_detection_service._model = object()
    ocr_service.read_plate = fake_read_plate
    ocr_service._engine, ocr_service._attempted = object(), True

    clip_dir = tmp_path_factory.mktemp("clips")
    clip = str(clip_dir / "cam9reg2.mp4")
    _write_clip(clip)

    with TestClient(app, raise_server_exceptions=True) as c:
        yield c, clip

    (
        vehicle_detection_service.detect,
        vehicle_detection_service._ensure_model,
        vehicle_detection_service._model,
    ) = saved_detector
    # `available` is a read-only property derived from _engine/_attempted.
    ocr_service.read_plate, ocr_service._engine, ocr_service._attempted = saved_ocr
    app.router.lifespan_context = original_lifespan
    app.dependency_overrides.clear()

    db = SessionLocal()
    try:
        db.query(VehicleEvent).filter(
            func.upper(VehicleEvent.camera_id) == "CAM9REG2"
        ).delete(synchronize_session=False)
        db.query(Camera).filter(func.upper(Camera.camera_id) == "CAM9REG2").delete(
            synchronize_session=False
        )
        db.commit()
    finally:
        db.close()
    try:
        (uvs.upload_root() / "cam9reg2.mp4").unlink(missing_ok=True)
    except OSError:
        pass


# --------------------------------------------------------------------------- #
# Item 1 — bandwidth engine shadowing / recursion
# --------------------------------------------------------------------------- #
def test_stats_bandwidth_endpoints_do_not_recurse(client):
    c, _app = client
    for path in ("/api/stats/bandwidth", "/api/stats/scaling", "/api/stats/federation"):
        resp = c.get(path)
        assert resp.status_code == 200, f"{path} -> {resp.status_code}: {resp.text[:200]}"

    body = c.get("/api/stats/bandwidth").json()
    assert body["gujarat_network"]["total_cameras"] == 80000
    assert body["savings"]["bandwidth_savings_percent"] > 0
    # The projection is computed, not a hardcoded timestamp.
    assert body["generated_at"].endswith("Z")
    assert datetime.fromisoformat(body["generated_at"].replace("Z", "+00:00")).tzinfo


def test_bandwidth_module_does_not_shadow_engine_functions():
    """The handler names must differ from the imported engine names."""
    from app.api import bandwidth as bandwidth_api
    from app.services import bandwidth_engine

    assert bandwidth_api.engine_calculate_bandwidth_savings is (
        bandwidth_engine.calculate_bandwidth_savings
    )
    assert bandwidth_api.engine_get_scaling_projection is (
        bandwidth_engine.get_scaling_projection
    )
    # The route handlers are distinct callables — no self-recursion.
    assert bandwidth_api.get_bandwidth_analysis is not (
        bandwidth_engine.calculate_bandwidth_savings
    )
    assert bandwidth_api.get_scaling_projection_endpoint is not (
        bandwidth_engine.get_scaling_projection
    )


# --------------------------------------------------------------------------- #
# Item 2 — uploaded-video pipeline (timedelta NameError)
# --------------------------------------------------------------------------- #
def test_uploaded_video_pipeline_creates_timed_events(upload_env):
    c, clip = upload_env
    camera_id = "CAM9REG2"

    with open(clip, "rb") as fh:
        resp = c.post(
            "/api/uploads/videos",
            files={"file": ("cam9reg2.mp4", fh, "video/mp4")},
            data={"camera_id": camera_id},
        )
    assert resp.status_code == 201, resp.text

    job = None
    for _ in range(120):
        job = c.get(f"/api/uploads/videos/{camera_id}").json()
        if job["job_status"] in ("DONE", "FAILED"):
            break
        time.sleep(0.25)

    assert job is not None
    # The NameError used to surface here as a FAILED job.
    assert job["job_status"] == "DONE", job
    assert not (job.get("error") or "")
    assert job["frames_total"] == 12

    db = SessionLocal()
    try:
        events = (
            db.query(VehicleEvent)
            .filter(func.upper(VehicleEvent.camera_id) == camera_id)
            .order_by(VehicleEvent.id)
            .all()
        )
        assert events, "the stubbed detector produced no sighting"
        for event in events:
            # event_time = started_at + timedelta(seconds=offset)
            assert event.event_time is not None
            assert event.event_time.tzinfo is not None, "naive timestamp stored"
            assert event.plate_number == "GJ01AB1234"
            assert event.video_offset_sec is not None and event.video_offset_sec >= 0
    finally:
        db.close()


# --------------------------------------------------------------------------- #
# Item 4 — one handler for GET /events/{id}
# --------------------------------------------------------------------------- #
def test_single_handler_for_event_by_id(client):
    """Two handlers used to register the same path; the second shadowed the first."""
    c, app = client
    from app.api.events import router as events_router

    matches = [
        route
        for route in events_router.routes
        if getattr(route, "path", "") == "/events/{event_id}"
        and "GET" in (getattr(route, "methods", set()) or set())
    ]
    assert len(matches) == 1, f"expected exactly one GET handler, got {matches}"
    assert matches[0].endpoint.__name__ == "get_event_by_id"

    # FastAPI mounts each router under /api and /api/v1; both must expose ONE
    # get operation for the path, served by that same handler.
    spec = app.openapi()
    for path in ("/api/events/{event_id}", "/api/v1/events/{event_id}"):
        assert path in spec["paths"], path
        assert spec["paths"][path]["get"]["operationId"].startswith("get_event_by_id")

    assert c.get("/api/events/99999999").status_code == 404


# --------------------------------------------------------------------------- #
# Item 5 — every timestamp on the wire is UTC with a Z suffix
# --------------------------------------------------------------------------- #
def _walk_timestamps(node, found):
    if isinstance(node, dict):
        for value in node.values():
            _walk_timestamps(value, found)
    elif isinstance(node, list):
        for value in node:
            _walk_timestamps(value, found)
    elif isinstance(node, str) and ISO_TS.match(node):
        found.append(node)


@pytest.mark.parametrize(
    "path",
    [
        "/api/cameras",
        "/api/events?size=5",
        "/api/alerts?size=5",
        "/api/stats/kpis",
        "/api/stats/insights",
        "/api/stats/bandwidth",
        "/api/health",
    ],
)
def test_api_timestamps_are_zulu_utc(client, path):
    c, _app = client
    resp = c.get(path)
    assert resp.status_code == 200, resp.text
    found: list = []
    _walk_timestamps(resp.json(), found)
    for value in found:
        assert value.endswith("Z"), f"{path} returned a non-UTC timestamp: {value}"
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        assert parsed.tzinfo is not None
        assert parsed.utcoffset() == timedelta(0)


def test_database_timestamps_round_trip_as_aware_utc(client):
    _c, _app = client
    db = SessionLocal()
    try:
        now = datetime.now(timezone.utc)
        event = VehicleEvent(
            camera_id="CAMTZTEST",
            plate_number="GJ01TZ9999",
            vehicle_class="car",
            event_time=now,
            watchlist_match=False,
        )
        db.add(event)
        db.commit()
        db.refresh(event)
        assert event.event_time.tzinfo is not None, "column returned a naive datetime"
        assert abs((event.event_time - now).total_seconds()) < 2
        assert event.created_at.tzinfo is not None
        event_id = event.id
    finally:
        db.close()

    db = SessionLocal()
    try:
        db.query(VehicleEvent).filter(VehicleEvent.id == event_id).delete()
        db.commit()
    finally:
        db.close()


def test_schema_serializer_assumes_naive_input_is_utc():
    from app.database.schemas import AlertResponse

    naive = datetime(2026, 9, 12, 8, 30, 0)  # no tzinfo
    alert = AlertResponse(
        id=1,
        camera_id="CAM01",
        alert_type="WATCHLIST_MATCH",
        message="test",
        timestamp=naive,
        severity="HIGH",
        status="NEW",
    )
    dumped = json.loads(alert.model_dump_json())
    assert dumped["timestamp"] == "2026-09-12T08:30:00Z"


# --------------------------------------------------------------------------- #
# Item 6 — one authority for EVIDENCE_ROOT
# --------------------------------------------------------------------------- #
def test_evidence_root_is_cwd_independent(client, tmp_path, monkeypatch):
    c, _app = client
    monkeypatch.setattr(settings, "EVIDENCE_ROOT", "../../cv-engine/evidence")

    resolved = core_paths.evidence_root(create=False)
    assert resolved.is_absolute()
    # Relative configured paths anchor to the backend root, never to the CWD.
    assert resolved == (core_paths.BACKEND_ROOT / "../../cv-engine/evidence").resolve()

    # The API and the pipelines call the very same resolver.
    from app.api import evidence as evidence_api

    assert evidence_api.evidence_root is core_paths.evidence_root
    assert uvs.evidence_root is core_paths.evidence_root

    # Functional proof: serve a crop with the process CWD somewhere else entirely.
    root = core_paths.evidence_root(create=True)
    rel = Path("regression") / "cwd_probe.jpg"
    target = root / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(b"\xff\xd8\xff\xe0probe")
    original_cwd = os.getcwd()
    try:
        os.chdir("/")
        resp = c.get(f"/api/evidence/{rel.as_posix()}")
        assert resp.status_code == 200, resp.text
    finally:
        os.chdir(original_cwd)
        target.unlink(missing_ok=True)


def test_evidence_rejects_path_traversal(client):
    c, _app = client
    resp = c.get("/api/evidence/..%2F..%2Fapp%2Fcore%2Fconfig.py")
    assert resp.status_code in (400, 404)


# --------------------------------------------------------------------------- #
# Item 17C/D — websocket envelope + thread-safe broadcast
# --------------------------------------------------------------------------- #
def test_ws_envelope_has_a_single_payload_key():
    frame = json.loads(ws_manager.envelope("VEHICLE_DETECTED", {"event_id": 7}))
    assert frame["type"] == "VEHICLE_DETECTED"
    assert frame["payload"] == {"event_id": 7}
    assert "data" not in frame, "duplicate payload/data keys confuse every consumer"
    assert frame["timestamp"].endswith("Z")


def test_broadcast_threadsafe_without_loop_is_a_noop():
    ws_manager.detach_loop()
    assert ws_manager.broadcast_threadsafe("VEHICLE_DETECTED", {"event_id": 1}) is False


def test_broadcast_threadsafe_delivers_from_another_thread():
    received: list = []
    ready = threading.Event()

    async def _run():
        loop = asyncio.get_running_loop()
        ws_manager.attach_loop(loop)
        queue = ws_manager.subscribe_sse()
        ready.set()
        try:
            frame = await asyncio.wait_for(queue.get(), timeout=5)
            received.append(json.loads(frame))
        finally:
            ws_manager.unsubscribe_sse(queue)
            ws_manager.detach_loop()

    thread = threading.Thread(target=lambda: asyncio.run(_run()), daemon=True)
    thread.start()
    assert ready.wait(timeout=5)
    # Called from the main thread while the loop lives in another thread.
    assert ws_manager.broadcast_threadsafe("ALERT_CREATED", {"alert_id": 42}) is True
    thread.join(timeout=6)
    assert received and received[0]["payload"]["alert_id"] == 42
    assert "data" not in received[0]


# --------------------------------------------------------------------------- #
# Item 17A — `status` query param no longer shadows fastapi.status
# --------------------------------------------------------------------------- #
def test_alert_status_filter_and_http_status_constants(client):
    c, _app = client
    db = SessionLocal()
    try:
        alert = Alert(
            camera_id="CAMSTATUSTEST",
            alert_type="WATCHLIST_MATCH",
            severity="HIGH",
            message="status filter probe",
            plate_number="GJ01ST1234",
            status="NEW",
        )
        db.add(alert)
        db.commit()
        alert_id = alert.id
    finally:
        db.close()

    try:
        # The wire contract keeps ?status= (alias) while the handler's Python
        # name no longer shadows `fastapi.status`.
        listed = c.get("/api/alerts", params={"status": "new", "size": 100}).json()
        assert any(item["id"] == alert_id for item in listed["items"])
        assert all(item["status"] == "NEW" for item in listed["items"])

        empty = c.get("/api/alerts", params={"status": "RESOLVED", "size": 100}).json()
        assert all(item["status"] == "RESOLVED" for item in empty["items"])

        # `status.HTTP_404_NOT_FOUND` still resolves inside the same module.
        missing = c.post(f"/api/alerts/{alert_id + 999999}/ack", json={"operator": "x"})
        assert missing.status_code == 404
        assert "not found" in missing.json()["detail"].lower()
    finally:
        db = SessionLocal()
        try:
            db.query(Alert).filter(Alert.id == alert_id).delete()
            db.commit()
        finally:
            db.close()


# --------------------------------------------------------------------------- #
# Item 17B — operator identity and resolution note stay separate
# --------------------------------------------------------------------------- #
def _make_alert(status="NEW") -> int:
    db = SessionLocal()
    try:
        alert = Alert(
            camera_id="CAMRESOLVETEST",
            alert_type="WATCHLIST_MATCH",
            severity="CRITICAL",
            message="resolve probe",
            plate_number="GJ01RV1234",
            status=status,
        )
        db.add(alert)
        db.commit()
        return alert.id
    finally:
        db.close()


def _delete_alert(alert_id: int) -> None:
    db = SessionLocal()
    try:
        db.query(Alert).filter(Alert.id == alert_id).delete()
        db.commit()
    finally:
        db.close()


def test_resolve_stores_operator_and_note_separately(client):
    c, _app = client
    alert_id = _make_alert()
    try:
        resp = c.post(
            f"/api/alerts/{alert_id}/resolve",
            json={"operator": "Officer-7", "note": "Driver verified on site"},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["status"] == "RESOLVED"
        assert body["resolved_by"] == "Officer-7"
        assert body["resolution_note"] == "Driver verified on site"
        assert body["resolved_at"].endswith("Z")
    finally:
        _delete_alert(alert_id)


def test_resolve_without_note_keeps_operator(client):
    c, _app = client
    alert_id = _make_alert()
    try:
        body = c.post(f"/api/alerts/{alert_id}/resolve", json={}).json()
        assert body["resolved_by"] == "system"
        assert body["resolution_note"] is None
    finally:
        _delete_alert(alert_id)


def test_resolve_understands_legacy_packed_operator(client):
    """Older bundles posted the note inside `operator` ("resolve: <note>")."""
    c, _app = client
    alert_id = _make_alert()
    try:
        body = c.post(
            f"/api/alerts/{alert_id}/resolve", json={"operator": "resolve: plate expired"}
        ).json()
        assert body["resolved_by"] == "system", "the note must not become the officer"
        assert body["resolution_note"] == "plate expired"
    finally:
        _delete_alert(alert_id)


def test_acknowledge_records_operator(client):
    c, _app = client
    alert_id = _make_alert()
    try:
        body = c.post(f"/api/alerts/{alert_id}/ack", json={"operator": "Control-Room"}).json()
        assert body["status"] == "ACKNOWLEDGED"
        assert body["acknowledged_by"] == "Control-Room"
    finally:
        _delete_alert(alert_id)


# --------------------------------------------------------------------------- #
# Item 17E — unknown camera on /live is a 404, not an endless placeholder stream
# --------------------------------------------------------------------------- #
def test_live_stream_for_unknown_camera_is_404(client):
    c, _app = client
    resp = c.get("/api/cameras/does-not-exist-99/live")
    assert resp.status_code == 404
    assert "does-not-exist-99" in resp.json()["detail"]


# --------------------------------------------------------------------------- #
# Item 17F — upload size limit is enforced while streaming
# --------------------------------------------------------------------------- #
def test_upload_writer_enforces_limit_without_buffering(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "MAX_UPLOAD_SIZE_MB", 1)
    monkeypatch.setattr(settings, "UPLOAD_DIR", str(tmp_path))
    assert uvs.UPLOAD_CHUNK_BYTES == 1024 * 1024

    chunk = b"x" * (512 * 1024)
    with pytest.raises(ValueError) as excinfo:
        with uvs.open_upload_writer("big.mp4") as writer:
            for _ in range(4):        # 2 MB through a 1 MB cap
                writer.write(chunk)   # must raise before the whole body is read
            writer.finish()
    assert "1 MB" in str(excinfo.value) or "upload limit" in str(excinfo.value)

    # No partial file is left behind, and nothing was written to the target name.
    leftovers = [p.name for p in tmp_path.iterdir()]
    assert "big.mp4" not in leftovers
    assert not [name for name in leftovers if name.endswith(".part")]


def test_upload_writer_rejects_unsupported_type_before_writing(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "UPLOAD_DIR", str(tmp_path))
    with pytest.raises(ValueError):
        uvs.open_upload_writer("notes.txt")
    assert list(tmp_path.iterdir()) == []


def test_upload_endpoint_rejects_oversized_and_empty_files(client, tmp_path, monkeypatch):
    c, _app = client
    monkeypatch.setattr(settings, "MAX_UPLOAD_SIZE_MB", 1)

    oversized = b"0" * (2 * 1024 * 1024)
    resp = c.post(
        "/api/uploads/videos",
        files={"file": ("toobig.mp4", oversized, "video/mp4")},
        data={"camera_id": "CAM9TOOBIG"},
    )
    assert resp.status_code == 422
    assert "upload limit" in resp.json()["detail"].lower()

    empty = c.post(
        "/api/uploads/videos",
        files={"file": ("empty.mp4", b"", "video/mp4")},
        data={"camera_id": "CAM9EMPTY"},
    )
    assert empty.status_code == 422
    assert "empty" in empty.json()["detail"].lower()

    # Nothing reached the upload directory under those names.
    stored = {p.name for p in uvs.upload_root(create=False).iterdir()} if uvs.upload_root(create=False).exists() else set()
    assert "toobig.mp4" not in stored
    assert "empty.mp4" not in stored


def test_upload_endpoint_streams_instead_of_reading_the_whole_body():
    """Source-level guard: the handler must not slurp the upload into RAM."""
    source = Path(backend_root / "app" / "api" / "uploads.py").read_text(encoding="utf-8")
    assert "await file.read()" not in source
    assert "open_upload_writer" in source
    assert "UPLOAD_CHUNK_BYTES" in source
