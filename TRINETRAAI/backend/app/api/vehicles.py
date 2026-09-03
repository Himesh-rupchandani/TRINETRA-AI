"""
Vehicles API — cross-camera vehicle investigation endpoints.

GET /api/v1/vehicles/{plate}/events  — full event history across all cameras
GET /api/v1/vehicles/{plate}/route   — ordered GIS coordinate route
"""
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session

from ..database.database import get_db
from ..database.models import VehicleEvent
from ..database.schemas import (
    VehicleEventResponse,
    VehicleRouteResponse,
    RoutePoint,
    PaginatedResponse,
)
from ..utils.plate_normalizer import normalize_plate

router = APIRouter(prefix="/vehicles", tags=["Vehicles"])


@router.get(
    "/{plate}/events",
    response_model=PaginatedResponse[VehicleEventResponse],
    summary="Cross-camera vehicle event history",
    description=(
        "Returns all recorded sightings of a vehicle across all CCTV cameras, "
        "ordered chronologically. The plate is auto-normalized before lookup."
    ),
)
def get_vehicle_events(
    plate: str,
    page: int = Query(1, ge=1),
    size: int = Query(25, ge=1, le=100),
    db: Session = Depends(get_db),
):
    plate_norm = normalize_plate(plate)
    if not plate_norm:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid or empty plate number.",
        )

    query = (
        db.query(VehicleEvent)
        .filter(VehicleEvent.plate_number == plate_norm)
        .order_by(VehicleEvent.event_time.asc())
    )
    total = query.count()
    items = query.offset((page - 1) * size).limit(size).all()
    pages = (total + size - 1) // size if total > 0 else 1

    return PaginatedResponse[VehicleEventResponse](
        items=items,
        total=total,
        page=page,
        size=size,
        pages=pages,
    )


@router.get(
    "/{plate}/route",
    response_model=VehicleRouteResponse,
    summary="Vehicle GIS detection route",
    description=(
        "Returns the chronological list of GPS coordinates where this vehicle was detected "
        "across all cameras — suitable for map visualization of a vehicle's travel route."
    ),
)
def get_vehicle_route(plate: str, db: Session = Depends(get_db)):
    plate_norm = normalize_plate(plate)
    if not plate_norm:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid or empty plate number.",
        )

    events = (
        db.query(VehicleEvent)
        .filter(VehicleEvent.plate_number == plate_norm)
        .order_by(VehicleEvent.event_time.asc())
        .all()
    )

    route_points = [
        RoutePoint(
            sequence=idx + 1,
            camera_id=ev.camera_id,
            event_time=ev.event_time,
            latitude=ev.latitude,
            longitude=ev.longitude,
            confidence=ev.plate_confidence,
        )
        for idx, ev in enumerate(events)
    ]

    return VehicleRouteResponse(
        plate_number=plate_norm,
        total_sightings=len(events),
        route=route_points,
    )
