"""
Evidence Endpoints
==================
Serves the cropped detection imagery captured by the CV engine's
EvidenceWriter so operators can view exactly what the AI saw when an
event was raised.

The CV engine stores evidence as JPEG crops under a root directory
(``cv-engine/evidence`` by default) and references them relatively in each
event's ``evidence_ref`` (e.g. ``camd01/camd01_13133_4754ms_unknown.jpg``).
This router maps that reference to a safe absolute path inside the
configured root and streams the file.
"""
import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import FileResponse

from ..core.config import settings

logger = logging.getLogger("trinetra")

router = APIRouter(prefix="/evidence", tags=["Evidence"])

_ALLOWED_SUFFIXES = {".jpg", ".jpeg", ".png"}


@router.get(
    "/{ref:path}",
    response_class=FileResponse,
    summary="Fetch detection evidence imagery",
    description=(
        "Streams the JPEG crop the CV engine stored for an event. The "
        "reference is the event's ``evidence_ref``; paths are confined to "
        "the configured evidence root."
    ),
)
def get_evidence(ref: str):
    """Serve one evidence file, safely rooted."""
    if not ref or ref.startswith(("/", "\\")) or ".." in Path(ref).parts:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Invalid evidence reference.")

    suffix = Path(ref).suffix.lower()
    if suffix not in _ALLOWED_SUFFIXES:
        raise HTTPException(
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail="Unsupported evidence type."
        )

    root = Path(settings.EVIDENCE_ROOT).resolve()
    target = (root / ref).resolve()
    try:
        target.relative_to(root)
    except ValueError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Invalid evidence reference.")

    if not target.is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=f"Evidence '{ref}' not found.")

    media_type = "image/png" if suffix == ".png" else "image/jpeg"
    return FileResponse(target, media_type=media_type)
