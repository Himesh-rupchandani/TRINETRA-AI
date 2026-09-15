"""
Boot-seeding regression tests for Vercel / serverless fix.

- blank DB + serverless env → 30/22/5 + CAMLIVE (31 via API)
- atomicity: event stage fails → 4 bootstrap cameras remain, health FAILED
- persistent DB with events → skipped
- TRINETRA_API_ONLY=1 → boot succeeds and /live → 503
"""
import sys
from pathlib import Path
for _p in [str(Path(__file__).resolve().parents[1])]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

import os
import tempfile
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient


def _clear_demo_report():
    from app.core import bootstrap
    bootstrap._LAST_DEMO_REPORT = None


# ---------------------------------------------------------------------------
# 1. Blank DB + serverless → 30/22/5 and 31 via API
# ---------------------------------------------------------------------------

def test_blank_db_serverless_seeds_30_and_camlive(monkeypatch, tmp_path):
    """Blank DB on a serverless host seeds 30/22/5 and GET /api/cameras returns 31."""
    monkeypatch.setenv("VERCEL", "1")
    monkeypatch.delenv("VERCEL_ENV", raising=False)
    monkeypatch.delenv("VERCEL_REGION", raising=False)
    from app.core.config import settings
    monkeypatch.setattr(settings, "AUTO_SEED_DEMO", False)
    _clear_demo_report()

    db_file = tmp_path / "blank_serverless.db"
    engine = create_engine(
        f"sqlite:///{db_file}",
        connect_args={"check_same_thread": False, "timeout": 15},
    )
    from app.database.models import Base, Camera, VehicleEvent, Alert, Watchlist
    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(bind=engine)
    monkeypatch.setattr("app.database.database.engine", engine)
    monkeypatch.setattr("app.database.database.SessionLocal", TestingSession)
    monkeypatch.setattr("app.main.SessionLocal", TestingSession)

    db = TestingSession()
    assert db.query(Camera).count() == 0
    assert db.query(VehicleEvent).count() == 0
    db.close()

    from app.main import app
    from app.database.database import get_db

    def override_get_db():
        d = TestingSession()
        try:
            yield d
        finally:
            d.close()

    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as client:
        d = TestingSession()
        try:
            cam_count = d.query(Camera).count()
            ev_count = d.query(VehicleEvent).count()
            alert_count = d.query(Alert).count()
            wl_count = d.query(Watchlist).count()
        finally:
            d.close()

        assert cam_count == 31, f"expected 31 cameras (30+ CAMLIVE), got {cam_count}"
        assert ev_count == 22, f"expected 22 events, got {ev_count}"
        assert alert_count == 5, f"expected 5 alerts, got {alert_count}"
        assert wl_count == 10, f"expected 10 watchlist, got {wl_count}"

        resp = client.get("/api/cameras")
        assert resp.status_code == 200
        body = resp.json()
        assert "data" in body
        assert len(body["data"]) == 31, f"/api/cameras data length {len(body['data'])}"

        h = client.get("/api/health")
        assert h.status_code == 200
        hj = h.json()
        assert hj["total_cameras"] == 31
        assert hj["components"]["storage"] == "EPHEMERAL"
        demo_data = hj["components"]["demo_data"]
        assert demo_data.startswith("SEEDED"), f"demo_data={demo_data}"
        assert "30/22/5" in demo_data

        k = client.get("/api/stats/kpis")
        assert k.status_code == 200
        kj = k.json()
        assert kj["total_cameras"] == 31
        assert kj["cameras_online"] == 30, f"kpis {kj}"

        r = client.get("/api/vehicles/GJ01AB1234/route")
        assert r.status_code == 200
        route = r.json().get("route", [])
        assert len(route) == 4, f"GJ01AB1234 route length {len(route)} expected 4"

        post = client.post(
            "/api/events",
            json={
                "camera_id": "CAM04",
                "plate": "GJ01AB1234",
                "plate_confidence": 0.95,
                "vehicle_class": "car",
                "latitude": 23.0126,
                "longitude": 72.5647,
            },
        )
        assert post.status_code in (200, 201), post.text

    app.dependency_overrides.clear()
    _clear_demo_report()
    monkeypatch.delenv("VERCEL", raising=False)


# ---------------------------------------------------------------------------
# 2. Atomicity: failure during event stage leaves 4 bootstrap cameras and health FAILED
# ---------------------------------------------------------------------------

