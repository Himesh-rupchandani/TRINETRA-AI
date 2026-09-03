"""
Backend client (spec §23): timeout/retry/backoff, dead-letter, non-blocking.
Runs against a real local HTTP server — no Government feed involved.
"""
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from integration.backend_client import BackendClient


def _make_event(plate="GJ01AB1234"):
    return {
        "camera_id": "cam04",
        "vehicle_id": 17,
        "plate_raw": "GJ 01 AB-1234",
        "plate": plate,
        "plate_confidence": 0.94,
        "timestamp_pts": 123456.78,
        "event_time": "2026-09-02T14:32:18Z",
        "latitude": 23.0001,
        "longitude": 72.5001,
        "vehicle_class": "car",
        "evidence_ref": "cam04/x.jpg",
    }


class _Handler(BaseHTTPRequestHandler):
    mode = "ok"          # ok | flaky | reject | down
    received = []
    calls = 0

    def do_POST(self):
        _Handler.calls += 1
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length) or b"{}")
        _Handler.received.append((self.path, body))
        if self.path != "/api/events":
            self.send_response(404)
            self.end_headers()
            return
        if _Handler.mode == "flaky" and _Handler.calls < 3:
            self.send_response(500)
            self.end_headers()
            return
        if _Handler.mode == "reject":
            self.send_response(422)
            self.end_headers()
            self.wfile.write(b'{"detail":"bad payload"}')
            return
        self.send_response(201)
        self.end_headers()
        self.wfile.write(b'{"ok":true}')

    def log_message(self, *args):  # silence
        pass


@pytest.fixture()
def http_server():
    _Handler.received = []
    _Handler.calls = 0
    _Handler.mode = "ok"
    srv = HTTPServer(("127.0.0.1", 0), _Handler)
    th = threading.Thread(target=srv.serve_forever, daemon=True)
    th.start()
    yield f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()


def test_post_event_accepted(http_server, tmp_path):
    client = BackendClient(base_url=http_server, dead_letter_path=str(tmp_path / "dl.jsonl"))
    assert client.send_now(_make_event()) is True
    assert client.stats["accepted"] == 1
    path, body = _Handler.received[0]
    assert path == "/api/events"
    assert body["plate"] == "GJ01AB1234"
    assert body["camera_id"] == "cam04"


def test_retry_with_backoff_then_success(http_server, tmp_path):
    _Handler.mode = "flaky"  # 500, 500, then 201
    sleeps = []
    client = BackendClient(
        base_url=http_server,
        max_retries=3,
        backoff_base_sec=1.0,
        dead_letter_path=str(tmp_path / "dl.jsonl"),
        sleep_fn=sleeps.append,
    )
    assert client.send_now(_make_event()) is True
    assert _Handler.calls == 3
    assert sleeps == [1.0, 2.0], "exponential backoff between retries"
    assert client.stats["accepted"] == 1


def test_no_infinite_retry_and_dead_letter(http_server, tmp_path):
    _Handler.mode = "flaky"  # 500 for the first two calls — exceeds retry budget of 1
    dl = tmp_path / "dl.jsonl"
    client = BackendClient(base_url=http_server, max_retries=1,
                           dead_letter_path=str(dl), sleep_fn=lambda s: None)
    assert client.send_now(_make_event()) is False
    assert _Handler.calls == 2  # initial + 1 retry, then stops — no infinite loop
    assert client.stats["failed_after_retries"] == 1
    lines = dl.read_text().strip().splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0])["reason"] == "retries_exhausted"
    assert json.loads(lines[0])["event"]["plate"] == "GJ01AB1234"


def test_4xx_not_retried_dead_lettered(http_server, tmp_path):
    _Handler.mode = "reject"
    dl = tmp_path / "dl.jsonl"
    client = BackendClient(base_url=http_server, max_retries=5,
                           dead_letter_path=str(dl), sleep_fn=lambda s: None)
    assert client.send_now(_make_event()) is False
    assert _Handler.calls == 1, "4xx must not be retried"
    assert json.loads(dl.read_text().strip())["reason"] == "http_422"


def test_submit_is_nonblocking_when_backend_down(tmp_path):
    """A dead backend must never block the CV pipeline (spec §23)."""
    client = BackendClient(
        base_url="http://127.0.0.1:1",  # nothing listening
        timeout_sec=0.3,
        max_retries=1,
        dead_letter_path=str(tmp_path / "dl.jsonl"),
    )
    client.start()
    t0 = time.monotonic()
    for i in range(50):
        assert client.submit(_make_event()) is True
    elapsed = time.monotonic() - t0
    assert elapsed < 0.5, f"submit must be near-instant, took {elapsed:.2f}s"
    client.close(timeout_sec=3)
    assert client.stats["submitted"] == 50


def test_queue_full_drops_to_dead_letter(tmp_path):
    dl = tmp_path / "dl.jsonl"
    client = BackendClient(base_url="http://127.0.0.1:1", queue_size=2,
                           dead_letter_path=str(dl))
    # worker NOT started -> queue fills up
    assert client.submit(_make_event()) is True
    assert client.submit(_make_event()) is True
    assert client.submit(_make_event()) is False
    assert client.stats["dropped_queue_full"] == 1
    assert "queue_full" in dl.read_text()
