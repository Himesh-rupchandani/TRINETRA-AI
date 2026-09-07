"""
Sentinel Camera Catalogue (spec §7).

Fetches and parses the Sentinel camera catalogue (cameras.json) into internal
`Camera` objects. Cameras are NEVER hard-coded: identity, location, codec,
resolution and stream URLs all come from the catalogue payload, which may
have heterogeneous fields per camera.
"""
from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from urllib.parse import urlsplit

logger = logging.getLogger("cv_engine.catalogue")

DEFAULT_CATALOGUE_URL = "https://cctv.corp8.cloud/cameras.json"

# Credentials may only ever be attached for the official Sentinel CDN host
# (exact hostname match - never a substring, never a redirect target).
APPROVED_CATALOGUE_HOSTS = {"cctv.corp8.cloud"}


def _is_approved_catalogue_host(url: str) -> bool:
    """True only when ``url`` sits on an approved Sentinel host."""
    try:
        return (urlsplit(url).hostname or "").lower() in APPROVED_CATALOGUE_HOSTS
    except Exception:
        return False


class CatalogueError(Exception):
    """Raised when the catalogue cannot be fetched or is structurally invalid."""


@dataclass
class Camera:
    """Internal camera representation derived from catalogue metadata."""

    camera_id: str
    name: str = ""
    location: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    status: str = "UNKNOWN"
    codec: Optional[str] = None
    width: Optional[int] = None
    height: Optional[int] = None
    rtsp_url: Optional[str] = None
    hls_url: Optional[str] = None
    raw: Dict[str, Any] = field(default_factory=dict, repr=False)

    def stream_url(self, prefer: str = "rtsp") -> Optional[str]:
        """Preferred stream URL with graceful fallback to the other protocol."""
        if prefer.lower() == "hls":
            return self.hls_url or self.rtsp_url
        return self.rtsp_url or self.hls_url

    def has_location(self) -> bool:
        return (
            self.latitude is not None
            and self.longitude is not None
            and -90.0 <= self.latitude <= 90.0
            and -180.0 <= self.longitude <= 180.0
        )


# ---------------------------------------------------------------------------
# Parsing helpers — never assume identical fields across cameras
# ---------------------------------------------------------------------------

def _first_str(raw: Dict[str, Any], *keys: str) -> Optional[str]:
    for k in keys:
        v = raw.get(k)
        if v not in (None, ""):
            return str(v).strip()
    return None


def _first_float(raw: Dict[str, Any], *keys: str) -> Optional[float]:
    for k in keys:
        v = raw.get(k)
        if v is None or v == "":
            continue
        try:
            f = float(v)
            return f
        except (TypeError, ValueError):
            continue
    return None


def _first_int(raw: Dict[str, Any], *keys: str) -> Optional[int]:
    f = _first_float(raw, *keys)
    return int(f) if f is not None else None


def _extract_stream_urls(raw: Dict[str, Any], camera_id: str) -> Dict[str, Optional[str]]:
    """Find RTSP/HLS URLs across varied payload shapes."""
    rtsp_url: Optional[str] = None
    hls_url: Optional[str] = None

    # Explicit fields
    rtsp_url = _first_str(raw, "rtsp_url", "rtsp", "rtsp_stream", "stream_rtsp")
    hls_url = _first_str(raw, "hls_url", "hls", "hls_stream", "stream_hls")

    # Nested "streams": {"rtsp": ..., "hls": ...}
    streams = raw.get("streams")
    if isinstance(streams, dict):
        rtsp_url = rtsp_url or _first_str(streams, "rtsp", "rtsp_url")
        hls_url = hls_url or _first_str(streams, "hls", "hls_url")

    # Generic single URL fields — classify by scheme
    generic = _first_str(raw, "stream_url", "url", "source_url", "video_url")
    if generic:
        if generic.lower().startswith("rtsp://") and not rtsp_url:
            rtsp_url = generic
        elif (".m3u8" in generic or generic.lower().startswith(("http://", "https://"))) and not hls_url:
            hls_url = generic

    return {"rtsp": rtsp_url, "hls": hls_url}


