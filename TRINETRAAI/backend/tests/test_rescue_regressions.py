"""
Regression guards for the emergency debug/rescue fixes.

Every test here pins a behaviour that was actually broken and is now fixed:

* ANPR model path is covered by the model-path test in the config layer,
  here we pin the *plate-shape* decision and the OCR fixes instead;
* raw colour crop is authoritative (CLAHE/Otsu must not override it);
* multi-line OCR within ONE crop is joined into one plate;
* the canonical Indian-plate contract still accepts the real demo plates
  and still rejects a 5-digit legacy number (``GJ03P08696`` stays a
  confidence-discounted, LOW_CONFIDENCE read — never silently promoted);
* a camera with no real-world position stores NULL lat/lng, never a default;
* ``analyze_video`` emits ONE immutable sighting per track whose frame number,
  bbox and evidence JPEGs all come from the SAME frame, and orders sightings
  by track id regardless of retirement order;
* re-running analysis replaces a video's prior sightings (no duplicates).

None of these tests load a model or hit the network: detection and OCR are
stubbed, so the suite stays deterministic and fast.
"""
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

for _p in [str(Path(__file__).resolve().parents[1])]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

import cv2
import numpy as np
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database.models import Base, Camera
from app.services.anpr_pipeline import PlateRead, format_score
from app.services.ocr_service import (
    candidate_from_text,
    joined_plate_candidate,
    preprocess_variants,
    upscale_plate,
)
from app.services.vehicle_detection_service import VehicleDetection
from app.services.video_analysis_core import analyze_video
from app.utils.plate_normalizer import is_indian_plate, normalize_plate, pretty_plate


# --------------------------------------------------------------------------- #
# Plate-format decision (the GJ03P08696 case)
# --------------------------------------------------------------------------- #
def test_real_demo_plates_are_canonical():
    """The plates actually read from the validated video are canonical."""
    for plate in ("GJ03AG6167", "GJ03DE8157"):
        assert is_indian_plate(plate), plate
        assert format_score(normalize_plate(plate)) == 1.0
        assert pretty_plate(plate) == "GJ 03 AG 6167" or pretty_plate(plate) == "GJ 03 DE 8157"


def test_five_digit_legacy_plate_is_discounted_not_promoted():
    """
    ``GJ03P08696`` is the demo feed's two-row plate read. A five-digit number
    group is NOT the canonical MoRTH/HSRP layout, so it must be discounted to
    the plausible tier (0.7) and never promoted to canonical/HIGH.
    """
    norm = normalize_plate("GJ03P08696")
    assert norm == "GJ03P08696"
    assert is_indian_plate("GJ03P08696") is False
    assert format_score(norm) == 0.7  # LOOSE tier, discounted
    # pretty_plate must not half-split a non-canonical string.
    assert pretty_plate("GJ03P08696") == "GJ03P08696"

    read = PlateRead(
        raw="GJ03P 08696", normalized=norm,
        confidence=round(0.90 * 0.7, 4), ocr_confidence=0.90,
        indian_format=False,
    )
    assert read.status == "LOW_CONFIDENCE"


# --------------------------------------------------------------------------- #
# OCR fixes
# --------------------------------------------------------------------------- #
def test_preprocess_variants_returns_raw_colour_crop_first():
    """The raw crop is authoritative: enhancement variants must follow, never lead."""
    crop = np.full((80, 160, 3), 120, dtype=np.uint8)
    cv2.rectangle(crop, (40, 20), (120, 60), (200, 200, 200), -1)
    base = upscale_plate(crop)
    variants = preprocess_variants(crop)
    assert len(variants) == 3, f"expected raw + CLAHE + Otsu, got {len(variants)}"
    # First variant IS the raw (upscaled) colour crop.
    assert variants[0] is base
    assert variants[0].ndim == 3 and variants[0].shape[2] == 3  # colour, not greyscale
    # The two enhancement variants are greyscale-derived (all channels equal).
    for v in variants[1:]:
        assert v.ndim == 3 and v.shape[2] == 3
        assert np.array_equal(v[:, :, 0], v[:, :, 1]) and np.array_equal(v[:, :, 0], v[:, :, 2])


def test_joined_plate_candidate_joins_two_ocr_lines():
    """A plate OCR split into two text regions of one crop is re-joined."""
    lines = [("GJ03P", 0.915), ("08696", 0.979)]
    joined = joined_plate_candidate(lines)
    assert joined is not None
    raw, norm, conf = joined
    assert raw == "GJ03P 08696"
    assert norm == "GJ03P08696"
    assert abs(conf - (0.915 + 0.979) / 2) < 1e-6


