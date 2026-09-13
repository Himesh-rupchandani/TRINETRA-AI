"""
Tests: Real-time vehicle detection (live view green boxes)
==========================================================
Covers the OpenCV + YOLO vehicle-detection overlay that the live camera view
serves at ``GET /api/cameras/{id}/live/detect``:

- green bounding boxes + class/confidence labels drawn with OpenCV
- per-camera inference throttling with cached-box reuse
- graceful degradation (disabled flag, bad frames, model failure)
- model weight resolution (configured path → in-repo fallback → auto-download)
- stream ticket contract (detection_url) and the /live/detect endpoint
"""
import sys
from pathlib import Path
from types import SimpleNamespace

for p in [str(Path(__file__).resolve().parents[1])]:
    if p not in sys.path:
        sys.path.insert(0, p)

import numpy as np
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.core.logging_config import logger  # noqa: F401  (keeps logging consistent)
from app.database.models import Base, Camera
from app.database.database import get_db
from app.services.vehicle_detection_service import (
    VEHICLE_CLASS_IDS,
    VehicleDetection,
    VehicleDetectionService,
    vehicle_detection_service,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
REPO_WEIGHTS = REPO_ROOT / "trinetra_detection" / "models" / "yolo11n.pt"


def _dets(n=2):
    """Two fixed detections inside a 640x360 frame."""
    return [
        VehicleDetection(50, 50, 200, 150, "car", 0.91),
        VehicleDetection(300, 120, 500, 300, "bus", 0.87),
    ]


def _green_pixels(frame):
    """Count bright-green (BGR) pixels — the colour of the drawn boxes."""
    if frame is None:
        return 0
    b, g, r = frame[:, :, 0].astype(int), frame[:, :, 1].astype(int), frame[:, :, 2].astype(int)
    return int(np.count_nonzero((g > 180) & (b < 80) & (r < 80)))


# ============================================================================
# Drawing (pure OpenCV — no model needed)
# ============================================================================
class TestDraw:
    def test_draws_green_box_borders(self):
        frame = np.zeros((360, 640, 3), dtype=np.uint8)
        VehicleDetectionService.draw(frame, _dets())
        assert _green_pixels(frame) > 100
        # Border pixels of the first box must be exactly green (BGR 0,255,0).
        assert tuple(frame[50, 100]) == (0, 255, 0)
        assert tuple(frame[100, 50]) == (0, 255, 0)

    def test_draws_nothing_without_detections(self):
        frame = np.zeros((360, 640, 3), dtype=np.uint8)
        VehicleDetectionService.draw(frame, [])
        assert _green_pixels(frame) == 0

    def test_vehicle_is_covered_by_green_fill(self):
        """With DETECTION_BOX_FILL_ALPHA > 0 the box interior (the vehicle
        itself) is covered by a semi-transparent green layer: the green
        channel dominates clearly over red/blue and differs from the
        original grey frame."""
        frame = np.full((360, 640, 3), 128, dtype=np.uint8)
        VehicleDetectionService.draw(frame, [_dets()[0]])  # box (50,50)-(200,150)
        b, g, r = (int(v) for v in frame[100, 120])
        assert g > 160, f"interior not tinted green: BGR=({b},{g},{r})"
        assert g - r > 40 and g - b > 40, f"green not dominant: BGR=({b},{g},{r})"
        assert (b, g, r) != (128, 128, 128), "frame unchanged — no fill applied"
        assert (b, g, r) != (0, 255, 0), "fill must be semi-transparent, not solid green"

    def test_fill_alpha_zero_keeps_outline_only(self, monkeypatch):
        monkeypatch.setattr(settings, "DETECTION_BOX_FILL_ALPHA", 0.0)
        frame = np.full((360, 640, 3), 128, dtype=np.uint8)
        VehicleDetectionService.draw(frame, [_dets()[0]])
        # Interior untouched (still plain grey), border still drawn.
        assert tuple(frame[100, 120]) == (128, 128, 128)
        assert tuple(frame[50, 100]) == (0, 255, 0)


# ============================================================================
# Annotate pipeline (throttling, caching, safety)
# ============================================================================
class TestAnnotate:
    def test_throttles_inference_and_reuses_last_boxes(self, monkeypatch):
        svc = VehicleDetectionService()
        calls = []

        def fake_detect(frame):
            calls.append(1)
            return _dets()

        monkeypatch.setattr(svc, "detect", fake_detect)
        monkeypatch.setattr(settings, "DETECTION_EVERY_N_FRAMES", 2)

        for _ in range(4):
            out = svc.annotate("cam-test", np.zeros((360, 640, 3), dtype=np.uint8))
            assert _green_pixels(out) > 100  # boxes visible on every frame
        assert len(calls) == 2  # model ran only every 2nd frame

    def test_disabled_returns_frame_unchanged(self, monkeypatch):
        svc = VehicleDetectionService()
        monkeypatch.setattr(svc, "detect", lambda f: _dets())
        monkeypatch.setattr(settings, "VEHICLE_DETECTION_ENABLED", False)
        frame = np.zeros((360, 640, 3), dtype=np.uint8)
        out = svc.annotate("cam-off", frame)
        assert out is frame
        assert _green_pixels(out) == 0

    def test_never_raises_on_bad_frames(self):
        svc = VehicleDetectionService()
        svc._model = object()  # force the "model ready" path without loading
        svc.detect = lambda f: _dets()  # type: ignore[method-assign]
        assert svc.annotate("cam-x", None) is None
        assert svc.annotate("cam-x", np.zeros((0, 0, 3), dtype=np.uint8)).size == 0

    def test_forget_clears_per_camera_state(self):
        svc = VehicleDetectionService()
        svc._frame_counter["cam-z"] = 7
        svc._last_detections["cam-z"] = _dets()
        svc.forget("cam-z")
        assert "cam-z" not in svc._frame_counter
        assert "cam-z" not in svc._last_detections


# ============================================================================
# Detection post-processing (class filter + confidence) with a fake model
# ============================================================================
class TestDetectPostProcessing:
    @staticmethod
    def _fake_model(boxes, confs, clss):
        import torch

        boxes_ns = SimpleNamespace(
            xyxy=torch.tensor(boxes, dtype=torch.float32),
            conf=torch.tensor(confs, dtype=torch.float32),
            cls=torch.tensor(clss, dtype=torch.float32),
        )
        return SimpleNamespace(predict=lambda *a, **k: [SimpleNamespace(boxes=boxes_ns)])

    def test_filters_non_vehicles_and_low_confidence(self):
        svc = VehicleDetectionService()
        # car (kept), person (not a vehicle), truck under threshold, bus (kept)
        svc._model = self._fake_model(
            [[10, 10, 100, 100], [20, 20, 110, 110], [30, 30, 120, 120], [40, 40, 130, 130]],
            [0.95, 0.95, 0.20, 0.90],
            [2, 0, 7, 5],
        )
        dets = svc.detect(np.zeros((360, 640, 3), dtype=np.uint8))
        names = sorted(d.class_name for d in dets)
        assert names == ["bus", "car"]
        assert all(d.confidence >= settings.CONFIDENCE_THRESHOLD for d in dets)


# ============================================================================
# Model weight resolution
# ============================================================================
class TestModelResolution:
    def test_prefers_configured_existing_file(self, monkeypatch, tmp_path):
        weights = tmp_path / "weights.pt"
        weights.write_bytes(b"x")
        monkeypatch.setattr(settings, "YOLO_MODEL_PATH", str(weights))
        assert VehicleDetectionService()._resolve_model_path() == str(weights)

    def test_falls_back_to_in_repo_weight(self, monkeypatch):
        monkeypatch.setattr(settings, "YOLO_MODEL_PATH", "models/does_not_exist_zz.pt")
        resolved = VehicleDetectionService()._resolve_model_path()
        if REPO_WEIGHTS.is_file():
            assert resolved == str(REPO_WEIGHTS)
        else:  # checkout without the standalone module -> auto-download name
            assert resolved == "does_not_exist_zz.pt"

    def test_bare_name_when_nothing_on_disk(self, monkeypatch, tmp_path):
        monkeypatch.setattr(settings, "YOLO_MODEL_PATH", "models/missing_xx.pt")
        # Simulate a checkout that lacks the in-repo fallback as well.
        monkeypatch.setattr(
            "app.services.vehicle_detection_service.os.path.isfile",
            lambda p: False if "yolo11n.pt" in p else Path(p).is_file(),
        )
        assert VehicleDetectionService()._resolve_model_path() == "missing_xx.pt"


# ============================================================================
# API contract: stream ticket + /live/detect endpoint
# ============================================================================
@pytest.fixture(scope="module")
def client(tmp_path_factory):
    # File-backed SQLite: the TestClient runs the app in another thread, and
    # ":memory:" databases are per-connection, so a shared file is required.
    db_file = tmp_path_factory.mktemp("vehicle_detection") / "test.db"
    engine = create_engine(
        f"sqlite:///{db_file}", connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(bind=engine)
    TestSession = sessionmaker(bind=engine)

    def override_get_db():
        db = TestSession()
        try:
            yield db
        finally:
            db.close()

    from contextlib import asynccontextmanager
    from app.main import app

    app.dependency_overrides[get_db] = override_get_db

    @asynccontextmanager
    async def noop_lifespan(app):
        yield

    original_lifespan = app.router.lifespan_context
    app.router.lifespan_context = noop_lifespan

    with TestClient(app, raise_server_exceptions=True) as c:
        c.session_factory = TestSession  # type: ignore[attr-defined]
        yield c

    app.router.lifespan_context = original_lifespan
    app.dependency_overrides.clear()


def _make_tmp_video(path: Path, frames: int = 12) -> Path:
    import cv2

    vw = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), 10, (640, 360))
    for i in range(frames):
        frame = np.full((360, 640, 3), 40 + i, dtype=np.uint8)
        vw.write(frame)
    vw.release()
    return path