def sentinel_stream_urls(camera_id: str, settings) -> Dict[str, Optional[str]]:
    """Build Sentinel RTSP/HLS URLs for a camera from env credentials.

    - RTSP carries credentials (email '@' -> %40, password URL-quoted) and is
      used for backend AI ingestion only; never log it unredacted.
    - HLS is the public playback URL (no credentials).
    Returns empty strings when credentials are not configured.
    """
    from urllib.parse import quote

    cid = str(camera_id).strip().lower()
    if not re.match(r"^[A-Za-z0-9_-]{1,32}$", cid):
        return {"rtsp": None, "hls": None}
    hls = f"{settings.sentinel_hls_base_url.rstrip('/')}/{cid}/index.m3u8"
    if not (settings.sentinel_email.strip() and settings.sentinel_password.strip()):
        return {"rtsp": None, "hls": hls}
    email = quote(settings.sentinel_email.strip(), safe="")
    password = quote(settings.sentinel_password.strip(), safe="")
    rtsp = (
        f"rtsp://{email}:{password}@{settings.sentinel_rtsp_host.strip()}:"
        f"{int(settings.sentinel_rtsp_port)}/stream/{cid}"
    )
    return {"rtsp": rtsp, "hls": hls}


def redact_url(url: Optional[str]) -> Optional[str]:
    """Strip userinfo for safe logging: rtsp://u:p@h/x -> rtsp://h/x."""
    if not url or "://" not in url:
        return url
    scheme, rest = url.split("://", 1)
    if "@" in rest:
        rest = rest.split("@", 1)[1]
    return f"{scheme}://{rest}"


def parse_camera(raw: Dict[str, Any]) -> Optional[Camera]:
    """Parse one catalogue entry. Returns None if the entry has no usable ID."""
    if not isinstance(raw, dict):
        return None

    cam_id = _first_str(raw, "camera_id", "id", "cam_id", "cameraId")
    if not cam_id:
        name = _first_str(raw, "name")
        if not name:
            return None
        cam_id = "CAM_" + re.sub(r"[^A-Za-z0-9]+", "_", name).strip("_").upper()

    urls = _extract_stream_urls(raw, cam_id)
    # Official catalogue entries may list only camera IDs. For such entries
    # (no URL information at all), synthesize Sentinel stream URLs from env
    # credentials — entries that carry their own URLs are left untouched.
    if not urls["rtsp"] and not urls["hls"]:
        try:
            from config.settings import Settings

            _synth = sentinel_stream_urls(cam_id, Settings.from_env())
            urls["rtsp"] = _synth["rtsp"]
            urls["hls"] = _synth["hls"]
        except Exception:
            pass
    status = (_first_str(raw, "status", "state") or "UNKNOWN").upper()
    codec = _first_str(raw, "codec", "video_codec", "encoding")
    if codec:
        codec = codec.upper().replace(".", "").replace("-", "")

    return Camera(
        camera_id=cam_id,
        name=_first_str(raw, "name") or f"Camera {cam_id}",
        location=_first_str(raw, "location", "location_name", "area", "place"),
        latitude=_first_float(raw, "latitude", "lat"),
        longitude=_first_float(raw, "longitude", "lon", "lng"),
        status=status,
        codec=codec,
        width=_first_int(raw, "width", "resolution_w"),
        height=_first_int(raw, "height", "resolution_h"),
        rtsp_url=urls["rtsp"],
        hls_url=urls["hls"],
        raw=raw,
    )


def parse_cameras(payload: Any) -> List[Camera]:
    """Parse a catalogue payload (list of cameras, or dict wrapper)."""
    if isinstance(payload, dict):
        for key in ("cameras", "data", "items"):
            if isinstance(payload.get(key), list):
                payload = payload[key]
                break
        else:
            # single camera object
            payload = [payload]
    if not isinstance(payload, list):
        raise CatalogueError(f"Unexpected catalogue payload type: {type(payload).__name__}")

    cameras: List[Camera] = []
    for entry in payload:
        cam = parse_camera(entry)
        if cam is not None:
            cameras.append(cam)
    return cameras


# ---------------------------------------------------------------------------
# Catalogue client
# ---------------------------------------------------------------------------

