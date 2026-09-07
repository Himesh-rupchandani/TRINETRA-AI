"""Sighting segmentation & reporting for recorded-video analysis."""

from .quality import bbox_area, edge_distance_ratio, evidence_score, sharpness  # noqa: F401
from .segmenter import (  # noqa: F401
    PLATE_DETECTED,
    PLATE_NOT_DETECTED,
    PLATE_UNCERTAIN,
    Evidence,
    PlateObservation,
    Sighting,
    SightingSegmenter,
)
