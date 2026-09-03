"""Sentinel camera catalogue client.

The catalogue (``https://cctv.corp8.cloud/cameras.json``) is the single source
of truth for what exists, where it is, what codec it speaks and how to reach it.
Camera IDs are *never* hard-coded anywhere else in the engine.

Design notes
------------
* The published schema is not guaranteed to be stable, and not every camera
  carries every field. Parsing is therefore alias-driven and defensive: an
  unknown shape yields fewer populated fields, never an exception.
* The raw payload for each camera is preserved on :attr:`Camera.raw` so a new
  upstream field is usable without a parser change.
* Failure is a normal condition (gateway down, TLS blocked, truncated JSON).
  Callers get an explicit :class:`CatalogueError` or an empty result, depending
  on ``strict``.
"""

from __future__ import annotations

import logging
import re
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Iterable
from urllib.parse import urljoin, urlsplit

import requests

from config.settings import DEFAULT_CATALOGUE_URL, Settings, load_settings

log = logging.getLogger("trinetra.catalogue")

DEFAULT_TIMEOUT_S = 8.0

# Aliases are matched case-insensitively against the raw key names.
_ID_KEYS = ("id", "camera_id", "cameraid", "cam", "camera", "name_id", "uid", "slug")
_NAME_KEYS = ("name", "label", "title", "camera_name", "description", "desc")
_LOCATION_KEYS = (
    "location",
    "place",
    "area",
    "address",
    "locality",
    "junction",
    "site",
    "landmark",
    "location_name",
)
_LAT_KEYS = ("latitude", "lat", "y")
_LNG_KEYS = ("longitude", "lng", "lon", "long", "x")
_STATUS_KEYS = ("status", "state", "health", "online", "active", "enabled")
_CODEC_KEYS = ("codec", "video_codec", "videocodec", "encoding", "encoder", "format")
_WIDTH_KEYS = ("width", "w", "frame_width")
_HEIGHT_KEYS = ("height", "h", "frame_height")
_FPS_KEYS = ("fps", "framerate", "frame_rate", "frames_per_second")
_RTSP_KEYS = ("rtsp", "rtsp_url", "rtspurl", "rtsp_stream", "stream_rtsp")
_HLS_KEYS = ("hls", "hls_url", "hlsurl", "m3u8", "m3u8_url", "playlist", "hls_stream")
_ANY_URL_KEYS = ("url", "stream", "stream_url", "streamurl", "source", "src", "link", "live")
_STREAM_CONTAINER_KEYS = ("streams", "stream", "urls", "endpoints", "sources", "media")

_ONLINE_WORDS = {"online", "up", "active", "ok", "healthy", "running", "true", "1", "yes"}
_OFFLINE_WORDS = {"offline", "down", "inactive", "error", "failed", "false", "0", "no"}

_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_\-]{0,63}$")


class CatalogueError(RuntimeError):
    """Raised when the catalogue cannot be retrieved or parsed at all."""


@dataclass(frozen=True)
class Camera:
    """Normalised view of one Sentinel camera.

    Optional fields are ``None`` when the catalogue does not publish them —
    callers must not assume uniform completeness across the grid.
    """

    camera_id: str
    name: str = ""
    location: str = ""
    latitude: float | None = None
    longitude: float | None = None
    status: str | None = None
    codec: str | None = None
    width: int | None = None
    height: int | None = None
    fps: float | None = None
    rtsp_url: str | None = None
    hls_url: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)

    # -- derived ------------------------------------------------------------
    @property
    def is_online(self) -> bool:
        if self.status is None:
            return True  # absence of a status field is not evidence of failure
        return self.status.strip().lower() in _ONLINE_WORDS

    @property
    def has_location(self) -> bool:
        return self.latitude is not None and self.longitude is not None

    def stream_url(self, preferred: str = "rtsp") -> str | None:
        """Best available URL for ``preferred`` transport ('rtsp' or 'hls')."""
        order = (
            (self.rtsp_url, self.hls_url)
            if preferred.lower() == "rtsp"
            else (self.hls_url, self.rtsp_url)
        )
        return next((u for u in order if u), None)

    @property
    def resolution(self) -> tuple[int, int] | None:
        if self.width and self.height:
            return (self.width, self.height)
        return None

    def describe(self) -> str:
        res = f"{self.width}x{self.height}" if self.resolution else "n/a"
        return (
            f"{self.camera_id} name={self.name or '-'} loc={self.location or '-'} "
            f"codec={self.codec or '-'} res={res} fps={self.fps if self.fps else '-'} "
            f"status={self.status or '-'} rtsp={'yes' if self.rtsp_url else 'no'} "
            f"hls={'yes' if self.hls_url else 'no'}"
        )


