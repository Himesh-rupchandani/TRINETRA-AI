import os
import time
from unittest.mock import MagicMock, patch
import numpy as np

from backend.app.camera.packet import FramePacket, CameraState
from backend.app.camera.reconnect import StreamReconnectHandler
from backend.app.camera.stream import CameraStream
from backend.app.camera.manager import CameraManager


# ============================================================================
# Test Item 1: RTSP connection using TCP (Rule 1)
# ============================================================================
def test_rtsp_connection_forces_tcp():
    """Verify that RTSP streams set OPENCV_FFMPEG_CAPTURE_OPTIONS=rtsp_transport;tcp."""
    stream = CameraStream(
        camera_id="CAM_TEST_RTSP",
        source="rtsp://103.250.160.189:8554/stream/cam01",
        source_type="rtsp",
    )
    
    with patch("cv2.VideoCapture") as mock_cap_cls:
        mock_cap = MagicMock()
        mock_cap.isOpened.return_value = True
        mock_cap.read.return_value = (True, np.zeros((480, 640, 3), dtype=np.uint8))
        mock_cap.get.return_value = 25.0
        mock_cap_cls.return_value = mock_cap

        connected = stream.connect()
        assert connected is True
        assert "rtsp_transport;tcp" in os.environ.get("OPENCV_FFMPEG_CAPTURE_OPTIONS", "")
        assert stream.state == CameraState.ONLINE
    stream.release()


# ============================================================================
# Test Item 2: HLS Fallback when RTSP fails (Rule 1)
# ============================================================================
def test_hls_fallback_on_rtsp_failure():
    """Verify that when RTSP connection fails, HLS fallback URL is automatically attempted."""
    stream = CameraStream(
        camera_id="CAM_TEST_FALLBACK",
        source="rtsp://10.0.0.99:8554/blocked_rtsp",
        source_type="rtsp",
        fallback_source="https://cctv.corp8.cloud/cam04/index.m3u8",
    )

    call_count = 0

    def mock_video_capture(url, *args, **kwargs):
        nonlocal call_count
        call_count += 1
        mock = MagicMock()
        if "rtsp://" in url:
            # RTSP fails
            mock.isOpened.return_value = False
            mock.read.return_value = (False, None)
        else:
            # HLS fallback succeeds
            mock.isOpened.return_value = True
            mock.read.return_value = (True, np.zeros((480, 640, 3), dtype=np.uint8))
            mock.get.return_value = 25.0
        return mock

    with patch("cv2.VideoCapture", side_effect=mock_video_capture):
        with patch("backend.app.core.config.settings.DEMO_MODE", False):
            connected = stream.connect()
            assert connected is True
            assert stream.source_type == "hls"
            assert stream.source == "https://cctv.corp8.cloud/cam04/index.m3u8"
            assert stream.state == CameraState.ONLINE
    stream.release()


# ============================================================================
# Test Item 3: Successful frame reading yielding FramePacket (Rule 11 & 12)
# ============================================================================
def test_successful_frame_reading_packet():
    """Verify stream reads frame and packages into FramePacket."""
    stream = CameraStream(
        camera_id="CAM_TEST_FRAME",
        source="https://cctv.corp8.cloud/cam01/index.m3u8",
        source_type="hls",
    )
    
    with patch("cv2.VideoCapture") as mock_cap_cls:
        mock_cap = MagicMock()
        mock_cap.isOpened.return_value = True
        dummy_frame = np.ones((480, 640, 3), dtype=np.uint8) * 120
        mock_cap.read.return_value = (True, dummy_frame)
        mock_cap.get.side_effect = lambda prop: 1050.0 if prop == 0 else 30.0  # CAP_PROP_POS_MSEC = 0
        mock_cap_cls.return_value = mock_cap

        stream.connect()
        packet = stream.read_packet()

        assert packet is not None
        assert isinstance(packet, FramePacket)
        assert packet.camera_id == "CAM_TEST_FRAME"
        assert packet.frame.shape == (480, 640, 3)
        assert packet.pts_ms == 1050.0
        assert packet.sequence_number == 1
        assert packet.is_discontinuity is True  # First frame after connection
    stream.release()