def test_joined_plate_candidate_ignores_single_line():
    assert joined_plate_candidate([("GJ03AG6167", 0.95)]) is None
    assert joined_plate_candidate([]) is None


def test_candidate_from_text_rejects_non_plate_lines():
    assert candidate_from_text("") is None
    assert candidate_from_text("12345") is None          # no letters
    assert candidate_from_text("ABCDEF") is None         # no digits
    assert candidate_from_text("GJ") is None             # too short
    assert candidate_from_text("GJ01AB1234") == "GJ01AB1234"


# --------------------------------------------------------------------------- #
# Camera GPS honesty
# --------------------------------------------------------------------------- #
def test_camera_without_location_stores_null_not_a_default():
    """No fabricated coordinate: a camera with no real position keeps NULL."""
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        cam = Camera(
            camera_id="NULLGPS", name="no position", stream_url="file.mp4",
            stream_type="file",
        )
        session.add(cam)
        session.commit()
        session.refresh(cam)
        assert cam.latitude is None
        assert cam.longitude is None

        # A camera WITH real coordinates keeps them untouched.
        cam2 = Camera(
            camera_id="REALGPS", name="real position", stream_url="rtsp://x",
            stream_type="rtsp", latitude=23.0338, longitude=72.585,
        )
        session.add(cam2)
        session.commit()
        session.refresh(cam2)
        assert cam2.latitude == pytest.approx(23.0338)
        assert cam2.longitude == pytest.approx(72.585)
    finally:
        session.close()


# --------------------------------------------------------------------------- #
# Same-frame evidence + deterministic ordering (the core evidence bug)
# --------------------------------------------------------------------------- #
SIZE = (160, 120)
FPS = 10
FRAMES = 12


def _write_clip(path: Path, with_second: bool) -> None:
    w = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), FPS, SIZE)
    for i in range(FRAMES):
        frame = np.full((SIZE[1], SIZE[0], 3), 40, dtype=np.uint8)
        # Moving bright vehicle, position encodes the frame index.
        cv2.rectangle(frame, (20 + i, 30), (80 + i, 90), (200, 200, 200), -1)
        if with_second and i < 8:
            cv2.rectangle(frame, (110, 30), (150, 90), (200, 200, 200), -1)
        w.write(frame)
    w.release()


def _make_stubs(with_second: bool):
    state = {"i": 0}

    def detect(frame):
        i = state["i"]
        state["i"] += 1
        dets = [VehicleDetection(
            x1=20 + i, y1=30, x2=80 + i, y2=90, class_name="car", confidence=0.9,
        )]
        if with_second and i < 8:
            dets.append(VehicleDetection(
                x1=110, y1=30, x2=150, y2=90, class_name="car", confidence=0.85,
            ))
        return dets

    def read_plate(frame, bbox, vehicle_class="car"):
        x1, y1, _x2, _y2 = bbox
        # Realistic stub: the stationary vehicle (bbox x1 == 110, i.e. x1 > 60)
        # leaves the scene after frame 7, so a real OCR returns nothing once it
        # is gone — a stale box over empty road must never yield a plate read.
        if x1 > 60 and state["i"] >= 8:
            return None
        plate = "GJ01AB1234" if x1 < 60 else "MH12XY4567"
        raw = plate
        conf = 0.7 + 0.02 * state["i"]  # grows, so the LAST read wins each track
        box = SimpleNamespace(x1=x1 + 5, y1=y1 + 5, x2=x1 + 35, y2=y1 + 25)
        return PlateRead(raw=raw, normalized=plate, confidence=round(conf, 4),
                         ocr_confidence=round(conf, 4), indian_format=True,
                         plate_box=box)

    return detect, read_plate


def _config() -> dict:
    return {
        "EVERY_N_FRAMES": 1,
        "MIN_TRACK_HITS": 1,
        "OCR_COOLDOWN_STEPS": 1,
        "MIN_VEHICLE_AREA": 0,
        "TRACK_MAX_MISSES": 2,
        "TRACK_IOU_THRESHOLD": 0.25,
    }


def _decode(jpeg: bytes) -> np.ndarray:
    arr = np.frombuffer(jpeg, dtype=np.uint8)
    return cv2.imdecode(arr, cv2.IMREAD_COLOR)


