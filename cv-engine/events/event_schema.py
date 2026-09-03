"""
Vehicle event schema (spec §21).

This is the STABLE contract with the backend (POST /api/events). Field names
must not be silently renamed — the backend's VehicleEventCreate schema mirrors
these exactly:

    camera_id, vehicle_id, plate_raw, plate, plate_confidence,
    timestamp_pts, event_time, latitude, longitude, vehicle_class,
    evidence_ref
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

EVENT_FIELDS = [
    "camera_id",
    "vehicle_id",
    "plate_raw",
    "plate",
    "plate_confidence",
    "timestamp_pts",
    "event_time",
    "latitude",
    "longitude",
    "vehicle_class",
    "evidence_ref",
]

REQUIRED_FIELDS = ["camera_id"]


class EventValidationError(ValueError):
    pass


def validate_event(event: Dict[str, Any]) -> Dict[str, Any]:
    """
    Validate an event payload against the contract. Raises
    EventValidationError on violations. Returns the payload unchanged.
    """
    unknown = [k for k in event.keys() if k not in EVENT_FIELDS]
    if unknown:
        raise EventValidationError(f"unknown event field(s): {unknown}")

    for f in REQUIRED_FIELDS:
        if not event.get(f):
            raise EventValidationError(f"missing required field: {f}")

    conf = event.get("plate_confidence")
    if conf is not None and not (0.0 <= float(conf) <= 1.0):
        raise EventValidationError(f"plate_confidence out of [0,1]: {conf}")

    lat, lon = event.get("latitude"), event.get("longitude")
    if lat is not None and not (-90.0 <= float(lat) <= 90.0):
        raise EventValidationError(f"latitude out of range: {lat}")
    if lon is not None and not (-180.0 <= float(lon) <= 180.0):
        raise EventValidationError(f"longitude out of range: {lon}")

    pts = event.get("timestamp_pts")
    if pts is not None and float(pts) < 0:
        raise EventValidationError(f"timestamp_pts must be >= 0: {pts}")

    vid = event.get("vehicle_id")
    if vid is not None and int(vid) < 0:
        raise EventValidationError(f"vehicle_id must be >= 0: {vid}")

    return event


def to_backend_payload(event: Dict[str, Any]) -> Dict[str, Any]:
    """
    Serialize for POST /api/events. Field names pass through unchanged —
    this function exists so the contract has exactly one owner.
    """
    validate_event(event)
    return {k: event[k] for k in EVENT_FIELDS if k in event}
