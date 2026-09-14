"""
Tests: Event Ingestion Service
================================
Tests the full ingest_event() pipeline using an in-memory SQLite database.
Validates: camera validation, confidence range check, coordinate validation,
           plate normalization, VehicleEvent persistence.
"""
import sys
from pathlib import Path

for p in [str(Path(__file__).resolve().parents[1])]:
    if p not in sys.path:
        sys.path.insert(0, p)

import pytest
from datetime import datetime, timezone
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database.models import Base, Camera
from app.services.event_service import ingest_event


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def db_session():
    """In-memory SQLite session for isolation."""
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()

    # Seed a test camera
    cam = Camera(
        camera_id="CAM04",
        name="Test Camera",
        stream_url="https://test.local/cam04/index.m3u8",
        stream_type="hls",
        latitude=23.0338,
        longitude=72.585,
        status="OFFLINE",
    )
    session.add(cam)
    session.commit()

    yield session
    session.close()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_ingest_event_basic(db_session):
    """Happy path: event ingested, VehicleEvent created."""
    event, wl, alert = await ingest_event(
        db=db_session,
        camera_id="CAM04",
        vehicle_track_id=101,
        plate_raw="GJ 01 AB-1234",
        plate_confidence=0.95,
        vehicle_class="car",
        event_time=datetime.now(timezone.utc),
        latitude=23.0338,
        longitude=72.585,
        evidence_ref=None,
    )
    assert event.id is not None
    assert event.plate_number == "GJ01AB1234"
    assert event.plate_raw == "GJ 01 AB-1234"
    assert event.camera_id == "CAM04"
    assert event.watchlist_match is False  # no watchlist entry seeded
    assert wl is None
    assert alert is None


@pytest.mark.asyncio
async def test_ingest_event_invalid_camera(db_session):
    """Invalid camera_id should raise ValueError."""
    with pytest.raises(ValueError, match="not found in registry"):
        await ingest_event(
            db=db_session,
            camera_id="CAM_NOTEXIST",
            vehicle_track_id=None,
            plate_raw="GJ01XX1234",
            plate_confidence=0.9,
            vehicle_class="car",
            event_time=None,
            latitude=None,
            longitude=None,
            evidence_ref=None,
        )


@pytest.mark.asyncio
async def test_ingest_event_invalid_confidence_high(db_session):
    """plate_confidence > 1.0 should raise ValueError."""
    with pytest.raises(ValueError, match="plate_confidence"):
        await ingest_event(
            db=db_session,
            camera_id="CAM04",
            vehicle_track_id=None,
            plate_raw="GJ01AB1234",
            plate_confidence=1.5,
            vehicle_class="car",
            event_time=None,
            latitude=None,
            longitude=None,
            evidence_ref=None,
        )


@pytest.mark.asyncio
async def test_ingest_event_invalid_confidence_negative(db_session):
    """plate_confidence < 0.0 should raise ValueError."""
    with pytest.raises(ValueError, match="plate_confidence"):
        await ingest_event(
            db=db_session,
            camera_id="CAM04",
            vehicle_track_id=None,
            plate_raw="GJ01AB1234",
            plate_confidence=-0.1,
            vehicle_class="car",
            event_time=None,
            latitude=None,
            longitude=None,
            evidence_ref=None,
        )


@pytest.mark.asyncio
async def test_ingest_event_invalid_latitude(db_session):
    """Latitude out of range should raise ValueError."""
    with pytest.raises(ValueError, match="latitude"):
        await ingest_event(
            db=db_session,
            camera_id="CAM04",
            vehicle_track_id=None,
            plate_raw="GJ01AB1234",
            plate_confidence=0.9,
            vehicle_class="car",
            event_time=None,
            latitude=95.0,
            longitude=72.5,
            evidence_ref=None,
        )


@pytest.mark.asyncio
async def test_ingest_event_no_plate(db_session):
    """Event with no plate (None) should be persisted with plate_number=None."""
    event, wl, alert = await ingest_event(
        db=db_session,
        camera_id="CAM04",
        vehicle_track_id=999,
        plate_raw=None,
        plate_confidence=None,
        vehicle_class="motorcycle",
        event_time=None,
        latitude=23.0338,
        longitude=72.585,
        evidence_ref=None,
    )
    assert event.plate_number is None
    assert event.plate_raw is None
    assert event.watchlist_match is False


# ---------------------------------------------------------------------------
# Coordinate fallback (GIS consistency)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_ingest_without_coordinates_uses_camera_registry_position(db_session):
    """A sighting with no GPS must land on the camera that saw it.

    CV clients legitimately omit coordinates (the detector reports pixels, not
    geography). Storing NULL pushed the point off the map; storing a generic
    city centre put it in the wrong place. The registry is authoritative.
    """
    event, _, _ = await ingest_event(
        db=db_session,
        camera_id="CAM04",
        vehicle_track_id=7,
        plate_raw="GJ 01 AB 1234",
        plate_confidence=0.93,
        vehicle_class="car",
        event_time=None,
        latitude=None,
        longitude=None,
        evidence_ref=None,
    )

    assert event.latitude == 23.0338
    assert event.longitude == 72.585


@pytest.mark.asyncio
async def test_ingest_keeps_reported_coordinates_when_present(db_session):
    """An explicit coordinate from the CV pipeline must not be overwritten."""
    event, _, _ = await ingest_event(
        db=db_session,
        camera_id="CAM04",
        vehicle_track_id=8,
        plate_raw="GJ01AB1234",
        plate_confidence=0.91,
        vehicle_class="car",
        event_time=None,
        latitude=23.1000,
        longitude=72.6000,
        evidence_ref=None,
    )

    assert event.latitude == 23.1000
    assert event.longitude == 72.6000
