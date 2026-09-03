"""Sentinel catalogue parsing.

The live payload is not reachable from CI, so these tests pin the *contract* the
parser must satisfy for every plausible shape: a bare list, a wrapped object, an
id-keyed map, alternative field names, partially-populated entries, and outright
failure. ``scripts/dump_catalogue.py`` records the real payload into
``tests/fixtures/`` so a captured response can be replayed here.
"""

from __future__ import annotations

import json

import pytest
import requests

from capture.sentinel_catalogue import (
    Camera,
    CatalogueError,
    fetch_catalogue,
    get_camera,
    get_cameras,
    parse_camera,
    parse_cameras,
    reset_cache,
    require_camera,
    select_test_subset,
)


class FakeResponse:
    def __init__(self, payload=None, text="", status=200, raise_for_status=None):
        self._payload = payload
        self.text = text or json.dumps(payload)
        self.status_code = status
        self._raise = raise_for_status

    def json(self):
        if self._payload is None:
            raise ValueError("no json")
        return self._payload

    def raise_for_status(self):
        if self._raise:
            raise self._raise


class FakeSession:
    def __init__(self, payload=None, error=None):
        self.payload = payload
        self.error = error
        self.calls = 0

    def get(self, url, timeout=None, headers=None):
        self.calls += 1
        if self.error:
            raise self.error
        return FakeResponse(self.payload)


# ---------------------------------------------------------------------------
# shapes
# ---------------------------------------------------------------------------

LIST_PAYLOAD = [
    {
        "id": "cam04",
        "name": "Paldi Circle",
        "location": "Paldi, Ahmedabad",
        "latitude": 23.0126,
        "longitude": 72.5647,
        "status": "online",
        "codec": "H264",
        "width": 1920,
        "height": 1080,
        "fps": 25,
        "rtsp_url": "rtsp://103.250.160.189:8554/stream/cam04",
        "hls_url": "https://cctv.corp8.cloud/cam04/index.m3u8",
    },
    {
        "camera_id": "cam12",
        "label": "Kankaria Lake Circle",
        "place": "Kankaria",
        "lat": 22.999,
        "lng": 72.602,
        "state": "OFFLINE",
        "video_codec": "h265",
        "resolution": "1920x1080",
        "frame_rate": "25",
        "streams": {
            "rtsp": "rtsp://103.250.160.189:8554/stream/cam12",
            "hls": "/cam12/index.m3u8",
        },
    },
]


def test_parses_a_bare_list_with_both_field_spelling_styles():
    cameras, skipped = parse_cameras(LIST_PAYLOAD)
    assert skipped == 0
    assert [c.camera_id for c in cameras] == ["cam04", "cam12"]
    first = cameras[0]
    assert first.name == "Paldi Circle"
    assert first.latitude == 23.0126 and first.longitude == 72.5647
    assert first.codec == "H264"
    assert first.resolution == (1920, 1080)
    assert first.fps == 25.0
    assert first.rtsp_url.startswith("rtsp://")
    assert first.is_online is True


def test_parses_aliases_relative_urls_and_status_words():
    cameras, _ = parse_cameras(LIST_PAYLOAD, base_url="https://cctv.corp8.cloud/cameras.json")
    second = cameras[1]
    assert second.codec == "h265"
    assert second.resolution == (1920, 1080)  # from "1920x1080"
    assert second.fps == 25.0  # from the string "25"
    assert second.is_online is False
    # Relative HLS path resolved against the catalogue origin.
    assert second.hls_url == "https://cctv.corp8.cloud/cam12/index.m3u8"


def test_parses_wrapped_and_id_keyed_payloads():
    wrapped, _ = parse_cameras({"cameras": LIST_PAYLOAD})
    assert len(wrapped) == 2
    keyed, _ = parse_cameras({"cam04": LIST_PAYLOAD[0], "cam12": LIST_PAYLOAD[1]})
    assert sorted(c.camera_id for c in keyed) == ["cam04", "cam12"]
    nested, nested_skipped = parse_cameras({"data": {"cameras": LIST_PAYLOAD}})
    assert [c.camera_id for c in nested] == ["cam04", "cam12"]
    assert nested_skipped == 0


def test_geojson_coordinate_order_is_corrected():
    entry = {"id": "cam21", "coordinates": [72.626, 23.073]}  # [lng, lat]
    cam = parse_camera(entry)
    assert cam.latitude == pytest.approx(23.073)
    assert cam.longitude == pytest.approx(72.626)


def test_partial_entries_never_raise_and_missing_fields_stay_none():
    cam = parse_camera({"id": "cam99"})
    assert cam is not None
    assert cam.latitude is None and cam.longitude is None
    assert cam.codec is None and cam.rtsp_url is None and cam.hls_url is None
    assert cam.has_location is False
    # No status field is not evidence of a failure.
    assert cam.is_online is True


def test_entries_without_a_usable_id_are_skipped_not_fatal():
    payload = [{"name": "no id here"}, {"id": "cam05", "status": "online"}, 42, None]
    cameras, skipped = parse_cameras(payload)
    assert [c.camera_id for c in cameras] == ["cam05"]
    assert skipped == 3


