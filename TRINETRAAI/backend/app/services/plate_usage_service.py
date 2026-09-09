"""
Number-plate usage report — "every plate in this video, and how long it was there".

Built entirely from :class:`VehiclePresence` rows written by the analysis
pipeline, so every figure is measured from the video itself. Nothing here is
estimated, extrapolated or demo data.

The three time figures, and why there are three
-----------------------------------------------
For one plate seen in one video:

* **dwell** — ``last_seen - first_seen``. The span from when the plate first
  appeared to when it was last seen. If a car arrives at 0:05, is blocked by a
  bus for 20 s and reappears until 1:00, its dwell is 55 s.
* **on-screen (visible)** — the time it was *actually* tracked, i.e.
  ``frames_present x sample_period``. Same car: 35 s. Always ``<= dwell``.
* **appearances** — how many separate times it entered the shot (2 above).

Which one you want depends on the question: "how long was it in the area" is
dwell, "how long did we actually have eyes on it" is on-screen.

Both are reported for every plate, together with entry/exit timestamps and the
share of the video each plate occupies. A vehicle whose plate could not be read
is never dropped or guessed — it is listed separately under ``unreadable``.
"""
from __future__ import annotations

import csv
import io
from typing import Dict, List, Optional, Sequence, Tuple

from sqlalchemy.orm import Session

from ..core.logging_config import logger
from ..database.models import VehiclePresence, VideoSource
from .video_analysis_service import format_offset

__all__ = [
    "merge_intervals",
    "build_report",
    "report_to_csv",
    "report_to_rows",
]


# ---------------------------------------------------------------------------
# Interval maths
# ---------------------------------------------------------------------------

def merge_intervals(
    intervals: Sequence[Tuple[float, float]]
) -> List[Tuple[float, float]]:
    """
    Merge overlapping/adjacent ``(start, end)`` pairs into disjoint spans.

    ``[(0, 10), (5, 12), (30, 40)]`` -> ``[(0, 12), (30, 40)]``

    Two appearances of the same vehicle can overlap when the tracker briefly
    splits one vehicle into two tracks; merging stops that from double-counting
    the shared seconds.
    """
    cleaned = sorted(
        (float(a), float(b)) for a, b in intervals if b is not None and a is not None
    )
    if not cleaned:
        return []
    merged: List[List[float]] = [list(cleaned[0])]
    for start, end in cleaned[1:]:
        last = merged[-1]
        if start <= last[1]:          # overlapping or touching
            last[1] = max(last[1], end)
        else:
            merged.append([start, end])
    return [(a, b) for a, b in merged]


def _total(merged: Sequence[Tuple[float, float]]) -> float:
    return round(sum(b - a for a, b in merged), 3)


# ---------------------------------------------------------------------------
# Report building
# ---------------------------------------------------------------------------

def _presence_rows(db: Session, video_id: str) -> List[VehiclePresence]:
    return (
        db.query(VehiclePresence)
        .filter(VehiclePresence.video_id == video_id)
        .order_by(VehiclePresence.first_seen_sec.asc())
        .all()
    )


