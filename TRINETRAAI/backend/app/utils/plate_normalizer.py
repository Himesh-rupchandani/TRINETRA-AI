import re
from typing import Optional


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
