"""
Event builder (spec §21, §22).

Assembles the backend event payload from:
- camera metadata (camera_id + location — GPS is NEVER inferred from video)
- track identity (vehicle_id = track_id, vehicle_class, PTS)
- aggregated plate candidate (may be None -> plateless sighting event)
- evidence references

event_time is wall-clock UTC at emission time (the real-world anchor the
backend stores); *video* timing travels in timestamp_pts.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from .event_schema import validate_event


def build_event(
    camera,                       # capture.sentinel_catalogue.Camera
    track,                        # tracking.vehicle_tracker.Track
    plate: Optional[dict] = None, # PlateMemory.best() result or None
    evidence_ref: Optional[str] = None,
    event_time: Optional[datetime] = None,
    pts_ms: Optional[float] = None,  # authoritative packet PTS fallback
) -> dict:
    """
    Build a validated backend event dict.

    Low-confidence plates are NOT dropped and NOT upgraded: the stored
    plate_confidence value itself communicates the uncertainty (spec §30).
    """
    ts = event_time or datetime.now(timezone.utc)

    # Tracks not matched on the current frame can carry a sentinel (-1) PTS;
    # the capture packet's PTS is the authoritative timing source (spec §10).
    pts = track.last_pts_ms
    if pts is None or pts < 0:
        pts = pts_ms

    event = {
        "camera_id": camera.camera_id,
        "vehicle_id": int(track.track_id),
        "plate_raw": plate.get("plate_raw") if plate else None,
        "plate": plate.get("plate") if plate else None,
        "plate_confidence": float(plate["confidence"]) if plate else None,
        "timestamp_pts": float(pts) if pts is not None else None,
        "event_time": ts.isoformat().replace("+00:00", "Z"),
        "latitude": camera.latitude if camera.has_location() else None,
        "longitude": camera.longitude if camera.has_location() else None,
        "vehicle_class": track.class_name or "car",
        "evidence_ref": evidence_ref,
    }
    return validate_event(event)
