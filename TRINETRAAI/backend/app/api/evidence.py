"""
Evidence delivery
=================
Serves the CCTV frame and plate crop that back a vehicle event (spec §15).

The CV engine writes evidence as `<camera>/<camera>_<track>_<pts>ms_<plate>.jpg`
and stores that relative path on the event as `evidence_ref`. This endpoint
resolves that reference to a file on disk.

Security: `evidence_ref` originates from OCR output, so it is untrusted. Every
request is resolved against the evidence root and rejected if it escapes it,
which makes path traversal (`../../etc/passwd`) impossible.
"""
import os
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import FileResponse

from ..core.config import settings
from ..core.logging_config import logger

router = APIRouter(prefix="/evidence", tags=["Evidence"])


def _evidence_root() -> Path:
    """Absolute evidence root, configurable via EVIDENCE_DIR."""
    configured = os.getenv("EVIDENCE_DIR") or getattr(settings, "EVIDENCE_DIR", None)
    if configured:
        return Path(configured).resolve()
    # Default: the cv-engine writes here in the standard checkout layout
    # (<repo>/cv-engine/evidence, with this file at
    #  <repo>/TRINETRAAI/backend/app/api/evidence.py).
    return (Path(__file__).resolve().parents[4] / "cv-engine" / "evidence").resolve()


def _resolve(ref: str) -> Path:
    root = _evidence_root()
    candidate = (root / ref).resolve()
    if not candidate.is_relative_to(root):
        logger.warning("[EVIDENCE] Rejected traversal attempt for ref=%r", ref)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid evidence reference.",
        )
    return candidate


@router.get(
    "",
    summary="Fetch evidence image",
    description=(
        "Returns the CCTV frame for an event's `evidence_ref`, or the ANPR "
        "plate crop when `variant=plate`."
    ),
)
def get_evidence(
    ref: str = Query(..., description="Relative evidence reference from the event"),
    variant: str = Query("frame", pattern="^(frame|plate)$"),
):
    path = _resolve(ref)

    if variant == "plate":
        path = path.with_name(f"{path.stem}_plate{path.suffix}")

    if not path.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Evidence not retained for this event.",
        )

    return FileResponse(path, media_type="image/jpeg")
