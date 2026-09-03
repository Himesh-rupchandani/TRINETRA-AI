"""TRINETRA reference backend — bridges the CV engine to the control-room UI.

Runs the *real* CV pipeline (YOLO11 + ByteTrack + PP-OCR) on the controlled
fixture in a background thread, POSTs its events to ``POST /api/events`` through
the same client the field deployment uses, stores them, matches the watchlist,
and serves the exact contract the frontend expects (events, alerts, cameras,
health, KPIs, vehicle investigation, evidence, and an SSE ``/api/stream``).

This is a reference/demo backend (in-memory). The production backend is a
separate team's deliverable; the CV -> ``/api/events`` wire contract is identical.
"""

from __future__ import annotations

import asyncio
import json
import queue
import sys
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent
CV_ROOT = BACKEND_DIR.parent / "cv-engine"
sys.path.insert(0, str(CV_ROOT))

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, StreamingResponse

from config.settings import load_settings
from detection.classes import to_backend_class
from events.event_schema import validate_payload

SETTINGS = load_settings(env={}, evidence_dir=str(CV_ROOT / "var" / "evidence"))
FIXTURE = CV_ROOT / "tests" / "fixtures" / "traffic_cam04.jpg"

app = FastAPI(title="TRINETRA reference backend")

_lock = threading.Lock()
_EVENTS: list[dict] = []          # camelCase VehicleEvent (frontend shape)
_ALERTS: list[dict] = []
_SUBSCRIBERS: list[queue.Queue] = []

