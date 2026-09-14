"""One canonical Indian registration-plate definition for the whole backend.

The plate format used to be re-declared in three places with three *different*
patterns (``anpr_pipeline.INDIAN_PLATE_RE``, ``ocr_service._INDIAN_PLATE`` and
the frontend's ``isValidPlate``), so the same OCR string could be "canonical"
for the pipeline, "implausible" for the OCR stage and "invalid" for the UI.

Canonical civilian layout (MoRTH / HSRP)::

    SS  DD  L{1,3}  N{3,4}      e.g. GJ 01 AB 1234, MH 02 CD 5678

* ``SS``  two-letter state/UT code
* ``DD``  RTO code — two digits today, one digit on legacy plates
* ``L``   series letters, at least one (a letterless "GJ011234" is not a plate)
* ``N``   unique number, four digits today, three on legacy plates

cv-engine (``cv-engine/anpr/normalizer.py``) and the frontend
(``trinetra-ai/src/lib/utils.ts``) carry the same pattern verbatim;
``tests/test_plate_format_consistency.py`` fails if any layer drifts.
"""
import re
from typing import Optional

# Canonical Indian civilian plate, applied to an already-normalized string.
CANONICAL_PLATE_PATTERN = r"^[A-Z]{2}[0-9]{1,2}[A-Z]{1,3}[0-9]{3,4}$"
INDIAN_PLATE_RE = re.compile(CANONICAL_PLATE_PATTERN)

# Plausible-but-not-canonical tier (Bharat series, defence, diplomatic, OCR
# noise that still looks plate-shaped). Used only to *discount* confidence —
# never to promote a reading to canonical.
LOOSE_PLATE_PATTERN = r"^[A-Z]{2}[0-9]{2}[A-Z0-9]{4,8}$"
LOOSE_PLATE_RE = re.compile(LOOSE_PLATE_PATTERN)


def normalize_plate(plate_raw: Optional[str]) -> str:
    """
    Reusable vehicle license plate normalization function.
    
    Rules:
    - Uppercase
    - Strip leading/trailing whitespace
    - Remove all internal whitespace, hyphens, dots, underscores, and special punctuation
    - Preserves original raw OCR string separately
    
    Examples:
        "GJ 01 AB-1234"  -> "GJ01AB1234"
        "mh-02 cd 5678"  -> "MH02CD5678"
        "DL.08-EF_9012"  -> "DL08EF9012"
        "  ka 05   xy 9999 " -> "KA05XY9999"
    """
    if not plate_raw:
        return ""
    
    # Uppercase
    normalized = plate_raw.upper().strip()
    
    # Remove all non-alphanumeric characters (spaces, hyphens, dots, underscores, etc.)
    normalized = re.sub(r"[^A-Z0-9]", "", normalized)
    
    return normalized


def is_indian_plate(plate: Optional[str]) -> bool:
    """True when a plate (raw or already normalized) is canonically formatted."""
    return bool(INDIAN_PLATE_RE.match(normalize_plate(plate)))


def pretty_plate(plate: Optional[str]) -> str:
    """Display form of a canonical plate: ``GJ01AB1234`` -> ``GJ 01 AB 1234``.

    Non-canonical input is returned normalized-but-unsplit, so the UI never
    shows a half-split plate such as "GJ 01 1234" for a malformed read.
    """
    normalized = normalize_plate(plate)
    match = re.match(r"^([A-Z]{2})([0-9]{1,2})([A-Z]{1,3})([0-9]{3,4})$", normalized)
    if not match:
        return normalized or (plate or "")
    state, rto, series, number = match.groups()
    return f"{state} {rto.zfill(2)} {series} {number}"
