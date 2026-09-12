"""Regression tests for the speed engine (item 10) and AI insights (item 11).

Item 10 — ``app/services/speed_engine.py``:
  * optical velocity divided by ``n / fps`` instead of ``(n - 1) / fps``,
    inflating every single-camera speed estimate;
  * ``calibration_factor`` was accepted and silently ignored;
  * GPS segments were skipped with a truthiness test, so a legitimate 0.0
    latitude/longitude (equator / prime meridian) disappeared from the analysis;
  * the ``evidence_chain`` was guarded by ``if 'hashlib' in locals() or True``
    with an in-loop import — dead code that could never take the other branch.

Item 11 — ``/api/stats/insights`` + ``/api/stats/traffic-patterns``:
  * the "24h analytics" were computed from the newest 500 rows regardless of age
    and then labelled ``time_range_hours: 24``;
  * crowd density reported a raw event count as ``vehicles_per_hour``;
  * an empty window must return zeros — never invented numbers.
"""
import sys
from contextlib import asynccontextmanager
from datetime import timedelta
from pathlib import Path

backend_root = Path(__file__).resolve().parents[1]
if str(backend_root) not in sys.path:
    sys.path.insert(0, str(backend_root))

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database.database import get_db
from app.database.models import Alert, Base, Camera, VehicleEvent
from app.services.speed_engine import (
    SpeedPoint,
    calculate_speed_analysis,
    estimate_optical_velocity,
    haversine_km,
)
from app.utils.timestamps import utc_now


# --------------------------------------------------------------------------- #
# Item 10 — speed engine
# --------------------------------------------------------------------------- #
def _bbox_history(samples, dx=20.0, height=60):
    """A track whose centroid moves ``dx`` pixels per sample."""
    return [
        {"bbox": [100 + i * dx, 100, 100 + i * dx + 120, 100 + height], "timestamp": i}
        for i in range(samples)
    ]


def test_optical_velocity_spans_n_minus_one_intervals():
    """3 samples at 10 fps cover 2 intervals = 0.2 s, not 3/10 = 0.3 s."""
    result = estimate_optical_velocity(_bbox_history(3, dx=20.0), fps=10.0)
    assert result["time_observed_sec"] == pytest.approx(0.2, abs=0.05)

    # Recompute independently: 2 gaps of 20 px, 60 px bbox height, 4.5 m car length.
    expected_m = (40.0 / 60.0) * 4.5
    expected_kmh = (expected_m / 0.2) * 3.6
    assert result["estimated_speed_kmh"] == pytest.approx(expected_kmh, abs=0.2)
    assert result["real_distance_m"] == pytest.approx(expected_m, abs=0.1)


def test_optical_velocity_two_samples_use_one_interval():
    """A two-sample track spans a single interval: 1/25 s, not 2/25 s."""
    # Small per-sample motion so the result stays below the 150 km/h clamp.
    two = estimate_optical_velocity(_bbox_history(2, dx=5.0), fps=25.0)
    expected_kmh = ((5.0 / 60.0) * 4.5 / (1 / 25.0)) * 3.6
    assert two["estimated_speed_kmh"] == pytest.approx(expected_kmh, abs=0.2)
    assert two["fps"] == 25.0
    # The reported field is rounded to one decimal, so 0.04 s reads as 0.0;
    # the unrounded interval is what the speed above already pins down.
    assert two["time_observed_sec"] == pytest.approx(0.04, abs=0.05)


def test_calibration_factor_actually_scales_the_result():
    """It used to be a parameter the function accepted and ignored."""
    base = estimate_optical_velocity(_bbox_history(6, dx=8.0), fps=10.0, calibration_factor=1.0)
    doubled = estimate_optical_velocity(_bbox_history(6, dx=8.0), fps=10.0, calibration_factor=2.0)
    assert base["calibration_factor"] == 1.0
    assert doubled["calibration_factor"] == 2.0
    assert doubled["real_distance_m"] == pytest.approx(base["real_distance_m"] * 2, abs=0.2)
    assert doubled["estimated_speed_kmh"] == pytest.approx(base["estimated_speed_kmh"] * 2, abs=0.5)