# ============================================================================
# Test Item 4: PTS extraction and propagation (Rule 2 & 3)
# ============================================================================
def test_pts_extraction_and_propagation():
    """Verify that timing is driven by PTS deltas and not assumed constant FPS."""
    stream = CameraStream(
        camera_id="CAM_PTS_TEST",
        source="sample.mp4",
        source_type="file",
    )

    pts_values = [1000.0, 1045.0, 1110.0]  # Non-constant variable PTS
    pts_idx = 0

    mock_cap = MagicMock()
    mock_cap.isOpened.return_value = True
    mock_cap.read.return_value = (True, np.zeros((480, 640, 3), dtype=np.uint8))

    def mock_get(prop):
        nonlocal pts_idx
        if prop == 0:  # CAP_PROP_POS_MSEC
            val = pts_values[min(pts_idx, len(pts_values) - 1)]
            pts_idx += 1
            return val
        return 30.0

    mock_cap.get.side_effect = mock_get

    with patch("cv2.VideoCapture", return_value=mock_cap):
        stream.connect()
        p1 = stream.read_packet()
        p2 = stream.read_packet()
        p3 = stream.read_packet()

        assert p1 is not None and p1.pts_ms == 1000.0
        assert p2 is not None and p2.pts_ms == 1045.0
        assert p3 is not None and p3.pts_ms == 1110.0

        # Calculate delta_t from PTS (Rule 3)
        delta_t_1 = p2.pts_ms - p1.pts_ms
        delta_t_2 = p3.pts_ms - p2.pts_ms
        assert delta_t_1 == 45.0
        assert delta_t_2 == 65.0
    stream.release()


# ============================================================================
# Test Item 5 & 6: Irregular timing & transient decode slips (DEGRADED state) (Rules 4 & 6)
# ============================================================================
def test_irregular_timing_and_degraded_state():
    """Verify transient frame slips move camera to DEGRADED without instantly disconnecting."""
    stream = CameraStream(
        camera_id="CAM_DEGRADE_TEST",
        source="sample.mp4",
        source_type="file",
        consecutive_failure_threshold=10,
        stream_timeout_sec=5.0,
    )

    mock_cap = MagicMock()
    mock_cap.isOpened.return_value = True
    
    # 1 for connect(), 1 good frame for p1, then 4 failed reads
    read_results = [
        (True, np.zeros((480, 640, 3), dtype=np.uint8)),  # for connect()
        (True, np.zeros((480, 640, 3), dtype=np.uint8)),  # for read_packet() -> p1
        (False, None),  # slip 1
        (False, None),  # slip 2
        (False, None),  # slip 3 -> DEGRADED
        (False, None),  # slip 4 -> DEGRADED
    ]

    def mock_read():
        if read_results:
            return read_results.pop(0)
        return (False, None)

    mock_cap.read.side_effect = mock_read
    mock_cap.get.return_value = 100.0

    with patch("cv2.VideoCapture", return_value=mock_cap):
        stream.connect()
        assert stream.state == CameraState.ONLINE

        p1 = stream.read_packet()
        assert p1 is not None

        # Slip 1, 2, 3, 4
        stream.read_packet()
        stream.read_packet()
        stream.read_packet()
        stream.read_packet()

        # Should be DEGRADED, not OFFLINE or RECONNECTING yet
        assert stream.state == CameraState.DEGRADED
        assert stream.is_alive() is True  # Still considered alive while degraded
    stream.release()


# ============================================================================
# Test Item 7 & 8: Sustained failure & Exponential Backoff Reconnect (Rule 5)
# ============================================================================
def test_exponential_backoff_reconnect_progression():
    """Verify exponential backoff progression: 2.0s -> 4.0s -> 8.0s -> 16.0s -> 30.0s max."""
    reconnect_attempts = 0

    def mock_reconnect_cb():
        nonlocal reconnect_attempts
        reconnect_attempts += 1
        return reconnect_attempts >= 5  # Succeed on 5th attempt

    handler = StreamReconnectHandler(
        camera_id="CAM_BACKOFF_TEST",
        reconnect_callback=mock_reconnect_cb,
        initial_delay=2.0,
        max_delay=30.0,
        backoff_factor=2.0,
    )

    # Check progression sequence
    d1 = handler.get_next_delay()
    assert d1 == 2.0
    d2 = handler.get_next_delay()
    assert d2 == 4.0
    d3 = handler.get_next_delay()
    assert d3 == 8.0
    d4 = handler.get_next_delay()
    assert d4 == 16.0
    d5 = handler.get_next_delay()
    assert d5 == 30.0  # Capped at max_delay
    d6 = handler.get_next_delay()
    assert d6 == 30.0

    # Reset
    handler.reset()
    assert handler.current_delay == 2.0
    assert handler.attempts == 0