class TestStreamTicketDetectionUrl:
    def test_ticket_offers_detection_view_for_playable_file_camera(self, client, tmp_path):
        video = _make_tmp_video(tmp_path / "feed.mp4")
        db = client.session_factory()  # type: ignore[attr-defined]
        try:
            db.add(
                Camera(
                    camera_id="CAMDETECT",
                    name="Detect test camera",
                    stream_url=str(video),
                    stream_type="file",
                    status="ONLINE",
                )
            )
            db.commit()
            data = client.get("/api/cameras/camdetect/stream").json()
            assert data["stream_type"] == "MJPEG"
            assert data["stream_url"] == "/api/cameras/camdetect/live"
            assert data["detection_url"] == "/api/cameras/camdetect/live/detect"
        finally:
            db.query(Camera).filter(Camera.camera_id == "CAMDETECT").delete()
            db.commit()
            db.close()

    def test_ticket_omits_detection_url_when_disabled(self, client, tmp_path, monkeypatch):
        monkeypatch.setattr(settings, "VEHICLE_DETECTION_ENABLED", False)
        video = _make_tmp_video(tmp_path / "feed2.mp4")
        db = client.session_factory()  # type: ignore[attr-defined]
        try:
            db.add(
                Camera(
                    camera_id="CAMDETECT2",
                    name="Detect disabled test camera",
                    stream_url=str(video),
                    stream_type="file",
                    status="ONLINE",
                )
            )
            db.commit()
            data = client.get("/api/cameras/camdetect2/stream").json()
            assert data["detection_url"] is None
        finally:
            db.query(Camera).filter(Camera.camera_id == "CAMDETECT2").delete()
            db.commit()
            db.close()

    def test_ticket_unknown_camera_404(self, client):
        assert client.get("/api/cameras/nope-does-not-exist/stream").status_code == 404


