"""
Secure camera stream resolution (backend-only).

All authenticated camera endpoints are built at connection time from server-side
configuration.  They are deliberately never persisted in the camera registry,
returned from an API, or written to logs.  The frontend receives only a
same-origin playback ticket from ``GET /api/cameras/{id}/stream``.

This module supports both the Sentinel grid and the single authorized live
camera slot configured through ``LIVE_CAMERA_*`` variables.  A WHEP/WebRTC
camera can use a separate server-side RTSP/HLS ``LIVE_CAMERA_INGEST_URL`` for
OpenCV inference while the browser continues to use its existing WHEP path.
"""
from __future__ import annotations

import logging
import re
from typing import Optional, Tuple
from urllib.parse import parse_qsl, quote, unquote, urlsplit, urlunsplit

from ..core.config import settings

logger = logging.getLogger("trinetra")

# Sentinel camera ids are simple slugs (cam04, north-gate-2, ...).
_CAMERA_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,32}$")
# A stream URL can contain a short-lived signed token in its query string.  It
# is just as sensitive as userinfo, so it is never persisted or logged either.
_SENSITIVE_QUERY_KEYS = {
    "access_token",
    "api_key",
    "apikey",
    "auth",
    "authorization",
    "credential",
    "expires",
    "expiry",
    "expiration",
    "jwt",
    "key",
    "password",
    "passwd",
    "policy",
    "secret",
    "session",
    "sessionid",
    "sid",
    "sig",
    "signature",
    "ticket",
    "token",
    "x-amz-algorithm",
    "x-amz-credential",
    "x-amz-date",
    "x-amz-expires",
    "x-amz-security-token",
    "x-amz-signature",
}
_SENSITIVE_QUERY_NORMALIZED = {item.replace("_", "").replace("-", "") for item in _SENSITIVE_QUERY_KEYS}


def _is_sensitive_query_key(key: str) -> bool:
    """Conservatively recognize common signed-URL/token parameter spellings."""
    value = (key or "").strip().lower()
    normalized = value.replace("_", "").replace("-", "")
    return (
        value in _SENSITIVE_QUERY_KEYS
        or normalized in _SENSITIVE_QUERY_NORMALIZED
        or any(part in normalized for part in ("token", "secret", "password", "passwd", "credential", "signature", "auth"))
    )


_URL_IN_TEXT_RE = re.compile(r"(?:rtsps?|https?|webrtc)://[^\s'\"<>]+", re.IGNORECASE)


def validate_camera_id(camera_id: str) -> str:
    """Return the validated, lowercased camera id or raise ``ValueError``."""
    cid = (camera_id or "").strip().lower()
    if not _CAMERA_ID_RE.match(cid):
        raise ValueError(f"Invalid camera id: {camera_id!r}")
    return cid


def credentials_configured() -> bool:
    """True when Sentinel credentials are present in server-side configuration."""
    return bool(settings.SENTINEL_EMAIL.strip() and settings.SENTINEL_PASSWORD.strip())


def _safe_netloc(parts) -> str:
    """Return a URL netloc without userinfo, tolerating malformed port values."""
    try:
        host = parts.hostname
        port = parts.port
    except ValueError:
        # A malformed URL is never safe to echo verbatim.  Preserve only the
        # authority after the final '@' as a best-effort diagnostic reference.
        return parts.netloc.rsplit("@", 1)[-1]
    if not host:
        return parts.netloc.rsplit("@", 1)[-1]
    # urlsplit.hostname removes IPv6 brackets; put them back for a valid URL.
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"
    return f"{host}:{port}" if port is not None else host


def redact(url: str) -> str:
    """Return a safe diagnostic/reference form of a stream URL.

    Userinfo, query parameters and fragments are removed.  The function keeps
    the scheme/host/path so an operator can identify the source without seeing
    a password, bearer token, signed query, or other access credential.
    """
    raw = (url or "").strip()
    if not raw:
        return ""
    try:
        parts = urlsplit(raw)
        if not parts.scheme or not parts.netloc:
            # File paths and opaque values have no URL userinfo to redact.
            return raw
        return urlunsplit((parts.scheme, _safe_netloc(parts), parts.path, "", ""))
    except Exception:
        # Never let an error path reveal a userinfo-bearing value.
        if "://" in raw:
            scheme, rest = raw.split("://", 1)
            authority_path = rest.rsplit("@", 1)[-1]
            authority_path = authority_path.split("?", 1)[0].split("#", 1)[0]
            return f"{scheme}://{authority_path}"
        return raw