def test_optical_velocity_survives_invalid_fps_and_short_tracks():
    zero_fps = estimate_optical_velocity(_bbox_history(4), fps=0.0)
    assert zero_fps["estimated_speed_kmh"] == 0
    assert zero_fps["reason"] == "invalid_fps"

    negative = estimate_optical_velocity(_bbox_history(4), fps=-5.0)
    assert negative["estimated_speed_kmh"] == 0

    single = estimate_optical_velocity(_bbox_history(1))
    assert single["estimated_speed_kmh"] == 0
    assert estimate_optical_velocity([])["estimated_speed_kmh"] == 0

    tiny = estimate_optical_velocity(
        [{"bbox": [0, 0, 4, 4], "timestamp": 0}, {"bbox": [2, 0, 6, 4], "timestamp": 1}], fps=25.0
    )
    assert tiny["reason"] == "bbox_too_small"


def _point(camera_id, lat, lon, minutes, event_id):
    return SpeedPoint(
        camera_id=camera_id,
        camera_name=f"{camera_id} junction",
        latitude=lat,
        longitude=lon,
        timestamp=utc_now() + timedelta(minutes=minutes),
        event_id=event_id,
        plate="GJ01SP1234",
        confidence=0.9,
    )


def test_zero_coordinates_are_not_skipped():
    """0.0 latitude/longitude is a real place, not a missing GPS fix."""
    points = [
        _point("CAM01", 0.0, 0.0, 0, 1),
        _point("CAM02", 0.0, 0.10, 10, 2),   # ~11.1 km east along the equator
    ]
    analysis = calculate_speed_analysis(points, speed_limit_kmh=80.0, critical_limit_kmh=120.0)
    assert analysis["total_points"] == 2
    assert len(analysis["segments"]) == 1, "the equator segment was dropped"
    segment = analysis["segments"][0]
    assert segment["distance_km"] == pytest.approx(haversine_km(0.0, 0.0, 0.0, 0.10), abs=0.1)
    assert segment["avg_speed_kmh"] > 0


def test_missing_coordinates_are_still_skipped():
    points = [
        _point("CAM01", None, None, 0, 1),
        _point("CAM02", 23.03, 72.58, 10, 2),
    ]
    analysis = calculate_speed_analysis(points, 80.0, 120.0)
    assert analysis["segments"] == []


def test_evidence_chain_is_always_built():
    """The `if 'hashlib' in locals() or True` guard could never be false."""
    points = [_point(f"CAM{i:02d}", 23.0 + i * 0.05, 72.5, i * 10, 100 + i) for i in range(4)]
    analysis = calculate_speed_analysis(points, 80.0, 120.0)
    chain = analysis["evidence_chain"]
    assert isinstance(chain, list)
    assert len(chain) == len(points)
    for link in chain:
        assert len(link["hash"]) == 16
        assert int(link["hash"], 16) >= 0            # real hex digest
        assert link["timestamp"].endswith("Z")        # UTC on the wire
        assert link["camera_id"]
    assert analysis["analysis_timestamp"].endswith("Z")


def test_speed_analysis_endpoint_counts_zero_coordinate_sightings(client_with_events):
    """The API applied the same truthiness test when building SpeedPoints."""
    c, _session = client_with_events
    resp = c.get("/api/vehicles/GJ01EQ1234/speed-analysis")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    # With >= 2 GPS-tagged sightings the endpoint returns the analysis itself.
    assert body["plate"] == "GJ01EQ1234"
    assert body["total_points"] == 2, "a sighting at 0.0/0.0 was treated as untagged"
    assert len(body["segments"]) == 1
    assert len(body["evidence_chain"]) == 2

    # 11.1 km in 10 minutes = 66.7 km/h: under the 80 km/h default limit...
    assert body["segments"][0]["avg_speed_kmh"] == pytest.approx(66.7, abs=0.5)
    assert body["violation_count"] == 0
    assert body["judge_notes"]["can_issue_challan"] is False

    # ...and a violation when the caller sets a 40 km/h limit.
    strict = c.get("/api/vehicles/GJ01EQ1234/speed-analysis", params={"speed_limit": 40}).json()
    assert strict["violation_count"] == 1
    assert strict["segments"][0]["is_violation"] is True
    assert strict["judge_notes"]["can_issue_challan"] is True
    assert strict["court_admissible"] is True


