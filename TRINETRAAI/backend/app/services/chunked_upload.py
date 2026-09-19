"""
Chunked upload service — bypasses Vercel's hard 4.5 MB serverless-function
body limit by splitting files into ~3 MB chunks on the client, posting each
one individually to `/uploads/chunks`, and assembling them server-side when
the final chunk arrives.

Flow (per file):
  1. POST /uploads/chunks/init          -> upload_id
  2. POST /uploads/chunks/{upload_id}   (repeated, with chunk_number, total, data)
     - every chunk is <4 MB so it sails straight through Vercel's proxy
     - chunks are appended to a temp file in upload_root()/._chunks/
  3. Final chunk triggers: validate size, assemble (no copies needed — we
     write straight to the final path), return Path + metadata.

Works for both the single-video `/api/uploads/videos` endpoint and the
multi-video `/api/analysis/videos/upload` endpoint. The legacy multipart
endpoints are kept and automatically fall back to chunked assembly when a
client signals it via `X-Upload-Id`.
"""
from __future__ import annotations

import os
import re
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Optional

from fastapi import HTTPException, status
try:
    _413 = status.HTTP_413_CONTENT_TOO_LARGE  # Starlette/FastAPI >= 0.110
except AttributeError:  # pragma: no cover - backwards compat
    _413 = _413

from ..core.config import settings
from ..core.logging_config import logger
from ..core.paths import upload_root

# Each chunk must comfortably fit under Vercel's 4.5 MB serverless-function
# body cap. Headers/FormData overhead eats a few hundred KB, so leave headroom.
CHUNK_SIZE_BYTES = 3 * 1024 * 1024           # 3 MB per chunk — safe under 4.5 MB
MAX_CHUNK_AGE_SECONDS = 24 * 60 * 60        # abandon sessions older than a day
CHUNK_SESSIONS_DIRNAME = "._chunks"

_lock = threading.Lock()
_sessions: Dict[str, "ChunkSession"] = {}


def _sessions_dir() -> Path:
    d = upload_root() / CHUNK_SESSIONS_DIRNAME
    d.mkdir(parents=True, exist_ok=True)
    return d


def _safe_filename(name: str) -> str:
    base = os.path.basename(name or "upload.mp4")
    base = re.sub(r"[^A-Za-z0-9._-]+", "_", base).strip("._") or "upload.mp4"
    return base[:160]


def _max_bytes() -> int:
    return int(settings.MAX_UPLOAD_SIZE_MB) * 1024 * 1024


@dataclass
class ChunkSession:
    upload_id: str
    filename: str
    total_chunks: int
    total_size: int
    part_path: Path
    received: set = field(default_factory=set)
    bytes_written: int = 0
    created_at: float = field(default_factory=time.time)
    camera_id: Optional[str] = None
    name: Optional[str] = None
    location: Optional[str] = None
    source: str = "upload"           # "upload" | "analysis"
    camera_ids_csv: Optional[str] = None
    batch_id: Optional[str] = None
    auto_start: bool = False
    finalized: bool = False

    @property
    def safe_name(self) -> str:
        return _safe_filename(self.filename)

    @property
    def complete(self) -> bool:
        return len(self.received) >= self.total_chunks and self.total_chunks > 0


# ---------------------------------------------------------------- session mgmt


def _gc() -> None:
    """Drop abandoned/expired sessions and their orphaned part files."""
    cutoff = time.time() - MAX_CHUNK_AGE_SECONDS
    stale = [uid for uid, s in _sessions.items() if s.created_at < cutoff or s.finalized]
    for uid in stale:
        s = _sessions.pop(uid, None)
        if s is None:
            continue
        try:
            s.part_path.unlink(missing_ok=True)
        except OSError:
            pass


def init_session(
    filename: str,
    total_chunks: int,
    total_size: int,
    *,
    source: str = "upload",
    camera_id: Optional[str] = None,
    name: Optional[str] = None,
    location: Optional[str] = None,
    camera_ids_csv: Optional[str] = None,
    batch_id: Optional[str] = None,
    auto_start: bool = False,
) -> ChunkSession:
    if total_chunks < 1 or total_chunks > 10_000:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid total_chunks={total_chunks}.",
        )
    if total_size <= 0 or total_size > _max_bytes():
        raise HTTPException(
            _413,
            detail=f"Video exceeds the {settings.MAX_UPLOAD_SIZE_MB} MB upload limit.",
        )
    safe = _safe_filename(filename)
    suffix = Path(safe).suffix.lower()
    # suffix validation is deferred until finalize so chunk init is cheap
    upload_id = uuid.uuid4().hex
    part_path = _sessions_dir() / f"{upload_id}.part"
    # Ensure any old .part is gone before we start appending fresh chunks.
    try:
        part_path.unlink(missing_ok=True)
    except OSError:
        pass
    part_path.touch()
    sess = ChunkSession(
        upload_id=upload_id,
        filename=safe,
        total_chunks=int(total_chunks),
        total_size=int(total_size),
        part_path=part_path,
        source=source,
        camera_id=camera_id,
        name=name,
        location=location,
        camera_ids_csv=camera_ids_csv,
        batch_id=batch_id,
        auto_start=bool(auto_start),
    )
    with _lock:
        _gc()
        _sessions[upload_id] = sess
    logger.info(f"[CHUNK:{upload_id}] init {safe} {total_chunks} chunks, {total_size} bytes")
    return sess


