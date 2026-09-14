"""Plate normalization (spec §17) + equivalence with the backend normalizer."""
import sys
from pathlib import Path

from anpr.normalizer import (
    candidate_from_ocr_text,
    is_indian_plate_format,
    normalize_plate,
    plate_format_score,
)

BACKEND = Path(__file__).resolve().parents[2] / "TRINETRAAI" / "backend"


def test_normalize_plate_spec_examples():
    assert normalize_plate("GJ 01 AB-1234") == "GJ01AB1234"
    assert normalize_plate("mh-02 cd 5678") == "MH02CD5678"
    assert normalize_plate("DL.08-EF_9012") == "DL08EF9012"
    assert normalize_plate("  ka 05   xy 9999 ") == "KA05XY9999"


def test_normalize_plate_edge_cases():
    assert normalize_plate(None) == ""
    assert normalize_plate("") == ""
    assert normalize_plate("!!!") == ""
    # normalization never invents characters — only removes formatting
    assert normalize_plate("GJ0?AB1234") == "GJ0AB1234"


def test_matches_backend_normalizer_exactly():
    """CV-stage normalization must agree with the backend's, field-for-field."""
    sys.path.insert(0, str(BACKEND))
    try:
        from app.utils.plate_normalizer import normalize_plate as backend_normalize
    finally:
        sys.path.pop(0)

    cases = [
        "GJ 01 AB-1234", "mh-02 cd 5678", "DL.08-EF_9012", "ka 05 xy 9999",
        "gj01ab1234", "GJ-01-AB-1234", "", None, "  GJ 01 AB 1234  ",
        "UP32BX7589", "RJ27 UB 6043",
    ]
    for c in cases:
        assert normalize_plate(c) == backend_normalize(c), f"mismatch for {c!r}"


def test_indian_plate_format():
    assert is_indian_plate_format("GJ01AB1234")
    assert is_indian_plate_format("MH02CD5678")
    assert not is_indian_plate_format("GJ01AB12")      # too few digits
    assert not is_indian_plate_format("1234567890")    # no state letters
    assert not is_indian_plate_format("")


def test_format_score_never_upgrades():
    assert plate_format_score("GJ01AB1234") == 1.0
    assert plate_format_score("AB12345") == 0.5   # generic
    assert plate_format_score("???") == 0.0
    assert plate_format_score("") == 0.0


def test_candidate_from_ocr_text_filters_garbage():
    assert candidate_from_ocr_text("GJ 01 AB-1234") == "GJ01AB1234"
    assert candidate_from_ocr_text("No Parking") is None     # mostly letters no digits pattern fails len? has no digits
    assert candidate_from_ocr_text("12345") is None          # too short
    assert candidate_from_ocr_text("1234567890123") is None  # too long
    assert candidate_from_ocr_text("ABCDEFGH") is None       # no digits
    assert candidate_from_ocr_text("12345678") is None       # no letters
    assert candidate_from_ocr_text("") is None
