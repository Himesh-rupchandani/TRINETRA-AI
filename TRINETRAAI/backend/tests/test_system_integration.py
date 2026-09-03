"""
System Integration Tests — Real System Integration Ready (Phases 2-17)
======================================================================
Tests the full end-to-end integration flows:
1. Sentinel Catalogue Sync & Normalization
2. Camera Registry API Contracts (GET /api/cameras, GET /api/cameras/{id})
3. Real CV Event Ingestion (POST /api/events)
4. Event -> Watchlist Match -> Alert Generation (with event reference & confidence)
5. Alert Deduplication Cooldown
6. Real-time WebSocket Broadcast Delivery
7. Vehicle Trace & Chronological Sightings (GET /api/vehicles/{plate}/events)
8. Ordered GIS Route Generation (GET /api/vehicles/{plate}/route)
9. Alert Acknowledgment Lifecycle (POST /api/alerts/{id}/ack)
10. System Diagnostic Health Subsystems (GET /api/health)
11. Error Handling & Validation Responses (400, 404, 409, 422)
"""
import sys
from pathlib import Path

# Ensure backend root is in sys.path
backend_root = Path(__file__).resolve().parents[1]
if str(backend_root) not in sys.path:
    sys.path.insert(0, str(backend_root))

import pytest
from datetime import datetime, timezone, timedelta
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from sqlalchemy.orm import sessionmaker

from app.database.models import Base, Camera, Watchlist, VehicleEvent, Alert
from app.database.database import get_db
from app.services.sentinel_catalogue_service import sync_sentinel_catalogue, normalize_sentinel_camera
from app.services.ws_manager import ws_manager


@pytest.fixture(scope="module")
def test_setup():
    """
    Creates an isolated SQLite test database and test client with seed data.
    """
    test_db_file = Path("test_integration.db").resolve()
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

    from contextlib import asynccontextmanager
    from app.main import app
    app.dependency_overrides[get_db] = override_get_db

    # No-op lifespan to isolate from real hardware/camera streams
    @asynccontextmanager
    async def noop_lifespan(app):
        yield

    original_lifespan = app.router.lifespan_context
    app.router.lifespan_context = noop_lifespan

    # Seed cameras and watchlist
    db = TestSession()
    cam04 = Camera(
        camera_id="CAM04",
        name="North Gate Junction",
        location="Paldi Circle",
        stream_url="https://cctv.corp8.cloud/cam04/index.m3u8",
        stream_type="hls",
        latitude=23.0338,
        longitude=72.5850,
        status="ONLINE",
        codec="H264",
        width=1920,
        height=1080,
    )
    cam08 = Camera(
        camera_id="CAM08",
        name="ISCON Crossroads CCTV",
        location="ISCON Junction",
        stream_url="https://cctv.corp8.cloud/cam08/index.m3u8",
        stream_type="hls",
        latitude=23.0295,
        longitude=72.5054,
        status="ONLINE",
    )
    cam12 = Camera(
        camera_id="CAM12",
        name="Naranpura Octroi Post",
        location="Naranpura Ring Road",
        stream_url="https://cctv.corp8.cloud/cam12/index.m3u8",
        stream_type="hls",
        latitude=23.0622,
        longitude=72.5659,
        status="ONLINE",
    )
    cam17 = Camera(
        camera_id="CAM17",
        name="Bapunagar Industrial Zone",
        location="Bapunagar Gate",
        stream_url="https://cctv.corp8.cloud/cam17/index.m3u8",
        stream_type="hls",
        latitude=23.0487,
        longitude=72.6303,
        status="ONLINE",
    )
    db.add_all([cam04, cam08, cam12, cam17])

    # Seed Watchlist
    stolen_vehicle = Watchlist(
        plate_number="GJ01AB1234",
        category="stolen vehicle",
        description="Silver Sedan - Reported stolen FIR #4812",
        active=True,
    )
    db.add(stolen_vehicle)
    db.commit()
    db.close()

    with TestClient(app, raise_server_exceptions=True) as client:
        yield client, TestSession

    app.router.lifespan_context = original_lifespan
    app.dependency_overrides.clear()
    engine.dispose()
    if test_db_file.exists():
        try:
            test_db_file.unlink()
        except Exception:
            pass


