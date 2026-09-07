"""Catalogue parsing (spec §7): heterogeneous fields, graceful failure."""
import pytest

from capture.sentinel_catalogue import (
    Camera,
    CatalogueError,
    SentinelCatalogue,
    parse_camera,
    parse_cameras,
    select_test_subset,
)


SAMPLE_PAYLOAD = [
    {  # rich entry
        "camera_id": "cam04",
        "name": "North Gate Junction",
        "location": "Paldi Circle",
        "latitude": 23.0338,
        "longitude": 72.585,
        "status": "online",
        "codec": "h.264",
        "width": 1920,
        "height": 1080,
        "rtsp_url": "rtsp://103.250.160.189:8554/stream/cam04",
        "hls_url": "https://cctv.corp8.cloud/cam04/index.m3u8",
    },
    {  # alternate field names, nested streams
        "id": "cam08",
        "name": "SG Highway",
        "lat": "23.05",
        "lng": 72.52,
        "streams": {"rtsp": "rtsp://10.0.0.8/stream/cam08", "hls": "https://x/cam08/index.m3u8"},
        "state": "OFFLINE",
        "video_codec": "H265",
        "resolution_w": "1280",
        "resolution_h": 720,
    },
    {  # minimal entry — single generic url
        "id": "cam12",
        "url": "rtsp://10.0.0.12/stream/cam12",
    },
    {  # no id -> derived from name
        "name": "Ashram Road Cam",
        "latitude": "bad-value",
    },
    "not-a-dict",  # garbage must be skipped
]


def test_parse_cameras_heterogeneous_fields():
    cams = parse_cameras(SAMPLE_PAYLOAD)
    assert len(cams) == 4

    cam04 = next(c for c in cams if c.camera_id == "cam04")
    assert cam04.latitude == 23.0338
    assert cam04.status == "ONLINE"
    assert cam04.codec == "H264"
    assert cam04.width == 1920 and cam04.height == 1080
    assert cam04.rtsp_url.startswith("rtsp://")
    assert cam04.hls_url.endswith(".m3u8")
    assert cam04.has_location()
    # raw metadata preserved
    assert cam04.raw["name"] == "North Gate Junction"

    cam08 = next(c for c in cams if c.camera_id == "cam08")
    assert cam08.latitude == 23.05
    assert cam08.longitude == 72.52
    assert cam08.codec == "H265"
    assert cam08.width == 1280
    assert cam08.status == "OFFLINE"
    assert cam08.stream_url(prefer="rtsp").startswith("rtsp://")
    assert cam08.stream_url(prefer="hls").endswith(".m3u8")

    cam12 = next(c for c in cams if c.camera_id == "cam12")
    assert cam12.rtsp_url == "rtsp://10.0.0.12/stream/cam12"
    assert cam12.hls_url is None
    # stream_url falls back gracefully
    assert cam12.stream_url(prefer="hls") == "rtsp://10.0.0.12/stream/cam12"


def test_parse_camera_without_id_derives_from_name():
    cams = parse_cameras(SAMPLE_PAYLOAD)
    derived = cams[3]
    assert derived.camera_id == "CAM_ASHRAM_ROAD_CAM"
    assert derived.latitude is None  # bad lat string -> None, not a crash
    assert not derived.has_location()


def test_parse_wrapped_payload_and_single_object():
    wrapped = parse_cameras({"cameras": SAMPLE_PAYLOAD})
    assert len(wrapped) == 4
    single = parse_cameras({"camera_id": "cam01", "rtsp_url": "rtsp://x/1"})
    assert len(single) == 1 and single[0].camera_id == "cam01"


def test_parse_invalid_payload_raises():
    with pytest.raises(CatalogueError):
        parse_cameras(42)


def test_get_camera_case_insensitive_and_missing():
    cat = SentinelCatalogue(url="http://unused")
    cat.load_payload(SAMPLE_PAYLOAD)
    assert cat.get_camera("CAM04") is not None
    assert cat.get_camera(" cam04 ").camera_id == "cam04"
    assert cat.get_camera("cam99") is None
    assert len(cat.get_cameras()) == 4


