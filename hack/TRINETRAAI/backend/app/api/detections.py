import sys
from pathlib import Path
from typing import Optional

# Allow running this file directly as a script
if __name__ == "__main__" and not __package__:
    project_root = Path(__file__).resolve().parents[3]
    backend_root = Path(__file__).resolve().parents[2]
    for p in [str(project_root), str(backend_root)]:
        if str(p) not in sys.path:
            sys.path.insert(0, str(p))
    __package__ = "backend.app.api"

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..database.database import get_db
from ..database.models import Detection, VehicleObservation
from ..database.schemas import (
    DetectionResponse,
    VehicleObservationResponse,
    PaginatedResponse,
)

router = APIRouter(prefix="/detections", tags=["Detections"])


@router.get("", response_model=PaginatedResponse[DetectionResponse])
def list_detections(
    camera_id: Optional[str] = Query(None),
    object_type: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    size: int = Query(25, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """List object detections (vehicles, persons) with pagination and filters."""
    query = db.query(Detection)
    if camera_id:
        query = query.filter(Detection.camera_id == camera_id)
    if object_type:
        query = query.filter(Detection.object_type == object_type.lower())

    total = query.count()
    items = query.order_by(Detection.timestamp.desc()).offset((page - 1) * size).limit(size).all()
    pages = (total + size - 1) // size if total > 0 else 1

    return PaginatedResponse[DetectionResponse](
        items=items,
        total=total,
        page=page,
        size=size,
        pages=pages,
    )


@router.get("/vehicles", response_model=PaginatedResponse[VehicleObservationResponse])
def list_vehicle_observations(
    camera_id: Optional[str] = Query(None),
    plate_number: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    size: int = Query(25, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """List vehicle observations with recognized license plates (ANPR/OCR)."""
    query = db.query(VehicleObservation)
    if camera_id:
        query = query.filter(VehicleObservation.camera_id == camera_id)
    if plate_number:
        query = query.filter(VehicleObservation.plate_number.ilike(f"%{plate_number}%"))

    total = query.count()
    items = query.order_by(VehicleObservation.timestamp.desc()).offset((page - 1) * size).limit(size).all()
    pages = (total + size - 1) // size if total > 0 else 1

    return PaginatedResponse[VehicleObservationResponse](
        items=items,
        total=total,
        page=page,
        size=size,
        pages=pages,
    )
