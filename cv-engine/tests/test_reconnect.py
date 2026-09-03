"""Reconnect backoff and the supervised capture loop."""

from __future__ import annotations

import itertools

import numpy as np

from capture.frames import FramePacket
from capture.reconnect import ExponentialBackoff, ReconnectingCapture, backoff_schedule
from capture.sentinel_catalogue import Camera


class FakeCapture:
    """Scripted capture: ``fail_opens`` failed opens, then ``frames`` good reads."""

    def __init__(self, fail_opens=0, frames=3, fail_reads=0, source="rtsp"):
        self.fail_opens = fail_opens
        self.frames = frames
        self.fail_reads = fail_reads
        self.source = source
        self.opened = False
        self.closed = False
        self.open_calls = 0
        self._i = 0

    def open(self):
        self.open_calls += 1
        if self.open_calls <= self.fail_opens:
            return False
        self.opened = True
        return True

    def read(self):
        if self._i < self.fail_reads:
            self._i += 1
            return None
        if self._i >= self.fail_reads + self.frames:
            return None
        self._i += 1
        return FramePacket(frame=np.zeros((4, 4, 3), np.uint8), camera_id="cam04", pts_ms=self._i * 40.0)

    def close(self):
        self.closed = True


class BoundedSleep:
    """Records backoff delays, and refuses to spin forever.

    The production loop is paced by the real ``time.sleep``; a test double that
    returns instantly would otherwise let a mis-bounded test burn CPU and RAM.
    """

    def __init__(self, limit: int = 25):
        self.calls: list[float] = []
        self.limit = limit

    def __call__(self, delay: float) -> None:
        self.calls.append(delay)
        if len(self.calls) > self.limit:
            raise AssertionError(f"reconnect loop exceeded {self.limit} backoff sleeps")

    def __eq__(self, other):
        return self.calls == other

    def __len__(self):
        return len(self.calls)


# ---------------------------------------------------------------------------
# backoff schedule
# ---------------------------------------------------------------------------


def test_backoff_follows_2_4_8_16_and_caps_at_30():
    assert backoff_schedule(6, min_s=2, max_s=30, multiplier=2) == [2, 4, 8, 16, 30, 30]


def test_backoff_is_capped_by_configured_maximum():
    assert backoff_schedule(4, min_s=1, max_s=5, multiplier=2) == [1, 2, 4, 5]


def test_backoff_reset_returns_to_the_minimum():
    bo = ExponentialBackoff(min_s=2, max_s=30, jitter=0.0)
    assert [bo.next_delay() for _ in range(3)] == [2, 4, 8]
    bo.reset()
    assert bo.next_delay() == 2
    assert bo.attempts == 1


def test_jitter_stays_within_bounds():
    bo = ExponentialBackoff(min_s=2, max_s=30, jitter=0.15)
    for _ in range(50):
        delay = bo.next_delay()
        assert 0 < delay <= 30


def test_backoff_rejects_nonsense_bounds():
    try:
        ExponentialBackoff(min_s=0)
    except ValueError:
        return
    raise AssertionError("expected ValueError for a zero minimum")


def test_peek_does_not_advance_the_schedule():
    bo = ExponentialBackoff(min_s=2, max_s=30, jitter=0.0)
    assert bo.peek_delay() == 2
    assert bo.peek_delay() == 2
    assert bo.next_delay() == 2
    assert bo.peek_delay() == 4


# ---------------------------------------------------------------------------
# supervised loop
# ---------------------------------------------------------------------------


def _camera():
    return Camera(camera_id="cam04", rtsp_url="rtsp://host/cam04")


def test_reconnects_after_failed_opens_then_delivers_frames():
    sleeps = BoundedSleep()
    captures = [
        FakeCapture(fail_opens=1, frames=0),  # attempt 1: open fails
        FakeCapture(fail_opens=0, frames=2),  # attempt 2: works
        FakeCapture(fail_opens=0, frames=0),
    ]
    made = iter(captures)
    supervisor = ReconnectingCapture(
        camera=_camera(),
        factory=lambda: next(made),
        jitter=0.0,
        max_reconnects=3,
        sleep_fn=sleeps,
        clock=lambda: 0.0,
    )
    # Take exactly the frames we expect, then stop: the loop is infinite by
    # design (an unattended run must never exit), so a test must bound it.
    packets = list(itertools.islice(supervisor.frames(), 2))
    supervisor.stop()
    assert len(packets) == 2
    assert sleeps.calls == [2.0]  # exactly one backoff, not a tight loop
    assert supervisor.state.reconnects == 1
    assert captures[0].closed is True  # the dead capture was released


def test_backoff_escalates_across_repeated_failures_and_stops_at_max_reconnects():
    sleeps = BoundedSleep()
    supervisor = ReconnectingCapture(
        camera=_camera(),
        factory=lambda: FakeCapture(fail_opens=99),
        jitter=0.0,
        max_reconnects=5,
        sleep_fn=sleeps,
        clock=lambda: 0.0,
    )
    assert list(supervisor.frames()) == []
    assert sleeps.calls == [2.0, 4.0, 8.0, 16.0, 30.0]


def test_backoff_resets_once_the_connection_is_stable():
    clock = {"t": 0.0}
    sleeps = BoundedSleep()
    captures = [
        FakeCapture(fail_opens=1, frames=0),  # drives backoff to 2s
        FakeCapture(fail_opens=0, frames=3),  # then a stable connection
    ]
    made = iter(captures)
    supervisor = ReconnectingCapture(
        camera=_camera(),
        factory=lambda: next(made),
        jitter=0.0,
        stable_s=10.0,
        max_reconnects=3,
        sleep_fn=sleeps,
        clock=lambda: clock["t"],
    )

    packets = []
    for packet in itertools.islice(supervisor.frames(), 3):
        clock["t"] += 5.0  # the link is healthy and time is passing
        packets.append(packet)
    supervisor.stop()

    assert len(packets) == 3
    assert sleeps.calls == [2.0]
    assert supervisor.backoff.attempts == 0  # recovered: schedule is back at 2s


def test_read_failures_are_tolerated_before_giving_up_on_the_connection():
    sleeps = BoundedSleep()
    capture = FakeCapture(fail_opens=0, frames=2, fail_reads=3)
    supervisor = ReconnectingCapture(
        camera=_camera(),
        factory=lambda: capture,
        jitter=0.0,
        max_reconnects=1,
        sleep_fn=sleeps,
        clock=lambda: 0.0,
    )
    packets = list(supervisor.frames())
    assert len(packets) == 2  # transient read failures did not kill the stream


def test_a_raising_capture_is_contained():
    class Boom:
        source = "rtsp"

        def open(self):
            raise RuntimeError("decoder exploded")

        def read(self):  # pragma: no cover
            return None

        def close(self):
            pass

    sleeps = BoundedSleep()
    supervisor = ReconnectingCapture(
        camera=_camera(),
        factory=Boom,
        jitter=0.0,
        max_reconnects=2,
        sleep_fn=sleeps,
        clock=lambda: 0.0,
    )
    assert list(supervisor.frames()) == []
    assert "decoder exploded" in (supervisor.state.last_error or "")
    assert len(sleeps) == 2