@dataclass
class Catalogue:
    """Result of one catalogue fetch."""

    cameras: list[Camera]
    url: str
    fetched_at: float
    raw: Any = None
    error: str | None = None
    skipped_entries: int = 0

    @property
    def ok(self) -> bool:
        return self.error is None and bool(self.cameras)

    def by_id(self, camera_id: str) -> Camera | None:
        return _index(self.cameras).get(_normalise_id(camera_id))

    def ids(self) -> list[str]:
        return [c.camera_id for c in self.cameras]

    def online(self) -> list[Camera]:
        return [c for c in self.cameras if c.is_online]


# ---------------------------------------------------------------------------
# fetching
# ---------------------------------------------------------------------------

_cache: dict[str, Catalogue] = {}
_cache_lock = threading.Lock()


def reset_cache() -> None:
    with _cache_lock:
        _cache.clear()


def _http_get(url: str, timeout: float, session: requests.Session | None) -> Any:
    http = session or requests
    response = http.get(url, timeout=timeout, headers={"Accept": "application/json"})
    response.raise_for_status()
    body = response.text
    try:
        return response.json()
    except ValueError:
        # Some gateways serve JSON with a wrong content-type or a BOM.
        import json

        return json.loads(body.lstrip("\ufeff"))


def fetch_catalogue(
    url: str = DEFAULT_CATALOGUE_URL,
    timeout: float = DEFAULT_TIMEOUT_S,
    session: requests.Session | None = None,
) -> Catalogue:
    """Fetch and parse the catalogue. Never raises for a payload-level problem.

    Raises :class:`CatalogueError` only when ``url`` is unusable.
    """
    if not url or not urlsplit(url).scheme:
        raise CatalogueError(f"catalogue URL is not usable: {url!r}")

    try:
        payload = _http_get(url, timeout=timeout, session=session)
    except requests.RequestException as exc:
        message = f"catalogue fetch failed for {url}: {type(exc).__name__}: {exc}"
        log.warning("catalogue_unavailable", extra={"url": url, "error": str(exc)})
        return Catalogue(cameras=[], url=url, fetched_at=time.time(), error=message)

    cameras, skipped = parse_cameras(payload, base_url=url)
    error = None
    if not cameras:
        error = f"catalogue at {url} parsed to zero cameras (skipped {skipped} entries)"
        log.warning("catalogue_empty", extra={"url": url, "skipped": skipped})
    else:
        log.info(
            "catalogue_loaded",
            extra={"url": url, "cameras": len(cameras), "skipped": skipped},
        )
    return Catalogue(
        cameras=cameras,
        url=url,
        fetched_at=time.time(),
        raw=payload,
        error=error,
        skipped_entries=skipped,
    )


def get_cameras(
    url: str | None = None,
    timeout: float | None = None,
    settings: Settings | None = None,
    use_cache: bool = True,
    session: requests.Session | None = None,
    strict: bool = False,
) -> list[Camera]:
    """Return the camera list, honouring a short TTL cache.

    On failure this returns ``[]`` (graceful) unless ``strict=True``, in which
    case :class:`CatalogueError` is raised so an operator script can fail loudly.
    """
    settings = settings or load_settings()
    url = url or settings.sentinel_catalogue_url
    timeout = settings.catalogue_timeout_s if timeout is None else timeout
    ttl = settings.catalogue_cache_ttl_s

    if use_cache:
        with _cache_lock:
            cached = _cache.get(url)
        if cached and (time.time() - cached.fetched_at) < ttl and cached.ok:
            return cached.cameras

    catalogue = fetch_catalogue(url=url, timeout=timeout, session=session)
    with _cache_lock:
        _cache[url] = catalogue

    if not catalogue.cameras and strict:
        raise CatalogueError(catalogue.error or "catalogue unavailable")
    return catalogue.cameras


