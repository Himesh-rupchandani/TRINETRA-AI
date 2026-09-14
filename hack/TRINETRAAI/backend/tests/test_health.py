"""
Tests: Health Endpoint
========================
Tests /health and /api/v1/health system diagnostic endpoint.
"""
import sys
from pathlib import Path

for p in [str(Path(__file__).resolve().parents[1])]:
    if p not in sys.path:
        sys.path.insert(0, p)

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database.models import Base
from app.database.database import get_db


@pytest.fixture(scope="module")
def client():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
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
    # Override lifespan with no-op to skip camera initialization
    @asynccontextmanager
    async def noop_lifespan(app):
        yield
    original_lifespan = app.router.lifespan_context
    app.router.lifespan_context = noop_lifespan

    with TestClient(app, raise_server_exceptions=True) as c:
        yield c

    app.router.lifespan_context = original_lifespan
    app.dependency_overrides.clear()


class TestHealthEndpoint:
    def test_health_returns_200(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200

    def test_health_schema_fields(self, client):
        data = client.get("/health").json()
        required_fields = [
            "status", "app_name", "version", "environment",
            "database_connected", "active_cameras", "total_cameras",
            "demo_mode", "timestamp",
        ]
        for field in required_fields:
            assert field in data, f"Missing field: {field}"

    def test_health_database_connected(self, client):
        data = client.get("/health").json()
        assert data["database_connected"] is True

    def test_health_status_healthy(self, client):
        data = client.get("/health").json()
        assert data["status"] == "healthy"

    def test_api_v1_health_returns_200(self, client):
        resp = client.get("/api/v1/health")
        assert resp.status_code == 200

    def test_health_version(self, client):
        data = client.get("/health").json()
        assert data["version"] == "1.0.0"

    def test_root_endpoint_contains_docs(self, client):
        data = client.get("/").json()
        assert "docs" in data
        assert data["docs"] == "/docs"

    def test_root_endpoint_contains_websocket(self, client):
        data = client.get("/").json()
        assert "websocket" in data
