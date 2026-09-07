"""Live-mode bootstrap safeguards.

A real deployment must never be populated with example camera/watchlist rows:
operators otherwise see a small offline demo registry and can mistake it for an
authorized official camera list.
"""
import sys
from pathlib import Path

backend_root = Path(__file__).resolve().parents[1]
if str(backend_root) not in sys.path:
    sys.path.insert(0, str(backend_root))

import httpx
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.camera.live_source import sync_live_camera
from app.core.config import settings
from app.database import database
from app.database.models import Base, Camera, Watchlist
from app.services import sentinel_catalogue_service as catalogue


def _isolated_database(monkeypatch):
    """Point the database module at an ephemeral SQLite database."""
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    session_factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    monkeypatch.setattr(database, "engine", engine)
    monkeypatch.setattr(database, "SessionLocal", session_factory)
    return engine, session_factory


def test_live_mode_does_not_seed_example_camera_or_watchlist_records(monkeypatch):
    engine, session_factory = _isolated_database(monkeypatch)
    monkeypatch.setattr(settings, "DEMO_MODE", False)

    try:
        database.init_db()
        db = session_factory()
        try:
            assert db.query(Camera).count() == 0
            assert db.query(Watchlist).count() == 0
        finally:
            db.close()
    finally:
        engine.dispose()


def test_empty_optional_live_slot_is_not_added_in_real_mode(monkeypatch):
    engine, session_factory = _isolated_database(monkeypatch)
    monkeypatch.setattr(settings, "DEMO_MODE", False)
    monkeypatch.setattr(settings, "LIVE_CAMERA_ID", "CAMLIVE")
    monkeypatch.setattr(settings, "LIVE_CAMERA_STREAM_URL", "")
    monkeypatch.setattr(settings, "LIVE_CAMERA_STATUS", "")

    try:
        Base.metadata.create_all(bind=engine)
        db = session_factory()
        try:
            sync_live_camera(db)
            assert db.query(Camera).count() == 0
        finally:
            db.close()
    finally:
        engine.dispose()


def test_catalogue_request_attaches_auth_only_to_the_approved_host(monkeypatch):
    """A caller-controlled URL must never receive the configured credentials."""
    monkeypatch.setattr(settings, "SENTINEL_EMAIL", "operator@example.test")
    monkeypatch.setattr(settings, "SENTINEL_PASSWORD", "test-only-password")
    monkeypatch.setattr(settings, "SENTINEL_HLS_BASE_URL", "https://cctv.corp8.cloud")
    monkeypatch.setattr(settings, "SENTINEL_RTSP_HOST", "103.250.160.189")

    approved = catalogue._catalogue_auth("https://cctv.corp8.cloud/cameras.json")
    assert isinstance(approved, httpx.BasicAuth)
    assert catalogue._catalogue_auth("https://untrusted.example/cameras.json") is None


def test_catalogue_sync_uses_server_side_auth_without_returning_it(monkeypatch):
    engine, session_factory = _isolated_database(monkeypatch)
    monkeypatch.setattr(settings, "SENTINEL_EMAIL", "operator@example.test")
    monkeypatch.setattr(settings, "SENTINEL_PASSWORD", "test-only-password")
    monkeypatch.setattr(settings, "SENTINEL_HLS_BASE_URL", "https://cctv.corp8.cloud")
    monkeypatch.setattr(settings, "SENTINEL_RTSP_HOST", "103.250.160.189")
    monkeypatch.setattr(catalogue.camera_manager, "add_camera", lambda **_kwargs: None)

    captured = {}

    class StubResponse:
        status_code = 200

        @staticmethod
        def json():
            return [{"id": "cam-auth", "name": "Authorised Camera", "status": "online"}]

    class StubClient:
        def __init__(self, **kwargs):
            captured["client_kwargs"] = kwargs

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def get(self, url, auth=None):
            captured["url"] = url
            captured["auth"] = auth
            return StubResponse()

    monkeypatch.setattr(catalogue.httpx, "Client", StubClient)

    try:
        Base.metadata.create_all(bind=engine)
        db = session_factory()
        try:
            result = catalogue.sync_sentinel_catalogue(db)
            assert result["status"] == "success"
            assert result["synced_count"] == 1
            assert isinstance(captured["auth"], httpx.BasicAuth)
            assert captured["client_kwargs"]["follow_redirects"] is False
            assert "test-only-password" not in str(result)
        finally:
            db.close()
    finally:
        engine.dispose()
