"""Evidence hash chain — verification that can actually fail.

Regression coverage for the Evidence Vault rewrite:

* every sighting is sealed at capture (``POST /api/events``) with a stored
  SHA-256 hash + ``previous_hash``;
* ``GET /api/reports/evidence/{id}/verify`` recomputes the hash from the sealed
  snapshot *and* the live row, so a modified sighting, a modified record and a
  broken chain are each detected (the old endpoint recomputed a hash from the
  current row and answered VALID unconditionally);
* the BSA certificate advertises the routes this backend really serves and
  carries the sealed hash, not a second unrelated one.
"""
import sys
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

backend_root = Path(__file__).resolve().parents[1]
if str(backend_root) not in sys.path:
    sys.path.insert(0, str(backend_root))

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database.database import get_db
from app.database.models import Base, Camera, EvidenceRecord, VehicleEvent
from app.services.evidence_vault import GENESIS, EvidenceStatus, evidence_vault

HEX64 = set("0123456789abcdef")


@pytest.fixture(scope="module")
def vault_env():
    """Isolated SQLite DB + TestClient (no camera hardware, no real DB)."""
    db_file = Path("test_evidence_vault.db").resolve()
    db_file.unlink(missing_ok=True)

    engine = create_engine(
        f"sqlite:///{db_file}",
        connect_args={"check_same_thread": False, "timeout": 15},
    )
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    def override_get_db():
        db = Session()
        try:
            yield db
        finally:
            db.close()

    from app.main import app

    app.dependency_overrides[get_db] = override_get_db

    @asynccontextmanager
    async def noop_lifespan(_app):
        yield

    original_lifespan = app.router.lifespan_context
    app.router.lifespan_context = noop_lifespan

    db = Session()
    db.add(
        Camera(
            camera_id="CAM04",
            name="North Gate Junction",
            location="Paldi Circle",
            stream_url="https://cctv.corp8.cloud/cam04/index.m3u8",
            stream_type="hls",
            latitude=23.0338,
            longitude=72.5850,
            status="ONLINE",
        )
    )
    db.commit()
    db.close()

    with TestClient(app, raise_server_exceptions=True) as client:
        yield client, Session, app

    app.router.lifespan_context = original_lifespan
    app.dependency_overrides.clear()
    engine.dispose()
    db_file.unlink(missing_ok=True)


