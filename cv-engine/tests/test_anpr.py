"""ANPR: normalisation, confidence, aggregation, plate detection."""

from __future__ import annotations

import numpy as np
import pytest

from anpr.aggregator import TrackPlateAggregator
from anpr.confidence import combine_confidences, grade_confidence, is_low_confidence
from anpr.normalizer import is_plausible_indian_plate, normalize_plate, plate_score, strip_to_alnum
from anpr.plate_detector import PlateDetector
from anpr.ocr import RapidOcrEngine, get_ocr_engine


# ---------------------------------------------------------------------------
# normalizer
# ---------------------------------------------------------------------------


def test_clean_plate_is_untouched():
    result = normalize_plate("GJ 01 AB-1234")
    assert result.normalized == "GJ01AB1234"
    assert result.valid is True
    assert result.corrections == []
    assert result.state_code_known is True


def test_g_read_as_6_is_corrected_positionally_and_recorded():
    # This exact case came back from the real OCR engine on the fixture image.
    result = normalize_plate("6J01AB1234")
    assert result.normalized == "GJ01AB1234"
    assert (0, "6", "G") in result.corrections
    assert result.valid is True


def test_letter_digit_confusions_are_fixed_only_in_the_right_slots():
    # 'O' in a letter slot stays; 'O' in a digit slot becomes 0.
    result = normalize_plate("GJO1AB1234")  # slot2 'O' is a digit slot -> 0
    assert result.normalized == "GJ01AB1234"
    # An 'O' in slot0 (a letter slot) stays a letter. The layout still parses as
    # a plate, but the RTO code 'OJ' is unknown, so it must not be promoted.
    result2 = normalize_plate("OJ01AB1234")
    assert result2.normalized[0] == "O"
    assert result2.valid is True
    assert result2.state_code_known is False


def test_unknown_wrong_type_char_does_not_become_a_fake_plate():
    # '?' is stripped; '!' stripped; leaving a short string -> invalid.
    result = normalize_plate("GJ01AB12")
    assert result.length_ok is True
    assert result.valid is False
    # A '-' in a digit slot is not a known confusion and is dropped, so we do not
    # fabricate a digit for it.
    result2 = normalize_plate("GJ01AB-234")
    assert result2.normalized == "GJ01AB234"
    assert result2.valid is False


def test_strip_is_lossless_uppercase():
    assert strip_to_alnum(" gj 01 ab 1234 ") == "GJ01AB1234"
    assert strip_to_alnum("GJ-01-AB-1234") == "GJ01AB1234"


def test_plate_score_orders_valid_over_invalid():
    good = normalize_plate("GJ01AB1234")
    bad = normalize_plate("XY12")
    assert plate_score(good) > plate_score(bad)
    assert is_plausible_indian_plate("MH12XY9999") is True
    assert is_plausible_indian_plate("HELLO") is False


# ---------------------------------------------------------------------------
# confidence
# ---------------------------------------------------------------------------


def test_grading_boundaries():
    assert grade_confidence(0.9) == "high"
    assert grade_confidence(0.6) == "medium"
    assert grade_confidence(0.2) == "low"
    assert is_low_confidence(0.5) is True
    assert is_low_confidence(0.6) is False


def test_multi_frame_combine_boosts_agreement():
    combined = combine_confidences([0.81, 0.91, 0.95])
    assert 0.9 <= combined <= 0.96


# ---------------------------------------------------------------------------
# aggregator
# ---------------------------------------------------------------------------


def test_two_agreeing_reads_emit():
    agg = TrackPlateAggregator()
    agg.add(1, "GJ01AB1234", "GJ 01 AB 1234", 0.8, 100.0)
    assert agg.should_emit(1) is False  # one weak read is not enough
    agg.add(1, "GJ01AB1234", "GJ01AB1234", 0.9, 200.0)
    assert agg.should_emit(1) is True
    consumed = agg.consume(1)
    assert consumed.top_normalized == "GJ01AB1234"
    assert consumed.top_count == 2


def test_single_very_confident_read_emits_immediately():
    agg = TrackPlateAggregator()
    agg.add(5, "GJ05XY4321", "GJ05XY4321", 0.95, 10.0)
    assert agg.should_emit(5) is True


def test_conflicting_reads_do_not_emit():
    agg = TrackPlateAggregator()
    agg.add(7, "GJ01AB1234", "a", 0.6, 1.0)
    agg.add(7, "GJ05XY4321", "b", 0.6, 2.0)
    assert agg.should_emit(7) is False  # agreement too low


# ---------------------------------------------------------------------------
# plate detector + OCR (real engine, synthetic plate)
# ---------------------------------------------------------------------------


def _plate_image(text="GJ01AB1234"):
    img = np.full((90, 360, 3), 245, np.uint8)
    import cv2

    cv2.putText(img, text, (12, 62), cv2.FONT_HERSHEY_SIMPLEX, 1.5, (15, 15, 15), 3, cv2.LINE_AA)
    return img


def test_plate_detector_reads_a_real_synthetic_plate(settings):
    engine = get_ocr_engine(settings)
    assert engine is not None, "expected an offline OCR engine to be available"
    detector = PlateDetector(settings, engine)
    candidate = detector.best(_plate_image())
    assert candidate is not None
    assert strip_to_alnum(candidate.raw_text) == "GJ01AB1234"
    assert candidate.confidence > settings.anpr_conf_threshold


def test_plate_detector_returns_nothing_on_blank(settings):
    detector = PlateDetector(settings, RapidOcrEngine())
    assert detector.best(np.full((100, 300, 3), 120, np.uint8)) is None
