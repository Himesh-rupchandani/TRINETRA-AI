"""
Reporting layer for recorded-video analysis: evidence files, CSV, JSON,
backend-ready events, target-vehicle report and run summary.

Honesty rules baked in here (spec §12, §13, §16, §18 of the brief):
- ``evidence_ref`` is only written when the file was actually created.
- ``event_time`` is **null** for uploaded/recorded video: the upload time is
  NOT the capture time. Video timing travels in ``timestamp_pts``.
- The target report never fabricates a missing sighting; if no plate has
  exactly the requested number of sightings it says so and shows the closest.
"""
from __future__ import annotations

import csv
import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

from events.event_schema import validate_event
from sightings.segmenter import (
    PLATE_DETECTED,
    PLATE_NOT_DETECTED,
    PLATE_UNCERTAIN,
    Sighting,
)

logger = logging.getLogger("cv_engine.sightings.reporting")


@dataclass
class ReportContext:
    video_id: str
    camera_id: str
    location_name: str
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    reject_threshold: float = 0.60
    min_agree_reads: int = 2


def _fmt_ts(seconds: float) -> str:
    m, s = divmod(max(0.0, seconds), 60.0)
    return f"{int(m):02d}:{s:04.1f}"


def write_evidence(
    sightings: List[Sighting],
    evidence_dir: Path,
    jpeg_quality: int = 92,
) -> None:
    """Write best-frame and plate-crop JPEGs; fill the refs on each sighting."""
    import cv2

    evidence_dir.mkdir(parents=True, exist_ok=True)
    for i, s in enumerate(sightings, start=1):
        stem = f"sighting_{i:02d}"
        ev = s.evidence
        if ev.frame is not None:
            path = evidence_dir / f"{stem}.jpg"
            if cv2.imwrite(str(path), ev.frame, [int(cv2.IMWRITE_JPEG_QUALITY), jpeg_quality]):
                ev.frame_ref = f"evidence/{path.name}"
        if ev.plate_crop is not None and ev.plate_crop.size > 0:
            path = evidence_dir / f"{stem}_plate.jpg"
            if cv2.imwrite(str(path), ev.plate_crop, [int(cv2.IMWRITE_JPEG_QUALITY), jpeg_quality]):
                ev.plate_crop_ref = f"evidence/{path.name}"


def sighting_to_dict(s: Sighting, ctx: ReportContext) -> dict:
    plate, plate_raw, conf, support, status = s.plate_result(
        ctx.reject_threshold, ctx.min_agree_reads
    )
    return {
        "sighting_id": s.sighting_id,
        "video_id": ctx.video_id,
        "camera_id": ctx.camera_id,
        "location_name": ctx.location_name,
        "track_ids": s.track_ids,
        "track_id": s.track_id,
        "vehicle_class": s.vehicle_class,
        "start_pts_ms": round(s.start_pts_ms, 1),
        "end_pts_ms": round(s.end_pts_ms, 1),
        "start_sec": round(s.start_pts_ms / 1000.0, 3),
        "end_sec": round(s.end_pts_ms / 1000.0, 3),
        "start_timestamp": _fmt_ts(s.start_pts_ms / 1000.0),
        "duration_sec": round(s.duration_sec, 3),
        "first_frame_index": s.first_frame_index,
        "last_frame_index": s.last_frame_index,
        "frames_observed": s.frames_observed,
        "mean_detection_confidence": round(s.mean_detection_confidence, 4),
        "plate": plate,
        "plate_raw": plate_raw,
        "plate_confidence": round(conf, 4) if conf is not None else None,
        "plate_status": status,
        "supporting_frame_count": support,
        "ocr_reads": len(s.plate_observations),
        "plate_candidates": s.candidate_summary(),
        "sighting_index_for_plate": s.sighting_index_for_plate,
        "merged_track_sessions": s.merged_from,
        "evidence_ref": s.evidence.frame_ref,
        "plate_crop_ref": s.evidence.plate_crop_ref,
        "evidence_pts_ms": round(s.evidence.pts_ms, 1) if s.evidence.frame_ref else None,
        "evidence_quality": round(s.evidence.quality, 4) if s.evidence.quality >= 0 else None,
    }


CSV_COLUMNS = [
    "sighting_id", "video_id", "camera_id", "location_name", "start_timestamp",
    "start_sec", "end_sec", "duration_sec", "track_id", "track_ids",
    "vehicle_class", "plate", "plate_raw", "plate_confidence", "plate_status",
    "supporting_frame_count", "ocr_reads", "frames_observed",
    "mean_detection_confidence", "sighting_index_for_plate",
    "evidence_ref", "plate_crop_ref",
]


