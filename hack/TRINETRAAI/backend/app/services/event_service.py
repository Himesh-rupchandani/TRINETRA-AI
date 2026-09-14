"""
Event Ingestion Service — Core pipeline:
  1. Validate camera exists in DB
  2. Validate coordinates and confidence
  3. Normalize plate via normalize_plate()
  4. Persist VehicleEvent record
  5. Run watchlist matcher
  6. If match: run alert deduplication, create Alert if outside cooldown window
  7. Broadcast to WebSocket clients
"""
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, Tuple

from sqlalchemy.orm import Session
from sqlalchemy import func

from ..core.config import settings
from ..database.models import Camera, VehicleEvent, Watchlist, Alert
from ..utils.plate_normalizer import normalize_plate
from ..utils.timestamps import iso_utc
from .evidence_vault import evidence_vault
from .ws_manager import ws_manager

logger = logging.getLogger("trinetra")

# ---------------------------------------------------------------------------
# Watchlist Matching
# ---------------------------------------------------------------------------

def match_watchlist(db: Session, plate_number: str) -> Optional[Watchlist]:
    """Return the active Watchlist entry for a normalized plate, or None."""
    if not plate_number:
        return None
    return (
        db.query(Watchlist)
        .filter(Watchlist.plate_number == plate_number, Watchlist.active == True)
        .first()
    )


# ---------------------------------------------------------------------------
# Alert Deduplication
# ---------------------------------------------------------------------------

