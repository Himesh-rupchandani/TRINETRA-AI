"""
Plate normalization at the CV stage (spec §17).

Rules mirror the backend's normalize_plate() exactly so CV-side and
backend-side normalization always agree:
- uppercase
- strip whitespace
- remove all non-alphanumeric characters
- strip HSRP IND/INDIA country prefixes
- disambiguate common optical OCR character confusions in Indian plates

We preserve the raw OCR string alongside the normalized one.
"""
from __future__ import annotations

import re
from typing import Optional

_NON_ALNUM = re.compile(r"[^A-Z0-9]")

# Indian plate pattern: 2 letters (state) + 2 digits + 1-4 letters + 3-4 digits
# e.g. GJ01AB1234, MH02CD5678, KA05XY9999
# Canonical Indian plate pattern — MUST stay identical to
# cv-engine/anpr/normalizer.py and app/utils/plate_normalizer.py
# (guarded by tests/test_plate_format_consistency.py).
_INDIAN_PLATE = re.compile(r"^[A-Z]{2}[0-9]{1,2}[A-Z]{1,3}[0-9]{3,4}$")
# Generic fallback: mostly alnum, 6..12 chars
_GENERIC_PLATE = re.compile(r"^[A-Z0-9]{6,12}$")

# Indian State & Union Territory codes
_INDIAN_STATES = {
    "AN", "AP", "AR", "AS", "BR", "CG", "CH", "DD", "DL", "DN",
    "GA", "GJ", "HP", "HR", "JH", "JK", "KA", "KL", "LA", "LD",
    "MH", "ML", "MN", "MP", "MZ", "NL", "OD", "PB", "PY", "RJ",
    "SK", "TN", "TR", "TS", "UK", "UP", "WB", "BH",
}

_LETTER_TO_DIGIT = {
    "O": "0", "Q": "0", "D": "0",
    "I": "1", "L": "1",
    "Z": "2",
    "S": "5",
    "B": "8",
}


def normalize_plate(plate_raw: Optional[str]) -> str:
    """Normalize an OCR plate string. '' for None/empty."""
    if not plate_raw:
        return ""
    normalized = plate_raw.upper().strip()
    normalized = _NON_ALNUM.sub("", normalized)
    if not normalized:
        return ""

    # Strip HSRP blue strip IND / INDIA prefix
    if normalized.startswith("INDIA") and len(normalized) >= 11:
        normalized = normalized[5:]
    elif normalized.startswith("IND") and len(normalized) >= 9:
        normalized = normalized[3:]

    # Optical character disambiguation for standard Indian plates
    n = len(normalized)
    if 8 <= n <= 11 and (normalized[:2] in _INDIAN_STATES):
        chars = list(normalized)
        rto_plausible = (
            (chars[2].isdigit() or chars[2] in _LETTER_TO_DIGIT) and
            (chars[3].isdigit() or chars[3] in _LETTER_TO_DIGIT)
        )
        if rto_plausible:
            if chars[2] in _LETTER_TO_DIGIT:
                chars[2] = _LETTER_TO_DIGIT[chars[2]]
            if chars[3] in _LETTER_TO_DIGIT:
                chars[3] = _LETTER_TO_DIGIT[chars[3]]

            # Last 3 or 4 positions must be registration digits
            for i in range(max(4, n - 4), n):
                if chars[i] in _LETTER_TO_DIGIT:
                    chars[i] = _LETTER_TO_DIGIT[chars[i]]

            normalized = "".join(chars)

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