def test_seed_atomicity_on_event_failure(monkeypatch, tmp_path):
    """If event seeding raises, DB is exactly as before boot (4 init_db cameras) and health is FAILED."""
    for k in ("VERCEL", "VERCEL_ENV", "VERCEL_REGION", "AWS_LAMBDA_FUNCTION_NAME", "FUNCTION_TARGET", "K_SERVICE"):
        monkeypatch.delenv(k, raising=False)
    from app.core.config import settings
    monkeypatch.setattr(settings, "AUTO_SEED_DEMO", True)
    monkeypatch.setattr(settings, "RUNTIME_DATA_ROOT", "")
    _clear_demo_report()

    db_file = tmp_path / "atomic.db"
    engine = create_engine(f"sqlite:///{db_file}", connect_args={"check_same_thread": False})
    from app.database.models import Base, Camera, VehicleEvent
    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(bind=engine)
    monkeypatch.setattr("app.database.database.engine", engine)
    monkeypatch.setattr("app.database.database.SessionLocal", TestingSession)
    monkeypatch.setattr("app.main.SessionLocal", TestingSession)

    # Blank DB — ensure_demo_dataset will be attempted before init_db (lifespan order).
    # Patch the event stage to raise, then verify atomic rollback leaves DB as before (0),
    # and that a subsequent init_db still creates the 4 bootstrap cameras (no wipe).
    from app.database import demo_seed
    orig_seed_events = demo_seed.seed_events
    def _boom(db):
        raise RuntimeError("simulated event seed failure")
    monkeypatch.setattr(demo_seed, "seed_events", _boom)

    from app.core.bootstrap import ensure_demo_dataset, get_demo_seed_report, _format_demo_data
    db = TestingSession()
    try:
        # Ensure blank
        assert db.query(Camera).count() == 0
        assert db.query(VehicleEvent).count() == 0
        report = ensure_demo_dataset(db)
        assert report.get("seeded") is False
        assert "error" in report or "FAILED" in report.get("skipped_reason","")
        # Atomic: DB must be exactly as before (0 cameras, 0 events) — no partial insert
        assert db.query(Camera).count() == 0, f"atomicity violated: {db.query(Camera).count()} cameras after failure (expected 0 before init_db)"
        assert db.query(VehicleEvent).count() == 0
        formatted = _format_demo_data(report)
        assert formatted.startswith("FAILED"), f"demo_data {formatted}"
        global_report = get_demo_seed_report()
        assert global_report is not None
        assert _format_demo_data(global_report).startswith("FAILED")
    finally:
        db.close()
        monkeypatch.setattr(demo_seed, "seed_events", orig_seed_events)

    # After a failed demo seed, lifespan would still run init_db which creates the 4 bootstrap rows.
    from app.database.database import init_db
    init_db()
    db = TestingSession()
    try:
        assert db.query(Camera).count() == 4, f"after failed demo, init_db should still seed 4 bootstrap cameras, got {db.query(Camera).count()}"
    finally:
        db.close()

    from app.main import app
    from app.database.database import get_db
    def override_get_db():
        d = TestingSession()
        try:
            yield d
        finally:
            d.close()
    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as client:
        pass
    app.dependency_overrides.clear()

    from app.core import bootstrap
    bootstrap._LAST_DEMO_REPORT = report
    from app.main import app as app2
    def override2():
        d = TestingSession()
        try:
            yield d
        finally:
            d.close()
    app2.dependency_overrides[get_db] = override2
    from contextlib import asynccontextmanager
    orig_lifespan = app2.router.lifespan_context
    @asynccontextmanager
    async def noop(app):
        yield
    app2.router.lifespan_context = noop
    with TestClient(app2) as client2:
        h = client2.get("/api/health")
        assert h.status_code == 200
        demo_data = h.json()["components"]["demo_data"]
        assert demo_data.startswith("FAILED"), f"expected FAILED, got {demo_data}"
    app2.router.lifespan_context = orig_lifespan
    app2.dependency_overrides.clear()
    _clear_demo_report()


# ---------------------------------------------------------------------------
# 3. Persistent DB with events >0 → seeding skipped
# ---------------------------------------------------------------------------