def _summarise(
    plate: Optional[str],
    rows: List[VehiclePresence],
    duration_sec: Optional[float],
) -> dict:
    """Aggregate every appearance of one plate into a single report line."""
    ordered = sorted(rows, key=lambda r: (r.first_seen_sec, r.last_seen_sec))
    merged = merge_intervals([(r.first_seen_sec, r.last_seen_sec) for r in ordered])

    first_seen = round(float(ordered[0].first_seen_sec), 3)
    last_seen = round(float(max(r.last_seen_sec for r in ordered)), 3)
    # Entry-to-exit span, inclusive of one sampling window (a vehicle seen in a
    # single analysed frame occupies a whole window, not zero seconds).
    period = _sample_period(ordered)
    dwell = round(max(last_seen - first_seen, 0.0) + period, 3)
    # On-screen time is counted, not derived: add up the tracked frames of each
    # appearance, then cap it two ways — it can never exceed the total span,
    # and overlapping tracks describing the same vehicle must not double-count.
    span_cap = _total(merged) + period * len(merged)
    visible = round(
        min(sum(float(r.visible_sec or 0.0) for r in ordered), dwell, span_cap), 3
    )

    best = max(ordered, key=lambda r: (r.vehicle_confidence or 0.0))
    # Prefer the appearance whose plate read was most confident; fall back to
    # the sharpest (largest) vehicle box for unreadable vehicles.
    readable = [r for r in ordered if r.plate_number]
    if readable:
        best = max(readable, key=lambda r: (r.plate_confidence or 0.0, r.vehicle_confidence or 0.0))
    statuses = {r.plate_status for r in ordered if r.plate_status}
    status = "HIGH" if "HIGH" in statuses else (
        "LOW_CONFIDENCE" if "LOW_CONFIDENCE" in statuses else "UNKNOWN"
    )

    share = None
    if duration_sec and duration_sec > 0:
        share = round(min(dwell / float(duration_sec) * 100.0, 100.0), 1)

    return {
        "plate": plate,
        "plate_label": plate or "UNREADABLE",
        "vehicle_class": best.vehicle_class,
        "plate_status": status,
        "best_plate_confidence": round(float(best.plate_confidence), 4)
        if best.plate_confidence is not None else None,
        "best_detection_confidence": round(float(best.vehicle_confidence), 4)
        if best.vehicle_confidence is not None else None,

        "appearances": len(ordered),
        "first_seen_sec": first_seen,
        "last_seen_sec": last_seen,
        "first_seen": format_offset(first_seen),
        "last_seen": format_offset(last_seen),

        # The headline numbers.
        "dwell_sec": dwell,
        "dwell_label": format_offset(dwell),
        "visible_sec": visible,
        "visible_label": format_offset(visible),
        "presence_pct": share,

        "frames_present": sum(int(r.frames_present or 0) for r in ordered),
        "track_ids": [r.track_id for r in ordered],
        "evidence_ref": next((r.evidence_ref for r in reversed(ordered) if r.evidence_ref), None),
        "watchlist_match": any(r.watchlist_match for r in ordered),
        "segments": [
            {
                "start_sec": round(float(r.first_seen_sec), 3),
                "end_sec": round(float(r.last_seen_sec), 3),
                "duration_sec": round(float(r.dwell_sec or 0.0), 3),
                "start": format_offset(r.first_seen_sec),
                "end": format_offset(r.last_seen_sec),
                "track_id": r.track_id,
            }
            for r in ordered
        ],
    }


def _sample_period(rows: Sequence[VehiclePresence]) -> float:
    """
    Seconds of video one analysed frame stands for.

    A vehicle tracked in exactly one analysed sample occupies a whole sampling
    window (``every_n / fps`` seconds), not zero seconds.
    """
    periods = [float(r.sample_period_sec or 0.0) for r in rows]
    return max(periods) if periods else 0.0


def build_report(db: Session, video_id: str) -> dict:
    """
    Full "which plate, and for how long" report for one analysed video.

    Raises :class:`ValueError` when the video does not exist.
    """
    video = db.query(VideoSource).filter(VideoSource.video_id == video_id).first()
    if video is None:
        raise ValueError(f"Video '{video_id}' was not found.")

    rows = _presence_rows(db, video_id)
    duration = float(video.duration_sec) if video.duration_sec else None

    grouped: Dict[Optional[str], List[VehiclePresence]] = {}
    for row in rows:
        grouped.setdefault(row.plate_number, []).append(row)

    plates = [
        _summarise(plate, group, duration)
        for plate, group in grouped.items()
        if plate
    ]
    unreadable = [
        _summarise(None, group, duration)
        for plate, group in grouped.items()
        if not plate
    ]

    # Longest time in shot first — that is the question the report answers.
    plates.sort(key=lambda r: (-r["dwell_sec"], -r["visible_sec"], r["plate"]))
    unreadable.sort(key=lambda r: (-r["dwell_sec"], -r["visible_sec"]))

    total_dwell = round(sum(r["dwell_sec"] for r in plates), 3)
    longest = plates[0]["dwell_sec"] if plates else 0.0

    return {
        "video": {
            "video_id": video.video_id,
            "camera_id": video.camera_id,
            "source_name": video.source_name,
            "source_type": video.source_type,
            "status": video.status,
            "error": video.error,
            "progress_pct": video.progress_pct,
            "duration_sec": duration,
            "duration_label": format_offset(duration) if duration else None,
            "fps": video.fps,
            "width": video.width,
            "height": video.height,
            "vehicles_detected": video.vehicles_detected,
            "plates_read": video.plates_read,
            "unknown_plates": video.unknown_plates,
        },
        "summary": {
            "appearances": len(rows),
            "unique_plates": len(plates),
            "unreadable_vehicles": len(unreadable),
            "total_dwell_sec": total_dwell,
            "total_dwell_label": format_offset(total_dwell),
            "longest_dwell_sec": round(longest, 3),
            "longest_dwell_label": format_offset(longest),
            "longest_plate": plates[0]["plate"] if plates else None,
            "watchlist_hits": sum(1 for r in plates if r["watchlist_match"]),
            "video_duration_sec": duration,
        },
        "plates": plates,
        "unreadable": unreadable,
        "notes": _notes(video, plates, unreadable),
    }


