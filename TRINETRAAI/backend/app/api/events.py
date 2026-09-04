"""
Events API — POST /api/v1/events (AI ingestion)
            GET  /api/v1/events (paginated query)
"""
from typing import Optional
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session

from ..core.logging_config import logger
from ..database.database import get_db
from ..database.models import VehicleEvent
from ..database.schemas import (
    VehicleEventCreate,
    VehicleEventResponse,
    VehicleEventIngestResponse,
    PaginatedResponse,
)
from ..services.event_service import ingest_event

router = APIRouter(prefix="/events", tags=["Events"])


@router.get(
    "/{event_id}",
    response_model=VehicleEventResponse,
    summary="Get vehicle event by ID",
    description="Single AI event lookup — used by the frontend evidence / detection-detail panels.",
)
def get_event(event_id: int, db: Session = Depends(get_db)):
    """Return one vehicle event by its integer ID."""
    event = db.query(VehicleEvent).filter(VehicleEvent.id == event_id).first()
    if not event:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Event #{event_id} not found.",
        )
    return event


@router.post(
    "",
    response_model=VehicleEventIngestResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Ingest AI vehicle event",
    description=(
        "Primary ingestion endpoint consumed by AI/CV engines. "
        "Normalizes plate, matches watchlist, deduplicates alerts, and broadcasts via WebSocket."
    ),
)
async def create_event(payload: VehicleEventCreate, db: Session = Depends(get_db)):
    """Ingest a vehicle detection event from an AI/CV system."""
    try:
        event, watchlist_entry, alert = await ingest_event(
            db=db,
            camera_id=payload.camera_id,
            vehicle_track_id=payload.vehicle_id,
            plate_raw=payload.plate_raw,
            plate_confidence=payload.plate_confidence,
            vehicle_class=payload.vehicle_class,
            event_time=payload.event_time,
            latitude=payload.latitude,
            longitude=payload.longitude,
            evidence_ref=payload.evidence_ref,
            plate=payload.plate,
            timestamp_pts=payload.timestamp_pts,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))

    msg_parts = [f"Event #{event.id} ingested."]
    if watchlist_entry:
        msg_parts.append(f"WATCHLIST HIT: {watchlist_entry.category}.")
    if alert:
        msg_parts.append(f"Alert #{alert.id} created.")

    return VehicleEventIngestResponse(
        event=VehicleEventResponse.model_validate(event),
        plate_normalized=event.plate_number or "",
        watchlist_match=event.watchlist_match,
        alert_created=alert is not None,
        alert_id=alert.id if alert else None,
        message=" ".join(msg_parts),
    )


@router.get(
    "",
    response_model=PaginatedResponse[VehicleEventResponse],
    summary="List vehicle events",
    description="Paginated, filterable query of all ingested vehicle events.",
)
def list_events(
    camera_id: Optional[str] = Query(None, description="Filter by camera ID"),
    plate_number: Optional[str] = Query(None, description="Filter by normalized plate (exact match)"),
    watchlist_match: Optional[bool] = Query(None, description="Filter by watchlist match status"),
    from_time: Optional[datetime] = Query(None, description="Filter events from this time (ISO8601)"),
    to_time: Optional[datetime] = Query(None, description="Filter events up to this time (ISO8601)"),
    page: int = Query(1, ge=1),
    size: int = Query(25, ge=1, le=100),
    db: Session = Depends(get_db),
):
    query = db.query(VehicleEvent)
    if camera_id:
        query = query.filter(VehicleEvent.camera_id == camera_id)
    if plate_number:
        query = query.filter(VehicleEvent.plate_number == plate_number.strip().upper())
    if watchlist_match is not None:
        query = query.filter(VehicleEvent.watchlist_match == watchlist_match)
    if from_time:
        query = query.filter(VehicleEvent.event_time >= from_time)
    if to_time:
        query = query.filter(VehicleEvent.event_time <= to_time)

    total = query.count()
    items = query.order_by(VehicleEvent.event_time.desc()).offset((page - 1) * size).limit(size).all()
    pages = (total + size - 1) // size if total > 0 else 1

    return PaginatedResponse[VehicleEventResponse](
        items=items,
        total=total,
        page=page,
        size=size,
        pages=pages,
    )