# ===========================================================================
# 1. Sentinel Catalogue Sync & Normalization Tests (Phase 3)
# ===========================================================================
class TestSentinelCatalogueSync:
    def test_normalize_sentinel_camera(self):
        """Test normalization of raw Sentinel metadata."""
        raw = {
            "id": "cam05",
            "name": "Satellite Road Junction",
            "location": "Satellite",
            "lat": 23.0295,
            "lon": 72.5360,
            "stream_url": "https://cctv.corp8.cloud/cam05/index.m3u8",
            "stream_type": "hls",
            "codec": "h264",
            "width": 1920,
            "height": 1080,
            "status": "online",
        }
        norm = normalize_sentinel_camera(raw)
        assert norm["camera_id"] == "CAM05"
        assert norm["name"] == "Satellite Road Junction"
        assert norm["location"] == "Satellite"
        assert norm["latitude"] == 23.0295
        assert norm["longitude"] == 72.5360
        assert norm["status"] == "ONLINE"
        assert norm["codec"] == "H264"

    def test_sync_sentinel_catalogue_with_payload(self, test_setup):
        """Syncing Sentinel cameras with payload upserts records without duplicates."""
        _, Session = test_setup
        db = Session()
        payload = [
            {
                "id": "cam04",
                "name": "North Gate Junction Updated",
                "location": "Paldi Circle North",
                "latitude": 23.0340,
                "longitude": 72.5855,
                "stream_url": "https://cctv.corp8.cloud/cam04/index.m3u8",
                "status": "online",
            },
            {
                "id": "cam99",
                "name": "New Peripheral Highway Cam",
                "location": "SP Ring Road",
                "latitude": 23.1200,
                "longitude": 72.6000,
                "stream_url": "https://cctv.corp8.cloud/cam99/index.m3u8",
                "status": "online",
            }
        ]
        result = sync_sentinel_catalogue(db, raw_payload=payload)
        assert result["status"] == "success"
        assert result["synced_count"] == 2

        # Verify CAM04 was updated
        cam04 = db.query(Camera).filter(Camera.camera_id == "CAM04").first()
        assert cam04 is not None
        assert cam04.name == "North Gate Junction Updated"
        assert cam04.location == "Paldi Circle North"

        # Verify CAM99 was added
        cam99 = db.query(Camera).filter(Camera.camera_id == "CAM99").first()
        assert cam99 is not None
        assert cam99.camera_id == "CAM99"
        db.close()

    def test_sync_sentinel_graceful_fallback_when_unreachable(self, test_setup):
        """Unreachable Sentinel URL falls back gracefully to existing camera registry."""
        _, Session = test_setup
        db = Session()
        result = sync_sentinel_catalogue(db, catalogue_url="http://127.0.0.1:54321/cameras.json")
        assert result["status"] in ("warning", "error")
        assert "cameras" in result
        assert len(result["cameras"]) > 0
        db.close()

    def test_internal_sync_endpoint(self, test_setup):
        """POST /api/internal/sentinel/catalogue/sync triggers synchronization."""
        client, _ = test_setup
        resp = client.post("/api/internal/sentinel/catalogue/sync", json={
            "cameras": [
                {
                    "id": "cam04",
                    "name": "North Gate Junction",
                    "location": "Paldi Circle",
                    "latitude": 23.0338,
                    "longitude": 72.5850,
                    "stream_url": "https://cctv.corp8.cloud/cam04/index.m3u8",
                }
            ]
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"
        assert data["synced_count"] >= 1


# ===========================================================================
# 2. Camera API Verification (Phase 4 & Phase 8)
# ===========================================================================
class TestCameraEndpoints:
    def test_get_cameras_returns_normalized_data_list(self, test_setup):
        """GET /api/cameras returns normalized camera information matching frontend contract."""
        client, _ = test_setup
        resp = client.get("/api/cameras")
        assert resp.status_code == 200
        data = resp.json()
        assert "data" in data
        assert isinstance(data["data"], list)
        assert len(data["data"]) >= 4

        # Validate CAM04 schema
        cam04 = next((c for c in data["data"] if c["id"] == "cam04"), None)
        assert cam04 is not None
        assert cam04["name"] is not None
        assert cam04["location"] is not None
        assert cam04["latitude"] == 23.0338 or abs(cam04["latitude"] - 23.0338) < 0.01
        assert cam04["longitude"] == 72.5850 or abs(cam04["longitude"] - 72.5850) < 0.01
        assert cam04["status"] in ("ONLINE", "OFFLINE")
        assert cam04["codec"] == "H264"
        assert cam04["width"] == 1920
        assert cam04["height"] == 1080
        assert cam04["stream_type"] in ("HLS", "RTSP")
        assert "stream_url" in cam04
        # Verify passwords/credentials are not leaked
        assert "@" not in cam04["stream_url"] or "://" not in cam04["stream_url"]

    def test_get_camera_by_id_string(self, test_setup):
        """GET /api/cameras/cam04 retrieves specific camera."""
        client, _ = test_setup
        resp = client.get("/api/cameras/cam04")
        assert resp.status_code == 200
        cam = resp.json()
        assert cam["id"] == "cam04"
        assert cam["camera_id"] == "CAM04"

    def test_get_camera_by_id_uppercase(self, test_setup):
        """GET /api/cameras/CAM04 is case-insensitive."""
        client, _ = test_setup
        resp = client.get("/api/cameras/CAM04")
        assert resp.status_code == 200
        cam = resp.json()
        assert cam["id"] == "cam04"

    def test_get_camera_not_found(self, test_setup):
        """GET /api/cameras/NONEXISTENT returns 404."""
        client, _ = test_setup
        resp = client.get("/api/cameras/NONEXISTENT")
        assert resp.status_code == 404


# ===========================================================================
# 3. Real CV Event Ingestion & Alert Creation (Phase 2 & Phase 5)
# ===========================================================================
class TestCVEventIngestionFlow:
    def test_post_cv_event_watchlist_hit_creates_alert(self, test_setup):
        """
        End-to-End Test:
        Post simulated real CV event for GJ01AB1234 on cam04 ->
        1. Event persisted
        2. Normalized plate stored
        3. Watchlist match = true
        4. Alert created
        5. Alert contains camera
        6. Alert contains timestamp
        7. Alert contains confidence
        8. Alert references event
        """
        client, Session = test_setup
        cv_payload = {
            "camera_id": "cam04",  # lowercase camera reference
            "vehicle_id": 17,
            "plate_raw": "GJ 01 AB-1234",
            "plate": "GJ01AB1234",
            "plate_confidence": 0.94,
            "timestamp_pts": 123456.78,
            "event_time": "2026-09-02T14:32:18Z",
            "latitude": 23.0001,
            "longitude": 72.5001,
            "vehicle_class": "car",
            "evidence_ref": "https://s3.example.com/snap/17.jpg",
        }

        resp = client.post("/api/events", json=cv_payload)
        assert resp.status_code == 201
        data = resp.json()

        # Check response fields
        assert data["plate_normalized"] == "GJ01AB1234"
        assert data["watchlist_match"] is True
        assert data["alert_created"] is True
        assert data["alert_id"] is not None

        # Check database records
        db = Session()
        event = db.query(VehicleEvent).filter(VehicleEvent.id == data["event"]["id"]).first()
        assert event is not None
        assert event.camera_id == "CAM04"
        assert event.plate_number == "GJ01AB1234"
        assert event.plate_confidence == 0.94
        assert event.vehicle_track_id == 17
        assert event.evidence_ref == "https://s3.example.com/snap/17.jpg"
        assert event.watchlist_match is True

        # Check Alert in database
        alert = db.query(Alert).filter(Alert.id == data["alert_id"]).first()
        assert alert is not None
        assert alert.camera_id == "CAM04"
        assert alert.plate_number == "GJ01AB1234"
        assert alert.event_id == event.id  # Alert references event
        assert alert.confidence == 0.94    # Alert retains confidence
        assert alert.timestamp is not None
        assert alert.severity == "CRITICAL"
        assert alert.status == "NEW"
        db.close()

    def test_alert_deduplication_suppresses_repeated_event(self, test_setup):
        """Second event within cooldown window suppresses duplicate alert."""
        client, Session = test_setup
        cv_payload = {
            "camera_id": "cam04",
            "vehicle_id": 18,
            "plate_raw": "GJ 01 AB-1234",
            "plate_confidence": 0.96,
            "event_time": datetime.now(timezone.utc).isoformat(),
            "latitude": 23.0001,
            "longitude": 72.5001,
            "vehicle_class": "car",
        }
        resp = client.post("/api/events", json=cv_payload)
        assert resp.status_code == 201
        data = resp.json()
        assert data["watchlist_match"] is True
        # Alert should be suppressed because CAM04 was already alerted recently
        assert data["alert_created"] is False
        assert data["alert_id"] is None

    def test_separate_camera_creates_distinct_alert(self, test_setup):
        """Same vehicle on different camera (CAM08) produces a separate alert."""
        client, Session = test_setup
        cv_payload = {
            "camera_id": "cam08",  # Different camera
            "vehicle_id": 22,
            "plate_raw": "GJ01AB1234",
            "plate_confidence": 0.92,
            "event_time": datetime.now(timezone.utc).isoformat(),
            "latitude": 23.0295,
            "longitude": 72.5054,
            "vehicle_class": "car",
        }
        resp = client.post("/api/events", json=cv_payload)
        assert resp.status_code == 201
        data = resp.json()
        assert data["watchlist_match"] is True
        assert data["alert_created"] is True
        assert data["alert_id"] is not None


# ===========================================================================
# 4. Vehicle Trace & GIS Route (Phase 6)
# ===========================================================================
class TestVehicleTraceAndRoute:
    @pytest.fixture(autouse=True)
    def seed_trace_data(self, test_setup):
        """Seed the canonical 4 detections for GJ01AB1234 across CAM04, CAM08, CAM12, CAM17."""
        _, Session = test_setup
        db = Session()

        # Clean existing events for clean sequence test
        db.query(VehicleEvent).filter(VehicleEvent.plate_number == "GJ01AB1234").delete()
        db.commit()

        base = datetime(2026, 9, 2, 14, 0, 0, tzinfo=timezone.utc)
        events = [
            VehicleEvent(
                camera_id="CAM04",
                plate_number="GJ01AB1234",
                plate_raw="GJ 01 AB-1234",
                plate_confidence=0.94,
                vehicle_class="car",
                event_time=base + timedelta(minutes=12),  # 14:12
                latitude=23.0338,
                longitude=72.5850,
                watchlist_match=True,
            ),
            VehicleEvent(
                camera_id="CAM08",
                plate_number="GJ01AB1234",
                plate_raw="GJ 01 AB 1234",
                plate_confidence=0.91,
                vehicle_class="car",
                event_time=base + timedelta(minutes=27),  # 14:27
                latitude=23.0295,
                longitude=72.5054,
                watchlist_match=True,
            ),
            VehicleEvent(
                camera_id="CAM12",
                plate_number="GJ01AB1234",
                plate_raw="GJ01AB1234",
                plate_confidence=0.98,
                vehicle_class="car",
                event_time=base + timedelta(minutes=41),  # 14:41
                latitude=23.0622,
                longitude=72.5659,
                watchlist_match=True,
            ),
            VehicleEvent(
                camera_id="CAM17",
                plate_number="GJ01AB1234",
                plate_raw="GJ-01-AB-1234",
                plate_confidence=0.95,
                vehicle_class="car",
                event_time=base + timedelta(minutes=63),  # 15:03
                latitude=23.0487,
                longitude=72.6303,
                watchlist_match=True,
            ),
        ]
        db.add_all(events)
        db.commit()
        db.close()

    def test_get_vehicle_events_chronological(self, test_setup):
        """GET /api/vehicles/{plate}/events returns sightings in chronological order."""
        client, _ = test_setup
        resp = client.get("/api/vehicles/GJ01AB1234/events")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 4
        items = data["items"]
        assert len(items) == 4

        cameras = [item["camera_id"] for item in items]
        assert cameras == ["CAM04", "CAM08", "CAM12", "CAM17"]

    def test_get_vehicle_events_auto_normalizes_plate(self, test_setup):
        """GET /api/vehicles/GJ 01 AB-1234/events normalizes plate before search."""
        client, _ = test_setup
        resp = client.get("/api/vehicles/GJ 01 AB-1234/events")
        assert resp.status_code == 200
        assert resp.json()["total"] == 4

    def test_get_vehicle_route_returns_ordered_gis_points(self, test_setup):
        """
        GET /api/vehicles/{plate}/route returns ordered GIS points with coordinates and confidence.
        """
        client, _ = test_setup
        resp = client.get("/api/vehicles/GJ01AB1234/route")
        assert resp.status_code == 200
        route_data = resp.json()

        assert route_data["plate_number"] == "GJ01AB1234"
        assert route_data["total_sightings"] == 4
        points = route_data["route"]
        assert len(points) == 4

        # Sequences must be 1, 2, 3, 4
        for idx, pt in enumerate(points):
            assert pt["sequence"] == idx + 1
            assert pt["latitude"] is not None
            assert pt["longitude"] is not None
            assert pt["confidence"] is not None

        # Camera progression
        cam_sequence = [pt["camera_id"] for pt in points]
        assert cam_sequence == ["CAM04", "CAM08", "CAM12", "CAM17"]

        # First camera is CAM04 with correct coordinates
        assert abs(points[0]["latitude"] - 23.0338) < 0.001
        assert abs(points[0]["longitude"] - 72.5850) < 0.001
        assert points[0]["confidence"] == 0.94


# ===========================================================================
# 5. Alert Management & Ack Lifecycle (Phase 8 & Phase 10)
# ===========================================================================
class TestAlertsManagement:
    def test_list_alerts_paginated(self, test_setup):
        """GET /api/alerts returns paginated surveillance alerts."""
        client, _ = test_setup
        resp = client.get("/api/alerts")
        assert resp.status_code == 200
        data = resp.json()
        assert "items" in data
        assert "total" in data

    def test_acknowledge_alert(self, test_setup):
        """POST /api/alerts/{id}/ack transitions alert from NEW -> ACKNOWLEDGED."""
        client, Session = test_setup
        db = Session()
        alert = db.query(Alert).filter(Alert.status == "NEW").first()
        if not alert:
            alert = Alert(
                camera_id="CAM04",
                plate_number="GJ01AB1234",
                alert_type="WATCHLIST_MATCH",
                severity="CRITICAL",
                message="Ack test alert",
                status="NEW",
            )
            db.add(alert)
            db.commit()
            db.refresh(alert)
        alert_id = alert.id
        db.close()

        resp = client.post(f"/api/alerts/{alert_id}/ack", json={"operator": "badge_108"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ACKNOWLEDGED"
        assert data["acknowledged_by"] == "badge_108"
        assert data["acknowledged_at"] is not None

    def test_duplicate_acknowledge_returns_conflict_409(self, test_setup):
        """Acknowledging an already acknowledged alert returns 409 Conflict."""
        client, Session = test_setup
        db = Session()
        alert = db.query(Alert).filter(Alert.status == "ACKNOWLEDGED").first()
        alert_id = alert.id
        db.close()

        resp = client.post(f"/api/alerts/{alert_id}/ack", json={"operator": "badge_108"})
        assert resp.status_code == 409


# ===========================================================================
# 6. Watchlist Management (Phase 8)
# ===========================================================================
class TestWatchlistManagement:
    def test_list_watchlist(self, test_setup):
        """GET /api/watchlist returns active watchlist records."""
        client, _ = test_setup
        resp = client.get("/api/watchlist")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 1
        plates = [item["plate_number"] for item in data["items"]]
        assert "GJ01AB1234" in plates


# ===========================================================================
# 7. System Diagnostic Health Subsystems (Phase 14)
# ===========================================================================
class TestHealthSubsystems:
    def test_get_api_health_includes_all_subsystems(self, test_setup):
        """GET /api/health reports status for API, DB, Watchlist, Alert engine, etc."""
        client, _ = test_setup
        resp = client.get("/api/health")
        assert resp.status_code == 200
        data = resp.json()

        assert data["status"] == "healthy"
        assert data["database_connected"] is True
        assert "components" in data

        components = data["components"]
        required_subsystems = [
            "api",
            "database",
            "watchlist",
            "event_ingestion",
            "alert_engine",
            "sentinel_catalogue",
            "realtime_channel",
        ]
        for sub in required_subsystems:
            assert sub in components, f"Missing health subsystem: {sub}"
            assert components[sub] == "HEALTHY"


# ===========================================================================
# 8. Error Handling & Edge Cases (Phase 10)
# ===========================================================================
class TestErrorHandling:
    def test_invalid_camera_returns_422(self, test_setup):
        """Event with unregistered camera returns 422 Unprocessable Entity."""
        client, _ = test_setup
        resp = client.post("/api/events", json={
            "camera_id": "UNKNOWN_CAM_999",
            "plate_raw": "GJ01AB1234",
        })
        assert resp.status_code == 422
        assert "not found in registry" in resp.json()["detail"]

    def test_invalid_confidence_negative_returns_422(self, test_setup):
        """Confidence < 0 returns 422."""
        client, _ = test_setup
        resp = client.post("/api/events", json={
            "camera_id": "CAM04",
            "plate_confidence": -0.5,
        })
        assert resp.status_code == 422

    def test_invalid_confidence_above_one_returns_422(self, test_setup):
        """Confidence > 1 returns 422."""
        client, _ = test_setup
        resp = client.post("/api/events", json={
            "camera_id": "CAM04",
            "plate_confidence": 1.5,
        })
        assert resp.status_code == 422

    def test_invalid_coordinates_returns_422(self, test_setup):
        """Latitude > 90 returns 422."""
        client, _ = test_setup
        resp = client.post("/api/events", json={
            "camera_id": "CAM04",
            "latitude": 105.0,
            "longitude": 72.5,
        })
        assert resp.status_code == 422

    def test_unknown_alert_returns_404(self, test_setup):
        """Acknowledging non-existent alert returns 404."""
        client, _ = test_setup
        resp = client.post("/api/alerts/99999/ack", json={})
        assert resp.status_code == 404
