"""
Filesystem path resolution — ONE authority for every backend data directory.

Historically each module resolved ``EVIDENCE_ROOT`` on its own:

* ``app/api/evidence.py`` used ``Path(settings.EVIDENCE_ROOT).resolve()``, which
  is relative to the **current working directory**;
* ``main.py`` and the video services anchored the same relative value to the
  **backend root**.

Both are "correct" in isolation, so whenever uvicorn was started from anywhere
other than ``TRINETRAAI/backend`` the API looked for evidence crops in a
different tree than the one the pipeline wrote them to, and every
``GET /api/evidence/{ref}`` answered 404.

Everything now goes through this module: relative configured paths are anchored
to the backend root, absolute paths stay absolute, and the read side (API) and
the write side (pipelines) are guaranteed to agree regardless of CWD.
"""
from __future__ import annotations

from pathlib import Path

from .config import settings

# app/core/paths.py -> parents[0]=core, parents[1]=app, parents[2]=backend root
BACKEND_ROOT: Path = Path(__file__).resolve().parents[2]


def resolve_data_path(raw: str | Path, *, create: bool = False) -> Path:
    """Resolve a configured path deterministically.

    * absolute paths are returned unchanged (normalized);
    * relative paths are anchored to the backend root — never to the process
      CWD, which depends on how the server was launched.
    """
    p = Path(raw).expanduser()
    resolved = p if p.is_absolute() else (BACKEND_ROOT / p)
    resolved = resolved.resolve()
    if create:
        resolved.mkdir(parents=True, exist_ok=True)
    return resolved


def evidence_root(*, create: bool = True) -> Path:
    """Root of the detection-crop tree served by ``GET /api/evidence/{ref}``."""
    return resolve_data_path(settings.EVIDENCE_ROOT, create=create)


def upload_root(*, create: bool = True) -> Path:
    """Manually-uploaded CCTV videos (``POST /api/uploads/videos``)."""
    return resolve_data_path(getattr(settings, "UPLOAD_DIR", "uploads"), create=create)


def analysis_root(*, create: bool = True) -> Path:
    """Downloaded / uploaded videos for the multi-video analysis pipeline."""
    return resolve_data_path(getattr(settings, "ANALYSIS_DIR", "uploads/analysis"), create=create)


def model_path(raw: str | Path) -> Path:
    """Resolve a configured model-weights path against the backend root."""
    return resolve_data_path(raw, create=False)