def get_session(upload_id: str) -> ChunkSession:
    with _lock:
        _gc()
        s = _sessions.get(upload_id)
    if s is None or s.finalized:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Upload session not found (it may have expired).")
    return s


def append_chunk(upload_id: str, chunk_number: int, data: bytes) -> dict:
    """Append one chunk to the part file. Returns session progress."""
    if chunk_number < 0:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Invalid chunk_number.")
    sess = get_session(upload_id)
    if chunk_number >= sess.total_chunks:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="chunk_number past total_chunks.")
    # Reject duplicates — the client retries, we just idempotently accept.
    with _lock:
        if chunk_number in sess.received:
            return {
                "upload_id": upload_id,
                "chunk_number": chunk_number,
                "received": len(sess.received),
                "total_chunks": sess.total_chunks,
                "bytes_received": sess.bytes_written,
                "done": sess.complete,
            }
        # Enforce total-size cap as we write, even before the final chunk.
        if sess.bytes_written + len(data) > sess.total_size + CHUNK_SIZE_BYTES:
            raise HTTPException(
                _413,
                detail="Upload exceeds declared size.",
            )
        # Chunks MUST arrive in order so append-to-part-file produces the
        # correct byte sequence. The client sends them sequentially; any
        # out-of-order chunk is an error, not a "buffer & reorder" case,
        # because keeping many MB in memory defeats the purpose.
        expected = len(sess.received)
        if chunk_number != expected:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                detail=f"Out-of-order chunk: expected {expected}, got {chunk_number}.",
            )
        with sess.part_path.open("ab") as fh:
            fh.write(data)
        sess.bytes_written += len(data)
        sess.received.add(chunk_number)
        received = len(sess.received)
        done = sess.complete
    logger.debug(
        f"[CHUNK:{upload_id}] chunk {chunk_number + 1}/{sess.total_chunks} ok "
        f"({sess.bytes_written} bytes, done={done})"
    )
    return {
        "upload_id": upload_id,
        "chunk_number": chunk_number,
        "received": received,
        "total_chunks": sess.total_chunks,
        "bytes_received": sess.bytes_written,
        "done": done,
    }


def finalize_upload(upload_id: str) -> Path:
    """Validate the assembled part file and move it to its final destination.
    Returns the absolute final Path on disk.
    """
    from ..services import uploaded_video_service as uvs
    from ..services import video_analysis_service as vas

    sess = get_session(upload_id)
    with _lock:
        if not sess.complete:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                detail=(
                    f"Cannot finalize: only {len(sess.received)}/"
                    f"{sess.total_chunks} chunks received."
                ),
            )
        if sess.bytes_written != sess.total_size:
            # Clean up the corrupt session before raising.
            try:
                sess.part_path.unlink(missing_ok=True)
            except OSError:
                pass
            sess.finalized = True
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"Size mismatch: expected {sess.total_size} bytes, "
                    f"got {sess.bytes_written}."
                ),
            )
        suffix = Path(sess.safe_name).suffix.lower()
        allowed = (
            getattr(uvs, "ALLOWED_VIDEO_SUFFIXES", None)
            or getattr(vas, "ALLOWED_VIDEO_SUFFIXES", None)
            or {".mp4", ".avi", ".mov", ".mkv", ".webm", ".m4v"}
        )
        if suffix not in allowed:
            try:
                sess.part_path.unlink(missing_ok=True)
            except OSError:
                pass
            sess.finalized = True
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    f"Unsupported video type '{suffix or '?'}'. "
                    f"Use one of: {', '.join(sorted(allowed))}."
                ),
            )
        if sess.source == "analysis":
            # Finalize into the analysis directory.
            final_path = _move_to(sess.part_path, vas.analysis_dir(), sess.safe_name)
        else:
            # Finalize into the uploads directory (single-video CCTV upload).
            final_path = _move_to(sess.part_path, uvs.upload_dir(), sess.safe_name)
        sess.finalized = True
    logger.info(f"[CHUNK:{upload_id}] finalized -> {final_path}")
    try:
        sess.part_path.unlink(missing_ok=True)
    except OSError:
        pass
    return final_path


def _move_to(part: Path, directory: Path, filename: str) -> Path:
    """Move `part` to `directory/filename`, auto-deduplicating on collision."""
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / filename
    if target.exists():
        stem, ext = target.stem, target.suffix
        i = 2
        while (directory / f"{stem}_{i}{ext}").exists():
            i += 1
        target = directory / f"{stem}_{i}{ext}"
    os.replace(part, target)
    return target


def abort(upload_id: str) -> None:
    with _lock:
        s = _sessions.pop(upload_id, None)
    if s is None:
        return
    try:
        s.part_path.unlink(missing_ok=True)
    except OSError:
        pass
    logger.info(f"[CHUNK:{upload_id}] aborted")
