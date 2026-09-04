"""
Dashboard statistics
====================
Aggregate KPIs for the Command Center (spec Phase 9).

Every number here is computed from the database — nothing is fabricated —
so the dashboard shows the truth when running in LIVE mode.
"""
from datetime import timedelta

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..camera.manager import camera_manager
from ..database.database import get_db
from ..database.models import Alert, Camera, VehicleEvent
from ..utils.timestamps import utc_now

router = APIRouter(prefix="/stats", tags=["Stats"])


class DashboardKpis(BaseModel):
    totalCameras: int
    camerasOnline: int
    camerasDegraded: int
    camerasOffline: int
    activeAlerts: int
    vehicleDetections24h: int
    anprReads24h: int
    watchlistMatches24h: int


@router.get(
    "/kpis",
    response_model=DashboardKpis,
    summary="Command Center KPIs",
    description="Real aggregate counters for the dashboard. No synthetic values.",
)
def dashboard_kpis(db: Session = Depends(get_db)) -> DashboardKpis:
    cameras = db.query(Camera).all()

    # Live ingestion state wins over the persisted column, matching /api/cameras.
    statuses = []
    for cam in cameras:
        live = camera_manager.get_camera_status(cam.camera_id)
        statuses.append((live["status"] if live else (cam.status or "OFFLINE")).upper())

    since = utc_now() - timedelta(hours=24)
    recent = db.query(VehicleEvent).filter(VehicleEvent.event_time >= since)

    return DashboardKpis(
        totalCameras=len(cameras),
        camerasOnline=sum(1 for s in statuses if s == "ONLINE"),
        camerasDegraded=sum(1 for s in statuses if s in ("DEGRADED", "CONNECTING")),
        camerasOffline=sum(1 for s in statuses if s in ("OFFLINE", "ERROR")),
        activeAlerts=db.query(func.count(Alert.id))
        .filter(Alert.status != "RESOLVED")
        .scalar()
        or 0,
        vehicleDetections24h=recent.count(),
        anprReads24h=recent.filter(VehicleEvent.plate_number.isnot(None)).count(),
        watchlistMatches24h=recent.filter(VehicleEvent.watchlist_match.is_(True)).count(),
    )
