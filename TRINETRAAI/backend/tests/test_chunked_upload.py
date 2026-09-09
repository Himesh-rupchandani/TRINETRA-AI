"""
Chunked upload — large videos arrive as small parts so reverse proxies with
a request-body cap (HTTP 413) never see one big body. The reassembly and
registration logic runs for real; only the HTTP transport is the test client.
"""
import sys
from contextlib import asynccontextmanager
from pathlib import Path

for _p in [str(Path(__file__).resolve().parents[1])]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.database.database import SessionLocal, init_db
from app.database.models import Camera, VehicleEvent, VideoSource
from app.services import video_analysis_service as vas

TEST_NAME = "TCHU1.mp4"


def _clip_bytes() -> bytes:
    import io  # noqa: F401  (cv2 writes to temp file below)
    import tempfile

    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as t:
        path = t.name
    w = cv2.VideoWriter(path, cv2.VideoWriter_fourcc(*"mp4v"), 10, (160, 120))
    for i in range(20):
        frame = np.full((120, 160, 3), 30 + i, dtype=np.uint8)
        w.write(frame)
    w.release()
    data = Path(path).read_bytes()
    Path(path).unlink(missing_ok=True)
    return data


@pytest.fixture(scope="module")
def client():
    init_db()
    from app.main import app

    @asynccontextmanager
    async def noop_lifespan(app):
        yield

    original = app.router.lifespan_context
    app.router.lifespan_context = noop_lifespan
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c
    app.router.lifespan_context = original

    db = SessionLocal()
    try:
        db.query(VehicleEvent).filter(VehicleEvent.camera_id == "TCHU1").delete(
            synchronize_session=False)
        db.query(VideoSource).filter(VideoSource.camera_id == "TCHU1").delete(
            synchronize_session=False)
        db.query(Camera).filter(Camera.camera_id == "TCHU1").delete(
            synchronize_session=False)
        db.commit()
    finally:
        db.close()


def _post_chunks(client, upload_id, data, sizes):
    off = 0
    part = 0
    for n in sizes:
        chunk = data[off:off + n]
        if not chunk:
            break
        res = client.post(
            "/api/analysis/videos/upload/chunk",
            data={"upload_id": upload_id, "part": str(part)},
            files={"data": ("chunk", chunk, "application/octet-stream")},
        )
        assert res.status_code == 200, res.text
        off += n
        part += 1
    return part


def test_chunked_upload_reassembles_and_registers(client):
    data = _clip_bytes()
    n = _post_chunks(client, "tchu-a", data, [7, 13, 5, 10 ** 6])

    res = client.post(
        "/api/analysis/videos/upload/complete",
        data={"upload_id": "tchu-a", "filename": TEST_NAME},
    )
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["errors"] == []
    video = body["added"][0]
    assert video["camera_id"] == "TCHU1"
    assert video["frames_total"] == 20

    # the stored file is byte-identical to what the client sent
    db = SessionLocal()
    try:
        row = db.query(VideoSource).filter(VideoSource.video_id == video["video_id"]).first()
        stored = Path(row.file_path).read_bytes()
    finally:
        db.close()
    assert stored == data
    assert n >= 4


def test_missing_chunk_is_rejected(client):
    data = _clip_bytes()
    client.post(
        "/api/analysis/videos/upload/chunk",
        data={"upload_id": "tchu-b", "part": "0"},
        files={"data": ("chunk", data[:10], "application/octet-stream")},
    )
    client.post(
        "/api/analysis/videos/upload/chunk",
        data={"upload_id": "tchu-b", "part": "2"},
        files={"data": ("chunk", data[10:20], "application/octet-stream")},
    )
    res = client.post(
        "/api/analysis/videos/upload/complete",
        data={"upload_id": "tchu-b", "filename": "TCHU2.mp4"},
    )
    assert res.status_code == 422
    assert "chunk" in res.json()["detail"].lower()


def test_complete_without_chunks_is_rejected(client):
    res = client.post(
        "/api/analysis/videos/upload/complete",
        data={"upload_id": "tchu-none", "filename": "TCHU3.mp4"},
    )
    assert res.status_code == 422


def test_size_limit_still_enforced_on_chunks(client, monkeypatch):
    monkeypatch.setattr(settings, "MAX_UPLOAD_SIZE_MB", 0)
    res = client.post(
        "/api/analysis/videos/upload/chunk",
        data={"upload_id": "tchu-big", "part": "0"},
        files={"data": ("chunk", b"x" * 1024, "application/octet-stream")},
    )
    assert res.status_code == 422
    assert "upload limit" in res.json()["detail"].lower()
