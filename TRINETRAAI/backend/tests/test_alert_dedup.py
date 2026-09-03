"""
Tests: Alert Deduplication
============================
Validates the cooldown deduplication window:
- First watchlist event → Alert created
- Second watchlist event within cooldown window → Alert suppressed (deduplicated)
- Event after cooldown window expired → Alert created again
"""
import sys
from pathlib import Path

for p in [str(Path(__file__).resolve().parents[1])]:
    if p not in sys.path:
        sys.path.insert(0, p)

import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import patch
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database.models import Base, Camera, Watchlist, VehicleEvent, Alert
from app.services.event_service import (
    ingest_event,
    create_watchlist_alert,
    _is_duplicate_alert,
    match_watchlist,
)


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()

    session.add(Camera(
        camera_id="CAM04", name="Test Cam",
        stream_url="https://test.local/cam04/index.m3u8", stream_type="hls",
        latitude=23.0338, longitude=72.585, status="OFFLINE",
    ))
    session.add(Watchlist(
        plate_number="GJ01AB1234",
        category="stolen vehicle",
        description="FIR #4812",
        active=True,
    ))
    session.commit()
    yield session
    session.close()


class TestAlertDeduplication:
    @pytest.mark.asyncio
    async def test_first_event_creates_alert(self, db_session):
        """First watchlist event within session should produce an alert."""
        event, wl, alert = await ingest_event(
            db=db_session,
            camera_id="CAM04",
            vehicle_track_id=101,
            plate_raw="GJ 01 AB-1234",
            plate_confidence=0.97,
            vehicle_class="car",
            event_time=datetime.now(timezone.utc),
            latitude=23.0338,
            longitude=72.585,
            evidence_ref=None,
        )
        assert event.watchlist_match is True
        assert alert is not None
        assert alert.alert_type == "WATCHLIST_MATCH"
        assert alert.severity == "CRITICAL"
        assert alert.status == "NEW"

    @pytest.mark.asyncio
    async def test_duplicate_alert_suppressed_within_cooldown(self, db_session):
        """Second event for same plate+camera within cooldown → alert suppressed."""
        # First event
        await ingest_event(
            db=db_session,
            camera_id="CAM04",
            vehicle_track_id=101,
            plate_raw="GJ 01 AB-1234",
            plate_confidence=0.97,
            vehicle_class="car",
            event_time=datetime.now(timezone.utc),
            latitude=23.0338,
            longitude=72.585,
            evidence_ref=None,
        )
        # Second event immediately after (within cooldown)
        _, _, alert2 = await ingest_event(
            db=db_session,
            camera_id="CAM04",
            vehicle_track_id=102,
            plate_raw="GJ01AB1234",
            plate_confidence=0.91,
            vehicle_class="car",
            event_time=datetime.now(timezone.utc),
            latitude=23.0338,
            longitude=72.585,
            evidence_ref=None,
        )
        assert alert2 is None, "Duplicate alert should have been suppressed within cooldown"

    def test_is_duplicate_true_within_window(self, db_session):
        """_is_duplicate_alert returns True when existing alert is within cooldown."""
        # Plant an alert 30 seconds ago
        alert = Alert(
            camera_id="CAM04",
            plate_number="GJ01AB1234",
            alert_type="WATCHLIST_MATCH",
            severity="CRITICAL",
            message="Test alert",
            status="NEW",
            timestamp=datetime.now(timezone.utc) - timedelta(seconds=30),
        )
        db_session.add(alert)
        db_session.commit()

        result = _is_duplicate_alert(db_session, "GJ01AB1234", "CAM04", cooldown_seconds=180)
        assert result is True

    def test_is_duplicate_false_outside_window(self, db_session):
        """_is_duplicate_alert returns False when existing alert is outside cooldown."""
        # Plant an alert 300 seconds ago (outside 180s cooldown)
        alert = Alert(
            camera_id="CAM04",
            plate_number="GJ01AB1234",
            alert_type="WATCHLIST_MATCH",
            severity="CRITICAL",
            message="Old alert",
            status="NEW",
            timestamp=datetime.now(timezone.utc) - timedelta(seconds=300),
        )
        db_session.add(alert)
        db_session.commit()

        result = _is_duplicate_alert(db_session, "GJ01AB1234", "CAM04", cooldown_seconds=180)
        assert result is False

    def test_is_duplicate_false_different_camera(self, db_session):
        """_is_duplicate_alert returns False for same plate but different camera."""
        alert = Alert(
            camera_id="CAM08",  # different camera
            plate_number="GJ01AB1234",
            alert_type="WATCHLIST_MATCH",
            severity="CRITICAL",
            message="Alert on different cam",
            status="NEW",
            timestamp=datetime.now(timezone.utc) - timedelta(seconds=10),
        )
        db_session.add(alert)
        db_session.commit()

        result = _is_duplicate_alert(db_session, "GJ01AB1234", "CAM04", cooldown_seconds=180)
        assert result is False

    def test_alert_severity_stolen_is_critical(self, db_session):
        """Stolen vehicle category maps to CRITICAL severity."""
        event = VehicleEvent(
            camera_id="CAM04",
            plate_number="GJ01AB1234",
            watchlist_match=True,
            event_time=datetime.now(timezone.utc),
        )
        db_session.add(event)
        db_session.commit()

        wl = match_watchlist(db_session, "GJ01AB1234")
        alert = create_watchlist_alert(db_session, event, wl)
        assert alert is not None
        assert alert.severity == "CRITICAL"