def test_numeric_surrogate_key_does_not_win_over_a_string_id():
    cam = parse_camera({"id": 4, "camera_id": "cam04"})
    assert cam.camera_id == "cam04"


def test_raw_metadata_is_preserved_for_future_fields():
    entry = {"id": "cam04", "owner": "Gujarat Police", "zone": "Central", "future_field": 7}
    cam = parse_camera(entry)
    assert cam.raw["owner"] == "Gujarat Police"
    assert cam.raw["future_field"] == 7


def test_duplicate_ids_are_deduplicated():
    cameras, skipped = parse_cameras([LIST_PAYLOAD[0], dict(LIST_PAYLOAD[0])])
    assert len(cameras) == 1 and skipped == 1


# ---------------------------------------------------------------------------
# fetching / failure handling
# ---------------------------------------------------------------------------


def test_get_cameras_uses_the_session_and_caches(settings):
    reset_cache()
    session = FakeSession({"cameras": LIST_PAYLOAD})
    first = get_cameras(settings=settings, session=session)
    second = get_cameras(settings=settings, session=session)
    assert len(first) == 2 and len(second) == 2
    assert session.calls == 1  # second call served from the TTL cache
    reset_cache()


def test_network_failure_degrades_to_an_empty_list(settings):
    reset_cache()
    session = FakeSession(error=requests.ConnectionError("blocked by egress policy"))
    assert get_cameras(settings=settings, session=session) == []
    with pytest.raises(CatalogueError):
        get_cameras(settings=settings, session=session, use_cache=False, strict=True)
    reset_cache()


def test_unparseable_payload_is_reported_not_raised(settings):
    reset_cache()
    catalogue = fetch_catalogue(
        url="https://example.test/cameras.json",
        session=FakeSession({"unexpected": "shape"}),
    )
    assert catalogue.cameras == []
    assert catalogue.ok is False
    assert "zero cameras" in (catalogue.error or "")
    reset_cache()


def test_unusable_url_raises(settings):
    with pytest.raises(CatalogueError):
        fetch_catalogue(url="not-a-url", session=FakeSession([]))


def test_get_camera_is_case_insensitive_and_ids_are_not_hardcoded(settings):
    reset_cache()
    session = FakeSession({"cameras": LIST_PAYLOAD})
    assert get_camera("CAM04", settings=settings, session=session).camera_id == "cam04"
    assert get_camera("cam12", settings=settings, session=session).camera_id == "cam12"
    assert get_camera("cam99", settings=settings, session=session) is None
    with pytest.raises(CatalogueError):
        require_camera("cam99", settings=settings, session=FakeSession({"cameras": LIST_PAYLOAD}))
    reset_cache()


# ---------------------------------------------------------------------------
# camera selection
# ---------------------------------------------------------------------------


def _camera(cid, codec=None, res=None, status="online", rtsp=True, hls=True):
    return Camera(
        camera_id=cid,
        codec=codec,
        width=res[0] if res else None,
        height=res[1] if res else None,
        status=status,
        rtsp_url=f"rtsp://h/{cid}" if rtsp else None,
        hls_url=f"https://h/{cid}.m3u8" if hls else None,
    )


def test_test_subset_covers_codecs_and_resolutions_not_just_the_first_n():
    cameras = [
        _camera("cam01", "H264", (1920, 1080)),
        _camera("cam02", "H264", (1920, 1080)),
        _camera("cam03", "H265", (1280, 720)),
        _camera("cam04", "H264", (2560, 1440)),
        _camera("cam05", "H265", (1920, 1080)),
        _camera("cam06", "H264", (1280, 720), status="offline"),
    ]
    subset = select_test_subset(cameras, size=4)
    assert len(subset) == 4
    codecs = {c.codec for c in subset}
    resolutions = {c.resolution for c in subset}
    assert codecs == {"H264", "H265"}
    assert len(resolutions) >= 3
    assert all(c.is_online for c in subset)


def test_test_subset_falls_back_to_offline_cameras_when_nothing_is_online():
    cameras = [_camera("cam01", status="offline"), _camera("cam02", status="offline")]
    assert len(select_test_subset(cameras, size=2)) == 2


def test_stream_url_respects_preferred_transport():
    cam = _camera("cam04")
    assert cam.stream_url("rtsp").startswith("rtsp://")
    assert cam.stream_url("hls").endswith(".m3u8")
    rtsp_only = _camera("cam05", hls=False)
    assert rtsp_only.stream_url("hls").startswith("rtsp://")  # graceful degradation
    assert Camera(camera_id="cam06").stream_url("rtsp") is None


def test_camera_describe_never_includes_a_credential():
    cam = parse_camera(
        {
            "id": "cam04",
            "rtsp_url": "rtsp://user:pass@10.0.0.1:8554/stream/cam04",
            "codec": "H264",
        }
    )
    assert "pass" not in cam.describe()
