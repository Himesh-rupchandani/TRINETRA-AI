"""Reconnection with exponential backoff.

Behaviour required by the Sentinel guidance:

* connect -> read -> failure -> backoff -> reconnect
* backoff roughly 2s, 4s, 8s, 16s, capped at ~30s
* never a tight reconnect loop
* backoff resets once a connection has been *stable* for a while
* every transition is logged

``sleep`` and ``clock`` are injectable so the backoff schedule can be unit
tested without waiting 30 real seconds.
"""

from __future__ import annotations

import logging
import random
import time
from dataclasses import dataclass
from typing import Callable, Iterable, Iterator, Optional

from capture.frames import FramePacket
from capture.sentinel_catalogue import Camera
from logging_setup import log_event

log = logging.getLogger("trinetra.reconnect")

DEFAULT_MIN_S = 2.0
DEFAULT_MAX_S = 30.0
DEFAULT_MULTIPLIER = 2.0
DEFAULT_JITTER = 0.15
DEFAULT_STABLE_S = 15.0


class ExponentialBackoff:
    """2 -> 4 -> 8 -> 16 -> 30 (capped), with optional jitter."""

    def __init__(
        self,
        min_s: float = DEFAULT_MIN_S,
        max_s: float = DEFAULT_MAX_S,
        multiplier: float = DEFAULT_MULTIPLIER,
        jitter: float = DEFAULT_JITTER,
        rng: random.Random | None = None,
    ) -> None:
        if min_s <= 0 or max_s <= 0:
            raise ValueError("backoff bounds must be positive")
        self.min_s = float(min_s)
        self.max_s = max(float(max_s), float(min_s))
        self.multiplier = max(float(multiplier), 1.0)
        self.jitter = min(max(float(jitter), 0.0), 0.9)
        self._rng = rng or random.Random()
        self._attempt = 0

    @property
    def attempts(self) -> int:
        return self._attempt

    def next_delay(self) -> float:
        """Delay for the next attempt, then advance the schedule."""
        raw = self.min_s * (self.multiplier ** self._attempt)
        capped = min(raw, self.max_s)
        self._attempt += 1
        if self.jitter:
            spread = capped * self.jitter
            capped = max(self.min_s * (1 - self.jitter), capped + self._rng.uniform(-spread, spread))
        return min(capped, self.max_s)

    def peek_delay(self) -> float:
        """What the next delay would be, without advancing (for logging)."""
        raw = min(self.min_s * (self.multiplier ** self._attempt), self.max_s)
        return raw

    def reset(self) -> None:
        self._attempt = 0


@dataclass
class ConnectionState:
    connected: bool = False
    attempts: int = 0
    last_error: str | None = None
    last_connected_at: float | None = None
    reconnects: int = 0
    frames_since_open: int = 0