def get_camera(
    camera_id: str,
    url: str | None = None,
    timeout: float | None = None,
    settings: Settings | None = None,
    session: requests.Session | None = None,
) -> Camera | None:
    """Look up one camera by id (case-insensitive: ``CAM04`` == ``cam04``)."""
    for camera in get_cameras(url=url, timeout=timeout, settings=settings, session=session):
        if camera.camera_id.lower() == camera_id.strip().lower():
            return camera
    return None


def require_camera(
    camera_id: str,
    url: str | None = None,
    settings: Settings | None = None,
    session: requests.Session | None = None,
) -> Camera:
    """As :func:`get_camera` but raises if the camera is unknown."""
    camera = get_camera(camera_id, url=url, settings=settings, session=session)
    if camera is None:
        raise CatalogueError(f"camera {camera_id!r} is not present in the Sentinel catalogue")
    return camera


def select_test_subset(cameras: Iterable[Camera], size: int = 5) -> list[Camera]:
    """Pick a *representative* subset rather than the first N cameras.

    Coverage goals, in order: distinct codecs, distinct resolutions, online
    cameras, and cameras that publish both RTSP and HLS. This is what makes a
    3–5 camera test say something about the grid instead of about cam01.
    """
    pool = [c for c in cameras if c.is_online]
    if not pool:
        pool = list(cameras)
    chosen: list[Camera] = []
    seen_codec: set[str] = set()
    seen_res: set[tuple[int, int] | None] = set()

    def add(cam: Camera) -> None:
        if cam not in chosen and len(chosen) < size:
            chosen.append(cam)

    # Pass 1: one camera per distinct codec.
    for cam in pool:
        codec = (cam.codec or "unknown").upper()
        if codec not in seen_codec:
            seen_codec.add(codec)
            add(cam)
    # Pass 2: one camera per distinct resolution.
    for cam in pool:
        res = cam.resolution
        if res not in seen_res:
            seen_res.add(res)
            add(cam)
    # Pass 3: cameras with both transports (most useful for fallback testing).
    for cam in pool:
        if cam.rtsp_url and cam.hls_url:
            add(cam)
    # Pass 4: fill up with anything left, stable order.
    for cam in pool:
        add(cam)
    return chosen


# ---------------------------------------------------------------------------
# parsing
# ---------------------------------------------------------------------------


def parse_cameras(payload: Any, base_url: str = "") -> tuple[list[Camera], int]:
    """Parse any plausible catalogue payload into ``(cameras, skipped_count)``.

    Accepts a bare list, or a dict wrapping the list under a common key
    (``cameras``/``data``/``items``/``result``/...), or a dict keyed by camera id.
    """
    entries = _iter_entries(payload)
    cameras: list[Camera] = []
    seen: set[str] = set()
    skipped = 0
    for key, entry in entries:
        if not isinstance(entry, dict):
            skipped += 1
            continue
        camera = parse_camera(entry, base_url=base_url, fallback_id=key)
        if camera is None:
            skipped += 1
            continue
        if camera.camera_id in seen:
            skipped += 1
            continue
        seen.add(camera.camera_id)
        cameras.append(camera)
    return cameras, skipped


