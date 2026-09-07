"""Plate localisation must never invent a plate string."""
import numpy as np
import cv2

from anpr.plate_detector import (
    extract_plate_candidates,
    morphology_plate_boxes,
    plate_crops_for_vehicle,
)
from anpr.normalizer import candidate_from_ocr_text, normalize_plate


def test_heuristic_crops_exist_for_a_car_box():
    frame = np.zeros((240, 320, 3), dtype=np.uint8)
    crops = extract_plate_candidates(frame, [40, 40, 200, 180], "car")
    assert crops  # lower-half + full
    moto = extract_plate_candidates(frame, [40, 40, 200, 180], "motorcycle")
    assert len(moto) == 1  # full crop only


def test_morphology_finds_a_bright_plate_rectangle():
    crop = np.zeros((120, 200, 3), dtype=np.uint8)
    # Dark bumper + a bright 80x20 plate in the lower half, with vertical bars
    # so the Sobel-close stage has edges to lock onto.
    crop[80:100, 40:140] = (230, 230, 230)
    for x in range(48, 132, 8):
        crop[82:98, x:x + 3] = (20, 20, 20)
    boxes = morphology_plate_boxes(crop)
    assert boxes, "expected at least one plate-like rectangle"
    x1, y1, x2, y2, score = boxes[0]
    assert (x2 - x1) > (y2 - y1)
    assert score > 0


def test_morphology_empty_on_blank():
    crop = np.zeros((80, 80, 3), dtype=np.uint8)
    assert morphology_plate_boxes(crop) == []


def test_plate_crops_fallback_never_raises():
    frame = np.zeros((100, 160, 3), dtype=np.uint8)
    crops = plate_crops_for_vehicle(frame, [10, 10, 90, 80], "car")
    assert isinstance(crops, list)


def test_ocr_candidate_rejects_garbage_does_not_invent():
    assert candidate_from_ocr_text("hello") is None
    assert candidate_from_ocr_text("*****") is None
    assert candidate_from_ocr_text("12") is None
    assert candidate_from_ocr_text("GJ 01 AB 1234") == "GJ01AB1234"
    assert normalize_plate("GJ-01-AB-1234") == "GJ01AB1234"