def redact_text(value: object) -> str:
    """Scrub stream URLs and configured credentials from exception/log text.

    OpenCV/FFmpeg sometimes emits only a query-token or userinfo component
    rather than a complete URL. Derive those pieces from configured private
    live sources as well as the Sentinel credentials before logging anything.
    """
    text = str(value or "")
    text = _URL_IN_TEXT_RE.sub(lambda match: redact(match.group(0)), text)
    secrets = {
        str(getattr(settings, "SENTINEL_PASSWORD", "") or ""),
        str(getattr(settings, "SENTINEL_EMAIL", "") or ""),
    }
    for configured_url in (
        str(getattr(settings, "LIVE_CAMERA_STREAM_URL", "") or ""),
        str(getattr(settings, "LIVE_CAMERA_INGEST_URL", "") or ""),
    ):
        if not configured_url:
            continue
        # Cover a full URL even if its scheme is not recognized by the regex.
        text = text.replace(configured_url, redact(configured_url))
        try:
            parts = urlsplit(configured_url)
            secrets.update(
                item
                for item in (parts.username, parts.password, unquote(parts.username or ""), unquote(parts.password or ""))
                if item
            )
            secrets.update(item for _, item in parse_qsl(parts.query, keep_blank_values=True) if item)
        except ValueError:
            pass
    # Avoid replacing arbitrary one/two-character words in diagnostics, while
    # still removing every meaningful configured credential/token.
    for secret in sorted((item for item in secrets if len(item) >= 3), key=len, reverse=True):
        text = text.replace(secret, "***")
    return text


def has_embedded_credentials(url: str) -> bool:
    """Whether a URL includes userinfo or a credential-bearing query value."""
    raw = (url or "").strip()
    if not raw:
        return False
    try:
        parts = urlsplit(raw)
        if parts.username is not None or parts.password is not None:
            return True
        return any(_is_sensitive_query_key(key) for key, _ in parse_qsl(parts.query, keep_blank_values=True))
    except Exception:
        # Treat a userinfo-looking malformed value as sensitive instead of
        # risking storage/logging of a password.
        before_query = raw.split("?", 1)[0]
        return "://" in before_query and "@" in before_query.split("://", 1)[1]


def get_hls_url(camera_id: str) -> str:
    """Uncredentialed Sentinel HLS reference for server-side fallback only."""
    cid = validate_camera_id(camera_id)
    base = settings.SENTINEL_HLS_BASE_URL.rstrip("/")
    return f"{base}/{cid}/index.m3u8"


def get_rtsp_url(camera_id: str) -> str:
    """Build an authenticated Sentinel RTSP URL for backend AI ingestion only."""
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


def get_authenticated_hls_url(camera_id: str) -> str:
    """Build authenticated HLS for backend fallback only; never expose it."""
    cid = validate_camera_id(camera_id)
    if not credentials_configured():
        raise RuntimeError(
            "Sentinel credentials not configured "
            "(set SENTINEL_EMAIL / SENTINEL_PASSWORD in backend/.env)"
        )
    email = quote(settings.SENTINEL_EMAIL.strip(), safe="")
    password = quote(settings.SENTINEL_PASSWORD.strip(), safe="")
    base = settings.SENTINEL_HLS_BASE_URL.rstrip("/")
    scheme, host = base.split("://", 1)
    return f"{scheme}://{email}:{password}@{host}/{cid}/index.m3u8"


def get_whep_path(camera_id: str) -> str:
    """Return the browser-safe, same-origin Sentinel WHEP signalling path."""
    cid = validate_camera_id(camera_id)
    return f"/sentinel/stream/{cid}/whep"