class TestLiveDetectEndpoint:
    def test_unknown_camera_404(self, client):
        assert client.get("/api/cameras/nope-does-not-exist/live/detect").status_code == 404

    def test_unconfigured_camera_409(self, client, tmp_path):
        db = client.session_factory()  # type: ignore[attr-defined]
        try:
            db.add(
                Camera(
                    camera_id="CAMNOSRC",
                    name="No source camera",
                    stream_url="   ",
                    stream_type="file",
                    status="OFFLINE",
                )
            )
            db.commit()
            assert client.get("/api/cameras/camnosrc/live/detect").status_code == 409
        finally:
            db.query(Camera).filter(Camera.camera_id == "CAMNOSRC").delete()
            db.commit()
            db.close()

    def test_mjpeg_stream_carries_green_boxes(self, tmp_path, monkeypatch):
        """Full pipeline the /live/detect endpoint serves: on-demand decode →
        OpenCV annotate (green boxes) → multipart MJPEG bytes.

        Drives the generator directly: the stream is infinite, and Starlette's
        TestClient consumes ASGI responses to completion, so it cannot be used
        for a live stream.
        """
        import cv2

        from app.camera.manager import camera_manager

        video = _make_tmp_video(tmp_path / "feed3.mp4", frames=30)
        cam_id = "CAMDETECTLIVE"
        monkeypatch.setattr(vehicle_detection_service, "detect", lambda frame: _dets())
        try:
            camera_manager.add_camera(
                camera_id=cam_id, source=str(video), source_type="file", auto_start=False
            )
            gen = camera_manager.generate_mjpeg_stream(cam_id, detect_vehicles=True)

            frames_seen = 0
            green_found = 0
            try:
                for _ in range(6):
                    chunk = next(gen)
                    assert chunk.startswith(b"--frame\r\nContent-Type: image/jpeg\r\n\r\n")
                    jpeg = chunk.rsplit(b"\r\n", 1)[0]
                    jpeg = jpeg.split(b"\r\n\r\n", 1)[1]
                    frame = cv2.imdecode(np.frombuffer(jpeg, dtype=np.uint8), cv2.IMREAD_COLOR)
                    assert frame is not None
                    frames_seen += 1
                    green_found = max(green_found, _green_pixels(frame))
                    if frames_seen >= 4:
                        break
            finally:
                gen.close()

            assert frames_seen >= 2, "detect stream produced no decodable frames"
            assert green_found > 100, f"no green vehicle boxes found (max={green_found})"
        finally:
            camera_manager.remove_camera(cam_id)
            vehicle_detection_service.forget(cam_id.lower())