def parse_camera(
    entry: dict[str, Any], base_url: str = "", fallback_id: str | None = None
) -> Camera | None:
    """Parse one catalogue entry. Returns ``None`` when there is no usable id."""
    flat = _flatten(entry)
    camera_id = _first_id(flat, _ID_KEYS) or (fallback_id if _valid_id(fallback_id) else None)
    if not camera_id or not _valid_id(camera_id):
        return None
    camera_id = _normalise_id(camera_id)

    name = _first_str(flat, _NAME_KEYS) or ""
    if name.lower() == camera_id.lower():
        name = ""
    location = _first_str(flat, _LOCATION_KEYS) or ""
    lat, lng = _parse_coordinates(flat)
    status = _parse_status(flat)
    codec = _first_str(flat, _CODEC_KEYS)
    width = _first_int(flat, _WIDTH_KEYS)
    height = _first_int(flat, _HEIGHT_KEYS)
    if (width is None or height is None) and not (width and height):
        res_w, res_h = _parse_resolution_string(flat)
        width = width or res_w
        height = height or res_h
    fps = _first_float(flat, _FPS_KEYS)

    rtsp_url = _first_url(flat, _RTSP_KEYS, base_url)
    hls_url = _first_url(flat, _HLS_KEYS, base_url)
    if rtsp_url is None or hls_url is None:
        for url in _all_urls(entry, base_url):
            low = url.lower()
            if rtsp_url is None and low.startswith("rtsp://"):
                rtsp_url = url
            elif hls_url is None and (".m3u8" in low or low.startswith("http") and "hls" in low):
                hls_url = url

    return Camera(
        camera_id=camera_id,
        name=name,
        location=location,
        latitude=lat,
        longitude=lng,
        status=status,
        codec=codec,
        width=width,
        height=height,
        fps=fps,
        rtsp_url=rtsp_url,
        hls_url=hls_url,
        raw=entry,
    )


# -- small helpers ----------------------------------------------------------


def _iter_entries(payload: Any, depth: int = 0) -> Iterable[tuple[str | None, Any]]:
    """Yield ``(fallback_id, entry)`` pairs from any plausible wrapper shape.

    Handles ``[...]``, ``{"cameras": [...]}``, ``{"data": {"cameras": [...]}}``
    and ``{"cam01": {...}}`` without needing to know which one Sentinel serves.
    """
    if depth > 3:
        return
    if isinstance(payload, list):
        yield from ((None, item) for item in payload)
        return
    if isinstance(payload, dict):
        for key in ("cameras", "data", "items", "result", "results", "camera_list", "cctv"):
            value = payload.get(key)
            if isinstance(value, list):
                yield from ((None, item) for item in value)
                return
            if isinstance(value, dict):
                # Nested wrapper ({"data": {"cameras": [...]}}) or an id-keyed map.
                yield from _iter_entries(value, depth + 1)
                return
        # Dict keyed by camera id: {"cam01": {...}, "cam02": {...}}
        if payload and all(isinstance(v, dict) for v in payload.values()):
            yield from payload.items()
            return
    yield None, payload


def _flatten(entry: dict[str, Any], depth: int = 0) -> dict[str, Any]:
    """One/two-level flatten so ``{"geo": {"lat": ...}}`` is still findable."""
    out: dict[str, Any] = {}
    for key, value in entry.items():
        out[str(key).lower()] = value
        if isinstance(value, dict) and depth < 1:
            for sub_key, sub_value in value.items():
                out.setdefault(str(sub_key).lower(), sub_value)
                out[f"{str(key).lower()}.{str(sub_key).lower()}".lower()] = sub_value
    return out


def _first_id(flat: dict[str, Any], keys: Iterable[str]) -> str | None:
    """Prefer a string identifier over a numeric surrogate key."""
    for key in keys:
        value = flat.get(key)
        if isinstance(value, str) and value.strip() and _valid_id(value.strip()):
            return value.strip()
    for key in keys:
        value = flat.get(key)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return str(int(value))
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _valid_id(value: str | None) -> bool:
    return bool(value) and bool(_ID_PATTERN.match(str(value).strip()))


def _normalise_id(value: str) -> str:
    return str(value).strip().lower()


def _index(cameras: Iterable[Camera]) -> dict[str, Camera]:
    return {_normalise_id(c.camera_id): c for c in cameras}


def _first_str(flat: dict[str, Any], keys: Iterable[str]) -> str | None:
    for key in keys:
        value = flat.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return str(value)
    return None


