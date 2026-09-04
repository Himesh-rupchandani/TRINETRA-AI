"""Tests for additive integration endpoints: GET /events/{id}, /stats/kpis,
/api/evidence static mount and the SSE hub."""
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

for p in [str(Path(__file__).resolve().parents[1])]:
    if p not in sys.path:
        sys.path.insert(0, p)

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from app.database.database import get_db  # noqa: E402
from app.database.models import Base, Camera, VehicleEvent, Watchlist  # noqa: E402
from app.main import app  # noqa: E402
from app.services.ws_manager import ws_manager  # noqa: E402


@pytest.fixture(scope="module")
def db_engine():
    # StaticPool: one shared connection so tables created here are visible to
    # the app threads spun up by TestClient.
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    return engine


@pytest.fixture(scope="module")
def client(db_engine):
    TestSession = sessionmaker(bind=db_engine)

    def override_get_db():
        db = TestSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _seed(db_engine):
    TestSession = sessionmaker(bind=db_engine)
    db = TestSession()
    if not db.query(Camera).filter(Camera.camera_id == "CAM04").first():
        db.add(Camera(camera_id="CAM04", name="North Gate Junction",
                      stream_url="https://cctv.corp8.cloud/cam04/index.m3u8",
                      stream_type="hls", latitude=23.0338, longitude=72.585,
                      status="ONLINE"))
    if not db.query(Watchlist).filter(Watchlist.plate_number == "GJ01AB1234").first():
        db.add(Watchlist(plate_number="GJ01AB1234", category="stolen vehicle", active=True))
    ev = VehicleEvent(camera_id="CAM04", plate_number="GJ01AB1234",
                      plate_confidence=0.94, vehicle_class="car",
                      event_time=datetime.now(timezone.utc))
    db.add(ev)
    db.commit()
    ev_id = ev.id
    db.close()
    return ev_id


def test_get_event_by_id(client, db_engine):
    ev_id = _seed(db_engine)

    r = client.get(f"/api/events/{ev_id}")
    assert r.status_code == 200
    body = r.json()
    assert body["id"] == ev_id
    assert body["plate_number"] == "GJ01AB1234"
    assert body["camera_id"] == "CAM04"
    assert 0.0 <= body["plate_confidence"] <= 1.0

    assert client.get("/api/events/999999").status_code == 404


def test_stats_kpis_counts_real_rows(client, db_engine):
    r = client.get("/api/stats/kpis")
    assert r.status_code == 200
    k = r.json()
    for key in ("total_cameras", "cameras_online", "cameras_degraded", "cameras_offline",
                "active_alerts", "vehicle_detections_24h", "anpr_reads_24h",
                "watchlist_matches_24h"):
        assert key in k and isinstance(k[key], int)
    # One seeded camera + at least the event created above.
    assert k["total_cameras"] >= 1
    assert k["vehicle_detections_24h"] >= 1
    assert k["anpr_reads_24h"] >= 1


def test_cameras_include_event_stats(client, db_engine):
    r = client.get("/api/cameras")
    assert r.status_code == 200
    cam = next(c for c in r.json()["data"] if c["id"] == "cam04")
    assert cam["event_count_24h"] >= 1
    assert cam["last_event_at"] is not None


def test_evidence_static_mount_serves_files():
    """A file dropped into EVIDENCE_DIR must be downloadable at /api/evidence."""
    import app.core.config as config_mod
    evidence_dir = config_mod.settings.EVIDENCE_DIR
    os.makedirs(os.path.join(evidence_dir, "cam04"), exist_ok=True)
    path = os.path.join(evidence_dir, "cam04", "test_frame.jpg")
    with open(path, "wb") as fh:
        fh.write(b"\xff\xd8\xff\xe0demo")

    with TestClient(app) as c:
        r = c.get("/api/evidence/cam04/test_frame.jpg")
        assert r.status_code == 200
        assert r.content == b"\xff\xd8\xff\xe0demo"


def test_sse_hub_receives_broadcasts():
    """subscribe_sse + broadcast must deliver the same envelope as WebSocket."""
    import asyncio

    async def scenario():
        q = ws_manager.subscribe_sse()
        try:
            await ws_manager.broadcast("VEHICLE_DETECTED", {"plate": "GJ01AB1234"})
            item = await asyncio.wait_for(q.get(), timeout=2)
            assert item["type"] == "VEHICLE_DETECTED"
            assert item["payload"]["plate"] == "GJ01AB1234"
            assert "timestamp" in item
        finally:
            ws_manager.unsubscribe_sse(q)

    asyncio.run(scenario())