def _notes(video: VideoSource, plates: List[dict], unreadable: List[dict]) -> List[str]:
    """Honest caveats, so the report never overstates what was measured."""
    notes: List[str] = []
    if video.status not in ("DONE",):
        notes.append(
            f"This video is {video.status}. Times below cover the part analysed so far "
            f"({video.progress_pct:.0f}%)."
        )
    if not plates and unreadable:
        notes.append(
            "Vehicles were tracked but no number plate could be read with "
            "sufficient confidence. They are listed under 'Unreadable'."
        )
    if plates:
        notes.append(
            "'Dwell' is the span from first to last sighting; 'on screen' counts only "
            "the frames the vehicle was actually tracked. Times are measured from the "
            "video, rounded to the frame-sampling interval."
        )
    return notes


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------

CSV_COLUMNS = [
    "plate",
    "vehicle_class",
    "appearances",
    "first_seen",
    "last_seen",
    "dwell_sec",
    "dwell_hms",
    "on_screen_sec",
    "on_screen_hms",
    "presence_pct_of_video",
    "frames_tracked",
    "plate_status",
    "best_plate_confidence",
    "watchlist_match",
    "track_ids",
]


def report_to_rows(report: dict) -> List[dict]:
    """Flat, CSV-ready rows: readable plates first, then unreadable vehicles."""
    out: List[dict] = []
    for row in list(report.get("plates", [])) + list(report.get("unreadable", [])):
        out.append(
            {
                "plate": row["plate_label"],
                "vehicle_class": row["vehicle_class"] or "",
                "appearances": row["appearances"],
                "first_seen": row["first_seen"],
                "last_seen": row["last_seen"],
                "dwell_sec": row["dwell_sec"],
                "dwell_hms": row["dwell_label"],
                "on_screen_sec": row["visible_sec"],
                "on_screen_hms": row["visible_label"],
                "presence_pct_of_video": row["presence_pct"]
                if row["presence_pct"] is not None else "",
                "frames_tracked": row["frames_present"],
                "plate_status": row["plate_status"],
                "best_plate_confidence": row["best_plate_confidence"]
                if row["best_plate_confidence"] is not None else "",
                "watchlist_match": "YES" if row["watchlist_match"] else "",
                "track_ids": ";".join(str(t) for t in row["track_ids"] if t is not None),
            }
        )
    return out


def report_to_csv(report: dict) -> str:
    """The same table as CSV, for Excel / evidence packs."""
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=CSV_COLUMNS, extrasaction="ignore")
    writer.writeheader()
    for row in report_to_rows(report):
        writer.writerow(row)
    return buf.getvalue()


def latest_video_id(db: Session) -> Optional[str]:
    """Most recently completed analysis video — the one the user just ran."""
    video = (
        db.query(VideoSource)
        .order_by(VideoSource.id.desc())
        .first()
    )
    return video.video_id if video else None
