"""Evidence writing and backend client behaviour."""

from __future__ import annotations

import json
import threading

import numpy as np
import pytest

from config.settings import load_settings
from evidence.evidence_writer import EvidenceWriter
from integration.backend_client import BackendClient


def _frame():
    return (np.random.rand(48, 64, 3) * 255).astype(np.uint8)


@pytest.fixture
def tmp_settings(tmp_path):
    return load_settings(
        env={},
        evidence_dir=str(tmp_path / "evidence"),
        dead_letter_path=str(tmp_path / "dl.jsonl"),
        backend_max_retries=2,
        backend_retry_base_s=0.01,
        backend_retry_max_s=0.02,
    )


# ---------------------------------------------------------------------------
# evidence
# ---------------------------------------------------------------------------


def test_evidence_writes_frame_and_crop_with_deterministic_names(tmp_settings):
    writer = EvidenceWriter(tmp_settings)
    ref = writer.write(_frame(), _frame(), "cam04", 17, "GJ01AB1234", 1234.0)
    assert ref is not None
    assert ref.startswith("cam04/") and ref.endswith(".jpg")
    assert ref == "cam04/GJ01AB1234_17_1234.jpg"
    base = tmp_settings.evidence_dir
    assert (tmp_path_for(base, ref)).exists()
    assert (tmp_path_for(base, ref.replace(".jpg", "_plate.jpg"))).exists()


def tmp_path_for(base, ref):
    from pathlib import Path

    return Path(base) / ref


def test_hostile_plate_cannot_escape_the_evidence_dir(tmp_settings):
    writer = EvidenceWriter(tmp_settings)
    ref = writer.write(_frame(), None, "cam04", 1, "../../../../etc/passwd", 5.0)
    assert ref is not None
    assert ".." not in ref
    assert "cam04/" in ref


def test_low_confidence_does_not_produce_evidence(tmp_settings):
    writer = EvidenceWriter(tmp_settings)
    assert writer.enabled(0.2) is False  # below evidence_min_confidence
    assert writer.enabled(0.9) is True


def test_write_failure_is_contained_and_reported(tmp_settings):
    writer = EvidenceWriter(tmp_settings)
    ref = writer.write(np.zeros((0, 0, 3), np.uint8), None, "cam04", 1, "GJ01AB1234", 1.0)
    assert ref is None
    assert writer.skipped == 1


# ---------------------------------------------------------------------------
# backend client
# ---------------------------------------------------------------------------


class FakeResponse:
    def __init__(self, status=200):
        self.status_code = status


class ScriptedBackend:
    """Returns the scripted status per call; records posted payloads.

    When the script is exhausted ``repeat`` is used (default: 200), so a backend
    that should keep failing is modelled with ``repeat=500``.
    """

    def __init__(self, statuses=(), repeat=200):
        self.statuses = list(statuses)
        self.repeat = repeat
        self.posted = []

    def post(self, url, json=None, timeout=None):
        self.posted.append((url, json))
        status = self.statuses.pop(0) if self.statuses else self.repeat
        if isinstance(status, Exception):
            raise status
        return FakeResponse(status)


def _payload():
    return {
        "camera_id": "cam04", "vehicle_id": 17, "plate_raw": "GJ 01 AB 1234",
        "plate": "GJ01AB1234", "plate_confidence": 0.94, "timestamp_pts": 1.0,
        "event_time": "2026-09-02T14:32:18Z", "latitude": 23.0, "longitude": 72.5,
        "vehicle_class": "car", "evidence_ref": None,
    }


def test_successful_post_returns_ok(tmp_settings):
    backend_session = ScriptedBackend([201])
    client = BackendClient(tmp_settings, session=backend_session)
    ok, status, error = client.post_now(_payload())
    assert ok is True and status == 201 and error == ""
    assert client.sent == 1


def test_5xx_retries_then_succeeds(tmp_settings):
    # max_retries=2 in tmp_settings -> two attempts; second one succeeds.
    session = ScriptedBackend([500, 200])
    client = BackendClient(tmp_settings, session=session)
    ok, status, _ = client.post_now(_payload())
    assert ok is True and status == 200
    assert len(session.posted) == 2


def test_client_error_is_not_retried(tmp_settings):
    session = ScriptedBackend([400])
    client = BackendClient(tmp_settings, session=session)
    ok, status, _ = client.post_now(_payload())
    assert ok is False and status == 400
    assert len(session.posted) == 1  # no pointless retries on 4xx


def test_exhausted_retries_dead_letter(tmp_settings):
    session = ScriptedBackend(repeat=500)  # a backend that never recovers
    client = BackendClient(tmp_settings, session=session)
    ok, status, _ = client.post_now(_payload())
    assert ok is False
    assert client.failed == 1
    # The queued path dead-letters; verify the worker path:
    client.enqueue(_payload())
    client.start()
    client.stop(drain_timeout_s=2.0)
    dl = tmp_settings.dead_letter_path
    lines = [json.loads(x) for x in open(dl)]
    assert len(lines) >= 1
    assert lines[0]["payload"]["plate"] == "GJ01AB1234"


def test_invalid_schema_is_rejected_before_any_request(tmp_settings):
    session = ScriptedBackend([200])
    client = BackendClient(tmp_settings, session=session)
    bad = _payload()
    bad["plate_confidence"] = 9.9
    ok, status, error = client.post_now(bad)
    assert ok is False and status is None
    assert "plate_confidence" in error
    assert session.posted == []


def test_queue_worker_sends_and_never_blocks_enqueue(tmp_settings):
    session = ScriptedBackend([200])
    client = BackendClient(tmp_settings, session=session)
    client.start()
    assert client.enqueue(_payload()) is True
    # Wait for the worker to drain.
    deadline = threading.Event()
    for _ in range(100):
        if client.sent >= 1:
            break
        deadline.wait(0.05)
    client.stop()
    assert client.sent == 1
    assert len(session.posted) == 1
