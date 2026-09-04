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

def _find_duplicate_sighting(
    db: Session,
    camera_id: str,
    vehicle_track_id: Optional[int],
    plate_number: Optional[str],
    event_time: datetime,
) -> Optional[VehicleEvent]:
    """Return an existing event that represents this same physical sighting.

    Keyed on (camera, track, plate) within SIGHTING_DEDUP_WINDOW_SECONDS.
    A different camera is never deduplicated against another — cross-camera
    sightings are exactly what the investigation flow depends on.
    """
    window = getattr(settings, "SIGHTING_DEDUP_WINDOW_SECONDS", 30)
    if window <= 0 or vehicle_track_id is None or not plate_number:
        # Without a stable track id + plate we cannot safely call it a duplicate.
        return None

    if event_time.tzinfo is None:
        event_time = event_time.replace(tzinfo=timezone.utc)
    earliest = event_time - timedelta(seconds=window)
    latest = event_time + timedelta(seconds=window)

    return (
        db.query(VehicleEvent)
        .filter(
            VehicleEvent.camera_id == camera_id,
            VehicleEvent.vehicle_track_id == vehicle_track_id,
            VehicleEvent.plate_number == plate_number,
            VehicleEvent.event_time >= earliest.replace(tzinfo=None),
            VehicleEvent.event_time <= latest.replace(tzinfo=None),
        )
        .order_by(VehicleEvent.id.asc())
        .first()
    )


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

    # Sighting idempotency (spec §25): the CV engine already suppresses
    # per-frame duplicates, but a retried POST after a network blip must not
    # create a second sighting — that would corrupt the cross-camera trace and
    # the GIS route. Same camera + track + plate inside the window == same event.
    existing = _find_duplicate_sighting(
        db,
        camera_id=canonical_camera_id,
        vehicle_track_id=vehicle_track_id,
        plate_number=plate_number,
        event_time=event_ts,
    )
    if existing is not None:
        logger.info(
            f"[SIGHTING DEDUP] Ignored duplicate sighting for plate={plate_number} "
            f"cam={canonical_camera_id} track={vehicle_track_id}; "
            f"returning existing event #{existing.id}."
        )
        watchlist_entry = match_watchlist(db, plate_number) if plate_number else None
        return existing, watchlist_entry, None

    event = VehicleEvent(
        camera_id=canonical_camera_id,
        vehicle_track_id=vehicle_track_id,
        plate_raw=raw_plate,
        plate_number=plate_number,
        plate_confidence=plate_confidence,
        vehicle_class=vehicle_class or "car",
        event_time=event_ts,
        latitude=latitude,
        longitude=longitude,
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

    # --- Step 7: Broadcast to WebSocket ---
    ws_payload = {
        "event_id": event.id,
        "camera_id": event.camera_id,
        "plate": event.plate_number,
        "plate_number": event.plate_number,
        "plate_raw": event.plate_raw,
        "vehicle_class": event.vehicle_class,
        "confidence": event.plate_confidence,
        "event_time": event.event_time.isoformat() if event.event_time else None,
        "latitude": event.latitude,
        "longitude": event.longitude,
        "watchlist_match": event.watchlist_match,
    }

    if watchlist_entry and alert:
        await ws_manager.broadcast("ALERT_CREATED", {
            **ws_payload,
            "alert_id": f"AL-{alert.id}",
            "id": alert.id,
            "severity": alert.severity,
            "message": alert.message,
        })
    elif watchlist_entry:
        await ws_manager.broadcast("WATCHLIST_MATCH", ws_payload)
    else:
        await ws_manager.broadcast("VEHICLE_DETECTED", ws_payload)

    return event, watchlist_entry, alert
