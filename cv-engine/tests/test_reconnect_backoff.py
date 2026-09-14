"""Reconnect backoff (spec §9): 2 -> 4 -> 8 -> 16 -> cap 30, reset on success."""
from capture.reconnect import ExponentialBackoff, ReconnectLoop


def test_backoff_sequence_matches_spec():
    b = ExponentialBackoff(min_delay=2.0, max_delay=30.0, factor=2.0)
    seq = [b.next_delay() for _ in range(6)]
    assert seq == [2.0, 4.0, 8.0, 16.0, 30.0, 30.0], "backoff must cap around 30s"


def test_backoff_preview_does_not_consume():
    b = ExponentialBackoff()
    assert b.delays(5) == [2.0, 4.0, 8.0, 16.0, 30.0]
    assert b.attempts == 0
    assert b.next_delay() == 2.0


def test_backoff_reset_after_success():
    b = ExponentialBackoff()
    b.next_delay(); b.next_delay()
    assert b.next_delay() == 8.0
    b.reset()
    assert b.attempts == 0
    assert b.next_delay() == 2.0


def test_backoff_validates_bounds():
    import pytest
    with pytest.raises(ValueError):
        ExponentialBackoff(min_delay=0)
    with pytest.raises(ValueError):
        ExponentialBackoff(min_delay=10, max_delay=5)


def test_reconnect_loop_not_tight_and_resets():
    """Failures sleep with growing delays; success resets and stops."""
    sleeps = []
    calls = {"n": 0}

    def connect():
        calls["n"] += 1
        return calls["n"] >= 4  # succeeds on 4th attempt

    loop = ReconnectLoop(
        camera_id="cam04",
        connect_fn=connect,
        backoff=ExponentialBackoff(),
        sleep_fn=sleeps.append,
    )
    assert loop.connect_with_backoff() is True
    assert calls["n"] == 4
    # three failed attempts -> three sleeps, never zero (no tight loop)
    assert len(sleeps) == 3
    assert sleeps == [2.0, 4.0, 8.0]
    assert loop.backoff.attempts == 0  # reset after success


def test_reconnect_loop_max_attempts_exhausts():
    sleeps = []
    loop = ReconnectLoop(
        camera_id="cam04",
        connect_fn=lambda: False,
        backoff=ExponentialBackoff(max_attempts=3),
        sleep_fn=sleeps.append,
    )
    assert loop.connect_with_backoff() is False
    assert sleeps == [2.0, 4.0, 8.0]


def test_reconnect_loop_stops_on_stop_check():
    sleeps = []
    stop = {"flag": False}

    def connect():
        stop["flag"] = True  # stop requested during first attempt
        return False

    loop = ReconnectLoop(
        camera_id="cam04",
        connect_fn=connect,
        sleep_fn=sleeps.append,
        stop_check=lambda: stop["flag"],
    )
    assert loop.connect_with_backoff() is False