class ReconnectingCapture:
    """Wraps a capture object and keeps it alive across failures.

    ``factory`` builds a *fresh* capture each time (a stale decoder cannot be
    revived). The generator yields :class:`FramePacket` forever unless
    ``stop()`` is called or ``max_reconnects`` is exceeded — which is what makes
    a multi-hour unattended run possible.
    """

    def __init__(
        self,
        camera: Camera,
        factory: Callable[[], object],
        min_s: float = DEFAULT_MIN_S,
        max_s: float = DEFAULT_MAX_S,
        multiplier: float = DEFAULT_MULTIPLIER,
        jitter: float = DEFAULT_JITTER,
        stable_s: float = DEFAULT_STABLE_S,
        max_reconnects: int | None = None,
        sleep_fn: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
        on_reconnect: Callable[[int, str], None] | None = None,
    ) -> None:
        self.camera = camera
        self.factory = factory
        self.backoff = ExponentialBackoff(min_s, max_s, multiplier, jitter)
        self.stable_s = float(stable_s)
        self.max_reconnects = max_reconnects
        self._sleep = sleep_fn
        self._clock = clock
        self._on_reconnect = on_reconnect
        self.state = ConnectionState()
        self._stopped = False

    def stop(self) -> None:
        self._stopped = True

    def frames(self) -> Iterator[FramePacket]:
        """Yield frames, reconnecting on failure. Never raises for I/O errors."""
        capture = None
        opened_at = 0.0
        while not self._stopped:
            try:
                capture = self.factory()
                opened = bool(capture.open())
            except Exception as exc:  # noqa: BLE001 - decoder libs raise anything
                opened = False
                self.state.last_error = f"{type(exc).__name__}: {exc}"
            else:
                self.state.last_error = None if opened else "open() returned False"

            if not opened:
                if not self._backoff_and_continue(capture, "open_failed"):
                    return
                continue

            # Connected.
            self.state.connected = True
            self.state.attempts = self.backoff.attempts
            self.state.last_connected_at = self._clock()
            self.state.frames_since_open = 0
            opened_at = self._clock()
            log_event(
                log,
                "camera_connected",
                camera=self.camera.camera_id,
                source=getattr(capture, "source", "?"),
                reconnects=self.state.reconnects,
            )

            consecutive_failures = 0
            while not self._stopped:
                packet = self._read(capture)
                if packet is None:
                    consecutive_failures += 1
                    if consecutive_failures >= 15:  # ~0.5s of nothing at 30fps
                        self.state.last_error = "read returned no frame 15x in a row"
                        log_event(
                            log,
                            "frame_decode_failure",
                            level=logging.WARNING,
                            camera=self.camera.camera_id,
                            consecutive=consecutive_failures,
                        )
                        break
                    continue
                consecutive_failures = 0
                self.state.frames_since_open += 1
                # Reset backoff once the link has proven stable.
                if (
                    self.backoff.attempts
                    and (self._clock() - opened_at) >= self.stable_s
                ):
                    self.backoff.reset()
                    log_event(
                        log,
                        "backoff_reset",
                        camera=self.camera.camera_id,
                        after_s=self.stable_s,
                    )
                yield packet

            delivered = self.state.frames_since_open
            self._close_quietly(capture)
            self.state.connected = False
            log_event(
                log,
                "camera_disconnected",
                level=logging.WARNING,
                camera=self.camera.camera_id,
                frames_delivered=delivered,
                error=self.state.last_error,
            )
            if delivered == 0:
                # Opened but produced nothing (a camera that accepts the
                # connection and sends no video). Retry with backoff — without
                # this the loop would spin hot on a permanently silent feed.
                if not self._backoff_and_continue(None, "no_frames_delivered"):
                    return

    def _backoff_and_continue(self, capture, reason: str) -> bool:
        """Sleep for the next backoff interval. Returns False when giving up."""
        if self.max_reconnects is not None and self.state.reconnects >= self.max_reconnects:
            log_event(
                log,
                "reconnect_giving_up",
                level=logging.ERROR,
                camera=self.camera.camera_id,
                attempts=self.state.reconnects,
                reason=reason,
                error=self.state.last_error,
            )
            return False
        delay = self.backoff.next_delay()
        self.state.reconnects += 1
        self.state.connected = False
        log_event(
            log,
            "reconnect_scheduled",
            level=logging.WARNING,
            camera=self.camera.camera_id,
            attempt=self.state.reconnects,
            delay_s=delay,
            reason=reason,
            error=self.state.last_error,
        )
        if self._on_reconnect:
            self._on_reconnect(self.state.reconnects, str(self.state.last_error))
        self._sleep(delay)
        self._close_quietly(capture)
        return True

    @staticmethod
    def _read(capture) -> Optional[FramePacket]:
        try:
            return capture.read()
        except Exception as exc:  # noqa: BLE001
            log_event(
                log,
                "frame_decode_failure",
                level=logging.WARNING,
                error=f"{type(exc).__name__}: {exc}",
            )
            return None

    @staticmethod
    def _close_quietly(capture) -> None:
        if capture is None:
            return
        try:
            capture.close()
        except Exception:  # noqa: BLE001
            pass


def backoff_schedule(
    n: int,
    min_s: float = DEFAULT_MIN_S,
    max_s: float = DEFAULT_MAX_S,
    multiplier: float = DEFAULT_MULTIPLIER,
) -> list[float]:
    """The uncapped/capped schedule, exposed for tests and documentation."""
    bo = ExponentialBackoff(min_s, max_s, multiplier, jitter=0.0)
    return [bo.next_delay() for _ in range(n)]