# Model-1 CCTV registry (mirrors what the Sentinel gateway publishes). The *grid*
# comes from here; which cameras actually produce AI events is live CV data.
_SEEDS = [
    ("CAM01", "Law Garden Circle", 23.0225, 72.5595, "Traffic Police", "Central", "ONLINE", "H264", 1920, 1080, 25),
    ("CAM02", "Ellis Bridge", 23.0234, 72.5714, "Traffic Police", "Central", "ONLINE", "H264", 2560, 1440, 25),
    ("CAM03", "Anjali Cross Roads", 22.995, 72.548, "Municipal (AMC)", "South", "ONLINE", "H264", 1280, 720, 20),
    ("CAM04", "Paldi Circle", 23.0126, 72.5647, "Police", "Central", "ONLINE", "H264", 1920, 1080, 25),
    ("CAM05", "Navrangpura Circle", 23.0367, 72.56, "Police", "West", "ONLINE", "H264", 1920, 1080, 25),
    ("CAM06", "Gujarat University Junction", 23.0395, 72.545, "Traffic Police", "West", "ONLINE", "H265", 1280, 720, 15),
    ("CAM07", "Panjrapole Cross Road", 23.029, 72.548, "Traffic Police", "West", "ONLINE", "H264", 1920, 1080, 25),
    ("CAM08", "Lal Darwaja Terminus", 23.025, 72.58, "Police", "Central", "ONLINE", "H264", 1920, 1080, 25),
    ("CAM09", "Kalupur Railway Station", 23.0272, 72.6014, "Railway Police", "East", "ONLINE", "H264", 2560, 1440, 30),
    ("CAM10", "Jamalpur Gate", 23.013, 72.582, "Police", "Central", "ONLINE", "H264", 1280, 720, 20),
    ("CAM11", "Delhi Darwaja", 23.04, 72.59, "Municipal (AMC)", "Central", "ONLINE", "H264", 1920, 1080, 25),
    ("CAM12", "Kankaria Lake Circle", 22.999, 72.602, "Police", "South", "ONLINE", "H265", 1920, 1080, 25),
    ("CAM13", "CTM Cross Road", 22.99, 72.625, "Traffic Police", "South", "ONLINE", "H264", 1920, 1080, 25),
    ("CAM14", "Isanpur Cross Road", 22.97, 72.6, "Traffic Police", "South", "ONLINE", "H264", 1280, 720, 20),
    ("CAM15", "Vatva GIDC Gate", 22.96, 72.63, "Industrial Security", "South", "ONLINE", "H264", 1280, 720, 12),
    ("CAM16", "Narol Circle", 22.955, 72.585, "Highway Authority", "South", "ONLINE", "H264", 2560, 1440, 30),
    ("CAM17", "Odhav Ring Road", 23.028, 72.665, "Highway Authority", "East", "ONLINE", "H265", 1920, 1080, 30),
    ("CAM18", "Nikol Circle", 23.045, 72.665, "Police", "East", "ONLINE", "H265", 1920, 1080, 25),
    ("CAM19", "Bapunagar Char Rasta", 23.04, 72.64, "Police", "East", "ONLINE", "H264", 1280, 720, 20),
    ("CAM20", "Naroda Patiya", 23.07, 72.66, "Traffic Police", "East", "ONLINE", "H264", 1920, 1080, 25),
    ("CAM21", "Airport Circle Hansol", 23.073, 72.626, "Airport Security", "North", "ONLINE", "H264", 2560, 1440, 30),
    ("CAM22", "Riverfront West Promenade", 23.05, 72.575, "Municipal (AMC)", "Central", "ONLINE", "H265", 1920, 1080, 25),
    ("CAM23", "Gandhi Ashram Gate", 23.06, 72.58, "Police", "North", "ONLINE", "H264", 1920, 1080, 25),
    ("CAM24", "RTO Circle Subhash Bridge", 23.055, 72.586, "Transport Dept", "North", "ONLINE", "H264", 1920, 1080, 25),
    ("CAM25", "Motera Stadium Approach", 23.092, 72.597, "Police", "North", "ONLINE", "H264", 2560, 1440, 30),
    ("CAM26", "Chandkheda Circle", 23.11, 72.59, "Traffic Police", "North", "OFFLINE", "H265", 1280, 720, 20),
    ("CAM27", "Vastrapur Lake Junction", 23.0395, 72.529, "Police", "West", "ONLINE", "H264", 1920, 1080, 25),
    ("CAM28", "Iskcon Cross Roads", 23.027, 72.507, "Traffic Police", "West", "DEGRADED", "H264", 2560, 1440, 30),
    ("CAM29", "S.G. Highway Bopal", 23.03, 72.47, "Highway Authority", "West", "OFFLINE", "H264", 2560, 1440, 30),
    ("CAM30", "Sarkhej Circle", 22.98, 72.5, "Highway Authority", "West", "DEGRADED", "H264", 1920, 1080, 25),
]
REGISTRY = [
    {
        "id": s[0].lower(), "name": s[0], "location": s[1], "latitude": s[2],
        "longitude": s[3], "department": s[4], "zone": s[5], "status": s[6],
        "codec": s[7], "width": s[8], "height": s[9], "fps": s[10], "streamType": "WEBRTC",
    }
    for s in _SEEDS
]
CAMERA_BY_ID = {c["id"]: c for c in REGISTRY}
CAMERA = CAMERA_BY_ID["cam04"]
#: Cameras the CV engine is actually processing right now (real AI).
CV_ACTIVE = {"cam04"}

WATCHLIST = [
    {
        "id": "wl-001", "plate": "GJ01AB1234", "category": "STOLEN VEHICLE",
        "severity": "HIGH", "reason": "Reported stolen, Paldi", "caseRef": "FIR/2026/PLD/0417",
        "addedBy": "SI Rathod", "addedAt": "2026-09-01T09:00:00Z", "active": True,
    },
]
_WATCH_BY_PLATE = {w["plate"]: w for w in WATCHLIST}


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _broadcast(message: dict) -> None:
    for q in list(_SUBSCRIBERS):
        try:
            q.put_nowait(message)
        except queue.Full:  # pragma: no cover
            pass


def _evidence_urls(ref):
    if not ref:
        return None
    return {
        "ref": ref,
        "frameUrl": f"/api/evidence/{ref}",
        "plateCropUrl": f"/api/evidence/{ref.replace('.jpg', '_plate.jpg')}",
        "capturedAt": _now(),
        "synthetic": False,
    }


