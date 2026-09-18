"""
Same-origin Sentinel media proxy (browser playback path).

The control room plays live cameras through SAME-ORIGIN ``/sentinel`` paths —
the browser never sees the media gateway's origin, and no credential ever
reaches the public bundle. In development the Vite dev server is that proxy
(``trinetra-ai/vite.config.ts``); on a deployed origin (Vercel, reverse
proxy, …) this module is the same proxy, running inside the backend:

    /sentinel/stream/<id>/whep            ->  http://<whep-host>:8889/stream/<id>/whep
    /sentinel/stream/<id>/whep/<session>  ->  same (WHEP session teardown, DELETE)
    /sentinel/live/stream/<id>/…          ->  http://<hls-host>/live/stream/<id>/…

Rules mirrored from the dev proxy (one behaviour, one place to reason about):

- the gateway's email + access password are injected as an ``Authorization:
  Basic`` header server-side (env only — ``SENTINEL_EMAIL`` /
  ``SENTINEL_PASSWORD`` — never a default, never a response body);
- the WHEP reply's ``Location`` header (the session resource the client
  DELETEs on teardown) is rewritten onto the same origin, so teardown never
  leaves our domain either;
- paths are strictly validated (camera-id slug rules) so the proxy can never
  be turned into an open relay to arbitrary gateway locations with our
  credentials attached;
- when credentials are missing the proxy answers 502 with an actionable
  message instead of forwarding an auth it cannot win — the player then shows
  an honest error, never a fake feed.

What flows over this proxy:
- WHEP signalling: one small POST (SDP offer) -> one small answer. The actual
  video is WebRTC between the browser and the gateway (ICE) and does NOT
  transit Vercel;
- HLS compatibility stream: short GETs (playlist + segments) that hls.js
  issues continuously. Serverless-friendly by construction.

OpenCV live MJPEG (``/api/cameras/<id>/live``) is intentionally NOT part of
this: it needs a long-lived CV process and stays on the Docker deployment.
"""
import base64
import logging
import re
from urllib.parse import urlsplit, urlunsplit

import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from ..core.config import settings
from ..services.sentinel_stream_service import validate_camera_id

logger = logging.getLogger("trinetra")

router = APIRouter(tags=["Sentinel Proxy"])

# OPTIONS: the System Health page sends a cheap preflight to
# /sentinel/stream/cam01/whep to report the grid's real reachability —
# the proxy forwards it so the probe reflects the gateway, not the proxy.
_ALLOWED_METHODS = ["GET", "POST", "DELETE", "HEAD", "OPTIONS"]

# Path shapes the gateway actually publishes. Anything else is rejected BEFORE
# credentials are attached — this proxy is for the camera grid, not a tunnel.
_WHEP_PATH_RE = re.compile(r"^stream/(?P<cid>[A-Za-z0-9_-]{1,32})(?P<rest>(?:/[A-Za-z0-9._~-]{1,128})*)/?$")
_HLS_PATH_RE = re.compile(r"^live/stream/(?P<cid>[A-Za-z0-9_-]{1,32})/(?P<rest>[A-Za-z0-9._~%-]+(?:/[A-Za-z0-9._~%-]+)*)/?$")

# Signalling must be snappy; playlist/segment reads get a bit more headroom.
_CONNECT_TIMEOUT = 8.0
_READ_TIMEOUT = 30.0
_CHUNK = 64 * 1024

_MIME_FORWARD = ("content-type", "content-length", "cache-control", "content-range", "accept-ranges")


def whep_origin() -> str:
    """WHEP signalling origin (env ``SENTINEL_WHEP_ORIGIN``)."""
    return (settings.SENTINEL_WHEP_ORIGIN or "http://103.250.160.189:8889").strip().rstrip("/")


def hls_origin() -> str:
    """HLS origin. Defaults to the WHEP host on its HTTP port (dev-proxy rule)."""
    origin = (settings.SENTINEL_HLS_ORIGIN or "").strip()
    if origin:
        return origin.rstrip("/")
    host = urlsplit(whep_origin()).hostname or "103.250.160.189"
    return f"http://{host}"


def _basic_auth_header() -> str | None:
    email = settings.SENTINEL_EMAIL.strip()
    password = settings.SENTINEL_PASSWORD.strip()
    if not (email and password):
        return None
    token = base64.b64encode(f"{email}:{password}".encode("utf-8")).decode("ascii")
    return f"Basic {token}"


