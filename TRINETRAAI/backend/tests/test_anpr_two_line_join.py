"""
Two-line number-plate OCR joining (Indian motorcycle plates).

Neither line of a two-line plate is a valid plate by itself
("GJ01" / "AB1234"), so per-line candidate filtering alone can never read it.
``read_plate_for_vehicle`` must concatenate the stacked lines. The plate
region proposer and OCR engine are stubbed; the joining logic under test is
the real pipeline code.
"""
import sys
from pathlib import Path

for _p in [str(Path(__file__).resolve().parents[1])]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

import numpy as np
import pytest

from app.services import anpr_pipeline
from app.services.ocr_service import ocr_service
from app.services.plate_detector_service import PlateBox, plate_detector_service

FRAME = np.full((200, 300, 3), 128, dtype=np.uint8)


def _stub(monkeypatch, lines):
    monkeypatch.setattr(
        plate_detector_service, "detect",
        lambda frame, bbox, vehicle_class="car", max_candidates=2: [
            PlateBox(x1=10, y1=10, x2=150, y2=60, confidence=0.9, source="model"),
        ],
    )
    calls = {"n": 0}

    def fake_read_lines(image):
        calls["n"] += 1
        if calls["n"] % 3 == 1:  # first preprocessing variant of each crop
            return lines
        return []

    monkeypatch.setattr(ocr_service, "read_lines", fake_read_lines)
    monkeypatch.setattr(ocr_service, "_engine", object())
    monkeypatch.setattr(ocr_service, "_attempted", True)


def test_two_line_plate_is_joined_to_canonical(monkeypatch):
    _stub(monkeypatch, [("GJ01", 0.95), ("AB1234", 0.97)])
    read = anpr_pipeline.read_plate_for_vehicle(FRAME, (0, 0, 300, 200), "motorcycle")
    assert read is not None, "a two-line plate must be readable"
    assert read.normalized == "GJ01AB1234"
    assert read.indian_format is True
    assert read.raw.replace(" ", "") == "GJ01AB1234"
    # joined confidence is bounded by the weaker line, above the trust floor
    assert 0.80 <= read.confidence <= 0.97


def test_five_digit_registration_reads_as_loose_low_confidence(monkeypatch):
    """Real motorcycle plates with 5-digit numbers are kept, but never HIGH."""
    _stub(monkeypatch, [("GJ03P", 0.95), ("08586", 0.97)])
    read = anpr_pipeline.read_plate_for_vehicle(FRAME, (0, 0, 300, 200), "motorcycle")
    assert read is not None
    assert read.normalized == "GJ03P08586"
    assert read.indian_format is False          # not canonical Indian layout
    assert read.confidence < 0.80               # discounted -> LOW_CONFIDENCE
    assert read.confidence >= 0.60              # still kept, searchable, flagged


def test_single_line_plate_still_reads_without_joining(monkeypatch):
    """A complete one-line plate must behave exactly as before the join."""
    _stub(monkeypatch, [("GJ01AB1234", 0.96)])
    read = anpr_pipeline.read_plate_for_vehicle(FRAME, (0, 0, 300, 200), "car")
    assert read is not None
    assert read.normalized == "GJ01AB1234"
    assert read.indian_format is True


def test_two_garbage_lines_do_not_fabricate_a_plate(monkeypatch):
    """Joining must not turn non-plate fragments into a plate."""
    _stub(monkeypatch, [("EXIT", 0.9), ("42", 0.9)])
    read = anpr_pipeline.read_plate_for_vehicle(FRAME, (0, 0, 300, 200), "car")
    # "EXIT42" is not a plausible layout; the discounted confidence stays
    # below the reject threshold, so nothing is reported.
    assert read is None
