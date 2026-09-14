"""Canonical Indian plate format — ONE definition across all three layers.

Regression guard for the fix that unified plate validation: cv-engine
(``cv-engine/anpr/normalizer.py``), the backend
(``app/utils/plate_normalizer.py``) and the frontend
(``trinetra-ai/src/lib/utils.ts``) used to carry three *different* patterns, so
the same OCR string could be canonical for one layer and invalid for another —
a plate the UI refused to search for was already stored as ``HIGH`` confidence
by the pipeline (and vice versa).

These tests fail the build the moment any layer drifts.
"""
import re
import sys
from pathlib import Path

import pytest

from app.utils.plate_normalizer import (
    CANONICAL_PLATE_PATTERN,
    LOOSE_PLATE_PATTERN,
    is_indian_plate,
    normalize_plate,
    pretty_plate,
)

# tests/ -> backend/ -> TRINETRAAI/ -> repository root
REPO_ROOT = Path(__file__).resolve().parents[3]
CV_NORMALIZER = REPO_ROOT / "cv-engine" / "anpr" / "normalizer.py"
FE_UTILS = REPO_ROOT / "trinetra-ai" / "src" / "lib" / "utils.ts"

CANONICAL = [
    "GJ01AB1234",       # standard: state, RTO, series, 4-digit number
    "GJ 01 AB-1234",    # formatting noise only
    "mh-02 cd 5678",    # lowercase + separators
    "DL08EF9012",
    "KA05XYZ999",       # 3-letter series, 3-digit number
    "GJ1AB1234",        # legacy single-digit RTO
    "UP32BX7589",
]

NOT_CANONICAL = [
    "",
    "GJ011234",         # no series letters — not an Indian plate
    "GJ1A2",            # number too short
    "GJ01AB12",         # number too short
    "GJ01ABCD1234",     # series too long
    "GJ001AB1234",      # RTO too long
    "1234567890",       # no state letters
    "GJAB1234",         # no RTO digits
    "??? ???",
]


def _read(path: Path) -> str:
    if not path.exists():
        pytest.skip(f"sibling layer not present in this checkout: {path}")
    return path.read_text(encoding="utf-8")


def test_cv_engine_uses_the_identical_pattern():
    """cv-engine's canonical pattern must be byte-identical to the backend's."""
    text = _read(CV_NORMALIZER)
    m = re.search(r'CANONICAL_PLATE_PATTERN\s*=\s*r?"([^"]+)"', text)
    assert m, "cv-engine no longer declares CANONICAL_PLATE_PATTERN"
    assert m.group(1) == CANONICAL_PLATE_PATTERN, (
        f"cv-engine pattern {m.group(1)!r} != backend {CANONICAL_PLATE_PATTERN!r}"
    )


def test_frontend_uses_the_identical_pattern():
    """The UI validator must accept exactly what the backend accepts."""
    text = _read(FE_UTILS)
    m = re.search(r"INDIAN_PLATE_PATTERN\s*=\s*'([^']+)'", text)
    assert m, "frontend no longer declares INDIAN_PLATE_PATTERN"
    assert m.group(1) == CANONICAL_PLATE_PATTERN, (
        f"frontend pattern {m.group(1)!r} != backend {CANONICAL_PLATE_PATTERN!r}"
    )


def test_all_layers_strip_the_same_characters():
    """Normalization parity: same character class, same uppercase-first order."""
    cv = _read(CV_NORMALIZER)
    fe = _read(FE_UTILS)
    assert 're.compile(r"[^A-Z0-9]")' in cv
    assert "replace(/[^A-Z0-9]/g, '')" in fe
    assert 're.sub(r"[^A-Z0-9]", "", normalized)' in Path(
        REPO_ROOT / "TRINETRAAI" / "backend" / "app" / "utils" / "plate_normalizer.py"
    ).read_text(encoding="utf-8")


def test_cv_engine_and_backend_agree_on_every_sample():
    """Cross-layer behaviour, not just cross-layer source text."""
    if not CV_NORMALIZER.exists():
        pytest.skip("cv-engine not present in this checkout")
    cv_root = str(CV_NORMALIZER.parents[1])
    sys.path.insert(0, cv_root)
    try:
        from anpr.normalizer import is_indian_plate_format  # type: ignore
    finally:
        sys.path.remove(cv_root)

    for sample in CANONICAL + NOT_CANONICAL:
        normalized = normalize_plate(sample)
        assert is_indian_plate(sample) is is_indian_plate_format(normalized), (
            f"backend and cv-engine disagree on {sample!r}"
        )


def test_canonical_plates_are_accepted():
    for sample in CANONICAL:
        assert is_indian_plate(sample), sample


def test_non_canonical_plates_are_rejected():
    for sample in NOT_CANONICAL:
        assert not is_indian_plate(sample), sample


def test_pretty_plate_splits_only_canonical_plates():
    """The display formatter must never half-split a malformed read."""
    assert pretty_plate("GJ01AB1234") == "GJ 01 AB 1234"
    assert pretty_plate("gj 01 ab 1234") == "GJ 01 AB 1234"
    assert pretty_plate("GJ1AB1234") == "GJ 01 AB 1234"   # RTO padded for display
    # Not canonical -> normalized but unsplit (the old UI printed "GJ 01 1234").
    assert pretty_plate("GJ011234") == "GJ011234"
    assert pretty_plate("GJ01AB12") == "GJ01AB12"
    assert pretty_plate("") == ""


def test_loose_tier_never_promotes_to_canonical():
    """The plausible-but-not-canonical tier stays strictly weaker."""
    loose = re.compile(LOOSE_PLATE_PATTERN)
    assert loose.match("GJ01ABCD1234")          # Bharat/odd series: plausible
    assert not is_indian_plate("GJ01ABCD1234")  # ...but never canonical
    assert is_indian_plate("GJ01AB1234") and loose.match("GJ01AB1234")