def _resolve_upstream(path: str) -> tuple[str, str]:
    """Map a /sentinel request path onto (upstream_url, camera_id).

    Raises HTTPException(404/400) for anything that is not a published
    camera path — before any credential is involved.
    """
    if path.startswith("live/"):
        m = _HLS_PATH_RE.match(path)
        if not m:
            raise HTTPException(status_code=404, detail="Unknown Sentinel media path.")
        try:
            cid = validate_camera_id(m.group("cid"))
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid camera id.")
        return f"{hls_origin()}/{path}", cid
    m = _WHEP_PATH_RE.match(path)
    if not m:
        raise HTTPException(status_code=404, detail="Unknown Sentinel media path.")
    try:
        cid = validate_camera_id(m.group("cid"))
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid camera id.")
    return f"{whep_origin()}/{path}", cid


def _rewrite_location(location: str | None, upstream: str) -> str | None:
    """Rewrite the gateway's Location header onto our same-origin /sentinel path.

    Mirrors the dev proxy: absolute URLs become their origin-relative form,
    root-relative paths get the /sentinel prefix, and relative paths are
    resolved against the upstream path first. Teardown DELETEs then stay on
    our origin — no mixed content, no CORS, no direct gateway talk.
    """
    if not location or location.startswith("/sentinel"):
        return location
    base = urlsplit(upstream)
    out = location
    if re.match(r"^https?://", out, re.I):
        out = urlsplit(out).path + (f"?{urlsplit(out).query}" if urlsplit(out).query else "")
    elif not out.startswith("/"):
        root, _, _ = base.path.rpartition("/")
        out = f"{root}/{out}"
    return f"/sentinel{out if out.startswith('/') else '/' + out}"


@router.api_route("/sentinel/{path:path}", methods=_ALLOWED_METHODS)
async def sentinel_media_proxy(path: str, request: Request) -> StreamingResponse:
    """Forward a browser playback request to the Sentinel media gateway."""
    upstream, camera_id = _resolve_upstream(path)

    auth = _basic_auth_header()
    if auth is None:
        # Fail fast and say exactly what to configure — an unauthenticated
        # forward would just 401 on every camera and burn minutes of the
        # operator's time.
        raise HTTPException(
            status_code=502,
            detail=(
                "Sentinel gateway credentials are not configured on this deployment. "
                "Set SENTINEL_EMAIL and SENTINEL_PASSWORD in the project's environment "
                "variables (Settings → Environment Variables) and redeploy."
            ),
        )

    fwd_headers = {"Authorization": auth, "User-Agent": "trinetra-live-proxy/1.0"}
    ctype = request.headers.get("content-type")
    if ctype:
        fwd_headers["Content-Type"] = ctype
    accept = request.headers.get("accept")
    if accept:
        fwd_headers["Accept"] = accept
    body = await request.body() if request.method in ("POST", "DELETE") else None

    client = httpx.AsyncClient(
        timeout=httpx.Timeout(_READ_TIMEOUT, connect=_CONNECT_TIMEOUT),
        follow_redirects=False,
    )
    try:
        upstream_response = await client.send(
            client.build_request(
                request.method,
                upstream,
                headers=fwd_headers,
                content=body,
                params=dict(request.query_params),
            ),
            stream=True,
        )
    except httpx.HTTPError as exc:
        await client.aclose()
        logger.warning("[sentinel-proxy] %s %s unreachable: %s", request.method, camera_id, type(exc).__name__)
        raise HTTPException(
            status_code=502,
            detail=(
                f"Sentinel gateway is unreachable from this server "
                f"({type(exc).__name__}). Check that the media gateway is up and its "
                "network allows this host's egress."
            ),
        )

    out_headers: dict[str, str] = {}
    for key in _MIME_FORWARD:
        if key in upstream_response.headers:
            out_headers[key] = upstream_response.headers[key]
    location = _rewrite_location(upstream_response.headers.get("location"), upstream)
    if location:
        out_headers["Location"] = location
    # We stream decoded bytes; never let an upstream content-encoding lie.
    out_headers.pop("content-encoding", None)

    async def payload():
        try:
            async for chunk in upstream_response.aiter_bytes(_CHUNK):
                yield chunk
        finally:
            await upstream_response.aclose()
            await client.aclose()

    logger.info("[sentinel-proxy] %s /sentinel/%s -> %s", request.method, camera_id, upstream.split("://", 1)[-1].rsplit("/", 1)[0])
    return StreamingResponse(
        payload(),
        status_code=upstream_response.status_code,
        headers=out_headers,
        media_type=upstream_response.headers.get("content-type"),
    )