# --------------------------------------------------------------------------- #
# Item 11 — insights window
# --------------------------------------------------------------------------- #
@pytest.fixture(scope="module")
def client_with_events():
    """Isolated DB with a known event/alert population across two windows."""
    db_file = Path("test_speed_insights.db").resolve()
    db_file.unlink(missing_ok=True)
    engine = create_engine(f"sqlite:///{db_file}", connect_args={"check_same_thread": False})
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
    now = utc_now()
    db.add(
        Camera(
            camera_id="CAM01", name="Equator Post", location="Null Island",
            latitude=0.0, longitude=0.0, status="ONLINE", stream_type="hls",
            stream_url="https://cctv.corp8.cloud/cam01/index.m3u8",
        )
    )
    db.add(
        Camera(
            camera_id="CAM02", name="Meridian Post", location="Null Island East",
            latitude=0.0, longitude=0.10, status="ONLINE", stream_type="hls",
            stream_url="https://cctv.corp8.cloud/cam02/index.m3u8",
        )
    )
    # Two GPS-tagged sightings on the equator/prime meridian, 10 minutes apart.
    for i, (cam, minutes) in enumerate([("CAM01", 0), ("CAM02", 10)]):
        db.add(
            VehicleEvent(
                camera_id=cam,
                plate_number="GJ01EQ1234",
                plate_raw="GJ 01 EQ 1234",
                plate_confidence=0.94,
                vehicle_class="car",
                event_time=now + timedelta(minutes=minutes),
                latitude=0.0,
                longitude=0.0 if i == 0 else 0.10,
                watchlist_match=False,
                created_at=now,
            )
        )
    db.commit()

    with TestClient(app, raise_server_exceptions=True) as c:
        yield c, Session

    app.router.lifespan_context = original_lifespan
    app.dependency_overrides.clear()
    engine.dispose()
    db_file.unlink(missing_ok=True)


@pytest.fixture()
def insights_client():
    """Empty, isolated DB — every insight must come out as a real zero."""
    db_file = Path("test_insights_empty.db").resolve()
    db_file.unlink(missing_ok=True)
    engine = create_engine(f"sqlite:///{db_file}", connect_args={"check_same_thread": False})
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

    with TestClient(app, raise_server_exceptions=True) as c:
        yield c, Session

    app.router.lifespan_context = original_lifespan
    app.dependency_overrides.clear()
    engine.dispose()
    db_file.unlink(missing_ok=True)


def test_insights_on_an_empty_database_return_zeros(insights_client):
    c, _session = insights_client
    body = c.get("/api/stats/insights").json()

    assert body["traffic_analysis"]["total_events"] == 0
    assert body["traffic_analysis"]["peak_hours"] == []
    assert body["traffic_analysis"]["camera_hotspots"] == []
    assert body["crowd_density"]["by_camera"] == []
    assert body["crowd_density"]["average_vph"] == 0
    assert body["threat_level"]["counts"] == {"critical": 0, "high": 0, "total_active": 0}
    assert body["window"]["events_total"] == 0
    # No invented accuracy/telemetry figures.
    assert "%" not in body["predictive"]["model_accuracy"]
    assert body["system_health"]["processing"]["events_in_window"] == "0"


