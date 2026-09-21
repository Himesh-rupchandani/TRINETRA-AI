"""
Alerts API — list, create, acknowledge, and resolve surveillance alerts.
"""
import sys
from pathlib import Path
from typing import Optional
from datetime import datetime, timezone

# Allow running this file directly as a script
if __name__ == "__main__" and not __package__:
    project_root = Path(__file__).resolve().parents[3]
    backend_root = Path(__file__).resolve().parents[2]
    for p in [str(project_root), str(backend_root)]:
        if str(p) not in sys.path:
            sys.path.insert(0, str(p))
    __package__ = "backend.app.api"

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session

from ..database.database import get_db
from ..database.models import Alert
from ..database.schemas import (
    AlertResponse,
    AlertCreate,
    AlertUpdate,
    AlertAckRequest,
    PaginatedResponse,
)

router = APIRouter(prefix="/alerts", tags=["Alerts"])

# Older bundles posted the resolution note inside `operator` ("resolve: <note>").
_LEGACY_NOTE_PREFIX = "resolve:"


def _split_legacy_operator(operator: Optional[str]) -> tuple:
    """Return ``(resolved_by, note_or_None)`` for an operator string.

    A plain operator is passed through; the legacy ``"resolve: <note>"`` form is
    split so the note never ends up stored as the resolving officer's identity.
    """
    raw = (operator or "").strip()
    if raw.lower().startswith(_LEGACY_NOTE_PREFIX):
        note = raw[len(_LEGACY_NOTE_PREFIX):].strip()
        return "system", (note or None)
    return (raw or "system"), None


@router.get("", response_model=PaginatedResponse[AlertResponse])
def list_alerts(
    camera_id: Optional[str] = Query(None),
    severity: Optional[str] = Query(None),
    # The query parameter stays `?status=` on the wire (alias); the Python name
    # is `status_filter` so it no longer shadows the imported `fastapi.status`
    # module inside this function.
    status_filter: Optional[str] = Query(None, alias="status"),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """List system and surveillance alerts with optional severity and status filtering."""
    query = db.query(Alert)
    if camera_id:
        query = query.filter(Alert.camera_id == camera_id)
    if severity:
        query = query.filter(Alert.severity == severity.upper())
    if status_filter:
        query = query.filter(Alert.status == status_filter.upper())

    total = query.count()
    items = query.order_by(Alert.timestamp.desc()).offset((page - 1) * size).limit(size).all()
    pages = (total + size - 1) // size if total > 0 else 1

    return PaginatedResponse[AlertResponse](
        items=items,
        total=total,
        page=page,
        size=size,
        pages=pages,
    )


@router.post("", response_model=AlertResponse, status_code=status.HTTP_201_CREATED)
def create_alert(payload: AlertCreate, db: Session = Depends(get_db)):
    """Create a new surveillance alert."""
    alert = Alert(
        camera_id=payload.camera_id,
        track_id=payload.track_id,
        plate_number=payload.plate_number,
        alert_type=payload.alert_type,
        severity=payload.severity.upper(),
        message=payload.message,
        status=payload.status.upper(),
    )
    db.add(alert)
    db.commit()
    db.refresh(alert)
    return alert


@router.put("/{alert_id}/status", response_model=AlertResponse)
def update_alert_status(alert_id: int, payload: AlertUpdate, db: Session = Depends(get_db)):
    """Update alert status (e.g. ACKNOWLEDGED, RESOLVED, DISMISSED)."""
    alert = db.query(Alert).filter(Alert.id == alert_id).first()
    if not alert:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Alert #{alert_id} not found.",
        )

    if payload.status is not None:
        alert.status = payload.status.upper()
    if payload.severity is not None:
        alert.severity = payload.severity.upper()

    db.commit()
    db.refresh(alert)
    return alert


@router.post("/{alert_id}/ack", response_model=AlertResponse, summary="Acknowledge alert")
@router.post("/{alert_id}/acknowledge", response_model=AlertResponse, summary="Acknowledge alert (alias)")
@router.patch("/{alert_id}/ack", response_model=AlertResponse, summary="Acknowledge alert (PATCH)")
@router.patch("/{alert_id}/acknowledge", response_model=AlertResponse, summary="Acknowledge alert (PATCH alias)")
def acknowledge_alert(
    alert_id: int,
    payload: AlertAckRequest = AlertAckRequest(),
    db: Session = Depends(get_db),
):
    """Transition an alert from NEW → ACKNOWLEDGED, recording operator and timestamp."""
    alert = db.query(Alert).filter(Alert.id == alert_id).first()
    if not alert:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Alert #{alert_id} not found.",
        )
    if alert.status not in ("NEW",):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Alert #{alert_id} is already in status '{alert.status}'.",
        )

    alert.status = "ACKNOWLEDGED"
    alert.acknowledged_at = datetime.now(timezone.utc)
    alert.acknowledged_by, _ = _split_legacy_operator(payload.operator)

    db.commit()
    db.refresh(alert)
    return alert


@router.post("/{alert_id}/resolve", response_model=AlertResponse, summary="Resolve alert")
@router.patch("/{alert_id}/resolve", response_model=AlertResponse, summary="Resolve alert (PATCH)")
def resolve_alert(
    alert_id: int,
    payload: AlertAckRequest = AlertAckRequest(),
    db: Session = Depends(get_db),
):
    """Transition an alert to RESOLVED, recording operator, note and timestamp.

    The operator identity and the free-text resolution note are stored
    separately: ``resolved_by`` must stay a person/badge, never a composite
    ``"resolve: <note>"`` string. Older clients that packed the note into
    ``operator`` are still understood (the prefix is split off).
    """
    alert = db.query(Alert).filter(Alert.id == alert_id).first()
    if not alert:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Alert #{alert_id} not found.",
        )
    if alert.status == "RESOLVED":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Alert #{alert_id} is already RESOLVED.",
        )

    operator, legacy_note = _split_legacy_operator(payload.operator)
    note = payload.note if payload.note is not None else legacy_note

    alert.status = "RESOLVED"
    alert.resolved_at = datetime.now(timezone.utc)
    alert.resolved_by = operator
    if note:
        alert.resolution_note = note

    db.commit()
    db.refresh(alert)
    return alert


@router.post("/trigger", summary="Manually trigger the next scheduled 60s alert tick")
async def trigger_alert():
    """Immediately triggers the next unique vehicle alert from the 60s rotation."""
    from ..core.config import settings
    if not (settings.DEMO_MODE and settings.DEMO_ALERTS_ENABLED):
        raise HTTPException(409, "Synthetic alerts are disabled. Live alerts come from real detections.")
    from ..services.alert_scheduler import run_alert_tick
    res = await run_alert_tick()
    return {"status": "success", "alert": res}