def test_fetch_failure_graceful(monkeypatch):
    """A failed fetch must not destroy the last known-good camera set."""
    cat = SentinelCatalogue(url="http://invalid.invalid/cameras.json", timeout_sec=1.0)
    cat.load_payload(SAMPLE_PAYLOAD)

    class _Boom:
        def get(self, *a, **kw):
            raise RuntimeError("network down")

    import httpx
    monkeypatch.setattr(httpx, "get", _Boom().get)
    with pytest.raises(CatalogueError):
        cat.fetch()
    # cache still usable
    assert cat.get_camera("cam04") is not None
    assert cat.last_fetch_ok is False
    assert cat.last_error


def test_select_test_subset_covers_diversity():
    cams = [
        Camera(camera_id=f"c{i}", codec="H264" if i % 2 else "H265",
               width=1920 if i < 3 else 1280, height=1080 if i < 3 else 720,
               status="ONLINE" if i % 3 else "OFFLINE")
        for i in range(8)
    ]
    subset = select_test_subset(cams, 4)
    assert len(subset) == 4
    codecs = {c.codec for c in subset}
    resolutions = {(c.width, c.height) for c in subset}
    assert len(codecs) >= 2, "subset should cover multiple codecs"
    assert len(resolutions) >= 2, "subset should cover multiple resolutions"
    # deterministic
    again = select_test_subset(
        [Camera(camera_id=f"c{i}", codec="H264" if i % 2 else "H265",
                width=1920 if i < 3 else 1280, height=1080 if i < 3 else 720,
                status="ONLINE" if i % 3 else "OFFLINE") for i in range(8)], 4)
    assert [c.camera_id for c in again] == [c.camera_id for c in subset]
    assert select_test_subset([], 3) == []


def test_sentinel_stream_urls_encoding_and_redaction(monkeypatch):
    from config.settings import Settings
    from capture.sentinel_catalogue import redact_text, sentinel_stream_urls, redact_url

    s = Settings.from_env()
    monkeypatch.setattr(s, "sentinel_email", "officer@gujaratpolice.gov.in", raising=False)
    monkeypatch.setattr(s, "sentinel_password", "p@ss", raising=False)
    urls = sentinel_stream_urls("cam04", s)
    assert urls["rtsp"].startswith("rtsp://officer%40gujaratpolice.gov.in:p%40ss@")
    assert urls["rtsp"].endswith("@103.250.160.189:8554/stream/cam04")
    assert urls["hls"] == "https://cctv.corp8.cloud/cam04/index.m3u8"
    assert redact_url(urls["rtsp"]) == "rtsp://103.250.160.189:8554/stream/cam04"
    private = "https://operator:top-secret@example.test/live.m3u8?token=abc123#fragment"
    assert redact_url(private) == "https://example.test/live.m3u8"
    assert "top-secret" not in redact_text(f"decoder failed for {private}")

    # without credentials: HLS only, no authenticated URL is produced
    monkeypatch.setattr(s, "sentinel_email", "", raising=False)
    monkeypatch.setattr(s, "sentinel_password", "", raising=False)
    urls2 = sentinel_stream_urls("cam04", s)
    assert urls2["rtsp"] is None and urls2["hls"].endswith("index.m3u8")

    # invalid ids are rejected
    assert sentinel_stream_urls("../etc", s) == {"rtsp": None, "hls": None}


# ---------------------------------------------------------------------------
# Portal-gated CDN: form login + session cookie (verified against live grid:
# unauthenticated / Basic-auth requests get 302 -> /auth/login)
# ---------------------------------------------------------------------------

class _FakeResp:
    def __init__(self, status_code=200, payload=None, location=None):
        self.status_code = status_code
        self._payload = payload
        self.headers = {"location": location} if location else {}
        self.content = b""

    def json(self):
        if self._payload is None:
            raise ValueError("not json")
        return self._payload


class _FakeClient:
    """Minimal httpx.Client stand-in with scripted GET responses."""

    def __init__(self, get_responses, post_status=302):
        self.get_responses = list(get_responses)
        self.post_status = post_status
        self.calls = []
        self.last_kwargs = None

    def __call__(self, **kwargs):  # httpx.Client(...) construction
        self.last_kwargs = kwargs
        return self

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def get(self, url, **kwargs):
        self.calls.append(("GET", url))
        return self.get_responses.pop(0)

    def post(self, url, **kwargs):
        self.calls.append(("POST", url, kwargs))
        return _FakeResp(self.post_status, location="/")


