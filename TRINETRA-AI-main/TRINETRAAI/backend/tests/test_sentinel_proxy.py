"""
Tests for the same-origin Sentinel media proxy (browser playback path) and
the Sentinel grid status rule.

The proxy is what lets live cameras play on a deployed origin (Vercel):
the browser posts WHEP offers / pulls HLS through /sentinel/* and the
backend forwards them to the media gateway with server-side Basic auth.

Covered behaviours (mirroring trinetra-ai/vite.config.ts exactly):
- Authorization header injected server-side, never present in responses
- WHEP Location header rewritten same-origin (absolute, root-relative and
  path-relative forms) so session teardown stays on our domain
- /sentinel/live/* rides the HLS origin, /sentinel/stream/* the WHEP origin
- only published camera paths are forwarded (no open relay)
- missing credentials -> 502 with an actionable message, never a 401 loop
- Sentinel grid cameras resolve ONLINE without a local worker; an empty
  source stays NOT_CONFIGURED; non-grid cameras keep their registry status
"""
import base64
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.cameras import _resolve_camera_status
from app.api.sentinel_proxy import hls_origin
from app.core.config import settings
from app.database.models import Camera

EMAIL = "officer@gujaratpolice.gov.in"
PASSWORD = "p@ss w0rd/2024"
EXPECT_AUTH = "Basic " + base64.b64encode(f"{EMAIL}:{PASSWORD}".encode()).decode()


class _Gateway:
    """Tiny stand-in for the Sentinel media gateway (WHEP + HLS)."""

    def __init__(self):
        self.requests: list[tuple[str, str, dict]] = []
        self.location_mode = "absolute"
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _record(self, headers):
                outer.requests.append(
                    (self.command, self.path, {k: v for k, v in headers.items()})
                )

            def _send(self, code, body=b"", ctype="application/octet-stream", extra=None):
                self.send_response(code)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(body)))
                for k, v in (extra or {}).items():
                    self.send_header(k, v)
                self.end_headers()
                if body and self.command != "HEAD":
                    self.wfile.write(body)

            def do_POST(self):
                self._record(self.headers)
                length = int(self.headers.get("Content-Length") or 0)
                body = self.rfile.read(length) if length else b""
                assert body.startswith(b"v="), "expected an SDP offer"
                port = self.server.server_address[1]
                if outer.location_mode == "absolute":
                    loc = f"http://127.0.0.1:{port}/stream/cam04/whep/SESSION123"
                elif outer.location_mode == "root-relative":
                    loc = "/stream/cam04/whep/REL123"
                else:
                    loc = "session77"
                self._send(201, b"v=0\no=answer 0 0 IN IP4 127.0.0.1", "application/sdp",
                           {"Location": loc})

            def do_DELETE(self):
                self._record(self.headers)
                self._send(200, b"deleted")

            def do_OPTIONS(self):
                # The System Health grid probe is an OPTIONS preflight;
                # whatever the gateway answers (200/204/405) must be
                # relayed verbatim.
                self._record(self.headers)
                self._send(204)

            def do_GET(self):
                self._record(self.headers)
                if self.path.startswith("/live/stream/cam04/index.m3u8"):
                    body = b"#EXTM3U\n#EXT-X-TARGETDURATION:6\n#EXTINF:6.0,\nseg0.ts\n"
                    self._send(200, body, "application/vnd.apple.mpegurl",
                               {"Cache-Control": "no-cache"})
                elif self.path.startswith("/live/stream/cam04/seg0.ts"):
                    self._send(200, b"\x47" + b"segdata" * 100, "video/mp2t")
                else:
                    self._send(404, b"not found")

            do_HEAD = do_GET

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.port = self.httpd.server_address[1]
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()

    def stop(self):
        self.httpd.shutdown()
        self.httpd.server_close()


@pytest.fixture()
def gateway(monkeypatch):
    gw = _Gateway()
    monkeypatch.setattr(settings, "SENTINEL_EMAIL", EMAIL, raising=False)
    monkeypatch.setattr(settings, "SENTINEL_PASSWORD", PASSWORD, raising=False)
    monkeypatch.setattr(settings, "SENTINEL_WHEP_ORIGIN", f"http://127.0.0.1:{gw.port}", raising=False)
    monkeypatch.setattr(settings, "SENTINEL_HLS_ORIGIN", f"http://127.0.0.1:{gw.port}", raising=False)
    yield gw
    gw.stop()


@pytest.fixture()
def client():
    app = FastAPI()
    from app.api.sentinel_proxy import router

    app.include_router(router)
    with TestClient(app) as c:
        yield c


def test_whep_offer_is_forwarded_with_basic_auth(client, gateway):
    res = client.post(
        "/sentinel/stream/cam04/whep",
        content=b"v=0\no=offer",
        headers={"Content-Type": "application/sdp"},
    )
    assert res.status_code == 201
    assert res.headers["content-type"].startswith("application/sdp")
    assert res.text.startswith("v=")
    method, path, headers = gateway.requests[0]
    assert (method, path) == ("POST", "/stream/cam04/whep")
    assert headers.get("Authorization") == EXPECT_AUTH
    # The reply's absolute Location is rewritten onto our origin.
    assert res.headers["location"] == "/sentinel/stream/cam04/whep/SESSION123"