def cv_to_frontend(payload: dict) -> tuple[dict, dict | None]:
    """Convert the CV engine's snake_case event to the frontend's camelCase."""
    plate = (payload.get("plate") or "").upper()
    watch = _WATCH_BY_PLATE.get(plate)
    vclass = to_backend_class(payload.get("vehicle_class"))
    evid = _evidence_urls(payload.get("evidence_ref"))
    event = {
        "id": f"evt-{uuid.uuid4().hex[:10]}",
        "cameraId": payload.get("camera_id"),
        "cameraName": CAMERA["name"],
        "vehicleId": payload.get("vehicle_id"),
        "plate": plate,
        "plateConfidence": round(float(payload.get("plate_confidence") or 0) * 100, 1),
        "timestamp": payload.get("event_time") or _now(),
        "latitude": payload.get("latitude"),
        "longitude": payload.get("longitude"),
        "location": CAMERA["location"],
        "vehicleClass": vclass if vclass != "UNKNOWN" else None,
        "eventType": "WATCHLIST_MATCH" if watch else (payload.get("event_type") or "ANPR_READ"),
        "severity": watch["severity"] if watch else "INFO",
        "evidenceRef": payload.get("evidence_ref"),
        "evidence": evid,
        "watchlistMatch": bool(watch and watch["active"]),
        "direction": None,
        "speedKmph": None,
    }
    return event, watch


@app.post("/api/events")
async def ingest(request: Request):
    payload = await request.json()
    problems = validate_payload(payload)
    if problems:
        return {"ok": False, "problems": problems}, 400
    with _lock:
        event, watch = cv_to_frontend(payload)
        _EVENTS.append(event)
        alert = None
        if watch and watch["active"]:
            alert = {
                "id": f"al-{uuid.uuid4().hex[:8]}", "eventId": event["id"],
                "plate": event["plate"], "cameraId": event["cameraId"],
                "cameraName": event["cameraName"], "location": event["location"],
                "latitude": event["latitude"], "longitude": event["longitude"],
                "severity": watch["severity"], "status": "NEW",
                "category": watch["category"], "createdAt": _now(),
                "confidence": event["plateConfidence"], "evidenceRef": event["evidenceRef"],
            }
            _ALERTS.insert(0, alert)
    _broadcast({"type": "EVENT", "payload": event})
    if alert:
        _broadcast({"type": "ALERT", "payload": alert})
    return {"ok": True, "id": event["id"], "alert": bool(alert)}


# ---------------------------------------------------------------------------
# reads
# ---------------------------------------------------------------------------
@app.get("/api/events")
async def list_events(request: Request):
    params = request.query_params
    with _lock:
        events = list(reversed(_EVENTS))  # newest first
    plate = (params.get("plate") or "").upper()
    camera = params.get("cameraId")
    if plate:
        events = [e for e in events if e["plate"] == plate]
    if camera and camera != "ALL":
        events = [e for e in events if e["cameraId"] == camera]
    if params.get("limit"):
        return events[: int(params["limit"])]
    page = int(params.get("page", 1)); size = int(params.get("pageSize", 25))
    return {"items": events[(page - 1) * size: page * size], "total": len(events), "page": page, "pageSize": size}


@app.get("/api/events/{event_id}")
async def get_event(event_id: str):
    with _lock:
        for e in _EVENTS:
            if e["id"] == event_id:
                return e
    return {"error": "not found"}, 404


@app.get("/api/cameras")
async def list_cameras():
    with _lock:
        count = sum(1 for e in _EVENTS if e["cameraId"] == "cam04")
    cam = dict(CAMERA); cam["eventCount24h"] = count; cam["lastEventAt"] = (_EVENTS[-1]["timestamp"] if _EVENTS else None)
    return [cam]


@app.get("/api/cameras/{camera_id}")
async def get_camera(camera_id: str):
    if camera_id == "cam04":
        return CAMERA
    return {"error": "not found"}, 404


@app.get("/api/cameras/{camera_id}/stream")
async def camera_stream(camera_id: str):
    return {
        "cameraId": camera_id, "streamType": "HLS",
        "streamUrl": "", "expiresAt": _now(), "poster": None,
    }


@app.get("/api/alerts")
async def list_alerts(request: Request):
    status = request.query_params.get("status")
    with _lock:
        alerts = list(_ALERTS)
    if status and status != "ALL":
        alerts = [a for a in alerts if a["status"] == status]
    return alerts


