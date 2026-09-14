"""
Tests: Watchlist Matching Service
===================================
Validates watchlist matching during event ingestion:
- Plate in watchlist → watchlist_match=True
- Plate not in watchlist → watchlist_match=False
- Inactive watchlist entry → not matched
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

from app.database.models import Base, Camera, Watchlist
from app.services.event_service import ingest_event, match_watchlist


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
        description="Test stolen car",
        active=True,
    ))
    session.add(Watchlist(
        plate_number="MH02CD5678",
        category="wanted vehicle",
        description="Inactive entry",
        active=False,   # inactive — should NOT match
    ))
    session.commit()
    yield session
    session.close()


class TestWatchlistMatch:
    def test_match_active_entry(self, db_session):
        """Normalized plate in active watchlist → matched."""
        result = match_watchlist(db_session, "GJ01AB1234")
        assert result is not None
        assert result.category == "stolen vehicle"

    def test_no_match_unknown_plate(self, db_session):
        """Unknown plate → None."""
        result = match_watchlist(db_session, "GJ01ZZ9999")
        assert result is None

    def test_no_match_inactive_entry(self, db_session):
        """Inactive watchlist entry → not returned."""
        result = match_watchlist(db_session, "MH02CD5678")
        assert result is None

    def test_no_match_empty_plate(self, db_session):
        """Empty plate string → None."""
        result = match_watchlist(db_session, "")
        assert result is None

    def test_no_match_none_plate(self, db_session):
        """None plate → None."""
        result = match_watchlist(db_session, None)
        assert result is None

    @pytest.mark.asyncio
    async def test_ingest_sets_watchlist_match_flag(self, db_session):
        """Ingesting a watchlist plate sets event.watchlist_match=True."""
        event, wl, _ = await ingest_event(
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
        assert wl is not None
        assert wl.plate_number == "GJ01AB1234"

    @pytest.mark.asyncio
    async def test_ingest_no_flag_for_non_watchlist_plate(self, db_session):
        """Ingesting a non-watchlist plate leaves event.watchlist_match=False."""
        event, wl, _ = await ingest_event(
            db=db_session,
            camera_id="CAM04",
            vehicle_track_id=102,
            plate_raw="GJ 01 ZZ 9999",
            plate_confidence=0.82,
            vehicle_class="car",
            event_time=datetime.now(timezone.utc),
            latitude=23.0338,
            longitude=72.585,
            evidence_ref=None,
        )
        assert event.watchlist_match is False
        assert wl is None
