"""
Tests for the Sentinel stream URL service.

Security-critical behaviours covered:
- '@' in the registered email is percent-encoded as %40 in RTSP URLs
- passwords are URL-quoted (special characters cannot break the URL)
- camera-id validation blocks path/URL injection
- redact() strips credentials for logging
- HLS/WHEP surfaces never contain credentials
- resolve_ingest_source() never embeds credentials unless configured
"""
import pytest

from app.core.config import settings
from app.services import sentinel_stream_service as svc


@pytest.fixture
def creds(monkeypatch):
    monkeypatch.setattr(settings, "SENTINEL_EMAIL", "officer@gujaratpolice.gov.in", raising=False)
    monkeypatch.setattr(settings, "SENTINEL_PASSWORD", "p@ss w0rd/2024", raising=False)
    monkeypatch.setattr(settings, "SENTINEL_RTSP_HOST", "103.250.160.189", raising=False)
    monkeypatch.setattr(settings, "SENTINEL_RTSP_PORT", 8554, raising=False)
    monkeypatch.setattr(settings, "SENTINEL_HLS_BASE_URL", "https://cctv.corp8.cloud", raising=False)


def test_email_at_sign_percent_encoded(creds):
    url = svc.get_rtsp_url("cam04")
    assert "officer%40gujaratpolice.gov.in" in url
    # no raw '@' inside the userinfo (the final user:pass@host '@' is legit)
    userinfo = url.split("://", 1)[1].rsplit("@", 1)[0]
    assert "@" not in userinfo


def test_password_is_url_quoted(creds):
    url = svc.get_rtsp_url("cam04")
    assert "p%40ss%20w0rd%2F2024" in url


def test_rtsp_shape(creds):
    url = svc.get_rtsp_url("cam04")
    assert url.startswith("rtsp://officer%40gujaratpolice.gov.in:")
    assert "@103.250.160.189:8554/stream/cam04" in url


def test_camera_id_validation_rejects_injection():
    for bad in ("../../etc/passwd", "cam04/other", "cam 04", "", "x" * 40, "cam?x=1"):
        with pytest.raises(ValueError):
            svc.get_rtsp_url(bad)
        with pytest.raises(ValueError):
            svc.get_hls_url(bad)


def test_redact_strips_credentials(creds):
    url = svc.get_rtsp_url("cam04")
    red = svc.redact(url)
    assert "officer" not in red and "p%40ss" not in red
    assert red == "rtsp://103.250.160.189:8554/stream/cam04"


def test_redact_strips_signed_query_and_scrubs_exception_text(creds):
    private = "https://operator:top-secret@example.test/live.m3u8?token=abc123&expires=999#frag"
    red = svc.redact(private)
    assert red == "https://example.test/live.m3u8"
    assert "top-secret" not in red and "token" not in red and "abc123" not in red
    assert svc.has_embedded_credentials(private)
    assert svc.has_embedded_credentials("https://example.test/live.m3u8?X-Amz-Signature=abc")
    assert "top-secret" not in svc.redact_text(f"decoder failed for {private}")


def test_hls_and_whep_never_carry_credentials(creds):
    assert svc.get_hls_url("cam04") == "https://cctv.corp8.cloud/cam04/index.m3u8"
    assert svc.get_whep_path("cam04") == "/sentinel/stream/cam04/whep"
    assert "@" not in svc.get_hls_url("cam04")


def test_rtsp_requires_credentials(monkeypatch):
    monkeypatch.setattr(settings, "SENTINEL_EMAIL", "", raising=False)
    monkeypatch.setattr(settings, "SENTINEL_PASSWORD", "", raising=False)
    with pytest.raises(RuntimeError):
        svc.get_rtsp_url("cam04")


def test_resolve_ingest_source_uses_rtsp_for_sentinel_camera(creds):
    out = svc.resolve_ingest_source(
        "CAM04", "https://cctv.corp8.cloud/cam04/index.m3u8", "hls"
    )
    assert out.startswith("rtsp://officer%40gujaratpolice.gov.in:")
    assert out.endswith("@103.250.160.189:8554/stream/cam04")


def test_resolve_ingest_source_falls_back_without_credentials(monkeypatch):
    monkeypatch.setattr(settings, "SENTINEL_EMAIL", "", raising=False)
    monkeypatch.setattr(settings, "SENTINEL_PASSWORD", "", raising=False)
    stored = "https://cctv.corp8.cloud/cam04/index.m3u8"
    assert svc.resolve_ingest_source("CAM04", stored, "hls") == stored


def test_resolve_ingest_source_ignores_non_sentinel_urls(creds):
    local = "/home/user/hack/cv-engine/feeds/india_road.mp4"
    assert svc.resolve_ingest_source("CAM01", local, "file") == local


def test_live_slot_keeps_private_ingest_only_in_environment(monkeypatch):
    private = "rtsp://operator:top-secret@camera.example:8554/stream/live?token=abc123"
    monkeypatch.setattr(settings, "LIVE_CAMERA_ID", "CAMLIVE", raising=False)
    monkeypatch.setattr(settings, "LIVE_CAMERA_STREAM_TYPE", "webrtc", raising=False)
    monkeypatch.setattr(settings, "LIVE_CAMERA_STREAM_URL", "https://viewer.example/live/whep?token=viewer", raising=False)
    monkeypatch.setattr(settings, "LIVE_CAMERA_INGEST_URL", private, raising=False)
    monkeypatch.setattr(settings, "LIVE_CAMERA_INGEST_TYPE", "rtsp", raising=False)

    assert svc.can_decode_for_detection("camlive", "webrtc")
    assert svc.resolve_ingest_source("CAMLIVE", "https://viewer.example/live/whep", "webrtc") == private
    assert svc.resolve_ingest_stream_type("CAMLIVE", "https://viewer.example/live/whep", "webrtc") == "rtsp"
    assert "top-secret" not in svc.redact(private)
    assert svc.redact_text("decoder rejected token abc123") == "decoder rejected token ***"


def test_is_sentinel_camera(creds):
    assert svc.is_sentinel_camera("https://cctv.corp8.cloud/cam04/index.m3u8")
    assert not svc.is_sentinel_camera("https://example.test/path/103.250.160.189")
    assert not svc.is_sentinel_camera("/tmp/clip.mp4")
    assert not svc.is_sentinel_camera("")


def test_whep_is_not_an_opencv_source_without_paired_ingest(monkeypatch):
    monkeypatch.setattr(settings, "LIVE_CAMERA_ID", "CAMLIVE", raising=False)
    monkeypatch.setattr(settings, "LIVE_CAMERA_STREAM_TYPE", "whep", raising=False)
    monkeypatch.setattr(settings, "LIVE_CAMERA_STREAM_URL", "https://viewer.example/whep", raising=False)
    monkeypatch.setattr(settings, "LIVE_CAMERA_INGEST_URL", "", raising=False)
    monkeypatch.setattr(settings, "LIVE_CAMERA_INGEST_TYPE", "", raising=False)
    assert not svc.can_decode_for_detection("CAMLIVE", "whep")
    assert not svc.can_decode_for_detection("OTHER", "whep")
