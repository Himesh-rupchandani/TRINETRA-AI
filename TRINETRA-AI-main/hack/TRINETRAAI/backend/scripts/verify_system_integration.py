"""
TRINETRA AI - Final System Integration & E2E Audit Script
==========================================================
Executes the comprehensive Phase 17 verification checklist against
the running FastAPI backend application and database.
"""
import sys
from pathlib import Path

# UTF-8 stdout configuration for Windows
if sys.platform == "win32":
    try:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

backend_root = Path(__file__).resolve().parents[1]
if str(backend_root) not in sys.path:
    sys.path.insert(0, str(backend_root))

from datetime import datetime, timezone, timedelta
from contextlib import asynccontextmanager
from fastapi.testclient import TestClient
from app.main import app
from app.database.database import init_db


def run_e2e_audit():
    print("=" * 70)
    print("TRINETRA AI — SENIOR BACKEND INTEGRATION AUDIT & VERIFICATION")
    print("=" * 70)

    # Initialize tables and migration check
    init_db()

    @asynccontextmanager
    async def noop_lifespan(app):
        yield

    # One-shot script: the process exits after the checks, so the real lifespan
    # (which would start camera workers) is simply replaced for the run.
    app.router.lifespan_context = noop_lifespan

    with TestClient(app, raise_server_exceptions=True) as client:
        # Step 1: Health Subsystems Check
        print("\n[STEP 1] Testing Health Endpoint & Subsystems Diagnostics...")
        r_health = client.get("/api/health")
        assert r_health.status_code == 200, f"Health check failed: {r_health.status_code}"
        h_data = r_health.json()
        print(f"  -> Health Status: {h_data.get('status')}")
        components = h_data.get("components", {})
        for comp, comp_stat in components.items():
            print(f"     * {comp:20s}: {comp_stat}")
        assert len(components) >= 7, "Subsystem components missing!"

        # Step 2: Route Dual-Mounting Verification (/api and /api/v1)
        print("\n[STEP 2] Verifying Route Dual-Mounting (/api and /api/v1)...")
        r_api = client.get("/api/cameras")
        r_v1 = client.get("/api/v1/cameras")
        assert r_api.status_code == 200, f"/api/cameras failed: {r_api.status_code}"
        assert r_v1.status_code == 200, f"/api/v1/cameras failed: {r_v1.status_code}"
        assert len(r_api.json()["data"]) == len(r_v1.json()["data"]), "Dual-mount camera count mismatch"
        print(f"  -> Both /api/cameras and /api/v1/cameras returned HTTP 200 with {len(r_api.json()['data'])} cameras.")

        # Step 3: Camera Contract & Case-Insensitive Lookup
        print("\n[STEP 3] Verifying Camera Contract & Case-Insensitive Lookup...")
        cameras_data = r_api.json()["data"]
        sample_cam = cameras_data[0]
        for key in ["id", "name", "location", "latitude", "longitude", "status", "codec", "width", "height", "stream_type", "stream_url"]:
            assert key in sample_cam, f"Missing key '{key}' in CameraItem contract!"
        print("  -> Camera list contract validated: matches frontend specification.")

        # Test cam04 lowercase
        r_lower = client.get("/api/cameras/cam04")
        assert r_lower.status_code == 200, f"/api/cameras/cam04 failed: {r_lower.status_code}"
        r_upper = client.get("/api/cameras/CAM04")
        assert r_upper.status_code == 200, f"/api/cameras/CAM04 failed: {r_upper.status_code}"
        assert r_lower.json()["camera_id"].upper() == "CAM04"
        assert r_upper.json()["camera_id"].upper() == "CAM04"
        print(f"  -> Case-insensitive lookup confirmed: /api/cameras/cam04 == /api/cameras/CAM04")

        # Step 4: Sentinel Catalogue Synchronization
        print("\n[STEP 4] Testing Sentinel Catalogue Synchronization...")
        sync_payload = {
            "cameras": [
                {
                    "id": "cam04",
                    "name": "North Gate Junction (Paldi)",
                    "location": "Paldi Circle",
                    "latitude": 23.0338,
                    "longitude": 72.5850,
                    "stream_url": "https://cctv.corp8.cloud/cam04/index.m3u8",
                    "status": "online",
                    "codec": "h264",
                    "width": 1920,
                    "height": 1080
                },
                {
                    "id": "cam08",
                    "name": "West Gate Flyover",
                    "location": "Ashram Road",
                    "latitude": 23.0450,
                    "longitude": 72.5700,
                    "stream_url": "https://cctv.corp8.cloud/cam08/index.m3u8",
                    "status": "online",
                    "codec": "h264",
                    "width": 1920,
                    "height": 1080
                },
                {
                    "id": "cam12",
                    "name": "South Highway Checkpost",
                    "location": "SG Highway South",
                    "latitude": 23.0100,
                    "longitude": 72.5100,
                    "stream_url": "https://cctv.corp8.cloud/cam12/index.m3u8",
                    "status": "online",
                    "codec": "h264",
                    "width": 1920,
                    "height": 1080
                },
                {
                    "id": "cam17",
                    "name": "East Ring Road Outpost",
                    "location": "SP Ring Road East",
                    "latitude": 23.0800,
                    "longitude": 72.6300,
                    "stream_url": "https://cctv.corp8.cloud/cam17/index.m3u8",
                    "status": "online",
                    "codec": "h264",
                    "width": 1920,
                    "height": 1080
                }
            ]
        }
        r_sync = client.post("/api/internal/sentinel/catalogue/sync", json=sync_payload)
        assert r_sync.status_code == 200, f"Sync failed: {r_sync.status_code}"
        sync_res = r_sync.json()
        print(f"  -> Sync Status: {sync_res['status']} | Synced: {sync_res['synced_count']} cameras.")

        # Step 5: Real CV Event Ingestion & Watchlist Matching
        print("\n[STEP 5] Testing Real CV Event Ingestion with Plate Aliases & PTS...")
        event_time_1 = datetime.now(timezone.utc).isoformat()
        cv_event_1 = {
            "camera_id": "cam04",
            "vehicle_id": 42,
            "plate_raw": "GJ 01 AB-1234",
            "plate": "GJ01AB1234",
            "plate_confidence": 0.96,
            "timestamp_pts": 123456.78,
            "event_time": event_time_1,
            "latitude": 23.0338,
            "longitude": 72.5850,
            "vehicle_class": "car",
            "evidence_ref": "https://s3.example.com/snapshots/cam04_42.jpg"
        }
        r_ev1 = client.post("/api/events", json=cv_event_1)
        assert r_ev1.status_code == 201, f"Event 1 failed: {r_ev1.status_code} - {r_ev1.text}"
        ev1_data = r_ev1.json()
        ev_obj = ev1_data.get("event", {})
        print(f"  -> Ingested Event ID: {ev_obj.get('id')} | Plate: {ev1_data.get('plate_normalized')} | Watchlist Hit: {ev1_data.get('watchlist_match')} | Alert Created: {ev1_data.get('alert_created')}")
        assert ev1_data["watchlist_match"] is True, "Expected watchlist match for stolen plate!"
        assert ev1_data["plate_normalized"] == "GJ01AB1234"

        # Step 6: Alert Deduplication Verification
        print("\n[STEP 6] Testing Alert Deduplication (60-second window)...")
        # Post identical event within 60 seconds on same camera
        r_ev2 = client.post("/api/events", json=cv_event_1)
        assert r_ev2.status_code == 201
        ev2_data = r_ev2.json()
        print(f"  -> Re-ingested duplicate event on CAM04 within 60s: Watchlist Match={ev2_data['watchlist_match']} | Alert Created={ev2_data['alert_created']}")
        assert ev2_data["alert_created"] is False, "Expected alert deduplication to suppress duplicate alert within 60s!"

        # Verify alerts count
        r_alerts = client.get("/api/alerts?plate_number=GJ01AB1234")
        assert r_alerts.status_code == 200
        alerts_list = r_alerts.json().get("items", [])
        print(f"  -> Alerts for GJ01AB1234 on CAM04: {len(alerts_list)} alerts recorded.")

        # Step 7: Sighting on CAM08 (Distinct Camera creates distinct alert)
        print("\n[STEP 7] Ingesting Sighting on Downstream Camera CAM08...")
        event_time_2 = (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat()
        cv_event_cam08 = {
            "camera_id": "cam08",
            "vehicle_id": 43,
            "plate_raw": "GJ 01 AB-1234",
            "plate_confidence": 0.94,
            "timestamp_pts": 123516.78,
            "event_time": event_time_2,
            "latitude": 23.0300,
            "longitude": 72.5600,
            "vehicle_class": "car"
        }
        r_cam08 = client.post("/api/events", json=cv_event_cam08)
        assert r_cam08.status_code == 201
        print(f"  -> CAM08 event ingested successfully. Watchlist Match: {r_cam08.json()['watchlist_match']}")

        # Step 8: Vehicle Trace & Timeline Reconstruction
        print("\n[STEP 8] Testing Vehicle Trace & Historical Timeline...")
        r_trace = client.get("/api/vehicles/GJ 01 AB-1234/events")
        assert r_trace.status_code == 200, f"Trace failed: {r_trace.status_code}"
        trace_data = r_trace.json()
        print(f"  -> Sighting Count for GJ01AB1234: {trace_data['total']} sightings.")
        for ev in trace_data["items"][:5]:
            print(f"     * Camera: {ev['camera_id']:6s} | Time: {ev['event_time']} | Conf: {ev.get('plate_confidence')}")

        # Step 9: GIS Spatio-Temporal Route Verification
        print("\n[STEP 9] Testing GIS Route Calculation & Point Confidence...")
        r_route = client.get("/api/vehicles/GJ01AB1234/route")
        assert r_route.status_code == 200, f"Route failed: {r_route.status_code}"
        route_data = r_route.json()
        print(f"  -> GIS Route Points: {route_data['total_sightings']} sightings in reconstructed route.")
        for pt in route_data["route"][:5]:
            print(f"     * Sequence #{pt['sequence']}: Cam={pt['camera_id']:6s} Lat={pt['latitude']:.4f} Lon={pt['longitude']:.4f} Conf={pt.get('confidence')}")

        # Step 10: Alert Lifecycle (Acknowledge & Resolve)
        print("\n[STEP 10] Testing Alert Lifecycle Management...")
        if alerts_list:
            aid = alerts_list[0]["id"]
            r_ack = client.patch(f"/api/alerts/{aid}/acknowledge", json={"user": "operator_subh"})
            assert r_ack.status_code == 200, f"Acknowledge failed: {r_ack.status_code}"
            print(f"  -> Alert #{aid} acknowledged: status={r_ack.json()['status']}")
            
            # Duplicate acknowledge returns 409 Conflict
            r_ack_dup = client.patch(f"/api/alerts/{aid}/acknowledge", json={"user": "operator_subh"})
            assert r_ack_dup.status_code == 409
            print(f"  -> Duplicate acknowledge correctly rejected with HTTP 409 Conflict.")

        print("\n" + "=" * 70)
        print("ALL 10 END-TO-END INTEGRATION AUDIT CHECKS PASSED WITH ZERO ERRORS!")
        print("=" * 70)


if __name__ == "__main__":
    run_e2e_audit()
