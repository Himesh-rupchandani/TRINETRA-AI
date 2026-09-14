"""
Frontend-contract endpoints (Phase 6/17 of the integration plan).

Covers the additive routes the React service layer depends on in LIVE mode:
  - GET  /api/events/{id}            (evidence / detection detail)
  - GET  /api/vehicles/{plate}       (investigation profile)
  - GET  /api/stats/kpis             (Command Center KPIs — real DB counts)
  - GET  /api/cameras/{id}/stream    (browser-safe playback ticket)
  - GET  /api/stream                 (SSE realtime channel)
"""
import json
import httpx
import sys
from contextlib import asynccontextmanager
from datetime import datetime, timezone, timedelta
from pathlib import Path

for p in [str(Path(__file__).resolve().parents[1])]:
    if p not in sys.path:
        sys.path.insert(0, p)

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database.models import Base, Camera, Watchlist, VehicleEvent, Alert
from app.database.database import get_db
from app.services.ws_manager import ws_manager


@pytest.fixture(scope="module")
def client():
    """Isolated SQLite DB + test client, following the established suite pattern."""
    test_db_file = Path("test_frontend_contract.db").resolve()
    if test_db_file.exists():
        try:
            test_db_file.unlink()
        except Exception:
            pass

    engine = create_engine(
        f"sqlite:///{test_db_file}",
        connect_args={"check_same_thread": False, "timeout": 15},
    )
    Base.metadata.create_all(bind=engine)
    TestSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    def override_get_db():
        db = TestSession()
        try:
            yield db
        finally:
            db.close()

    from app.main import app
    app.dependency_overrides[get_db] = override_get_db

    @asynccontextmanager
    async def noop_lifespan(app):
        yield

    original_lifespan = app.router.lifespan_context
    app.router.lifespan_context = noop_lifespan

    # Seed one canonical demo journey: CAM04 -> CAM08 for GJ01AB1234.
    db = TestSession()
    db.add(Camera(
        camera_id="CAM04", name="North Gate Junction", location="Paldi Circle",
        stream_url="https://cctv.corp8.cloud/cam04/index.m3u8", stream_type="hls",
        latitude=23.0338, longitude=72.585, status="ONLINE",
    ))
    db.add(Camera(
        camera_id="CAM08", name="ISCON Crossroads CCTV", location="ISCON Junction",
        stream_url="https://cctv.corp8.cloud/cam08/index.m3u8", stream_type="hls",
        latitude=23.0295, longitude=72.5054, status="OFFLINE",
    ))
    db.add(Watchlist(plate_number="GJ01AB1234", category="stolen vehicle",
                     description="Reported stolen near SG Highway", active=True))
    now = datetime.now(timezone.utc)
    db.add(VehicleEvent(
        camera_id="CAM04", vehicle_track_id=17, plate_raw="GJ 01 AB-1234",
        plate_number="GJ01AB1234", plate_confidence=0.94, vehicle_class="car",
        event_time=now - timedelta(minutes=30),
        latitude=23.0338, longitude=72.585, watchlist_match=True,
    ))
    db.add(VehicleEvent(
        camera_id="CAM08", vehicle_track_id=2, plate_raw="GJ 01 AB 1234",
        plate_number="GJ01AB1234", plate_confidence=0.91, vehicle_class="car",
        event_time=now - timedelta(minutes=10),
        latitude=23.0295, longitude=72.5054, watchlist_match=True,
    ))
    db.add(Alert(camera_id="CAM04", alert_type="WATCHLIST_MATCH", severity="CRITICAL",
                 message="WATCHLIST HIT: Plate GJ01AB1234 detected on CAM04.",
                 status="NEW", plate_number="GJ01AB1234", event_id=1))
    db.commit()
    db.close()

    with TestClient(app) as c:
        yield c

    app.router.lifespan_context = original_lifespan
    app.dependency_overrides.pop(get_db, None)
    try:
        test_db_file.unlink()
    except Exception:
        pass


def test_get_event_by_id(client):
    r = client.get("/api/events/1")
    assert r.status_code == 200
    body = r.json()
    assert body["id"] == 1
    assert body["plate_number"] == "GJ01AB1234"
    assert body["camera_id"] == "CAM04"
    assert 0.0 <= body["plate_confidence"] <= 1.0

    assert client.get("/api/events/999999").status_code == 404


def test_vehicle_profile(client):
    r = client.get("/api/vehicles/GJ01AB1234")
    assert r.status_code == 200
    body = r.json()
    assert body["plate_number"] == "GJ01AB1234"
    assert body["total_sightings"] == 2
    assert body["cameras_touched"] == 2
    assert body["watchlist"]["category"] == "stolen vehicle"
    assert body["watchlist"]["active"] is True
    assert body["first_seen"] is not None and body["last_seen"] is not None

    # Unknown plate: valid structure, zero sightings, no watchlist — not an error.
    r2 = client.get("/api/vehicles/GJ27ZZ9999")
    assert r2.status_code == 200
    assert r2.json()["total_sightings"] == 0
    assert r2.json()["watchlist"] is None


def test_stats_kpis_real_counts(client):
    r = client.get("/api/stats/kpis")
    assert r.status_code == 200
    k = r.json()
    assert k["total_cameras"] == 2
    assert k["cameras_online"] == 1
    assert k["cameras_offline"] >= 1
    assert k["active_alerts"] == 1
    assert k["vehicle_detections_24h"] == 2
    assert k["anpr_reads_24h"] == 2
    assert k["watchlist_matches_24h"] == 2