def test_persistent_db_with_events_skips_seeding(monkeypatch, tmp_path):
    """When DB has existing events, boot seeding is skipped (persistent)."""
    for k in ("VERCEL", "VERCEL_ENV", "VERCEL_REGION", "AWS_LAMBDA_FUNCTION_NAME", "FUNCTION_TARGET", "K_SERVICE"):
        monkeypatch.delenv(k, raising=False)
    from app.core.config import settings
    monkeypatch.setattr(settings, "AUTO_SEED_DEMO", False)
    monkeypatch.setattr(settings, "RUNTIME_DATA_ROOT", "")
    _clear_demo_report()

    db_file = tmp_path / "persistent.db"
    engine = create_engine(f"sqlite:///{db_file}", connect_args={"check_same_thread": False})
    from app.database.models import Base, Camera, VehicleEvent
    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(bind=engine)
    monkeypatch.setattr("app.database.database.engine", engine)
    monkeypatch.setattr("app.database.database.SessionLocal", TestingSession)
    monkeypatch.setattr("app.main.SessionLocal", TestingSession)

    db = TestingSession()
    try:
        from datetime import datetime, timezone
        db.add(Camera(camera_id="CAM99", name="Custom Cam", location="Lab", stream_url="rtsp://lab/cam99", stream_type="rtsp", latitude=0, longitude=0, status="ONLINE"))
        db.add(Camera(camera_id="CAM98", name="Custom Cam 2", location="Lab2", stream_url="rtsp://lab/cam98", stream_type="rtsp", latitude=1, longitude=1, status="ONLINE"))
        db.add(VehicleEvent(camera_id="CAM99", vehicle_track_id=1, plate_number="TEST1234", plate_confidence=0.9, vehicle_class="car", event_time=datetime.now(timezone.utc), latitude=0, longitude=0, watchlist_match=False))
        db.commit()
        assert db.query(Camera).count() == 2
        assert db.query(VehicleEvent).count() == 1
    finally:
        db.close()

    from app.core.bootstrap import ensure_demo_dataset, _format_demo_data
    db = TestingSession()
    try:
        report = ensure_demo_dataset(db)
        assert report.get("seeded") is False
        assert "SKIPPED" in _format_demo_data(report)
        assert db.query(Camera).count() == 2
        assert db.query(VehicleEvent).count() == 1
    finally:
        db.close()

    from app.main import app
    from app.database.database import get_db
    from contextlib import asynccontextmanager
    def override_get_db():
        d = TestingSession()
        try:
            yield d
        finally:
            d.close()
    app.dependency_overrides[get_db] = override_get_db
    orig = app.router.lifespan_context
    @asynccontextmanager
    async def noop(app):
        yield
    app.router.lifespan_context = noop
    with TestClient(app) as client:
        h = client.get("/api/health")
        assert h.status_code == 200
        demo_data = h.json()["components"]["demo_data"]
        assert demo_data.startswith("SKIPPED"), f"got {demo_data}"
    app.router.lifespan_context = orig
    app.dependency_overrides.clear()
    _clear_demo_report()


# ---------------------------------------------------------------------------
# 4. TRINETRA_API_ONLY=1 boot succeeds and /live → 503
# ---------------------------------------------------------------------------

def test_api_only_boot_and_live_503(monkeypatch, tmp_path):
    """TRINETRA_API_ONLY=1 makes the API boot without CV and /live returns 503."""
    monkeypatch.setenv("TRINETRA_API_ONLY", "1")
    import app.core.vision as vision_mod
    monkeypatch.setattr(vision_mod, "CV2_AVAILABLE", False)
    monkeypatch.setattr(vision_mod, "NUMPY_AVAILABLE", False)
    monkeypatch.setattr("app.core.vision.vision_available", lambda: False)
    monkeypatch.setattr("app.main.vision_available", lambda: False)

    db_file = tmp_path / "api_only.db"
    engine = create_engine(f"sqlite:///{db_file}", connect_args={"check_same_thread": False})
    from app.database.models import Base, Camera
    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(bind=engine)
    monkeypatch.setattr("app.database.database.engine", engine)
    monkeypatch.setattr("app.database.database.SessionLocal", TestingSession)
    monkeypatch.setattr("app.main.SessionLocal", TestingSession)

    db = TestingSession()
    try:
        db.add(Camera(camera_id="CAM04", name="Paldi Circle", location="Paldi Circle", stream_url="https://cctv.corp8.cloud/cam04/index.m3u8", stream_type="hls", latitude=23.0126, longitude=72.5647, status="ONLINE"))
        db.commit()
    finally:
        db.close()

    from app.main import app
    from app.database.database import get_db

    def override_get_db():
        d = TestingSession()
        try:
            yield d
        finally:
            d.close()

    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as client:
        h = client.get("/api/health")
        assert h.status_code == 200
        hj = h.json()
        assert hj["status"] == "healthy"
        assert "DISABLED" in hj["components"]["cv_pipeline"]

        r = client.get("/api/cameras/cam04/live")
        assert r.status_code == 503, f"expected 503 for API-only live, got {r.status_code} {r.text}"
        body = r.json()
        detail = body.get("detail", body)
        if isinstance(detail, dict):
            assert detail.get("error") == "VISION_STACK_UNAVAILABLE" or "VISION" in str(detail)
        else:
            assert "VISION" in str(detail) or "unavailable" in str(detail).lower()

        r2 = client.get("/api/cameras/cam04/live/detect")
        assert r2.status_code == 503

    app.dependency_overrides.clear()
    _clear_demo_report()
    monkeypatch.delenv("TRINETRA_API_ONLY", raising=False)
