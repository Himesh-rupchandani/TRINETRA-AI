"""
Statistics API — real dashboard aggregates computed from the database.

GET /api/stats/kpis — Command Center KPI block (Phase 9).
Every number is derived from actual rows; nothing is estimated.
"""
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..camera.manager import camera_manager
from ..database.database import get_db
from ..database.models import Alert, Camera, VehicleEvent

router = APIRouter(prefix="/stats", tags=["Statistics"])


class KpisResponse(BaseModel):
    total_cameras: int
    cameras_online: int
    cameras_degraded: int
    cameras_offline: int
    active_alerts: int
    vehicle_detections_24h: int
    anpr_reads_24h: int
    watchlist_matches_24h: int


@router.get("/kpis", response_model=KpisResponse, summary="Dashboard KPIs")
def get_kpis(db: Session = Depends(get_db)):
    """Camera fleet status, active alerts and 24h detection counters."""
    since = datetime.now(timezone.utc) - timedelta(hours=24)

    online = degraded = offline = 0
    for cam in db.query(Camera).all():
        stream_status = camera_manager.get_camera_status(cam.camera_id)
        current = stream_status["status"] if stream_status else (cam.status or "OFFLINE")
        if current == "ONLINE":
            online += 1
        elif current == "DEGRADED":
            degraded += 1
        else:
            offline += 1

    detections = db.query(VehicleEvent).filter(VehicleEvent.event_time >= since).count()
    anpr_reads = (
        db.query(VehicleEvent)
        .filter(VehicleEvent.event_time >= since)
        .filter(VehicleEvent.plate_number.isnot(None))
        .filter(VehicleEvent.plate_number != "")
        .count()
    )
    watchlist_matches = (
        db.query(VehicleEvent)
        .filter(VehicleEvent.event_time >= since)
        .filter(VehicleEvent.watchlist_match.is_(True))
        .count()
    )
    active_alerts = (
        db.query(Alert)
        .filter(Alert.status.notin_(["RESOLVED", "DISMISSED"]))
        .count()
    )

    return KpisResponse(
        total_cameras=online + degraded + offline,
        cameras_online=online,
        cameras_degraded=degraded,
        cameras_offline=offline,
        active_alerts=active_alerts,
        vehicle_detections_24h=detections,
        anpr_reads_24h=anpr_reads,
        watchlist_matches_24h=watchlist_matches,
    )