def _first_int(flat: dict[str, Any], keys: Iterable[str]) -> int | None:
    for key in keys:
        value = flat.get(key)
        if isinstance(value, bool):
            continue
        if isinstance(value, (int, float)):
            return int(value)
        if isinstance(value, str):
            try:
                return int(float(value.strip()))
            except ValueError:
                continue
    return None


def _first_float(flat: dict[str, Any], keys: Iterable[str]) -> float | None:
    for key in keys:
        value = flat.get(key)
        if isinstance(value, bool):
            continue
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            try:
                return float(value.strip())
            except ValueError:
                continue
    return None


def _parse_coordinates(flat: dict[str, Any]) -> tuple[float | None, float | None]:
    lat = _first_float(flat, _LAT_KEYS)
    lng = _first_float(flat, _LNG_KEYS)
    if lat is not None and lng is not None:
        return lat, lng

    # GeoJSON style: "coordinates": [lng, lat]
    coords = flat.get("coordinates") or flat.get("coord") or flat.get("latlong")
    if isinstance(coords, (list, tuple)) and len(coords) == 2:
        try:
            a, b = float(coords[0]), float(coords[1])
        except (TypeError, ValueError):
            return lat, lng
        # GeoJSON orders [lng, lat]; guard with plausible Indian bounds.
        if 68.0 <= a <= 97.5 and 8.0 <= b <= 37.5:
            return b, a
        return a, b
    if isinstance(coords, str):
        parts = [p for p in re.split(r"[,\s]+", coords.strip()) if p]
        if len(parts) == 2:
            try:
                return float(parts[0]), float(parts[1])
            except ValueError:
                pass
    return lat, lng


def _parse_status(flat: dict[str, Any]) -> str | None:
    raw = flat.get("status", flat.get("state", flat.get("health")))
    if isinstance(raw, bool):
        return "online" if raw else "offline"
    if isinstance(raw, str) and raw.strip():
        value = raw.strip()
        low = value.lower()
        if low in _ONLINE_WORDS:
            return "online"
        if low in _OFFLINE_WORDS:
            return "offline"
        return low
    if raw is None:
        for key in ("online", "active", "enabled"):
            value = flat.get(key)
            if isinstance(value, bool):
                return "online" if value else "offline"
    return None


def _parse_resolution_string(flat: dict[str, Any]) -> tuple[int | None, int | None]:
    for key in ("resolution", "res", "size", "frame_size", "framesize", "video_resolution"):
        value = flat.get(key)
        if not isinstance(value, str):
            continue
        match = re.search(r"(\d{3,5})\s*[x*,]\s*(\d{3,5})", value)
        if match:
            return int(match.group(1)), int(match.group(2))
    return None, None


def _first_url(flat: dict[str, Any], keys: Iterable[str], base_url: str) -> str | None:
    for key in keys:
        value = flat.get(key)
        if isinstance(value, str) and value.strip():
            return _absolute(value.strip(), base_url)
        if isinstance(value, dict):
            inner = value.get("url") or value.get("href") or value.get("src")
            if isinstance(inner, str) and inner.strip():
                return _absolute(inner.strip(), base_url)
    return None


def _all_urls(entry: Any, base_url: str, depth: int = 0) -> list[str]:
    """Collect every string that looks like a stream URL, at any nesting depth."""
    found: list[str] = []
    if depth > 3:
        return found
    if isinstance(entry, dict):
        for value in entry.values():
            found.extend(_all_urls(value, base_url, depth + 1))
    elif isinstance(entry, (list, tuple)):
        for value in entry:
            found.extend(_all_urls(value, base_url, depth + 1))
    elif isinstance(entry, str):
        text = entry.strip()
        low = text.lower()
        if low.startswith(("rtsp://", "rtsp+tcp://", "http://", "https://")) or ".m3u8" in low:
            found.append(_absolute(text, base_url))
    return found


def _absolute(url: str, base_url: str) -> str:
    if urlsplit(url).scheme:
        return url
    if not base_url:
        return url
    origin = urlsplit(base_url)
    root = f"{origin.scheme}://{origin.netloc}"
    return urljoin(root + "/", url.lstrip("/"))