def test_insights_window_is_applied_to_created_at(insights_client):
    c, Session = insights_client
    now = utc_now()
    db = Session()
    try:
        db.add(Camera(camera_id="CAM09", name="Window probe", latitude=23.0, longitude=72.5,
                      status="ONLINE", stream_url="https://x/cam09.m3u8", stream_type="hls"))
        # one inside 24h, one 48h old (inside 7d, outside 24h)
        for plate, age_hours in [("GJ09RC1234", 1), ("GJ09OLD5678", 48)]:
            db.add(
                VehicleEvent(
                    camera_id="CAM09", plate_number=plate, vehicle_class="car",
                    event_time=now - timedelta(hours=age_hours),
                    latitude=23.0, longitude=72.5, watchlist_match=False,
                    created_at=now - timedelta(hours=age_hours),
                )
            )
        db.add(Alert(camera_id="CAM09", alert_type="WATCHLIST_MATCH", severity="CRITICAL",
                     message="recent", status="NEW", timestamp=now - timedelta(hours=2)))
        db.add(Alert(camera_id="CAM09", alert_type="WATCHLIST_MATCH", severity="CRITICAL",
                     message="old", status="NEW", timestamp=now - timedelta(hours=72)))
        db.commit()
    finally:
        db.close()

    day = c.get("/api/stats/insights", params={"period": "24h"}).json()
    assert day["window"]["hours"] == 24
    assert day["window"]["events_total"] == 1, "the 48h-old row leaked into the 24h window"
    assert day["traffic_analysis"]["total_events"] == 1
    assert day["traffic_analysis"]["time_range_hours"] == 24
    assert day["threat_level"]["counts"]["critical"] == 1

    week = c.get("/api/stats/insights", params={"period": "7d"}).json()
    assert week["window"]["hours"] == 24 * 7
    assert week["window"]["events_total"] == 2
    assert week["traffic_analysis"]["time_range_hours"] == 24 * 7
    assert week["threat_level"]["counts"]["critical"] == 2

    hour = c.get("/api/stats/insights", params={"period": "1h"}).json()
    assert hour["window"]["events_total"] == 0
    assert hour["traffic_analysis"]["total_events"] == 0


def test_insights_period_parsing_defaults_to_24h():
    from app.api.insights import period_hours

    assert period_hours("24h") == 24
    assert period_hours("1h") == 1
    assert period_hours("6h") == 6
    assert period_hours("7d") == 168
    assert period_hours("30d") == 720
    assert period_hours(None) == 24
    assert period_hours("nonsense") == 24, "unknown periods fall back, never crash"


def test_crowd_density_is_a_real_rate(insights_client):
    """vehicles_per_hour must divide by the window, not echo the raw count."""
    c, Session = insights_client
    now = utc_now()
    db = Session()
    try:
        db.add(Camera(camera_id="CAM10", name="Density probe", latitude=23.1, longitude=72.6,
                      status="ONLINE", stream_url="https://x/cam10.m3u8", stream_type="hls"))
        for i in range(48):
            db.add(
                VehicleEvent(
                    camera_id="CAM10", plate_number=f"GJ10DN{1000 + i}", vehicle_class="car",
                    event_time=now - timedelta(minutes=i), latitude=23.1, longitude=72.6,
                    watchlist_match=False, created_at=now - timedelta(minutes=i),
                )
            )
        db.commit()
    finally:
        db.close()

    body = c.get("/api/stats/insights", params={"period": "24h"}).json()
    entry = body["crowd_density"]["by_camera"][0]
    assert entry["camera_id"] == "CAM10"
    assert entry["vehicles_per_hour"] == pytest.approx(48 / 24, abs=0.1)
    assert body["crowd_density"]["average_vph"] == pytest.approx(2.0, abs=0.1)
    assert body["system_health"]["processing"]["events_in_window"] == "48"


def test_traffic_patterns_endpoint_reports_the_requested_window(insights_client):
    c, Session = insights_client
    now = utc_now()
    db = Session()
    try:
        db.add(Camera(camera_id="CAM11", name="Pattern probe", latitude=23.2, longitude=72.7,
                      status="ONLINE", stream_url="https://x/cam11.m3u8", stream_type="hls"))
        db.add(VehicleEvent(camera_id="CAM11", plate_number="GJ11PT1234", vehicle_class="car",
                            event_time=now - timedelta(hours=30), latitude=23.2, longitude=72.7,
                            watchlist_match=False, created_at=now - timedelta(hours=30)))
        db.commit()
    finally:
        db.close()

    day = c.get("/api/stats/traffic-patterns", params={"period": "24h"}).json()
    assert day["total_events"] == 0
    assert day["time_range_hours"] == 24

    week = c.get("/api/stats/traffic-patterns", params={"period": "7d"}).json()
    assert week["total_events"] == 1
    assert week["time_range_hours"] == 168


def test_insights_threat_counts_match_the_dashboard_contract(insights_client):
    """AIInsightsDashboard reads threat_level.counts — it must exist."""
    c, _session = insights_client
    body = c.get("/api/stats/insights").json()
    counts = body["threat_level"]["counts"]
    assert set(counts) == {"critical", "high", "total_active"}
    assert body["generated_at"].endswith("Z")
    assert body["window"]["since"].endswith("Z")