# ============================================================================
# Live-signal probe (honest LIVE badge: real frames vs NO-SIGNAL placeholder)
# ============================================================================
class TestLiveSignalProbe:
    def test_true_while_real_frames_flow(self, tmp_path):
        from app.camera.manager import camera_manager

        video = _make_tmp_video(tmp_path / "signal_ok.mp4", frames=30)
        camera_manager.add_camera(
            camera_id="CAMSIGOK", source=str(video), source_type="file", auto_start=False
        )
        try:
            gen = camera_manager.generate_mjpeg_stream("CAMSIGOK")
            next(gen)  # one real frame is enough
            gen.close()
            assert camera_manager.has_live_signal("camsigok") is True
        finally:
            camera_manager.remove_camera("CAMSIGOK")
        assert camera_manager.has_live_signal("camsigok") is False  # cleaned up

    def test_false_for_unreachable_source(self, tmp_path):
        from app.camera.manager import camera_manager

        camera_manager.add_camera(
            camera_id="CAMSIGBAD",
            source=str(tmp_path / "missing.mp4"),
            source_type="file",
            auto_start=False,
        )
        try:
            gen = camera_manager.generate_mjpeg_stream("CAMSIGBAD")
            next(gen)  # placeholder frame only
            gen.close()
            assert camera_manager.has_live_signal("camsigbad") is False
        finally:
            camera_manager.remove_camera("CAMSIGBAD")

    def test_signal_endpoint(self, client, tmp_path):
        from app.camera.manager import camera_manager

        video = _make_tmp_video(tmp_path / "signal_http.mp4", frames=30)
        camera_manager.add_camera(
            camera_id="CAMSIGH", source=str(video), source_type="file", auto_start=False
        )
        try:
            gen = camera_manager.generate_mjpeg_stream("CAMSIGH")
            next(gen)
            gen.close()
            data = client.get("/api/cameras/camsigh/live/signal").json()
            assert data == {"camera_id": "camsigh", "has_signal": True}
        finally:
            camera_manager.remove_camera("CAMSIGH")

        # Unknown camera: honest False, no 500.
        data = client.get("/api/cameras/never-registered/live/signal").json()
        assert data["has_signal"] is False


# ============================================================================
# Real model inference — needs torch/ultralytics + weights; opt-in (slow)
# ============================================================================
@pytest.mark.slow
class TestRealInference:
    def test_detects_vehicles_in_real_traffic_image(self):
        sample = REPO_ROOT / "trinetra_detection" / "sample_data" / "sample_1.jpg"
        if not sample.is_file():
            pytest.skip("sample image not present in this checkout")
        import cv2

        frame = cv2.imread(str(sample))
        dets = vehicle_detection_service.detect(frame)
        assert len(dets) >= 1, "expected at least one vehicle in the traffic sample"
        h, w = frame.shape[:2]
        for d in dets:
            assert d.class_name in VEHICLE_CLASS_IDS.values()
            assert 0 <= d.x1 < d.x2 <= w
            assert 0 <= d.y1 < d.y2 <= h
            assert d.confidence >= settings.CONFIDENCE_THRESHOLD