def _is_duplicate_alert(db: Session, plate_number: str, camera_id: str, cooldown_seconds: int) -> bool:
    """
    Returns True if an alert for the same plate+camera was already created
    within the configured deduplication cooldown window.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=cooldown_seconds)
    existing = (
        db.query(Alert)
        .filter(
            Alert.plate_number == plate_number,
            Alert.camera_id == camera_id,
            Alert.alert_type == "WATCHLIST_MATCH",
            Alert.timestamp >= cutoff,
        )
        .first()
    )
    return existing is not None


def create_watchlist_alert(
    db: Session,
    event: VehicleEvent,
    watchlist_entry: Watchlist,
) -> Optional[Alert]:
    """
    Creates a WATCHLIST_MATCH alert for the given event, applying deduplication.
    Returns the created Alert, or None if suppressed by the cooldown window.
    """
    cooldown = settings.ALERT_DEDUP_COOLDOWN_SECONDS
    if _is_duplicate_alert(db, event.plate_number, event.camera_id, cooldown):
        logger.info(
            f"[ALERT DEDUP] Suppressed duplicate alert for {event.plate_number} "
            f"on {event.camera_id} (cooldown={cooldown}s)"
        )
        return None

    severity_map = {
        "stolen vehicle": "CRITICAL",
        "wanted vehicle": "CRITICAL",
        "suspicious vehicle": "HIGH",
    }
    severity = severity_map.get(watchlist_entry.category.lower(), "HIGH")

    alert = Alert(
        event_id=event.id,
        watchlist_id=watchlist_entry.id,
        confidence=event.plate_confidence,
        camera_id=event.camera_id,
        track_id=event.vehicle_track_id,
        plate_number=event.plate_number,
        alert_type="WATCHLIST_MATCH",
        severity=severity,
        message=(
            f"WATCHLIST HIT: Plate {event.plate_number} detected on {event.camera_id}. "
            f"Category: {watchlist_entry.category}. "
            f"Reason: {watchlist_entry.description or 'N/A'}."
        ),
        status="NEW",
    )
    db.add(alert)
    db.commit()
    db.refresh(alert)

    logger.warning(
        f"[ALERT CREATED] #{alert.id} | {alert.severity} | {event.plate_number} | {event.camera_id}"
    )
    return alert


# ---------------------------------------------------------------------------
# Full Event Ingestion Pipeline
# ---------------------------------------------------------------------------

async def ingest_event(
    db: Session,
    camera_id: str,
    vehicle_track_id: Optional[int],
    plate_raw: Optional[str],
    plate_confidence: Optional[float],
    vehicle_class: Optional[str],
    event_time: Optional[datetime],
    latitude: Optional[float],
    longitude: Optional[float],
    evidence_ref: Optional[str],
    plate: Optional[str] = None,
    timestamp_pts: Optional[float] = None,
) -> Tuple[VehicleEvent, Optional[Watchlist], Optional[Alert]]:
    """
    Full event ingestion pipeline.

    Returns:
        (VehicleEvent, WatchlistEntry|None, Alert|None)

    Raises:
        ValueError: On invalid camera, confidence out of range, or invalid coordinates.
    """
    # --- Step 1: Validate camera (case-insensitive) ---
    camera = (
        db.query(Camera)
        .filter(func.upper(Camera.camera_id) == camera_id.strip().upper())
        .first()
    )
    if not camera:
        raise ValueError(f"Camera '{camera_id}' not found in registry.")
    canonical_camera_id = camera.camera_id

    # --- Step 2: Validate confidence ---
    if plate_confidence is not None and not (0.0 <= plate_confidence <= 1.0):
        raise ValueError(f"plate_confidence must be between 0.0 and 1.0, got {plate_confidence}.")

    # --- Step 3: Validate coordinates ---
    if latitude is not None and not (-90.0 <= latitude <= 90.0):
        raise ValueError(f"latitude out of range: {latitude}")
    if longitude is not None and not (-180.0 <= longitude <= 180.0):
        raise ValueError(f"longitude out of range: {longitude}")

    # --- Step 4: Normalize plate ---
    raw_plate = plate_raw if plate_raw is not None else plate
    plate_number = normalize_plate(raw_plate) if raw_plate else None

    # --- Step 5: Persist VehicleEvent ---
    event_ts = event_time or datetime.now(timezone.utc)
    # A sighting with no coordinates must still land on the map at the camera
    # that saw it, not at a generic city centre. The registry is authoritative
    # for camera position, so fall back to it rather than storing NULL.
    event_latitude = latitude if latitude is not None else camera.latitude
    event_longitude = longitude if longitude is not None else camera.longitude
    event = VehicleEvent(
        camera_id=canonical_camera_id,
        vehicle_track_id=vehicle_track_id,
        plate_raw=raw_plate,
        plate_number=plate_number,
        plate_confidence=plate_confidence,
        vehicle_class=vehicle_class or "car",
        event_time=event_ts,
        latitude=event_latitude,
        longitude=event_longitude,
        evidence_ref=evidence_ref,
        watchlist_match=False,
    )
    db.add(event)
    db.commit()
    db.refresh(event)

    logger.info(
        f"[EVENT] #{event.id} | cam={camera_id} | plate={plate_number} | "
        f"conf={plate_confidence} | class={vehicle_class}"
    )

    # --- Step 6: Watchlist matching ---
    watchlist_entry = None
    alert = None

    if plate_number:
        watchlist_entry = match_watchlist(db, plate_number)
        if watchlist_entry:
            event.watchlist_match = True
            db.commit()
            db.refresh(event)
            logger.warning(
                f"[WATCHLIST MATCH] plate={plate_number} | category={watchlist_entry.category}"
            )
            # --- Step 6a: Alert deduplication + creation ---
            alert = create_watchlist_alert(db, event, watchlist_entry)

    # --- Step 6b: Seal the sighting into the evidence hash chain ---
    # Done after watchlist matching so the sealed snapshot covers the final
    # committed row. Sealing must never break ingestion: any failure is logged
    # and the sighting is still processed and broadcast.
    try:
        evidence_vault.seal(db, event, source="CAPTURE")
    except Exception as exc:
        db.rollback()
        logger.error(f"[EVIDENCE] seal failed for event #{event.id}: {exc}")

    # --- Step 7: Broadcast to WebSocket ---
    ws_payload = {
        "event_id": event.id,
        "camera_id": event.camera_id,
        "plate": event.plate_number,
        "plate_number": event.plate_number,
        "plate_raw": event.plate_raw,
        "vehicle_class": event.vehicle_class,
        "confidence": event.plate_confidence,
        "event_time": iso_utc(event.event_time) if event.event_time else None,
        "latitude": event.latitude,
        "longitude": event.longitude,
        "watchlist_match": event.watchlist_match,
    }

    if watchlist_entry and alert:
        await ws_manager.broadcast("ALERT_CREATED", {
            **ws_payload,
            # Numeric alert id, exactly like REST (AlertResponse.id /
            # EventCreateResponse.alert_id). This used to be the display ref
            # "AL-7"; the frontend coerced it with Number() and got NaN, so the
            # live alert card had id "NaN" and its ack/resolve calls 404'd.
            "alert_id": alert.id,
            "alert_ref": f"AL-{alert.id}",
            "id": alert.id,
            "alert_type": alert.alert_type,
            "severity": alert.severity,
            "message": alert.message,
            "status": alert.status,
            "timestamp": iso_utc(alert.timestamp) if alert.timestamp else None,
        })
    elif watchlist_entry:
        await ws_manager.broadcast("WATCHLIST_MATCH", ws_payload)
    else:
        await ws_manager.broadcast("VEHICLE_DETECTED", ws_payload)

    return event, watchlist_entry, alert
