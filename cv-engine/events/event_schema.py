"""Vehicle event schema — the stable CV -> backend contract.

The ten core field names below are the contract quoted in the integration
specification. They are *never* renamed or removed. Any additional context is
carried under extra keys (``track_id``, ``confidence_grade`` ...) so old
consumers keep working unchanged. If a core field must ever change, that is a
versioned decision, not a patch.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

#: The exact, stable field names the backend expects.
CORE_EVENT_FIELDS = (
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
)

#: Documented additions — safe to include, optional to consume.
EXTRA_EVENT_FIELDS = (
    "track_id",
    "confidence_grade",
    "low_confidence",
    "source_transport",
    "detection_confidence",
    "dwell_s",
    "event_type",
)

VALID_GRADES = {"high", "medium", "low"}


@dataclass
class VehicleEvent:
    camera_id: str
    plate: str
    plate_confidence: float
    timestamp_pts: float
    event_time: str
    vehicle_id: Optional[int] = None
    plate_raw: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    vehicle_class: Optional[str] = None
    evidence_ref: Optional[str] = None
    # extras (documented, not part of the core contract)
    track_id: Optional[int] = None
    confidence_grade: str = "low"
    low_confidence: bool = False
    source_transport: Optional[str] = None
    detection_confidence: Optional[float] = None
    dwell_s: Optional[float] = None
    event_type: str = "ANPR_READ"
    extras: dict = field(default_factory=dict)

    def to_payload(self) -> dict:
        """Serialise to the backend contract (core fields always present)."""
        payload: dict[str, Any] = {
            "camera_id": self.camera_id,
            "vehicle_id": self.vehicle_id,
            "plate_raw": self.plate_raw,
            "plate": self.plate,
            "plate_confidence": round(float(self.plate_confidence), 4),
            "timestamp_pts": float(self.timestamp_pts),
            "event_time": self.event_time,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "vehicle_class": self.vehicle_class,
            "evidence_ref": self.evidence_ref,
        }
        payload["track_id"] = self.track_id
        payload["confidence_grade"] = self.confidence_grade
        payload["low_confidence"] = bool(self.low_confidence)
        payload["source_transport"] = self.source_transport
        payload["detection_confidence"] = (
            round(float(self.detection_confidence), 4)
            if self.detection_confidence is not None
            else None
        )
        payload["dwell_s"] = self.dwell_s
        payload["event_type"] = self.event_type
        payload.update(self.extras)
        return payload


def validate_payload(payload: dict) -> list[str]:
    """Return a list of problems. Empty list means the payload is acceptable.

    Used both as a pre-send gate in the client and as the backend-contract test.
    """
    problems: list[str] = []
    for field_name in CORE_EVENT_FIELDS:
        if field_name not in payload:
            problems.append(f"missing core field: {field_name}")
    if not isinstance(payload.get("camera_id"), str) or not payload.get("camera_id"):
        problems.append("camera_id must be a non-empty string")
    conf = payload.get("plate_confidence")
    if not isinstance(conf, (int, float)) or not 0.0 <= float(conf) <= 1.0:
        problems.append("plate_confidence must be a number within [0, 1]")
    pts = payload.get("timestamp_pts")
    if not isinstance(pts, (int, float)):
        problems.append("timestamp_pts must be a number")
    event_time = payload.get("event_time")
    if not isinstance(event_time, str) or not event_time:
        problems.append("event_time must be a non-empty ISO string")
    for geo in ("latitude", "longitude"):
        value = payload.get(geo)
        if value is not None and not isinstance(value, (int, float)):
            problems.append(f"{geo} must be null or a number")
    grade = payload.get("confidence_grade")
    if grade is not None and grade not in VALID_GRADES:
        problems.append(f"confidence_grade must be one of {sorted(VALID_GRADES)}")
    return problems


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
