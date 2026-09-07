"""
Cross-video number-plate matching (Parts 10-13 of the brief).

Everything here is derived *at query time* from rows that the analysis pipeline
actually wrote into ``vehicle_events``. There is no cache, no seed data and no
hard-coded plate anywhere in this module — if the pipeline read nothing, the
results are empty.

Rules that keep the output honest:

* Only sightings whose OCR confidence is at or above ``MATCH_MIN_CONFIDENCE``
  can join a match group. Everything below is reported as *unreadable*.
* Exact grouping is on the **normalised** plate string.
* Fuzzy matching is offered separately and is deliberately conservative: same
  length, at most ``MATCH_FUZZY_MAX_DISTANCE`` differing characters, and every
  differing pair must be a documented OCR confusion (0/O, 1/I, 8/B, ...). A
  fuzzy pair is *never* merged into the exact group — it is surfaced as a
  clearly-labelled "possible match" for a human to confirm.
* The camera sequence is the order in which the plate was actually observed.
  A camera the vehicle was never seen on is never inserted into the path.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from sqlalchemy.orm import Session

from ..core.config import settings
from ..database.models import Camera, VehicleEvent, VideoSource
from ..utils.plate_normalizer import normalize_plate

# Character pairs OCR genuinely confuses on number plates.
CONFUSABLE: Dict[str, set] = {}
for _a, _b in [
    ("0", "O"), ("0", "D"), ("0", "Q"),
    ("1", "I"), ("1", "L"), ("1", "T"),
    ("2", "Z"), ("5", "S"), ("6", "G"),
    ("8", "B"), ("9", "G"), ("4", "A"),
    ("U", "V"), ("M", "H"), ("C", "G"),
]:
    CONFUSABLE.setdefault(_a, set()).add(_b)
    CONFUSABLE.setdefault(_b, set()).add(_a)


def _fmt_offset(seconds: Optional[float]) -> str:
    if seconds is None:
        return "--:--:--"
    s = max(0, int(seconds))
    return f"{s // 3600:02d}:{(s % 3600) // 60:02d}:{s % 60:02d}"


def confusable_distance(a: str, b: str) -> Optional[int]:
    """
    Number of differing characters between two equal-length plates, or None
    when the lengths differ or a difference is not an OCR-confusable pair.
    """
    if not a or not b or len(a) != len(b):
        return None
    diff = 0
    for ca, cb in zip(a, b):
        if ca == cb:
            continue
        if cb not in CONFUSABLE.get(ca, ()):
            return None
        diff += 1
    return diff


# ---------------------------------------------------------------------------
# Data shapes
# ---------------------------------------------------------------------------

@dataclass
class Sighting:
    event_id: int
    video_order: int          # position of this video in the analysis batch
    video_id: Optional[str]
    camera_id: str
    camera_label: str
    source_name: Optional[str]
    source_type: Optional[str]
    plate: str
    plate_raw: Optional[str]
    plate_confidence: float
    plate_status: str
    vehicle_class: Optional[str]
    vehicle_confidence: Optional[float]
    track_id: Optional[int]
    frame_number: Optional[int]
    bbox: Optional[list]
    video_offset_sec: Optional[float]
    event_time: object

    def to_dict(self) -> dict:
        return {
            "event_id": self.event_id,
            "video_id": self.video_id,
            "camera_id": self.camera_id,
            "camera_label": self.camera_label,
            "source_name": self.source_name,
            "source_type": self.source_type,
            "plate": self.plate,
            "raw_ocr": self.plate_raw,
            "ocr_confidence": self.plate_confidence,
            "plate_status": self.plate_status,
            "vehicle_class": self.vehicle_class,
            "detection_confidence": self.vehicle_confidence,
            "track_id": self.track_id,
            "frame_number": self.frame_number,
            "bbox": self.bbox,
            "video_offset_sec": self.video_offset_sec,
            "timestamp": _fmt_offset(self.video_offset_sec),
            "event_time": self.event_time,
        }


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------

def _video_index(db: Session, batch_id: Optional[str]) -> Tuple[Dict[str, VideoSource], List[VideoSource]]:
    q = db.query(VideoSource)
    if batch_id:
        q = q.filter(VideoSource.batch_id == batch_id)
    videos = q.order_by(VideoSource.id.asc()).all()
    return {v.video_id: v for v in videos}, videos


def load_sightings(
    db: Session,
    batch_id: Optional[str] = None,
    include_unreadable: bool = False,
) -> List[Sighting]:
    """Every analysis sighting, chronologically. Live-camera events are excluded."""
    videos_by_id, videos = _video_index(db, batch_id)
    if not videos:
        return []
    video_ids = list(videos_by_id.keys())
    # Uploaded files carry no synchronised wall clock, so the only defensible
    # cross-video ordering is the order the operator added the videos in,
    # refined by the offset inside each video. (Processing order is a race
    # between worker threads and must never decide a "camera sequence".)
    video_order = {v.video_id: i for i, v in enumerate(videos)}

    cams = {c.camera_id.upper(): c for c in db.query(Camera).all()}

    q = (
        db.query(VehicleEvent)
        .filter(VehicleEvent.video_id.in_(video_ids))
        .order_by(VehicleEvent.event_time.asc(), VehicleEvent.id.asc())
    )
    min_conf = float(getattr(settings, "MATCH_MIN_CONFIDENCE", 0.60))

    out: List[Sighting] = []
    for ev in q.all():
        readable = bool(ev.plate_number) and float(ev.plate_confidence or 0.0) >= min_conf
        if not readable and not include_unreadable:
            continue
        video = videos_by_id.get(ev.video_id or "")
        cam = cams.get((ev.camera_id or "").upper())
        out.append(
            Sighting(
                event_id=ev.id,
                video_order=video_order.get(ev.video_id or "", 10**6),
                video_id=ev.video_id,
                camera_id=ev.camera_id,
                camera_label=(cam.name if cam and cam.name else ev.camera_id),
                source_name=video.source_name if video else ev.video_file,
                source_type=video.source_type if video else None,
                plate=ev.plate_number or "",
                plate_raw=ev.plate_raw,
                plate_confidence=float(ev.plate_confidence or 0.0),
                plate_status=ev.plate_status or ("UNKNOWN" if not ev.plate_number else "LOW_CONFIDENCE"),
                vehicle_class=ev.vehicle_class,
                vehicle_confidence=ev.vehicle_confidence,
                track_id=ev.vehicle_track_id,
                frame_number=ev.frame_number,
                bbox=ev.bbox,
                video_offset_sec=ev.video_offset_sec,
                event_time=ev.event_time,
            )
        )
    out.sort(key=lambda s: (s.video_order, s.video_offset_sec or 0.0, s.event_id))
    return out


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------

def _camera_appearance(sightings: Sequence[Sighting]) -> dict:
    """Aggregate all sightings of one plate on one camera/video."""
    first = min(sightings, key=lambda s: (s.video_offset_sec if s.video_offset_sec is not None else 0.0))
    last = max(sightings, key=lambda s: (s.video_offset_sec if s.video_offset_sec is not None else 0.0))
    best = max(sightings, key=lambda s: s.plate_confidence)
    classes: Dict[str, int] = {}
    for s in sightings:
        if s.vehicle_class:
            classes[s.vehicle_class] = classes.get(s.vehicle_class, 0) + 1
    det_confs = [s.vehicle_confidence for s in sightings if s.vehicle_confidence is not None]
    return {
        "camera_id": first.camera_id,
        "camera_label": first.camera_label,
        "video_order": first.video_order,
        "video_id": first.video_id,
        "source_name": first.source_name,
        "source_type": first.source_type,
        "detections": len(sightings),
        "first_seen_sec": first.video_offset_sec,
        "first_seen": _fmt_offset(first.video_offset_sec),
        "last_seen_sec": last.video_offset_sec,
        "last_seen": _fmt_offset(last.video_offset_sec),
        "first_event_time": first.event_time,
        "last_event_time": last.event_time,
        "best_ocr_confidence": round(best.plate_confidence, 4),
        "best_raw_ocr": best.plate_raw,
        "best_event_id": best.event_id,
        "plate_status": "HIGH" if any(s.plate_status == "HIGH" for s in sightings) else "LOW_CONFIDENCE",
        "vehicle_class": max(classes, key=classes.get) if classes else None,
        "detection_confidence": round(max(det_confs), 4) if det_confs else None,
        "track_ids": sorted({s.track_id for s in sightings if s.track_id is not None}),
    }


def build_vehicle_record(plate: str, sightings: Sequence[Sighting]) -> dict:
    """
    Build the full cross-video record for one normalised plate:
    appearances, observed camera sequence, and vehicle history.
    """
    by_camera: Dict[str, List[Sighting]] = {}
    for s in sightings:
        by_camera.setdefault(s.camera_id, []).append(s)

    appearances = [_camera_appearance(v) for v in by_camera.values()]
    # The sequence is the ORDER OF OBSERVATION — nothing else. A camera the
    # vehicle was never seen on can never appear in this list.
    appearances.sort(
        key=lambda a: (a["video_order"], a["first_seen_sec"] or 0.0, a["camera_id"])
    )

    best = max(sightings, key=lambda s: s.plate_confidence)
    det_confs = [s.vehicle_confidence for s in sightings if s.vehicle_confidence is not None]
    classes: Dict[str, int] = {}
    for s in sightings:
        if s.vehicle_class:
            classes[s.vehicle_class] = classes.get(s.vehicle_class, 0) + 1

    history = [
        {
            "step": i + 1,
            "camera_id": a["camera_id"],
            "camera_label": a["camera_label"],
            "video_id": a["video_id"],
            "source_name": a["source_name"],
            "timestamp": a["first_seen"],
            "timestamp_sec": a["first_seen_sec"],
            "last_seen": a["last_seen"],
            "event_time": a["first_event_time"],
            "vehicle_class": a["vehicle_class"],
            "detections": a["detections"],
            "ocr_confidence": a["best_ocr_confidence"],
            "detection_confidence": a["detection_confidence"],
            "plate_status": a["plate_status"],
            "raw_ocr": a["best_raw_ocr"],
            "event_id": a["best_event_id"],
        }
        for i, a in enumerate(appearances)
    ]

    return {
        "plate": plate,
        "normalized_plate": plate,
        "video_count": len(appearances),
        "cameras": [a["camera_id"] for a in appearances],
        "sequence": [a["camera_id"] for a in appearances],
        "sequence_label": " → ".join(a["camera_id"] for a in appearances),
        "seen_in_multiple": len(appearances) > 1,
        "total_detections": len(sightings),
        "first_seen": {
            "camera_id": appearances[0]["camera_id"],
            "camera_label": appearances[0]["camera_label"],
            "timestamp": appearances[0]["first_seen"],
            "event_time": appearances[0]["first_event_time"],
        },
        "last_seen": {
            "camera_id": appearances[-1]["camera_id"],
            "camera_label": appearances[-1]["camera_label"],
            "timestamp": appearances[-1]["last_seen"],
            "event_time": appearances[-1]["last_event_time"],
        },
        "best_ocr_confidence": round(best.plate_confidence, 4),
        "best_raw_ocr": best.plate_raw,
        "best_detection_confidence": round(max(det_confs), 4) if det_confs else None,
        "vehicle_class": max(classes, key=classes.get) if classes else None,
        "plate_status": "HIGH" if any(s.plate_status == "HIGH" for s in sightings) else "LOW_CONFIDENCE",
        "appearances": appearances,
        "history": history,
    }


def find_possible_matches(records: Dict[str, dict]) -> List[dict]:
    """
    Conservative fuzzy pairing between distinct plate groups.

    Only reported when:
      * both plates have the same length,
      * they differ in at most MATCH_FUZZY_MAX_DISTANCE positions,
      * every differing pair is a known OCR confusion, and
      * at least one side is not a HIGH-confidence read (two independent HIGH
        reads that differ are treated as two different vehicles).
    """
    max_dist = int(getattr(settings, "MATCH_FUZZY_MAX_DISTANCE", 1))
    plates = sorted(records.keys())
    out: List[dict] = []
    for i, a in enumerate(plates):
        for b in plates[i + 1:]:
            dist = confusable_distance(a, b)
            if dist is None or dist == 0 or dist > max_dist:
                continue
            ra, rb = records[a], records[b]
            if ra["plate_status"] == "HIGH" and rb["plate_status"] == "HIGH":
                continue
            cams = sorted(set(ra["cameras"]) | set(rb["cameras"]))
            out.append({
                "plate_a": a,
                "plate_b": b,
                "differing_characters": dist,
                "confidence_a": ra["best_ocr_confidence"],
                "confidence_b": rb["best_ocr_confidence"],
                "status_a": ra["plate_status"],
                "status_b": rb["plate_status"],
                "combined_cameras": cams,
                "match_type": "fuzzy",
                "verdict": "POSSIBLE_SAME_VEHICLE",
                "note": (
                    f"{a} and {b} differ by {dist} visually-confusable character(s). "
                    "This is NOT confirmed as the same vehicle — an officer must verify "
                    "the evidence crops before treating it as one path."
                ),
            })
    return out


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def analyse(db: Session, batch_id: Optional[str] = None) -> dict:
    """
    Full cross-video comparison over every analysed video (or one batch).
    """
    readable = load_sightings(db, batch_id, include_unreadable=False)
    everything = load_sightings(db, batch_id, include_unreadable=True)

    grouped: Dict[str, List[Sighting]] = {}
    for s in readable:
        grouped.setdefault(s.plate, []).append(s)

    records = {plate: build_vehicle_record(plate, ss) for plate, ss in grouped.items()}
    ordered = sorted(
        records.values(),
        key=lambda r: (-r["video_count"], -r["total_detections"], r["plate"]),
    )

    unreadable = [s for s in everything if not s.plate or s.plate_confidence <
                  float(getattr(settings, "MATCH_MIN_CONFIDENCE", 0.60))]

    _, videos = _video_index(db, batch_id)
    return {
        "batch_id": batch_id,
        "videos": [
            {
                "video_id": v.video_id,
                "camera_id": v.camera_id,
                "source_name": v.source_name,
                "source_type": v.source_type,
                "status": v.status,
                "vehicles_detected": v.vehicles_detected,
                "plates_read": v.plates_read,
            }
            for v in videos
        ],
        "total_videos": len(videos),
        "total_sightings": len(everything),
        "readable_sightings": len(readable),
        "unreadable_sightings": len(unreadable),
        "unique_plates": len(records),
        "plates_in_multiple_videos": sum(1 for r in records.values() if r["video_count"] > 1),
        "vehicles": ordered,
        "multi_video_vehicles": [r for r in ordered if r["video_count"] > 1],
        "possible_matches": find_possible_matches(records),
    }


def search(db: Session, plate_query: str, batch_id: Optional[str] = None) -> dict:
    """
    Search one plate across every analysed video.

    Returns the exact record when found, plus any conservative fuzzy
    suggestions, so the operator is never silently given the wrong vehicle.
    """
    query = normalize_plate(plate_query)
    if not query:
        raise ValueError("Enter a number plate to search for.")

    readable = load_sightings(db, batch_id, include_unreadable=False)
    grouped: Dict[str, List[Sighting]] = {}
    for s in readable:
        grouped.setdefault(s.plate, []).append(s)

    exact = grouped.get(query)
    record = build_vehicle_record(query, exact) if exact else None

    suggestions: List[dict] = []
    max_dist = int(getattr(settings, "MATCH_FUZZY_MAX_DISTANCE", 1))
    for plate, ss in grouped.items():
        if plate == query:
            continue
        dist = confusable_distance(query, plate)
        if dist is None or dist == 0 or dist > max_dist:
            continue
        r = build_vehicle_record(plate, ss)
        suggestions.append({
            "plate": plate,
            "differing_characters": dist,
            "video_count": r["video_count"],
            "cameras": r["cameras"],
            "sequence_label": r["sequence_label"],
            "best_ocr_confidence": r["best_ocr_confidence"],
            "plate_status": r["plate_status"],
            "match_type": "fuzzy",
            "note": (
                f"Not an exact match — differs from {query} by {dist} "
                "visually-confusable character(s)."
            ),
        })
    suggestions.sort(key=lambda s: (s["differing_characters"], -s["best_ocr_confidence"]))

    return {
        "query": plate_query,
        "normalized_query": query,
        "found": record is not None,
        "match_type": "exact" if record else None,
        "vehicle": record,
        "possible_matches": suggestions,
        "sightings": [s.to_dict() for s in (exact or [])],
    }


def vehicle_history(db: Session, plate_query: str, batch_id: Optional[str] = None) -> Optional[dict]:
    """Detailed history for one plate: appearances + every individual sighting."""
    query = normalize_plate(plate_query)
    if not query:
        return None
    sightings = [s for s in load_sightings(db, batch_id, include_unreadable=False) if s.plate == query]
    if not sightings:
        return None
    record = build_vehicle_record(query, sightings)
    record["sightings"] = [s.to_dict() for s in sightings]
    return record
