"""
Sentinel Stream URL Service (backend-only)
==========================================

Builds AUTHENTICATED Sentinel stream URLs at connect time, from environment
config only. Security rules enforced here:

- Credentials never appear in the database, API responses, or error messages.
- The registered email's ``@`` is percent-encoded as ``%40`` (Sentinel rule).
- Passwords are URL-quoted so special characters cannot break the URL.
- ``redact()`` strips credentials for any URL that must be logged.
- Camera IDs are validated before being embedded in a URL (no path injection).

The frontend NEVER receives URLs from this module — it gets playback tickets
from ``GET /api/cameras/{id}/stream`` (same-origin paths only).
"""
import logging
import re
from urllib.parse import quote

from ..core.config import settings

logger = logging.getLogger("trinetra")

# Sentinel camera ids are simple slugs (cam04, north-gate-2, ...).
_CAMERA_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,32}$")


def validate_camera_id(camera_id: str) -> str:
    """Return the validated, lowercased camera id or raise ValueError."""
    cid = (camera_id or "").strip().lower()
    if not _CAMERA_ID_RE.match(cid):
        raise ValueError(f"Invalid camera id: {camera_id!r}")
    return cid


def credentials_configured() -> bool:
    """True when Sentinel credentials are present in the environment."""
    return bool(settings.SENTINEL_EMAIL.strip() and settings.SENTINEL_PASSWORD.strip())


def redact(url: str) -> str:
    """Strip userinfo from a URL for safe logging: rtsp://u:p@h/x -> rtsp://h/x."""
    if not url or "://" not in url:
        return url or ""
    scheme, rest = url.split("://", 1)
    if "@" in rest:
        rest = rest.split("@", 1)[1]
    return f"{scheme}://{rest}"


def get_hls_url(camera_id: str) -> str:
    """Public HLS playback URL (no credentials) — browser-viewable via proxy."""
    cid = validate_camera_id(camera_id)
    base = settings.SENTINEL_HLS_BASE_URL.rstrip("/")
    return f"{base}/{cid}/index.m3u8"


def get_rtsp_url(camera_id: str) -> str:
    """Authenticated RTSP URL for BACKEND AI ingestion only.

    Email '@' becomes %40 and the password is URL-quoted per the Sentinel
    connection spec. Never persist, return, or log this value unredacted.
    """
    cid = validate_camera_id(camera_id)
    if not credentials_configured():
        raise RuntimeError(
            "Sentinel credentials not configured "
            "(set SENTINEL_EMAIL / SENTINEL_PASSWORD in backend/.env)"
        )
    email = quote(settings.SENTINEL_EMAIL.strip(), safe="")
    password = quote(settings.SENTINEL_PASSWORD.strip(), safe="")
    host = settings.SENTINEL_RTSP_HOST.strip()
    port = int(settings.SENTINEL_RTSP_PORT)
    return f"rtsp://{email}:{password}@{host}:{port}/stream/{cid}"


def get_whep_path(camera_id: str) -> str:
    """Same-origin WHEP signalling PATH for the frontend (no credentials).

    The dev server / reverse proxy forwards /sentinel/* to the media gateway;
    browsers must never see an authenticated URL.
    """
    cid = validate_camera_id(camera_id)
    return f"/sentinel/stream/{cid}/whep"


def is_sentinel_camera(stream_url: str) -> bool:
    """Heuristic: does this registry URL belong to the Sentinel grid?"""
    url = (stream_url or "").strip()
    if not url:
        return False
    hls_base = settings.SENTINEL_HLS_BASE_URL.rstrip("/")
    rtsp_host = settings.SENTINEL_RTSP_HOST.strip()
    return url.startswith(hls_base + "/") or rtsp_host in url


def resolve_ingest_source(camera_id: str, stream_url: str, stream_type: str) -> str:
    """Pick the capture source for AI ingestion.

    Sentinel cameras ingest over authenticated RTSP (TCP transport is forced
    by CameraStream) when credentials exist; otherwise the stored URL is used
    as-is. The authenticated URL exists only for the lifetime of the capture.
    """
    if (
        (stream_type or "").lower() in ("rtsp", "hls")
        and is_sentinel_camera(stream_url)
        and credentials_configured()
    ):
        try:
            url = get_rtsp_url(camera_id)
            logger.info(
                "[%s] Sentinel RTSP ingest resolved (%s)",
                camera_id.upper(),
                redact(url),
            )
            return url
        except (RuntimeError, ValueError) as exc:
            logger.warning("[%s] falling back to registry URL: %s", camera_id.upper(), exc)
    return stream_url