@app.post("/api/alerts/{alert_id}/ack")
async def ack_alert(alert_id: str, request: Request):
    body = await request.json() if request.headers.get("content-length") else {}
    return _transition(alert_id, "ACKNOWLEDGED", by=(body or {}).get("by"))


@app.post("/api/alerts/{alert_id}/resolve")
async def resolve_alert(alert_id: str, request: Request):
    body = await request.json() if request.headers.get("content-length") else {}
    return _transition(alert_id, "RESOLVED", note=(body or {}).get("note"))


def _transition(alert_id, status, by=None, note=None):
    with _lock:
        for a in _ALERTS:
            if a["id"] == alert_id:
                a["status"] = status
                if by:
                    a["acknowledgedBy"], a["acknowledgedAt"] = by, _now()
                if note:
                    a["note"] = note
                if status == "RESOLVED":
                    a["resolvedAt"] = _now()
                _broadcast({"type": "ALERT", "payload": a})
                return a
    return {"error": "not found"}, 404


@app.get("/api/watchlist")
async def watchlist():
    return WATCHLIST


@app.get("/api/vehicles/{plate}/events")
async def vehicle_events(plate: str):
    plate = plate.upper()
    with _lock:
        return [e for e in reversed(_EVENTS) if e["plate"] == plate]


@app.get("/api/vehicles/{plate}")
async def vehicle_profile(plate: str):
    plate = plate.upper()
    with _lock:
        evs = [e for e in _EVENTS if e["plate"] == plate]
    if not evs:
        return None
    return {
        "plate": plate, "vehicleClass": evs[0]["vehicleClass"], "colour": None,
        "firstSeen": evs[0]["timestamp"], "lastSeen": evs[-1]["timestamp"],
        "totalSightings": len(evs), "watchlist": _WATCH_BY_PLATE.get(plate),
    }


@app.get("/api/vehicles/{plate}/route")
async def vehicle_route(plate: str):
    plate = plate.upper()
    with _lock:
        evs = [e for e in _EVENTS if e["plate"] == plate]
    points = []
    for i, e in enumerate(evs):
        points.append({
            "sequence": i + 1, "eventId": e["id"], "cameraId": e["cameraId"],
            "cameraName": e["cameraName"], "location": e["location"],
            "latitude": e["latitude"], "longitude": e["longitude"],
            "timestamp": e["timestamp"], "plateConfidence": e["plateConfidence"],
        })
    return {"plate": plate, "points": points, "totalDistanceKm": 0.0, "camerasTouched": len({p["cameraId"] for p in points})}


@app.get("/api/health")
async def health():
    with _lock:
        n = len(_EVENTS)
    return {
        "services": [
            {"id": "cv", "name": "CV Engine", "description": "YOLO11 + ByteTrack + PP-OCR",
             "status": "HEALTHY", "uptimePct": 100.0, "uptimeSince": _now(), "lastHeartbeat": _now(),
             "activeConnections": 1, "processingState": "PROCESSING"},
            {"id": "api", "name": "Backend API", "description": "Event ingest + query",
             "status": "HEALTHY", "uptimePct": 100.0, "uptimeSince": _now(), "lastHeartbeat": _now(),
             "activeConnections": len(_SUBSCRIBERS), "processingState": "PROCESSING", "queueDepth": 0},
            {"id": "sentinel", "name": "Sentinel Grid", "description": "Government media gateway",
             "status": "DEGRADED", "uptimePct": 0.0, "uptimeSince": _now(), "lastHeartbeat": _now(),
             "activeConnections": 0, "processingState": "IDLE",
             "latestError": "Unreachable from this sandbox (egress-blocked); CV runs on controlled fixture"},
        ],
        "ingestFps": 0.0, "eventsPerMinute": _rate(), "anprPerMinute": _rate("ANPR_READ"),
        "generatedAt": _now(),
    }


