"""
Stats API — dashboard KPI aggregates.

GET /api/stats/kpis — the numbers the Command Center header shows.

Everything here is computed from the database rather than returned from a
fixture, so in LIVE mode a KPI is never a fabricated value.
"""
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..database.database import get_db
from ..database.models import Alert, Camera, VehicleEvent
from ..database.schemas import KpisResponse

router = APIRouter(prefix="/stats", tags=["Stats"])


@router.get("/kpis", response_model=KpisResponse, summary="Command Center KPIs")
def get_kpis(db: Session = Depends(get_db)):
    now = datetime.now(timezone.utc)
    window = now - timedelta(hours=24)

    total_cameras = db.query(func.count(Camera.id)).scalar() or 0
    online = db.query(func.count(Camera.id)).filter(Camera.status == "ONLINE").scalar() or 0
    degraded = db.query(func.count(Camera.id)).filter(Camera.status == "DEGRADED").scalar() or 0
    offline = max(total_cameras - online - degraded, 0)

    active_alerts = (
        db.query(func.count(Alert.id))
        .filter(Alert.status.in_(["NEW", "ACKNOWLEDGED"]))
        .scalar()
        or 0
    )

    detections_24h = (
        db.query(func.count(VehicleEvent.id))
        .filter(VehicleEvent.event_time >= window)
        .scalar()
        or 0
    )
    # An ANPR read is a sighting that actually produced a plate.
    anpr_24h = (
        db.query(func.count(VehicleEvent.id))
        .filter(
            VehicleEvent.event_time >= window,
            VehicleEvent.plate_number.isnot(None),
            VehicleEvent.plate_number != "",
        )
        .scalar()
        or 0
    )
    watchlist_24h = (
        db.query(func.count(VehicleEvent.id))
        .filter(VehicleEvent.event_time >= window, VehicleEvent.watchlist_match == True)  # noqa: E712
        .scalar()
        or 0
    )

    return KpisResponse(
        total_cameras=total_cameras,
        cameras_online=online,
        cameras_degraded=degraded,
        cameras_offline=offline,
        active_alerts=active_alerts,
        vehicle_detections_24h=detections_24h,
        anpr_reads_24h=anpr_24h,
        watchlist_matches_24h=watchlist_24h,
    )