class SentinelCatalogue:
    """
    Retrieves and caches the Sentinel camera catalogue.

    Failure is graceful: on fetch/parse failure `fetch()` raises CatalogueError,
    but `get_cameras()` returns the last known-good cache (possibly empty) so
    callers can degrade instead of crashing.
    """

    def __init__(
        self,
        url: str = DEFAULT_CATALOGUE_URL,
        timeout_sec: float = 10.0,
        email: str = "",
        password: str = "",
    ):
        self.url = url
        self.timeout_sec = timeout_sec
        self.email = (email or os.environ.get("SENTINEL_EMAIL", "")).strip()
        self.password = (password or os.environ.get("SENTINEL_PASSWORD", "")).strip()
        self._cameras: List[Camera] = []
        self._by_id: Dict[str, Camera] = {}
        self.last_error: Optional[str] = None
        self.last_fetch_ok: bool = False

    # -- network -----------------------------------------------------------
    def fetch(self) -> List[Camera]:
        """Fetch + parse the catalogue. Raises CatalogueError on failure."""
        try:
            import httpx
        except ImportError as exc:  # pragma: no cover
            raise CatalogueError("httpx is required for catalogue fetch") from exc

        # The catalogue sits behind the same access password as the streams
        # (integrator guide §0): the server 302-redirects unauthenticated
        # requests to /auth/login. Attach Basic auth server-side, only to the
        # approved host, and never follow redirects while authenticated so
        # credentials can never leak to a redirect target.
        auth = None
        follow_redirects = True
        if self.email and self.password:
            if not _is_approved_catalogue_host(self.url):
                self.last_error = (
                    "refusing to send Sentinel credentials to an unapproved "
                    f"host: {redact_url(self.url)}"
                )
                self.last_fetch_ok = False
                logger.warning("[CATALOGUE] %s", self.last_error)
                raise CatalogueError(self.last_error)
            auth = httpx.BasicAuth(self.email, self.password)
            follow_redirects = False

        try:
            resp = httpx.get(
                self.url,
                timeout=self.timeout_sec,
                follow_redirects=follow_redirects,
                auth=auth,
            )
        except Exception as exc:
            self.last_error = f"catalogue request failed: {exc}"
            self.last_fetch_ok = False
            logger.warning("[CATALOGUE] %s", self.last_error)
            raise CatalogueError(self.last_error) from exc

        if resp.status_code != 200:
            location = resp.headers.get("location")
            hint = f" (redirect to {redact_url(location)})" if location else ""
            self.last_error = f"catalogue HTTP {resp.status_code}{hint}"
            self.last_fetch_ok = False
            logger.warning("[CATALOGUE] %s", self.last_error)
            raise CatalogueError(self.last_error)

        try:
            payload = resp.json()
        except Exception as exc:
            self.last_error = "catalogue response is not valid JSON"
            self.last_fetch_ok = False
            raise CatalogueError(self.last_error) from exc

        try:
            cameras = parse_cameras(payload)
        except CatalogueError as exc:
            self.last_error = str(exc)
            self.last_fetch_ok = False
            raise

        if not cameras:
            self.last_error = "catalogue contained no parseable cameras"
            self.last_fetch_ok = False
            raise CatalogueError(self.last_error)

        self._cameras = cameras
        self._by_id = {c.camera_id.upper(): c for c in cameras}
        self.last_error = None
        self.last_fetch_ok = True
        logger.info("[CATALOGUE] fetched %d cameras from %s", len(cameras), self.url)
        return cameras

    def load_payload(self, payload: Any) -> List[Camera]:
        """Load cameras directly from an already-fetched payload (tests/cache)."""
        cameras = parse_cameras(payload)
        self._cameras = cameras
        self._by_id = {c.camera_id.upper(): c for c in cameras}
        self.last_fetch_ok = True
        self.last_error = None
        return cameras

    # -- accessors -----------------------------------------------------------
    def get_cameras(self) -> List[Camera]:
        """All known cameras (last successful fetch). Never raises."""
        return list(self._cameras)

    def get_camera(self, camera_id: str) -> Optional[Camera]:
        """Case-insensitive single-camera lookup."""
        if not camera_id:
            return None
        return self._by_id.get(camera_id.strip().upper())


# ---------------------------------------------------------------------------
# Camera selection strategy (spec §27): representative test subset
# ---------------------------------------------------------------------------

def select_test_subset(cameras: List[Camera], n: int = 4) -> List[Camera]:
    """
    Deterministically pick a representative subset covering different codecs,
    resolutions and statuses — instead of random or hard-coded cameras.
    """
    if n <= 0 or not cameras:
        return []

    def bucket_key(cam: Camera) -> tuple:
        res = (cam.width, cam.height) if cam.width and cam.height else (None, None)
        return (cam.codec or "UNKNOWN", res, cam.status)

    buckets: Dict[tuple, List[Camera]] = {}
    for cam in cameras:
        buckets.setdefault(bucket_key(cam), []).append(cam)

    selected: List[Camera] = []
    # Round-robin across buckets so we cover diversity first.
    while len(selected) < n:
        progressed = False
        for key in sorted(buckets.keys(), key=lambda k: str(k)):
            if len(selected) >= n:
                break
            bucket = buckets[key]
            if bucket:
                selected.append(bucket.pop(0))
                progressed = True
        if not progressed:
            break
    return selected