@app.get("/api/stats/kpis")
async def kpis():
    with _lock:
        evs = list(_EVENTS); alerts = list(_ALERTS)
    anpr = [e for e in evs if e["eventType"] in ("ANPR_READ", "WATCHLIST_MATCH")]
    return {
        "totalCameras": 1, "camerasOnline": 1, "camerasDegraded": 0, "camerasOffline": 0,
        "activeAlerts": sum(1 for a in alerts if a["status"] == "NEW"),
        "vehicleDetections24h": len(evs), "anprReads24h": len(anpr),
        "watchlistMatches24h": sum(1 for e in evs if e["watchlistMatch"]),
    }


def _rate(kind=None):
    cutoff = time.time() - 60
    with _lock:
        recent = [e for e in _EVENTS if _iso_to_epoch(e["timestamp"]) >= cutoff]
    if kind:
        recent = [e for e in recent if e["eventType"] == kind]
    return len(recent)


def _iso_to_epoch(iso):
    try:
        return datetime.strptime(iso, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc).timestamp()
    except Exception:
        return 0.0


@app.get("/api/evidence/{path:path}")
async def evidence(path: str):
    full = (Path(SETTINGS.evidence_dir) / path).resolve()
    base = Path(SETTINGS.evidence_dir).resolve()
    if not str(full).startswith(str(base)) or not full.is_file():
        return {"error": "not found"}, 404
    return FileResponse(full, media_type="image/jpeg")


# ---------------------------------------------------------------------------
# SSE realtime
# ---------------------------------------------------------------------------
@app.get("/api/stream")
async def stream():
    q: queue.Queue = queue.Queue(maxsize=256)
    _SUBSCRIBERS.append(q)

    async def gen():
        try:
            yield "retry: 2000\n\n"
            while True:
                try:
                    msg = q.get_nowait()
                except queue.Empty:
                    yield ": keepalive\n\n"
                    await asyncio.sleep(1.0)
                    continue
                yield f"data: {json.dumps(msg)}\n\n"
        finally:
            if q in _SUBSCRIBERS:
                _SUBSCRIBERS.remove(q)

    return StreamingResponse(gen(), media_type="text/event-stream")


# ---------------------------------------------------------------------------
# CV feeder (real AI on the controlled fixture)
# ---------------------------------------------------------------------------
def _start_feeder():
    import os
    if os.environ.get("CV_FEED", "1") != "1":
        return
    threading.Thread(target=_feeder_loop, name="cv-feeder", daemon=True).start()


def _feeder_loop():
    import cv2
    from anpr.ocr import get_ocr_engine
    from anpr.plate_detector import PlateDetector
    from capture.frames import FramePacket
    from capture.sentinel_catalogue import Camera
    from integration.backend_client import BackendClient
    from pipeline import CameraPipeline
    from tracking.vehicle_tracker import VehicleTracker

    time.sleep(2.0)  # let uvicorn bind first
    frame = cv2.imread(str(FIXTURE))
    if frame is None:
        print("[feeder] fixture missing - CV feed disabled")
        return
    feed_settings = load_settings(
        env={}, anpr_interval_s=0.6, ocr_engine="rapidocr",
        dedup_window_s=6.0, dedup_unplated_window_s=6.0,
        evidence_dir=str(CV_ROOT / "var" / "evidence"),
        backend_base_url="http://127.0.0.1:8000",
    )
    camera = Camera(camera_id="cam04", name="Paldi Circle", latitude=23.0126, longitude=72.5647)
    backend = BackendClient(feed_settings)
    backend.start()
    pipeline = CameraPipeline(feed_settings, camera, tracker=VehicleTracker(feed_settings), backend=backend)
    pipeline.ocr = get_ocr_engine(feed_settings)
    pipeline.plate_detector = PlateDetector(feed_settings, pipeline.ocr)
    print("[feeder] real CV pipeline started on controlled fixture")
    t = 0
    while True:
        packet = FramePacket(frame=frame, camera_id="cam04", pts_ms=t * 500.0,
                             continuous_ms=t * 500.0, seq=t + 1, source="file")
        try:
            pipeline.process_packet(packet)
        except Exception as exc:  # noqa: BLE001
            print("[feeder] error:", exc)
        t += 1
        time.sleep(0.6)


@app.on_event("startup")
async def _on_startup():
    _start_feeder()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