@pytest.mark.parametrize("mode,expected", [
    ("root-relative", "/sentinel/stream/cam04/whep/REL123"),
    # RFC 3986: a relative reference resolves against the request URI, so the
    # last segment (the "whep" endpoint) is replaced, not kept.
    ("relative", "/sentinel/stream/cam04/session77"),
])
def test_whep_location_rewrites_same_origin(client, gateway, mode, expected):
    gateway.location_mode = mode
    res = client.post("/sentinel/stream/cam04/whep", content=b"v=0")
    assert res.status_code == 201
    assert res.headers["location"] == expected


def test_whep_session_teardown_delete(client, gateway):
    res = client.request("DELETE", "/sentinel/stream/cam04/whep/SESSION123")
    assert res.status_code == 200
    method, path, headers = gateway.requests[0]
    assert (method, path) == ("DELETE", "/stream/cam04/whep/SESSION123")
    assert headers.get("Authorization") == EXPECT_AUTH


def test_hls_playlist_and_segment_flow_through(client, gateway):
    res = client.get("/sentinel/live/stream/cam04/index.m3u8")
    assert res.status_code == 200
    assert res.headers["content-type"].startswith("application/vnd.apple.mpegurl")
    assert res.headers["cache-control"] == "no-cache"
    assert res.text.startswith("#EXTM3U")
    method, path, headers = gateway.requests[0]
    assert (method, path) == ("GET", "/live/stream/cam04/index.m3u8")
    assert headers.get("Authorization") == EXPECT_AUTH

    seg = client.get("/sentinel/live/stream/cam04/seg0.ts")
    assert seg.status_code == 200
    assert seg.content == b"\x47" + b"segdata" * 100
    assert gateway.requests[1][1] == "/live/stream/cam04/seg0.ts"


def test_options_preflight_is_relayed_for_the_grid_probe(client, gateway):
    res = client.options("/sentinel/stream/cam01/whep")
    assert res.status_code == 204
    method, path, headers = gateway.requests[0]
    assert (method, path) == ("OPTIONS", "/stream/cam01/whep")
    assert headers.get("Authorization") == EXPECT_AUTH


def test_credentials_never_leak_in_responses(client, gateway):
    for url in ("/sentinel/stream/cam04/whep", "/sentinel/live/stream/cam04/index.m3u8"):
        res = client.get(url) if url.endswith(".m3u8") else client.post(url, content=b"v=0")
        assert PASSWORD not in res.text
        assert EMAIL not in res.text
        assert "authorization" not in {k.lower() for k in res.headers}


def test_missing_credentials_fail_fast_with_actionable_message(client, monkeypatch):
    monkeypatch.setattr(settings, "SENTINEL_EMAIL", "", raising=False)
    res = client.post("/sentinel/stream/cam04/whep", content=b"v=0")
    assert res.status_code == 502
    detail = res.json()["detail"]
    assert "SENTINEL_EMAIL" in detail and "SENTINEL_PASSWORD" in detail


def test_non_camera_paths_are_not_relayed(client, gateway):
    assert client.get("/sentinel/foo").status_code == 404
    assert client.get("/sentinel/live/stream/cam04").status_code == 404  # missing media file
    assert client.get("/sentinel/stream/" + "x" * 40 + "/whep").status_code == 404
    assert gateway.requests == [], "nothing may reach the gateway for rejected paths"


def test_hls_origin_defaults_to_whep_host_http_port(monkeypatch):
    monkeypatch.setattr(settings, "SENTINEL_WHEP_ORIGIN", "http://10.1.2.3:8889", raising=False)
    monkeypatch.setattr(settings, "SENTINEL_HLS_ORIGIN", "", raising=False)
    assert hls_origin() == "http://10.1.2.3"


# ---------------------------------------------------------------- status rule

def _cam(**kw):
    defaults = dict(
        camera_id="CAM04", name="Paldi Circle",
        stream_url="https://cctv.corp8.cloud/cam04/index.m3u8",
        stream_type="hls", status="OFFLINE", last_seen=None,
    )
    defaults.update(kw)
    return Camera(**defaults)


def test_sentinel_grid_camera_is_online_without_worker():
    """Vercel/API-only hosts run no decode workers — the grid is still live."""
    status, _ = _resolve_camera_status(_cam())
    assert status == "ONLINE"


def test_sentinel_rtsp_camera_is_online_without_worker():
    status, _ = _resolve_camera_status(_cam(
        stream_url="rtsp://user:pass@103.250.160.189:8554/stream/cam04",
        stream_type="rtsp",
    ))
    assert status == "ONLINE"


def test_empty_source_stays_not_configured():
    status, _ = _resolve_camera_status(_cam(stream_url=""))
    assert status == "NOT_CONFIGURED"


def test_non_grid_camera_keeps_registry_status(tmp_path):
    # A private rtsp camera nobody is ingesting stays honestly OFFLINE.
    status, _ = _resolve_camera_status(_cam(
        camera_id="CAMLIVE",
        stream_url="rtsp://192.168.1.50:554/stream",
        stream_type="rtsp",
    ))
    assert status == "OFFLINE"
    # File-backed camera: playable iff the media actually exists.
    missing = _cam(camera_id="CAMFILE", stream_url=str(tmp_path / "nope.mp4"),
                   stream_type="file", status="OFFLINE")
    assert _resolve_camera_status(missing)[0] == "OFFLINE"
    real = tmp_path / "clip.mp4"
    real.write_bytes(b"0")
    present = _cam(camera_id="CAMFILE", stream_url=str(real), stream_type="file",
                   status="OFFLINE")
    assert _resolve_camera_status(present)[0] == "ONLINE"