def test_analyze_video_sighting_is_one_consistent_frame(tmp_path):
    """frame_number, bbox, full frame and crops all come from the SAME frame."""
    clip = tmp_path / "single.mp4"
    _write_clip(clip, with_second=False)
    detect, read_plate = _make_stubs(with_second=False)

    report = analyze_video(str(clip), detect=detect, read_plate=read_plate,
                           config=_config())

    assert report.stats.frames_read == FRAMES
    assert len(report.sightings) == 1
    s = report.sightings[0]

    # Highest-confidence read happens on the last analysed frame (index 10).
    assert s.has_plate
    assert s.plate_status == "HIGH"
    assert s.frame_number == 10
    assert s.vehicle_bbox == [30, 30, 90, 90]       # x1 = 20 + 10
    assert s.plate_bbox == [35, 35, 65, 55]

    # Evidence imagery exists and is cut from the SAME frame the fields describe.
    full = _decode(s.full_frame)
    assert full.shape == (SIZE[1], SIZE[0], 3)
    veh = _decode(s.vehicle_crop)
    assert veh.shape == (60, 60, 3)                 # exactly the bbox extent
    plate = _decode(s.plate_crop)
    assert plate.shape == (20, 30, 3)               # exactly the plate_bbox extent

    # The full frame actually shows the vehicle at the recorded position:
    # bright inside the recorded bbox, dark immediately to its left.
    x1, y1, x2, y2 = s.vehicle_bbox
    assert full[y1:y2, x1:x2].mean() > 180
    assert full[y1:y2, max(0, x1 - 10):x1].mean() < 80
    # And the crops are the bright vehicle interior, not the dark background.
    assert veh.mean() > 180
    assert plate.mean() > 180


def test_analyze_video_orders_sightings_by_track_id(tmp_path):
    """
    Track 2 (the stationary vehicle) retires mid-video, so it is finalised
    BEFORE track 1 (which persists to the end). The report must still order
    sightings by track id, not by retirement order.
    """
    clip = tmp_path / "two.mp4"
    _write_clip(clip, with_second=True)
    detect, read_plate = _make_stubs(with_second=True)

    report = analyze_video(str(clip), detect=detect, read_plate=read_plate,
                           config=_config())

    assert report.stats.vehicles_detected == 2
    assert len(report.sightings) == 2

    # Track ids: the moving vehicle is detected first (id 1), the stationary
    # one second (id 2). The stationary track retires mid-video and would be
    # finalised FIRST without the explicit ordering — the report must still
    # list id 1 before id 2.
    ids = [s.track_id for s in report.sightings]
    assert ids == [1, 2], f"sightings not ordered by track id: {ids}"
    assert ids == sorted(ids)
    assert len(set(ids)) == 2

    # Representative frames: the stationary vehicle (id 2) is genuinely present
    # on frames 0..7 but is OCR-read only on even frames (OCR_COOLDOWN_STEPS=1),
    # so its last real read is frame 6 — frame 7 is a cooldown skip, and frames
    # 8/9 are carried-over misses over empty road where OCR returns None (a
    # stale box must never yield a plate). The moving vehicle (id 1) is read
    # through frame 10 (frame 11 is a cooldown skip).
    frames = sorted(s.frame_number for s in report.sightings)
    assert frames == [6, 10]
    for s in report.sightings:
        # Every sighting's crop is cut exactly to its own recorded bbox.
        x1, y1, x2, y2 = s.vehicle_bbox
        veh = _decode(s.vehicle_crop)
        assert (veh.shape[0], veh.shape[1]) == (y2 - y1, x2 - x1)
        assert veh.mean() > 180


def test_analyze_video_fallback_frame_is_a_real_detection(tmp_path):
    """A track with no readable plate must fall back to a frame the vehicle was
    ACTUALLY detected in — never a carried-over box over empty road."""
    clip = tmp_path / "fallback.mp4"
    _write_clip(clip, with_second=True)
    detect, _ = _make_stubs(with_second=True)

    def no_plate(frame, bbox, vehicle_class="car"):
        return None

    report = analyze_video(str(clip), detect=detect, read_plate=no_plate,
                           config=_config())

    assert report.stats.vehicles_detected == 2
    assert report.stats.plates_read == 0
    assert report.stats.unknown_plates == 2
    by_id = {s.track_id: s for s in report.sightings}
    assert set(by_id) == {1, 2}

    # The stationary vehicle (id 2) leaves after frame 7 but its box is carried
    # over through frames 8/9. The fallback frame must be a genuine detection
    # (<= 7), and its crop must show the vehicle (bright), not empty road.
    s2 = by_id[2]
    assert s2.frame_number <= 7, f"fallback frame {s2.frame_number} is a missed frame"
    veh = _decode(s2.vehicle_crop)
    assert veh.mean() > 180
