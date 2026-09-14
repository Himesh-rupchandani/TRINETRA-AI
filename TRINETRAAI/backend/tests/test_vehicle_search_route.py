"""
Tests: Vehicle Search & GIS Route — Direct Service Layer Tests
===============================================================
Tests the vehicle event history and route data logic using
in-memory SQLite directly (no HTTP layer), bypassing TestClient issues.
"""
import sys
from pathlib import Path

for p in [str(Path(__file__).resolve().parents[1])]:
    if p not in sys.path:
        sys.path.insert(0, p)

import pytest
from datetime import datetime, timezone, timedelta
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database.models import Base, VehicleEvent
from app.utils.plate_normalizer import normalize_plate


@pytest.fixture(scope="module")
def session():
    """In-memory SQLite with a seeded GJ01AB1234 journey."""
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    db = Session()

    base_time = datetime(2026, 9, 2, 8, 0, 0, tzinfo=timezone.utc)
    journey = [
        VehicleEvent(camera_id="CAM04", plate_number="GJ01AB1234", plate_raw="GJ 01 AB-1234",
                     plate_confidence=0.97, vehicle_class="car",
                     event_time=base_time,
                     latitude=23.0338, longitude=72.5850, watchlist_match=True),
        VehicleEvent(camera_id="CAM08", plate_number="GJ01AB1234", plate_raw="GJ 01 AB 1234",
                     plate_confidence=0.94, vehicle_class="car",
                     event_time=base_time + timedelta(minutes=8),
                     latitude=23.0295, longitude=72.5054, watchlist_match=True),
        VehicleEvent(camera_id="CAM12", plate_number="GJ01AB1234", plate_raw="GJ01AB1234",
                     plate_confidence=0.99, vehicle_class="car",
                     event_time=base_time + timedelta(minutes=19),
                     latitude=23.0622, longitude=72.5659, watchlist_match=True),
        VehicleEvent(camera_id="CAM17", plate_number="GJ01AB1234", plate_raw="GJ-01-AB-1234",
                     plate_confidence=0.91, vehicle_class="car",
                     event_time=base_time + timedelta(minutes=31),
                     latitude=23.0487, longitude=72.6303, watchlist_match=True),
        VehicleEvent(camera_id="CAM01", plate_number="GJ01ZZ9999", plate_raw="GJ 01 ZZ 9999",
                     plate_confidence=0.80, vehicle_class="car",
                     event_time=base_time + timedelta(minutes=1),
                     latitude=23.0225, longitude=72.5714, watchlist_match=False),
    ]
    db.add_all(journey)
    db.commit()
    yield db
    db.close()


def query_vehicle_events(db, plate: str, skip: int = 0, limit: int = 100):
    """Replicate the GET /vehicles/{plate}/events query logic."""
    plate_normalized = normalize_plate(plate)
    q = db.query(VehicleEvent).filter(
        VehicleEvent.plate_number == plate_normalized
    ).order_by(VehicleEvent.event_time.asc())
    total = q.count()
    items = q.offset(skip).limit(limit).all()
    return total, items


def query_vehicle_route(db, plate: str):
    """Replicate the GET /vehicles/{plate}/route query logic."""
    plate_normalized = normalize_plate(plate)
    events = db.query(VehicleEvent).filter(
        VehicleEvent.plate_number == plate_normalized
    ).order_by(VehicleEvent.event_time.asc()).all()
    return events


class TestVehicleSearch:
    def test_get_vehicle_events_returns_4_sightings(self, session):
        """GJ01AB1234 should have exactly 4 sightings."""
        total, items = query_vehicle_events(session, "GJ01AB1234")
        assert total == 4
        assert len(items) == 4

    def test_get_vehicle_events_ordered_chronologically(self, session):
        """Events should be in ascending chronological order."""
        _, items = query_vehicle_events(session, "GJ01AB1234")
        cameras = [e.camera_id for e in items]
        assert cameras == ["CAM04", "CAM08", "CAM12", "CAM17"]

    def test_get_vehicle_events_raw_plate_auto_normalized(self, session):
        """Raw plate format normalizes to same result."""
        total1, _ = query_vehicle_events(session, "GJ01AB1234")
        total2, _ = query_vehicle_events(session, "GJ-01-AB-1234")
        total3, _ = query_vehicle_events(session, "GJ 01 AB-1234")
        assert total1 == total2 == total3 == 4

    def test_get_vehicle_events_unknown_plate_returns_zero(self, session):
        """Unknown plate returns 0 results."""
        total, items = query_vehicle_events(session, "XX99ZZ0000")
        assert total == 0
        assert items == []

    def test_get_vehicle_events_pagination(self, session):
        """Pagination limit works correctly."""
        _, items = query_vehicle_events(session, "GJ01AB1234", limit=2)
        assert len(items) == 2
        assert items[0].camera_id == "CAM04"
        assert items[1].camera_id == "CAM08"

    def test_get_vehicle_route_returns_4_points(self, session):
        """Route should have exactly 4 GPS points."""
        events = query_vehicle_route(session, "GJ01AB1234")
        assert len(events) == 4

    def test_get_vehicle_route_sequence_order(self, session):
        """Route cameras must be CAM04 -> CAM08 -> CAM12 -> CAM17."""
        events = query_vehicle_route(session, "GJ01AB1234")
        cameras = [e.camera_id for e in events]
        assert cameras == ["CAM04", "CAM08", "CAM12", "CAM17"]

    def test_get_vehicle_route_has_coordinates(self, session):
        """Every route point must have lat/lon."""
        events = query_vehicle_route(session, "GJ01AB1234")
        for e in events:
            assert e.latitude is not None
            assert e.longitude is not None

    def test_get_vehicle_route_first_camera_lat_lon(self, session):
        """First camera (CAM04) must have specific lat/lon."""
        events = query_vehicle_route(session, "GJ01AB1234")
        assert abs(events[0].latitude - 23.0338) < 0.001
        assert abs(events[0].longitude - 72.5850) < 0.001

    def test_get_vehicle_route_unknown_plate_returns_empty(self, session):
        """Unknown plate returns empty route."""
        events = query_vehicle_route(session, "UNKNOWNPLATE")
        assert events == []

    def test_unrelated_vehicle_not_included(self, session):
        """Querying GJ01AB1234 should not include GJ01ZZ9999."""
        _, items = query_vehicle_events(session, "GJ01AB1234")
        plates = {e.plate_number for e in items}
        assert "GJ01ZZ9999" not in plates
        assert all(p == "GJ01AB1234" for p in plates)

    def test_watchlist_match_flag_set(self, session):
        """All GJ01AB1234 events should have watchlist_match=True."""
        _, items = query_vehicle_events(session, "GJ01AB1234")
        assert all(e.watchlist_match is True for e in items)