def is_sentinel_camera(stream_url: str) -> bool:
    """Whether a registry reference belongs to the configured Sentinel hosts.

    Match parsed hostnames rather than a substring so a user-provided URL that
    merely contains the gateway IP/path cannot cause Sentinel credentials to be
    resolved for an unrelated camera.
    """
    url = (stream_url or "").strip()
    if not url:
        return False
    try:
        host = (urlsplit(url).hostname or "").lower()
        hls_host = (urlsplit(settings.SENTINEL_HLS_BASE_URL).hostname or "").lower()
        rtsp_host = settings.SENTINEL_RTSP_HOST.strip().lower().strip("[]")
        return bool(host and host in {hls_host, rtsp_host})
    except ValueError:
        return False


def _is_configured_live_camera(camera_id: str) -> bool:
    return (camera_id or "").strip().upper() == settings.LIVE_CAMERA_ID.strip().upper()


def _infer_stream_type(url: str, fallback: str = "") -> str:
    value = (url or "").strip().lower()
    requested = (fallback or "").strip().lower()
    if value.startswith(("rtsp://", "rtsps://")):
        return "rtsp"
    if ".m3u8" in value or value.startswith(("http://", "https://")):
        # HTTP stream URLs in this project are HLS unless a caller explicitly
        # identifies another browser-only protocol.
        return "hls" if requested not in {"file", "webrtc", "whep"} else requested
    if requested in {"rtsp", "hls", "file", "webrtc", "whep"}:
        return requested
    return ""


def configured_live_ingest(camera_id: str) -> Optional[Tuple[str, str]]:
    """Return the private OpenCV ingest source for the configured live slot.

    ``LIVE_CAMERA_INGEST_URL`` is useful when the viewer is WHEP/WebRTC while
    inference must use the authorized RTSP/HLS gateway URL.  If it is omitted,
    a RTSP/HLS/file ``LIVE_CAMERA_STREAM_URL`` itself is used.  WebRTC/WHEP is
    intentionally not handed to OpenCV because OpenCV's FFmpeg backend does
    not negotiate WHEP sessions; configure the paired ingest URL instead.
    """
    if not _is_configured_live_camera(camera_id):
        return None
    ingest_url = (getattr(settings, "LIVE_CAMERA_INGEST_URL", "") or "").strip()
    display_url = (getattr(settings, "LIVE_CAMERA_STREAM_URL", "") or "").strip()
    url = ingest_url or display_url
    requested_type = (
        (getattr(settings, "LIVE_CAMERA_INGEST_TYPE", "") or "").strip()
        if ingest_url
        else (getattr(settings, "LIVE_CAMERA_STREAM_TYPE", "") or "").strip()
    )
    source_type = _infer_stream_type(url, requested_type)
    if not url or source_type not in {"rtsp", "hls", "file"}:
        return None
    return url, source_type


def can_decode_for_detection(camera_id: str, stream_type: str) -> bool:
    """Whether the backend has an OpenCV-decodable source for this camera."""
    if _is_configured_live_camera(camera_id):
        return configured_live_ingest(camera_id) is not None
    return (stream_type or "").strip().lower() in {"rtsp", "hls", "file"}


def resolve_ingest_source(camera_id: str, stream_url: str, stream_type: str) -> str:
    """Resolve a private source for backend capture without persisting secrets.

    Resolution order:
    1. The authorized ``LIVE_CAMERA_INGEST_URL`` / live slot config.
    2. Authenticated Sentinel RTSP synthesized from environment credentials.
    3. The non-secret registry source as a graceful fallback.
    """
    live = configured_live_ingest(camera_id)
    if live is not None:
        return live[0]

    if (
        (stream_type or "").lower() in ("rtsp", "hls")
        and is_sentinel_camera(stream_url)
        and credentials_configured()
    ):
        try:
            url = get_rtsp_url(camera_id)
            logger.info("[%s] Sentinel RTSP ingest resolved (%s)", camera_id.upper(), redact(url))
            return url
        except (RuntimeError, ValueError) as exc:
            logger.warning("[%s] falling back to registry source: %s", camera_id.upper(), redact_text(exc))
    return stream_url


def resolve_ingest_stream_type(camera_id: str, stream_url: str, stream_type: str) -> str:
    """Return the protocol matching :func:`resolve_ingest_source`."""
    live = configured_live_ingest(camera_id)
    if live is not None:
        return live[1]
    source = resolve_ingest_source(camera_id, stream_url, stream_type)
    inferred = _infer_stream_type(source, stream_type)
    return inferred or (stream_type or "rtsp").strip().lower()
