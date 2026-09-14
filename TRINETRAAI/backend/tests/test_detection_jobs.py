"""
Tests: unified Detection Jobs API (merged from the standalone detection_backend).

Fast tests exercise routing/validation only (no model loads). The end-to-end
job lifecycle test is marked ``slow`` (real YOLO11 + RapidOCR inference) and is
opt-in via ``pytest -m slow`` — the default suite stays torch-free.
"""
import sys
import time
from pathlib import Path

for p in [str(Path(__file__).resolve().parents[1])]:
    if p not in sys.path:
        sys.path.insert(0, p)

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def client():
    # No lifespan: detection routes need neither DB nor camera managers.
    from app.main import app

    with TestClient(app) as c:
        yield c


def test_videos_endpoint_shape(client):
    r = client.get("/api/v1/videos")
    assert r.status_code == 200
    body = r.json()
    assert {"videos", "total"} <= set(body)
    assert isinstance(body["videos"], list)


def test_detect_video_requires_input(client):
    r = client.post("/api/v1/detect/video")
    assert r.status_code == 422


def test_detect_video_unknown_path_404(client):
    r = client.post("/api/v1/detect/video", data={"video_path": "no_such_file.mp4"})
    assert r.status_code == 404


def test_unknown_job_404(client):
    assert client.get("/api/v1/detect/jobs/job_nope").status_code == 404
    assert client.get("/api/v1/detect/jobs/job_nope/results").status_code == 404
    assert client.get("/api/v1/detect/jobs/job_nope/csv").status_code == 404


def test_detect_frame_rejects_garbage(client):
    r = client.post(
        "/api/v1/detect/frame",
        files={"file": ("bad.jpg", b"not-an-image", "image/jpeg")},
    )
    assert r.status_code == 422


def test_routes_mounted_under_both_prefixes(client):
    for prefix in ("/api", "/api/v1"):
        r = client.get(f"{prefix}/videos")
        assert r.status_code == 200


@pytest.mark.slow
def test_full_job_lifecycle(client, tmp_path):
    """Upload a synthetic clip → job COMPLETED → results + csv endpoints answer."""
    pytest.importorskip("torch")
    import cv2
    import numpy as np

    video = tmp_path / "tiny.mp4"
    writer = cv2.VideoWriter(str(video), cv2.VideoWriter_fourcc(*"mp4v"), 5, (160, 120))
    for i in range(20):
        frame = np.zeros((120, 160, 3), np.uint8)
        cv2.rectangle(frame, (10 + i * 4, 20), (60 + i * 4, 90), (210, 210, 210), -1)
        writer.write(frame)
    writer.release()
    assert video.exists() and video.stat().st_size > 0

    with open(video, "rb") as fh:
        r = client.post(
            "/api/v1/detect/video",
            files={"file": ("tiny.mp4", fh, "video/mp4")},
            data={"sample_seconds": "0", "target_fps": "5"},
        )
    assert r.status_code == 201, r.text
    job_id = r.json()["job_id"]

    status_body = {}
    for _ in range(150):  # up to ~5 min on CPU
        status_body = client.get(f"/api/v1/detect/jobs/{job_id}").json()
        if status_body.get("status") in ("COMPLETED", "FAILED"):
            break
        time.sleep(2)
    assert status_body.get("status") == "COMPLETED", status_body

    res = client.get(f"/api/v1/detect/jobs/{job_id}/results")
    assert res.status_code == 200
    assert {"job_id", "sightings", "summary"} <= set(res.json())

    # annotated video + csv exist for a completed job (zero-sighting clips still
    # produce both files)
    assert client.get(f"/api/v1/detect/jobs/{job_id}/annotated").status_code == 200
    assert client.get(f"/api/v1/detect/jobs/{job_id}/csv").status_code == 200
