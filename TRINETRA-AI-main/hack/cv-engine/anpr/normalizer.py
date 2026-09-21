"""
Plate normalization at the CV stage (spec §17).

Rules mirror the backend's normalize_plate() exactly so CV-side and
backend-side normalization always agree:
- uppercase
- strip whitespace
- remove all non-alphanumeric characters

We NEVER silently invent corrections: normalization only removes formatting
noise. The raw OCR string is always preserved alongside the normalized one.
"""
from __future__ import annotations

import re
from typing import Optional

_NON_ALNUM = re.compile(r"[^A-Z0-9]")

# Canonical Indian plate pattern — MUST stay byte-identical to the backend
# definition in TRINETRAAI/backend/app/utils/plate_normalizer.py
# (CANONICAL_PLATE_PATTERN) and the frontend one in trinetra-ai/src/lib/utils.ts
# (INDIAN_PLATE_PATTERN). backend/tests/test_plate_format_consistency.py fails
# the build if any of the three layers drifts.
#
#   SS  DD  L{1,3}  N{3,4}      e.g. GJ01AB1234, MH02CD5678, KA05XY9999
#
# Two state letters, RTO digits (two today, one on legacy plates), at least one
# series letter (a letterless "GJ011234" is not a plate) and a 3-4 digit number.
CANONICAL_PLATE_PATTERN = r"^[A-Z]{2}[0-9]{1,2}[A-Z]{1,3}[0-9]{3,4}$"
_INDIAN_PLATE = re.compile(CANONICAL_PLATE_PATTERN)
# Generic fallback: mostly alnum, 6..12 chars
_GENERIC_PLATE = re.compile(r"^[A-Z0-9]{6,12}$")


def normalize_plate(plate_raw: Optional[str]) -> str:
    """Normalize an OCR plate string. '' for None/empty."""
    if not plate_raw:
        return ""
    normalized = plate_raw.upper().strip()
    normalized = _NON_ALNUM.sub("", normalized)
    return normalized


def is_indian_plate_format(plate_normalized: str) -> bool:
    """True when the normalized string matches the standard Indian plate layout."""
    return bool(_INDIAN_PLATE.match(plate_normalized or ""))


def plate_format_score(plate_normalized: str) -> float:
    """
    1.0 = matches Indian plate pattern, 0.5 = plausible generic plate,
    0.0 = not plate-like. Used as a soft multiplier on OCR confidence —
    it never upgrades a reading, only discounts implausible strings.
    """
    if not plate_normalized:
        return 0.0
    if _INDIAN_PLATE.match(plate_normalized):
        return 1.0
    if _GENERIC_PLATE.match(plate_normalized):
        return 0.5
    return 0.0


def candidate_from_ocr_text(text: str) -> Optional[str]:
    """
    Given one OCR text line, return a normalized plate candidate or None.
    Discards strings that are obviously not plates (too short/long, symbols
    only, mostly letters with no digits, etc.).
    """
    if not text:
        return None
    norm = normalize_plate(text)
    if len(norm) < 6 or len(norm) > 12:
        return None
    if not any(ch.isdigit() for ch in norm):
        return None
    if not any(ch.isalpha() for ch in norm):
        return None
    return norm