def test_kpi_camera_counters_agree_with_camera_grid(client):
    """The Command Center counters and the camera grid must never disagree.

    Both read camera status, but they used to read it differently: the grid
    resolved it through the registry fallback while the KPI aggregate took the
    ingestion manager's word for it. With no stream workers running the manager
    reports every camera OFFLINE, so the dashboard showed "0 online" above a
    grid of green tiles. Both now share one resolver.
    """
    grid = client.get("/api/cameras").json()["data"]
    k = client.get("/api/stats/kpis").json()

    online = sum(1 for c in grid if c["status"] == "ONLINE")
    degraded = sum(1 for c in grid if c["status"] == "DEGRADED")
    offline = sum(1 for c in grid if c["status"] == "OFFLINE")

    assert k["total_cameras"] == len(grid)
    assert k["cameras_online"] == online
    assert k["cameras_degraded"] == degraded
    assert k["cameras_offline"] == offline


def test_camera_grid_exposes_registry_metadata(client):
    """Phase 3/19: the registry — not individual components — owns camera identity."""
    cam = client.get("/api/cameras/cam04").json()
    assert cam["camera_id"] == "CAM04"
    assert cam["location"] == "Paldi Circle"
    assert cam["latitude"] == 23.0338
    assert cam["longitude"] == 72.585
    assert cam["status"] == "ONLINE"

    listing = next(c for c in client.get("/api/cameras").json()["data"] if c["id"] == "cam04")
    assert listing["location"] == cam["location"]
    assert listing["status"] == cam["status"]
    assert listing["latitude"] == cam["latitude"]
    assert listing["longitude"] == cam["longitude"]


def test_camera_stream_ticket(client):
    r = client.get("/api/cameras/cam04/stream")
    assert r.status_code == 200
    t = r.json()
    assert t["camera_id"] == "cam04"
    assert t["stream_url"].startswith("/sentinel/stream/cam04/whep")
    assert t["playable"] is True
    # Never leak the RTSP/Sentinel origin to the browser.
    assert "103.250.160.189" not in t["stream_url"]
    assert "rtsp://" not in t["stream_url"]

    # Offline camera -> unplayable ticket with a human-readable reason.
    r2 = client.get("/api/cameras/CAM08/stream")
    assert r2.status_code == 200
    t2 = r2.json()
    assert t2["playable"] is False
    assert t2["stream_url"] == ""
    assert t2["reason"]

    assert client.get("/api/cameras/nosuch/stream").status_code == 404


def test_sse_stream_endpoint_and_ingest_broadcast(client):
    """End-to-end SSE check against a real uvicorn server.

    TestClient/httpx cannot incrementally read an infinite SSE stream with
    this stack (it buffers), so we boot the app on a free port — the same
    pattern as cv-engine's integration test — and verify:
      1. GET /api/stream speaks text/event-stream and greets with a comment
      2. POSTing a real CV event fans out to the SSE channel instantly
    """
    import socket
    import threading
    import time
    import uvicorn

    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()

    from app.main import app  # carries this module's DB override + noop lifespan

    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    base = f"http://127.0.0.1:{port}"
    deadline = time.monotonic() + 15
    with httpx.Client() as probe:
        while time.monotonic() < deadline:
            try:
                if probe.get(f"{base}/api/health", timeout=1.0).status_code == 200:
                    break
            except Exception:
                time.sleep(0.1)

    try:
        with httpx.Client(timeout=10.0) as c:
            with c.stream("GET", f"{base}/api/stream") as response:
                assert response.status_code == 200
                assert response.headers["content-type"].startswith("text/event-stream")
                assert response.headers["cache-control"] == "no-cache"

                lines = response.iter_lines()
                first = next(lines)
                assert first == ": connected"

                # A real ingest broadcasts VEHICLE_DETECTED on the server loop.
                r = c.post(f"{base}/api/events", json={
                    "camera_id": "CAM04",
                    "vehicle_id": 17,
                    "plate_raw": "GJ 01 AB-1234",
                    "plate": "GJ01AB1234",
                    "plate_confidence": 0.95,
                    "vehicle_class": "car",
                    "latitude": 23.0338,
                    "longitude": 72.585,
                })
                assert r.status_code == 201

                # The broadcast frame must arrive without waiting for a heartbeat.
                payload = None
                for line in lines:
                    if line.startswith("data: "):
                        payload = json.loads(line[len("data: "):])
                        break
                assert payload is not None
                # GJ01AB1234 is on the test watchlist, so the ingest broadcasts
                # WATCHLIST_MATCH/ALERT_CREATED instead of a plain detection.
                assert payload["type"] in ("VEHICLE_DETECTED", "WATCHLIST_MATCH", "ALERT_CREATED")
                assert payload["payload"]["plate_number"] == "GJ01AB1234"
                assert payload["payload"]["camera_id"] == "CAM04"
    finally:
        server.should_exit = True
        thread.join(timeout=5)


@pytest.mark.asyncio
async def test_sse_queue_receives_broadcasts():
    """broadcast() fans out the same typed envelope as the WebSocket channel."""
    q = ws_manager.subscribe_sse()
    try:
        await ws_manager.broadcast(
            "VEHICLE_DETECTED", {"event_id": 1, "plate_number": "GJ01AB1234"}
        )
        payload = json.loads(q.get_nowait())
        assert payload["type"] == "VEHICLE_DETECTED"
        assert payload["payload"]["plate_number"] == "GJ01AB1234"
        assert "timestamp" in payload
    finally:
        ws_manager.unsubscribe_sse(q)
    assert q not in ws_manager.sse_queues