# ============================================================================
# Test Item 9: Decoder Warnings without application crash (Rule 6)
# ============================================================================
def test_decoder_warnings_do_not_crash():
    """Verify transient OpenCV decode warnings/exceptions are handled safely."""
    stream = CameraStream(
        camera_id="CAM_DECODE_ERR",
        source="rtsp://127.0.0.1:8554/corrupted",
        source_type="rtsp",
    )

    mock_cap = MagicMock()
    mock_cap.isOpened.return_value = True
    # 1 for connect(), 1 good for p1, 1 error for p2, 1 good for p3
    mock_cap.read.side_effect = [
        (True, np.zeros((480, 640, 3), dtype=np.uint8)),  # connect()
        (True, np.zeros((480, 640, 3), dtype=np.uint8)),  # p1
        RuntimeError("Could not find ref with POC"),        # p2
        (True, np.zeros((480, 640, 3), dtype=np.uint8)),  # p3
    ]
    mock_cap.get.return_value = 500.0

    with patch("cv2.VideoCapture", return_value=mock_cap):
        stream.connect()
        p1 = stream.read_packet()
        assert p1 is not None

        # Decoder warning should not raise unhandled exception
        p2 = stream.read_packet()
        assert p2 is None

        # Subsequent valid frame recovers
        p3 = stream.read_packet()
        assert p3 is not None
        assert stream.state == CameraState.ONLINE
    stream.release()


# ============================================================================
# Test Item 10: Complete Camera State Transitions (Rule 10)
# ============================================================================
def test_camera_state_transitions():
    """Verify camera transitions through OFFLINE -> CONNECTING -> ONLINE -> DEGRADED -> STOPPED."""
    stream = CameraStream(
        camera_id="CAM_STATE_TEST",
        source="sample.mp4",
        source_type="file",
        consecutive_failure_threshold=3,
        stream_timeout_sec=1.0,
    )

    assert stream.state == CameraState.OFFLINE

    mock_cap = MagicMock()
    mock_cap.isOpened.return_value = True
    mock_cap.read.side_effect = [
        (True, np.zeros((480, 640, 3), dtype=np.uint8)),
        (True, np.zeros((480, 640, 3), dtype=np.uint8)),
        (False, None),
        (False, None),
        (False, None),
    ]
    mock_cap.get.return_value = 100.0

    with patch("cv2.VideoCapture", return_value=mock_cap):
        stream.connect()
        assert stream.state == CameraState.ONLINE

        stream.read_packet()
        assert stream.state == CameraState.ONLINE

        # Slips into degraded / reconnecting
        stream.read_packet()
        stream.read_packet()
        stream.read_packet()
        assert stream.state in (CameraState.DEGRADED, CameraState.RECONNECTING)

        stream.release()
        assert stream.state == CameraState.STOPPED


# ============================================================================
# Test Item 11: Scene/Stream Discontinuity Detection (Rule 7)
# ============================================================================
def test_scene_discontinuity_detection():
    """Verify PTS rollbacks (loops) and large jumps trigger is_discontinuity=True."""
    stream = CameraStream(
        camera_id="CAM_DISC_TEST",
        source="sample.mp4",
        source_type="file",
    )

    pts_sequence = [1000.0, 1033.0, 1066.0, 100.0, 8000.0]  # 100.0 is rollback, 8000.0 is jump
    pts_idx = 0

    mock_cap = MagicMock()
    mock_cap.isOpened.return_value = True
    mock_cap.read.return_value = (True, np.zeros((480, 640, 3), dtype=np.uint8))
    
    def mock_get(prop):
        nonlocal pts_idx
        if prop == 0:
            val = pts_sequence[min(pts_idx, len(pts_sequence) - 1)]
            pts_idx += 1
            return val
        return 30.0

    mock_cap.get.side_effect = mock_get

    with patch("cv2.VideoCapture", return_value=mock_cap):
        stream.connect()
        p1 = stream.read_packet()  # Initial frame -> Discontinuity = True
        assert p1.is_discontinuity is True

        p2 = stream.read_packet()  # 1033ms -> Normal
        assert p2.is_discontinuity is False

        p3 = stream.read_packet()  # 1066ms -> Normal
        assert p3.is_discontinuity is False

        p4 = stream.read_packet()  # 100ms (Rollback < 1066 - 500) -> Discontinuity = True
        assert p4.is_discontinuity is True

        p5 = stream.read_packet()  # 8000ms (Jump > 100 + 5000) -> Discontinuity = True
        assert p5.is_discontinuity is True
    stream.release()


# ============================================================================
# Test Item 12: Proper resource release when processing stops (Rule 9 & 10)
# ============================================================================
def test_resource_release_on_stop():
    """Verify stopping camera closes VideoCapture handle and frees resources."""
    manager = CameraManager()
    
    with patch("cv2.VideoCapture") as mock_cap_cls:
        mock_cap = MagicMock()
        mock_cap.isOpened.return_value = True
        mock_cap.read.return_value = (True, np.zeros((480, 640, 3), dtype=np.uint8))
        mock_cap.get.return_value = 25.0
        mock_cap_cls.return_value = mock_cap

        stream = manager.add_camera("CAM_RELEASE", "rtsp://10.0.0.1:8554/cam", auto_start=True)
        time.sleep(0.1)

        assert stream.state == CameraState.ONLINE

        # Stop camera
        manager.stop_camera("CAM_RELEASE")
        assert stream.state == CameraState.STOPPED
        mock_cap.release.assert_called()


