"""
Tests: Vehicle Sighting Deduplication (spec §25)
================================================
A retried POST /api/events for the same physical sighting must NOT create a
second VehicleEvent — that would inflate the cross-camera trace and the GIS
route. A genuinely different camera must always produce its own sighting.
"""
import sys
from pathlib import Path

for p in [str(Path(__file__).resolve().parents[1])]:
    if p not in sys.path:
        sys.path.insert(0, p)

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database.models import Base, Camera, VehicleEvent
from app.services.event_service import ingest_event


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine)()

    for cid, lat, lon in [("CAM04", 23.0338, 72.585), ("CAM08", 23.0295, 72.5054)]:
        session.add(
            Camera(
                camera_id=cid,
                name=f"{cid} Junction",
                stream_url=f"https://test.local/{cid.lower()}/index.m3u8",
                stream_type="hls",
                latitude=lat,
                longitude=lon,
                status="ONLINE",
            )
        )
    session.commit()
    yield session
    session.close()


async def _ingest(db, camera_id="CAM04", track=101, when=None, plate="GJ 01 AB-1234"):
    return await ingest_event(
        db=db,
        camera_id=camera_id,
        vehicle_track_id=track,
        plate_raw=plate,
        plate_confidence=0.93,
        vehicle_class="car",
        event_time=when or datetime.now(timezone.utc),
        latitude=23.0338,
        longitude=72.585,
        evidence_ref=None,
    )


@pytest.mark.asyncio
async def test_retried_sighting_does_not_duplicate(db_session):
    """Identical re-POST (CV retry) returns the original event, creates no new row."""
    when = datetime.now(timezone.utc)
    first, _, _ = await _ingest(db_session, when=when)
    second, _, _ = await _ingest(db_session, when=when)

    assert second.id == first.id, "a retry must resolve to the same sighting"
    assert db_session.query(VehicleEvent).count() == 1


@pytest.mark.asyncio
async def test_different_camera_is_always_a_new_sighting(db_session):
    """Cross-camera sightings are the whole point of the trace — never suppressed."""
    when = datetime.now(timezone.utc)
    await _ingest(db_session, camera_id="CAM04", when=when)
    await _ingest(db_session, camera_id="CAM08", when=when)

    assert db_session.query(VehicleEvent).count() == 2


@pytest.mark.asyncio
async def test_same_camera_outside_window_is_a_new_sighting(db_session):
    """The vehicle genuinely came back past the camera later."""
    when = datetime.now(timezone.utc)
    await _ingest(db_session, when=when)
    await _ingest(db_session, when=when + timedelta(minutes=10))

    assert db_session.query(VehicleEvent).count() == 2


@pytest.mark.asyncio
async def test_different_track_is_a_new_sighting(db_session):
    """Two distinct vehicles at the same camera must both be recorded."""
    when = datetime.now(timezone.utc)
    await _ingest(db_session, track=101, when=when)
    await _ingest(db_session, track=202, when=when, plate="GJ 05 XY-4321")

    assert db_session.query(VehicleEvent).count() == 2
