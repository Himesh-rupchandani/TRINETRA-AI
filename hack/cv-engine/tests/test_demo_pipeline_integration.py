"""
END-TO-END INTEGRATION TEST (spec §35) — CONTROLLED FIXTURE, NOT LIVE.

    camera  = cam04
    vehicle = GJ01AB1234

Scripted demo frames -> tracking -> multi-frame ANPR aggregation -> event
builder -> dedup -> evidence -> POST /api/events -> REAL backend
(uvicorn + SQLite) -> watchlist match -> alert.

This proves the CV->backend->watchlist->alert contract with deterministic
inputs. Live Sentinel capture is tested separately (tests/test_live_sentinel,
marked `live`, never faked).
"""
import socket
import sys
import threading
import time
from pathlib import Path

import pytest

# NOTE: the isolated test DATABASE_URL is configured in tests/conftest.py,
# which pytest imports before any test module (see conftest docstring).
BACKEND_ROOT = Path(__file__).resolve().parents[2] / "TRINETRAAI" / "backend"
sys.path.insert(0, str(BACKEND_ROOT))

import httpx  # noqa: E402
from app.database.database import SessionLocal, engine  # noqa: E402
from app.database.models import Base, Camera, Watchlist  # noqa: E402
from app.main import app as backend_app  # noqa: E402

from capture.sentinel_catalogue import Camera as CvCamera  # noqa: E402
from config.settings import Settings  # noqa: E402
from evidence.evidence_writer import EvidenceWriter  # noqa: E402
from integration.backend_client import BackendClient  # noqa: E402
from pipeline.camera_pipeline import CameraPipeline  # noqa: E402
from pipeline.demo_source import DemoDetector, DemoOcr, DemoScenario, demo_packets  # noqa: E402


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


@pytest.fixture(scope="module")
def backend_server():
    import uvicorn

    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    if not db.query(Camera).filter(Camera.camera_id == "cam04").first():
        db.add(Camera(
            camera_id="cam04", name="North Gate Junction", location="Paldi Circle",
            stream_url="rtsp://103.250.160.189:8554/stream/cam04", stream_type="rtsp",
            latitude=23.0338, longitude=72.585, status="ONLINE",
        ))
    if not db.query(Watchlist).filter(Watchlist.plate_number == "GJ01AB1234").first():
        db.add(Watchlist(
            plate_number="GJ01AB1234", category="stolen vehicle",
            description="Reported stolen near SG Highway", active=True,
        ))
    db.commit()
    db.close()

    port = _free_port()
    config = uvicorn.Config(backend_app, host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)
    th = threading.Thread(target=server.run, daemon=True)
    th.start()

    base = f"http://127.0.0.1:{port}"
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        try:
            if httpx.get(f"{base}/api/health", timeout=1.0).status_code == 200:
                break
        except Exception:
            time.sleep(0.2)
    else:
        raise RuntimeError("backend did not start")
    yield base
    server.should_exit = True
    th.join(timeout=5)


def test_full_demo_loop_to_watchlist_alert(backend_server, tmp_path):
    base_url = backend_server
    scenario = DemoScenario.default()   # cam04, GJ01AB1234 + MH02CD5678, feed loop @45

    camera = CvCamera(camera_id="cam04", latitude=23.0338, longitude=72.585,
                      location="Paldi Circle")
    settings = Settings(anpr_enabled=True, frame_skip=1, evidence_dir=str(tmp_path))
    demo_ocr = DemoOcr()

    backend = BackendClient(base_url=base_url, timeout_sec=5.0, max_retries=2,
                            dead_letter_path=str(tmp_path / "dl.jsonl"))
    backend.start()

    pipeline = CameraPipeline(
        camera, settings,
        detector=DemoDetector(),
        ocr_engine=demo_ocr,
        backend_client=backend,
        evidence_writer=EvidenceWriter(str(tmp_path / "evidence")),
        on_packet=lambda pkt: setattr(demo_ocr, "ctx", (scenario, getattr(pkt.frame, "demo_index", -1))),
    )
    pipeline.run(demo_packets(scenario))

    assert backend.flush(timeout_sec=20)
    backend.close()

    # --- CV-side assertions ------------------------------------------------
    assert pipeline.stats.events_emitted >= 2, "both vehicles should produce sightings"
    assert pipeline.stats.discontinuities >= 1, "feed loop must be detected"
    assert backend.stats["accepted"] >= 2
    assert backend.stats["failed_after_retries"] == 0

    # --- backend-side assertions over real HTTP ----------------------------
    # 1) Vehicle trace endpoint sees the watchlist vehicle sighting
    r = httpx.get(f"{base_url}/api/vehicles/GJ01AB1234/events", timeout=5.0)
    assert r.status_code == 200
    trace = r.json()
    sightings = trace.get("events") or trace.get("items") or trace.get("data") or trace
    assert sightings, f"no sightings recorded: {trace}"

    # 2) A WATCHLIST_MATCH alert was created for the stolen plate
    r = httpx.get(f"{base_url}/api/alerts", timeout=5.0, params={"size": 50})
    assert r.status_code == 200
    alerts_payload = r.json()
    alerts = alerts_payload.get("items", alerts_payload if isinstance(alerts_payload, list) else [])
    matches = [a for a in alerts if a.get("alert_type") == "WATCHLIST_MATCH"
               and a.get("plate_number") == "GJ01AB1234"
               and a.get("camera_id", "").lower() == "cam04"]
    assert matches, f"watchlist alert not found in {alerts_payload}"

    # 3) The non-watchlist plate produced an event but NO alert
    mh_alerts = [a for a in alerts if a.get("plate_number") == "MH02CD5678"]
    assert mh_alerts == [], "MH02CD5678 is not on the watchlist"

    # 4) Dedup worked: not one event per frame
    assert pipeline.stats.events_emitted < scenario.n_frames // 3

    # 5) Evidence files were written deterministically
    evidence_files = list((tmp_path / "evidence" / "cam04").glob("*.jpg"))
    assert evidence_files, "evidence frames expected for significant events"