def _ingest(client, plate: str, vehicle_id: int) -> dict:
    """Create one sighting through the real ingestion endpoint."""
    resp = client.post(
        "/api/events",
        json={
            "camera_id": "cam04",
            "vehicle_id": vehicle_id,
            "plate_raw": plate,
            "plate_confidence": 0.93,
            "event_time": datetime.now(timezone.utc).isoformat(),
            "latitude": 23.0301,
            "longitude": 72.5801,
            "vehicle_class": "car",
            "evidence_ref": f"ev/cam04/{vehicle_id}.jpg",
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


# --------------------------------------------------------------------------- #
# Sealing at capture
# --------------------------------------------------------------------------- #
def test_capture_seals_the_sighting(vault_env):
    client, Session, _app = vault_env
    created = _ingest(client, "GJ09ZZ4321", 901)
    event_id = created["event"]["id"]

    db = Session()
    try:
        rec = db.query(EvidenceRecord).filter(EvidenceRecord.event_id == event_id).first()
        assert rec is not None, "ingestion did not seal the sighting"
        assert rec.seal_source == "CAPTURE"
        assert rec.camera_id == "CAM04"
        assert len(rec.hash) == 64 and set(rec.hash) <= HEX64
        assert rec.payload_json  # canonical snapshot stored alongside the hash
        payload = rec.payload()
        assert payload["plate_number"] == "GJ09ZZ4321"
        assert payload["event_id"] == event_id
    finally:
        db.close()

    verdict = client.get(f"/api/reports/evidence/{event_id}/verify")
    assert verdict.status_code == 200, verdict.text
    body = verdict.json()
    assert body["status"] == EvidenceStatus.VALID
    assert body["tampered"] is False
    assert body["court_admissible"] is True
    assert body["checks"] == {
        "record_integrity": True,
        "evidence_integrity": True,
        "chain_integrity": True,
    }
    assert body["evidence_hash"] == body["recomputed_hash"]


def test_first_link_points_at_genesis(vault_env):
    client, Session, _app = vault_env
    db = Session()
    try:
        first = db.query(EvidenceRecord).order_by(EvidenceRecord.chain_index.asc()).first()
        assert first is not None
        assert first.chain_index == 0
        assert first.previous_hash is None
    finally:
        db.close()

    created = _ingest(client, "GJ09ZZ4322", 902)
    body = client.get(f"/api/reports/evidence/{created['event']['id']}/verify").json()
    # Every later link carries its predecessor's hash (GENESIS only for link 0).
    assert body["previous_hash"] != GENESIS or body["chain_index"] == 0
    assert len(body["previous_hash"]) == 64


def test_sealing_is_idempotent(vault_env):
    client, Session, _app = vault_env
    created = _ingest(client, "GJ09ZZ4323", 903)
    event_id = created["event"]["id"]

    db = Session()
    try:
        before = db.query(EvidenceRecord).filter(EvidenceRecord.event_id == event_id).count()
        event = db.query(VehicleEvent).filter(VehicleEvent.id == event_id).first()
        again = evidence_vault.seal(db, event, source="CAPTURE")
        assert again is not None
        after = db.query(EvidenceRecord).filter(EvidenceRecord.event_id == event_id).count()
        assert before == after == 1
    finally:
        db.close()


# --------------------------------------------------------------------------- #
# Tamper detection
# --------------------------------------------------------------------------- #
def test_modified_evidence_is_detected(vault_env):
    """Editing the sighting after sealing must be reported, field by field."""
    client, Session, _app = vault_env
    created = _ingest(client, "GJ09ZZ4324", 904)
    event_id = created["event"]["id"]

    db = Session()
    try:
        event = db.query(VehicleEvent).filter(VehicleEvent.id == event_id).first()
        event.plate_number = "GJ09ZZ9999"      # doctored read
        event.latitude = 21.1702               # doctored GPS fix
        db.commit()
    finally:
        db.close()

    try:
        body = client.get(f"/api/reports/evidence/{event_id}/verify").json()
        assert body["status"] == EvidenceStatus.TAMPERED
        assert body["tampered"] is True
        assert "EVIDENCE_MODIFIED" in body["findings"]
        assert body["checks"]["evidence_integrity"] is False
        changed = {f["field"] for f in body["modified_fields"]}
        assert {"plate_number", "latitude"} <= changed
        assert body["court_admissible"] is False
        assert body["evidence_hash"] != body["recomputed_hash"]
    finally:
        # Restore even if an assertion fails, so later tests see a clean chain.
        db = Session()
        try:
            event = db.query(VehicleEvent).filter(VehicleEvent.id == event_id).first()
            event.plate_number = "GJ09ZZ4324"
            event.latitude = 23.0301
            db.commit()
        finally:
            db.close()

    assert (
        client.get(f"/api/reports/evidence/{event_id}/verify").json()["status"]
        == EvidenceStatus.VALID
    )


def test_modified_record_hash_is_detected(vault_env):
    """Rewriting the stored hash breaks record integrity."""
    client, Session, _app = vault_env
    created = _ingest(client, "GJ09ZZ4325", 905)
    event_id = created["event"]["id"]

    db = Session()
    try:
        rec = db.query(EvidenceRecord).filter(EvidenceRecord.event_id == event_id).first()
        original_hash = rec.hash
        rec.hash = "0" * 64
        db.commit()
    finally:
        db.close()

    try:
        body = client.get(f"/api/reports/evidence/{event_id}/verify").json()
        assert body["status"] == EvidenceStatus.TAMPERED
        assert "RECORD_HASH_MISMATCH" in body["findings"]
        assert body["checks"]["record_integrity"] is False
        assert body["court_admissible"] is False
    finally:
        db = Session()
        try:
            rec = db.query(EvidenceRecord).filter(EvidenceRecord.event_id == event_id).first()
            rec.hash = original_hash
            db.commit()
        finally:
            db.close()
    assert (
        client.get(f"/api/reports/evidence/{event_id}/verify").json()["status"]
        == EvidenceStatus.VALID
    )


def test_broken_chain_link_is_detected(vault_env):
    """Re-pointing previous_hash at another link breaks the chain."""
    client, Session, _app = vault_env
    first = _ingest(client, "GJ09ZZ4326", 906)["event"]["id"]
    second = _ingest(client, "GJ09ZZ4327", 907)["event"]["id"]

    db = Session()
    try:
        rec = db.query(EvidenceRecord).filter(EvidenceRecord.event_id == second).first()
        original_previous = rec.previous_hash
        first_rec = db.query(EvidenceRecord).filter(EvidenceRecord.event_id == first).first()
        assert original_previous == first_rec.hash  # correctly linked before the attack
        rec.previous_hash = "f" * 64
        db.commit()
    finally:
        db.close()

    try:
        body = client.get(f"/api/reports/evidence/{second}/verify").json()
        assert "CHAIN_BROKEN" in body["findings"]
        assert body["status"] == EvidenceStatus.CHAIN_BROKEN
        assert body["chain_integrity"] == "BROKEN"
        assert body["checks"]["chain_integrity"] is False
        assert body["court_admissible"] is False
        # The record's own hash covers previous_hash, so a re-pointed link is
        # also reported as a record mismatch — both findings must be visible.
        assert "RECORD_HASH_MISMATCH" in body["findings"]

        chain = client.get("/api/reports/evidence/chain/verify").json()
        assert chain["valid"] is False
        assert chain["broken_links"]
    finally:
        db = Session()
        try:
            rec = db.query(EvidenceRecord).filter(EvidenceRecord.event_id == second).first()
            rec.previous_hash = original_previous
            db.commit()
        finally:
            db.close()

    assert client.get("/api/reports/evidence/chain/verify").json()["valid"] is True


def test_chain_verify_recomputes_every_link(vault_env):
    client, Session, _app = vault_env
    _ingest(client, "GJ09ZZ4328", 908)
    _ingest(client, "GJ09ZZ4329", 909)

    chain = client.get("/api/reports/evidence/chain/verify")
    assert chain.status_code == 200, chain.text
    body = chain.json()
    assert body["valid"] is True
    assert body["status"] == EvidenceStatus.VALID
    assert body["tampered_indices"] == []
    assert body["broken_links"] == []

    db = Session()
    try:
        assert body["total_records"] == db.query(EvidenceRecord).count()
        assert body["total_records"] >= 2
    finally:
        db.close()


# --------------------------------------------------------------------------- #
# Legacy rows + error paths
# --------------------------------------------------------------------------- #
def test_legacy_event_is_backfilled_and_labelled(vault_env):
    """A row written before the vault existed is sealed on first verification."""
    client, Session, _app = vault_env
    db = Session()
    try:
        event = VehicleEvent(
            camera_id="CAM04",
            plate_number="GJ09ZZ4330",
            plate_raw="GJ 09 ZZ 4330",
            plate_confidence=0.91,
            vehicle_class="car",
            event_time=datetime.now(timezone.utc),
            latitude=23.0338,
            longitude=72.5850,
            evidence_ref="ev/cam04/legacy.jpg",
            watchlist_match=False,
        )
        db.add(event)
        db.commit()
        event_id = event.id
        assert db.query(EvidenceRecord).filter(EvidenceRecord.event_id == event_id).count() == 0
    finally:
        db.close()

    body = client.get(f"/api/reports/evidence/{event_id}/verify").json()
    assert body["status"] == EvidenceStatus.VALID
    assert body["seal_source"] == "BACKFILL"
    assert body["sealed_at"]

    # Sealed once — a second verification does not append another link.
    db = Session()
    try:
        assert db.query(EvidenceRecord).filter(EvidenceRecord.event_id == event_id).count() == 1
    finally:
        db.close()


def test_verify_unknown_event_is_404(vault_env):
    client, _Session, _app = vault_env
    resp = client.get("/api/reports/evidence/99999999/verify")
    assert resp.status_code == 404
    assert "99999999" in resp.json()["detail"]


# --------------------------------------------------------------------------- #
# BSA 2023 certificate (route correctness + real verdict)
# --------------------------------------------------------------------------- #
def test_certificate_advertises_routes_that_exist(vault_env):
    """The certificate used to print /api/evidence/{id}/verify — not a route."""
    client, _Session, app = vault_env
    created = _ingest(client, "GJ09ZZ4331", 911)
    event_id = created["event"]["id"]

    cert = client.get(f"/api/reports/evidence/{event_id}/certificate")
    assert cert.status_code == 200, cert.text
    body = cert.json()

    paths = set(app.openapi()["paths"])
    verify_url = body["verification"]["verification_url"]
    certificate_url = body["verification"]["certificate_url"]
    assert verify_url == f"/api/reports/evidence/{event_id}/verify"
    assert certificate_url == f"/api/reports/evidence/{event_id}/certificate"
    assert "/api/reports/evidence/{event_id}/verify" in paths
    assert "/api/reports/evidence/{event_id}/certificate" in paths
    # And the advertised URL actually answers.
    assert client.get(verify_url).status_code == 200


def test_certificate_carries_the_sealed_hash_and_real_verdict(vault_env):
    client, Session, _app = vault_env
    created = _ingest(client, "GJ09ZZ4332", 912)
    event_id = created["event"]["id"]

    cert = client.get(f"/api/reports/evidence/{event_id}/certificate").json()
    verdict = client.get(f"/api/reports/evidence/{event_id}/verify").json()

    # One hash for the whole system: the certificate no longer invents a second,
    # unverifiable digest of its own field selection.
    assert cert["evidence_details"]["evidence_hash_sha256"] == verdict["evidence_hash"]
    assert cert["evidence_details"]["previous_hash"] == verdict["previous_hash"]
    assert cert["verification"]["status"] == EvidenceStatus.VALID
    assert cert["compliance"]["court_admissible"] is True
    assert cert["compliance"]["tamper_proof"] is True
    assert cert["technical_details"]["original_untampered"] is True

    # Tamper, and the very same endpoint must stop asserting admissibility.
    db = Session()
    try:
        event = db.query(VehicleEvent).filter(VehicleEvent.id == event_id).first()
        event.plate_number = "GJ09ZZ0000"
        db.commit()
    finally:
        db.close()

    tampered_cert = client.get(f"/api/reports/evidence/{event_id}/certificate").json()
    assert tampered_cert["verification"]["status"] == EvidenceStatus.TAMPERED
    assert tampered_cert["compliance"]["court_admissible"] is False
    assert tampered_cert["compliance"]["tamper_proof"] is False
    assert tampered_cert["technical_details"]["original_untampered"] is False
    assert "EVIDENCE_MODIFIED" in tampered_cert["verification"]["findings"]
