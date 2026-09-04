"""
Vehicles API — cross-camera vehicle investigation endpoints.

GET /api/v1/vehicles/{plate}/events  — full event history across all cameras
GET /api/v1/vehicles/{plate}/route   — ordered GIS coordinate route
"""
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session

from ..database.database import get_db
from ..database.models import Camera, VehicleEvent, Watchlist
from ..database.schemas import (
    VehicleEventResponse,
    VehicleProfileResponse,
    VehicleRouteResponse,
    WatchlistResponse,
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

    # Resolve registry metadata for the cameras in this route in ONE query
    # (no N+1) so a map point can show camera + location without another call.
    cam_ids = {ev.camera_id for ev in events}
    cams = {
        c.camera_id: c
        for c in db.query(Camera).filter(Camera.camera_id.in_(cam_ids)).all()
    } if cam_ids else {}

    route_points = []
    for idx, ev in enumerate(events):
        cam = cams.get(ev.camera_id)
        route_points.append(
            RoutePoint(
                sequence=idx + 1,
                camera_id=ev.camera_id,
                camera_name=cam.camera_id if cam else None,
                location=(cam.location or cam.name) if cam else None,
                event_time=ev.event_time,
                # Prefer the camera's registered position; fall back to the
                # coordinates reported with the event itself.
                latitude=ev.latitude if ev.latitude is not None else (cam.latitude if cam else None),
                longitude=ev.longitude if ev.longitude is not None else (cam.longitude if cam else None),
                confidence=ev.plate_confidence,
            )
        )

    return VehicleRouteResponse(
        plate_number=plate_norm,
        total_sightings=len(events),
        route=route_points,
    )


@router.get(
    "/{plate}",
    response_model=VehicleProfileResponse,
    summary="Vehicle investigation profile",
    description=(
        "Aggregated profile for one plate: sighting count, distinct cameras, "
        "first/last seen, watchlist state and the matched watchlist record."
    ),
)
def get_vehicle_profile(plate: str, db: Session = Depends(get_db)):
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

    wl = (
        db.query(Watchlist)
        .filter(Watchlist.plate_number == plate_norm, Watchlist.active == True)  # noqa: E712
        .first()
    )

    vehicle_classes = [e.vehicle_class for e in events if e.vehicle_class]

    return VehicleProfileResponse(
        plate_number=plate_norm,
        vehicle_class=vehicle_classes[-1] if vehicle_classes else None,
        total_sightings=len(events),
        cameras_touched=len({e.camera_id for e in events}),
        first_seen=events[0].event_time if events else None,
        last_seen=events[-1].event_time if events else None,
        watchlist_match=wl is not None or any(e.watchlist_match for e in events),
        watchlist=WatchlistResponse.model_validate(wl) if wl else None,
    )