def write_sightings(
    sightings: List[Sighting], ctx: ReportContext, out_dir: Path
) -> List[dict]:
    """Write vehicle_sightings.json + vehicle_sightings.csv. Returns the rows."""
    out_dir.mkdir(parents=True, exist_ok=True)
    rows = [sighting_to_dict(s, ctx) for s in sightings]

    with (out_dir / "vehicle_sightings.json").open("w", encoding="utf-8") as fh:
        json.dump(rows, fh, indent=2)

    with (out_dir / "vehicle_sightings.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=CSV_COLUMNS, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            row = dict(r)
            row["track_ids"] = "|".join(str(t) for t in r["track_ids"])
            w.writerow(row)
    return rows


def build_events(sightings: List[Sighting], ctx: ReportContext) -> List[dict]:
    """
    Backend-ready events (POST /api/events contract).

    One event per SIGHTING — never one per frame. ``event_time`` is null
    because a recorded upload carries no real capture clock.
    """
    events = []
    for s in sightings:
        plate, plate_raw, conf, _support, status = s.plate_result(
            ctx.reject_threshold, ctx.min_agree_reads
        )
        usable = status == PLATE_DETECTED
        event = {
            "camera_id": ctx.camera_id,
            "vehicle_id": int(s.track_id) if s.track_id >= 0 else None,
            "plate_raw": plate_raw if usable else None,
            "plate": plate if usable else None,
            "plate_confidence": round(float(conf), 4) if (usable and conf is not None) else None,
            "timestamp_pts": round(float(s.start_pts_ms), 1),
            "event_time": None,  # recorded video: no real-world capture clock
            "latitude": ctx.latitude,
            "longitude": ctx.longitude,
            "vehicle_class": s.vehicle_class,
            "evidence_ref": s.evidence.frame_ref,
        }
        events.append(validate_event(event))
    return events


def plate_summary(rows: List[dict]) -> List[dict]:
    """unique normalized plate -> number of sightings (validated plates only)."""
    counts: Dict[str, dict] = {}
    for r in rows:
        if r["plate_status"] != PLATE_DETECTED or not r["plate"]:
            continue
        c = counts.setdefault(r["plate"], {"plate": r["plate"], "sightings": 0,
                                           "timestamps": [], "max_confidence": 0.0})
        c["sightings"] += 1
        c["timestamps"].append(r["start_timestamp"])
        c["max_confidence"] = max(c["max_confidence"], r["plate_confidence"] or 0.0)
    out = list(counts.values())
    out.sort(key=lambda d: (-d["sightings"], -d["max_confidence"]))
    return out


def build_target_report(
    rows: List[dict], target_count: int = 5
) -> dict:
    """
    Find the vehicle with EXACTLY ``target_count`` distinct sightings.

    If none exists this is reported honestly, together with the closest
    candidate — no fabricated extra sighting, ever.
    """
    summary = plate_summary(rows)
    exact = [p for p in summary if p["sightings"] == target_count]

    def sighting_rows(plate: str) -> List[dict]:
        return [
            {
                "sighting_number": r["sighting_index_for_plate"],
                "sighting_id": r["sighting_id"],
                "timestamp": r["start_timestamp"],
                "start_sec": r["start_sec"],
                "end_sec": r["end_sec"],
                "duration_sec": r["duration_sec"],
                "track_id": r["track_id"],
                "track_ids": r["track_ids"],
                "vehicle_class": r["vehicle_class"],
                "plate_confidence": r["plate_confidence"],
                "supporting_frame_count": r["supporting_frame_count"],
                "evidence_ref": r["evidence_ref"],
                "plate_crop_ref": r["plate_crop_ref"],
            }
            for r in rows if r["plate"] == plate and r["plate_status"] == PLATE_DETECTED
        ]

    if exact:
        plate = exact[0]["plate"]
        return {
            "found": True,
            "requested_sighting_count": target_count,
            "plate": plate,
            "total_sightings": exact[0]["sightings"],
            "sightings": sighting_rows(plate),
            "note": None,
            "all_plate_counts": summary,
        }

    closest = summary[0] if summary else None
    return {
        "found": False,
        "requested_sighting_count": target_count,
        "plate": closest["plate"] if closest else None,
        "total_sightings": closest["sightings"] if closest else 0,
        "sightings": sighting_rows(closest["plate"]) if closest else [],
        "note": (
            f"No vehicle with exactly {target_count} validated sightings was found. "
            + (
                f"Closest: {closest['plate']} with {closest['sightings']} sighting(s)."
                if closest else "No plate was validated in this video."
            )
        ),
        "all_plate_counts": summary,
    }


def write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2)