def _patch_client(monkeypatch, fake):
    import httpx
    monkeypatch.setattr(httpx, "Client", fake)


def test_fetch_portal_login_flow_unlocks_catalogue(monkeypatch):
    import httpx

    fake = _FakeClient([
        _FakeResp(302, location="/auth/login"),     # first probe: gated
        _FakeResp(200, payload=SAMPLE_PAYLOAD),      # retry after login: JSON
    ])
    _patch_client(monkeypatch, fake)

    cat = SentinelCatalogue(email="alice@example.com", password="s3cret-pw")
    cameras = cat.fetch()

    assert cat.last_fetch_ok is True
    assert cat.get_camera("cam04") is not None
    kinds = [c[0] for c in fake.calls]
    assert kinds == ["GET", "POST", "GET"]
    _, login_url, login_kwargs = fake.calls[1]
    assert login_url.endswith("/auth/login")
    assert login_kwargs["data"]["email"] == "alice@example.com"
    assert login_kwargs["data"]["password"] == "s3cret-pw"
    # client-level auth/redirects: Basic auth attached, first probe never
    # follows redirects so credentials can't leak to a redirect target
    assert isinstance(fake.last_kwargs["auth"], httpx.BasicAuth)
    assert fake.last_kwargs["follow_redirects"] is False


def test_fetch_direct_200_skips_portal_login(monkeypatch):
    fake = _FakeClient([_FakeResp(200, payload=SAMPLE_PAYLOAD)])
    _patch_client(monkeypatch, fake)

    cat = SentinelCatalogue(email="alice@example.com", password="pw")
    cat.fetch()

    assert [c[0] for c in fake.calls] == ["GET"]
    assert cat.last_fetch_ok is True


def test_fetch_login_rejected_reports_credential_hint(monkeypatch):
    fake = _FakeClient([
        _FakeResp(302, location="/auth/login"),
        _FakeResp(302, location="/auth/login"),   # still gated after login
    ])
    _patch_client(monkeypatch, fake)

    cat = SentinelCatalogue(email="alice@example.com", password="wrong-pw")
    with pytest.raises(CatalogueError) as excinfo:
        cat.fetch()
    msg = str(excinfo.value)
    assert "HTTP 302" in msg
    assert "SENTINEL_PASSWORD" in msg      # actionable hint
    assert "wrong-pw" not in msg           # never leak the secret


def test_fetch_env_credentials_fallback(monkeypatch):
    monkeypatch.setenv("SENTINEL_EMAIL", "bob@example.com")
    monkeypatch.setenv("SENTINEL_PASSWORD", "env-pw")
    fake = _FakeClient([_FakeResp(200, payload=SAMPLE_PAYLOAD)])
    _patch_client(monkeypatch, fake)

    SentinelCatalogue().fetch()
    assert fake.last_kwargs["auth"] is not None


def test_fetch_without_credentials_sends_no_auth(monkeypatch):
    monkeypatch.delenv("SENTINEL_EMAIL", raising=False)
    monkeypatch.delenv("SENTINEL_PASSWORD", raising=False)
    fake = _FakeClient([_FakeResp(200, payload=SAMPLE_PAYLOAD)])
    _patch_client(monkeypatch, fake)

    SentinelCatalogue().fetch()
    assert fake.last_kwargs["auth"] is None


def test_fetch_refuses_credentials_on_unapproved_host(monkeypatch):
    import httpx

    def _boom(**kwargs):
        raise AssertionError("network must not be touched")

    monkeypatch.setattr(httpx, "Client", _boom)

    cat = SentinelCatalogue(
        url="https://evil.example.com/cameras.json",
        email="alice@example.com",
        password="s3cret-pw",
    )
    with pytest.raises(CatalogueError) as excinfo:
        cat.fetch()
    assert "unapproved" in cat.last_error
    assert "s3cret-pw" not in str(excinfo.value)
