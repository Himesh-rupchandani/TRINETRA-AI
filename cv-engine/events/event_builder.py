"""Assemble :class:`VehicleEvent` objects from pipeline outputs.

Location is *never* guessed: latitude/longitude come from the camera metadata,
and are left as ``null`` when the catalogue does not publish them.
"""

from __future__ import annotations

from anpr.confidence import grade_confidence, is_low_confidence
from capture.sentinel_catalogue import Camera
from config.settings import Settings
from events.event_schema import VehicleEvent, now_iso
from tracking.vehicle_tracker import TrackedVehicle


def build_event(
    settings: Settings,
    camera: Camera,
    track: TrackedVehicle | None,
    plate: str,
    plate_raw: str | None,
    plate_confidence: float,
    evidence_ref: str | None = None,
    source_transport: str | None = None,
    event_type: str = "ANPR_READ",
) -> VehicleEvent:
    """The ANPR sighting event — the primary deliverable of the CV engine."""
    low = is_low_confidence(plate_confidence, settings.anpr_low_confidence)
    return VehicleEvent(
        camera_id=camera.camera_id,
        plate=plate,
        plate_raw=plate_raw,
        plate_confidence=float(plate_confidence),
        timestamp_pts=float(track.continuous_ms if track else 0.0),
        event_time=now_iso(),
        vehicle_id=track.track_id if track else None,
        latitude=camera.latitude,
        longitude=camera.longitude,
        vehicle_class=track.class_name if track else None,
        evidence_ref=evidence_ref,
        track_id=track.track_id if track else None,
        confidence_grade=grade_confidence(
            plate_confidence, high=settings.anpr_low_confidence + 0.2, low=settings.anpr_low_confidence
        ),
        low_confidence=low,
        source_transport=source_transport,
        detection_confidence=track.confidence if track else None,
        dwell_s=round(track.dwell_s, 2) if track else None,
        event_type=event_type,
    )


def build_unplated_event(
    settings: Settings,
    camera: Camera,
    track: TrackedVehicle,
    source_transport: str | None = None,
) -> VehicleEvent:
    """A vehicle sighting with no readable plate (stored, never high-priority)."""
    return VehicleEvent(
        camera_id=camera.camera_id,
        plate="",
        plate_raw=None,
        plate_confidence=0.0,
        timestamp_pts=float(track.continuous_ms),
        event_time=now_iso(),
        vehicle_id=track.track_id,
        latitude=camera.latitude,
        longitude=camera.longitude,
        vehicle_class=track.class_name,
        evidence_ref=None,
        track_id=track.track_id,
        confidence_grade="low",
        low_confidence=True,
        source_transport=source_transport,
        detection_confidence=track.confidence,
        dwell_s=round(track.dwell_s, 2),
        event_type="VEHICLE_DETECTION",
    )
