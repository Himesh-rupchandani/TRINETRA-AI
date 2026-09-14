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

Also serves evidence from manually-uploaded videos (uploads/<camera>/...)
and multi-video analysis (analysis/<camera>/...).
"""
import logging
import urllib.parse
from pathlib import Path

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import FileResponse

from ..core.paths import evidence_root

logger = logging.getLogger("trinetra")

router = APIRouter(prefix="/evidence", tags=["Evidence"])

_ALLOWED_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}


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
    # URL decode the ref (frontend encodes each segment)
    try:
        ref = urllib.parse.unquote(ref)
    except Exception:
        pass

    if not ref or ref.startswith(("/", "\\")) or ".." in Path(ref).parts:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Invalid evidence reference.")

    # Strip any leading whitespace or control chars
    ref = ref.strip()
    if not ref:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Empty evidence reference.")

    suffix = Path(ref).suffix.lower()
    if suffix not in _ALLOWED_SUFFIXES:
        raise HTTPException(
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Unsupported evidence type '{suffix}'. Allowed: {', '.join(sorted(_ALLOWED_SUFFIXES))}",
        )

    # Ensure root exists — create=True guarantees the folder exists even on first run
    try:
        root = evidence_root(create=True)
    except Exception as exc:
        logger.error(f"Could not resolve evidence root: {exc}")
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Evidence storage unavailable.")

    # Resolve safely
    try:
        target = (root / ref).resolve()
        # Ensure target is inside root (prevent path traversal)
        target.relative_to(root.resolve())
    except ValueError:
        logger.warning(f"Path traversal attempt blocked: {ref}")
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Invalid evidence reference.")
    except Exception as exc:
        logger.warning(f"Invalid evidence path {ref}: {exc}")
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Invalid evidence reference.")

    if not target.is_file():
        # Provide helpful hint about where we looked
        logger.info(f"Evidence not found: {ref} -> looked at {target}, root {root}")
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=f"Evidence '{ref}' not found. Checked {root / ref}")

    media_type = "image/png" if suffix == ".png" else "image/webp" if suffix == ".webp" else "image/jpeg"
    return FileResponse(
        target,
        media_type=media_type,
        headers={
            "Cache-Control": "public, max-age=3600",
            "Access-Control-Allow-Origin": "*",
        },
    )