# ============================================================================
# Test Item 13: Multi-camera isolation (Rule 13)
# ============================================================================
def test_multi_camera_isolation():
    """Verify that a failure or crash in one camera does not crash other running cameras."""
    manager = CameraManager()

    def mock_cap_factory(url, *args, **kwargs):
        mock = MagicMock()
        if "failing" in url:
            mock.isOpened.return_value = True
            mock.read.side_effect = RuntimeError("Fatal hardware decoder error")
        else:
            mock.isOpened.return_value = True
            mock.read.return_value = (True, np.ones((480, 640, 3), dtype=np.uint8) * 200)
        mock.get.return_value = 25.0
        return mock

    with patch("cv2.VideoCapture", side_effect=mock_cap_factory):
        cam_good = manager.add_camera("CAM_GOOD", "rtsp://10.0.0.1:8554/good", auto_start=True)
        manager.add_camera("CAM_BAD", "rtsp://10.0.0.1:8554/failing", auto_start=True)

        time.sleep(0.3)

        # Good camera is operational despite bad camera's error
        assert cam_good.is_alive() is True
        latest_good = manager.get_latest_frame("CAM_GOOD")
        assert latest_good is not None

        # Clean up
        manager.stop_camera("CAM_GOOD")
        manager.stop_camera("CAM_BAD")


# ============================================================================
# Test Item 14: Subsampled frame selection preserves exact PTS (Rule 14)
# ============================================================================
def test_frame_subsampling_preserves_exact_pts():
    """Verify PROCESS_EVERY_N_FRAMES skips frames but preserves exact packet PTS."""
    received_packets = []

    def sample_callback(packet: FramePacket):
        received_packets.append(packet)

    manager = CameraManager()
    manager.set_pipeline_callback(sample_callback)

    pts_sequence = [1000.0, 1033.0, 1067.0, 1100.0, 1133.0, 1167.0]
    pts_idx = 0

    mock_cap = MagicMock()
    mock_cap.isOpened.return_value = True
    mock_cap.read.return_value = (True, np.zeros((480, 640, 3), dtype=np.uint8))

    def mock_get(prop):
        nonlocal pts_idx
        if prop == 0:
            val = pts_sequence[min(pts_idx, len(pts_sequence) - 1)]
            pts_idx += 1
            return val
        return 30.0

    mock_cap.get.side_effect = mock_get

    with patch("cv2.VideoCapture", return_value=mock_cap):
        with patch("backend.app.core.config.settings.PROCESS_EVERY_N_FRAMES", 2):
            manager.add_camera("CAM_SUBSAMPLE", "sample.mp4", source_type="file", auto_start=True)
            time.sleep(0.3)
            manager.stop_camera("CAM_SUBSAMPLE")

            # Check that received packets have sequence numbers multiples of 2
            assert len(received_packets) >= 1
            for pkt in received_packets:
                assert pkt.sequence_number % 2 == 0
                assert pkt.pts_ms > 0


# ============================================================================
# Test Item 15: Background non-blocking execution keeping event loop responsive (Rule 15)
# ============================================================================
def test_async_responsiveness_during_streaming():
    """Verify asyncio event loops and concurrent tasks remain responsive while ingestion runs."""
    import asyncio

    async def async_flow():
        manager = CameraManager()
        
        with patch("cv2.VideoCapture") as mock_cap_cls:
            mock_cap = MagicMock()
            mock_cap.isOpened.return_value = True
            mock_cap.read.return_value = (True, np.zeros((480, 640, 3), dtype=np.uint8))
            mock_cap.get.return_value = 30.0
            mock_cap_cls.return_value = mock_cap

            manager.add_camera("CAM_ASYNC_TEST", "rtsp://10.0.0.1:8554/cam", auto_start=True)

            # Ensure async tasks run concurrently without blocking
            t_start = time.perf_counter()
            await asyncio.sleep(0.1)
            t_elapsed = time.perf_counter() - t_start

            # Event loop was not blocked
            assert t_elapsed < 0.3

            # List cameras query runs instantaneously
            cam_list = manager.list_cameras()
            assert len(cam_list) == 1
            assert cam_list[0]["camera_id"] == "CAM_ASYNC_TEST"

            manager.stop_camera("CAM_ASYNC_TEST")

    asyncio.run(async_flow())
