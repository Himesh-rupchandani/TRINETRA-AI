"""
Reconnection with exponential backoff (spec §9).

Sequence: ~2s -> 4s -> 8s -> 16s -> capped at ~30s. Never a tight loop.
Backoff resets after a successful, stable connection.
"""
from __future__ import annotations

import logging
import time
from typing import Callable, Optional

logger = logging.getLogger("cv_engine.reconnect")


class ExponentialBackoff:
    """Delay generator: min * factor^n, capped at max. Injectable clock for tests."""

    def __init__(
        self,
        min_delay: float = 2.0,
        max_delay: float = 30.0,
        factor: float = 2.0,
        max_attempts: int = 0,  # 0 = unlimited
    ):
        if min_delay <= 0 or max_delay < min_delay:
            raise ValueError("require 0 < min_delay <= max_delay")
        self.min_delay = min_delay
        self.max_delay = max_delay
        self.factor = factor
        self.max_attempts = max_attempts
        self.attempts = 0
        self._next_delay = min_delay

    def next_delay(self) -> float:
        """Return the current delay and advance the backoff state."""
        self.attempts += 1
        delay = self._next_delay
        self._next_delay = min(self._next_delay * self.factor, self.max_delay)
        return delay

    def exhausted(self) -> bool:
        return bool(self.max_attempts and self.attempts >= self.max_attempts)

    def reset(self) -> None:
        self.attempts = 0
        self._next_delay = self.min_delay

    def delays(self, count: int) -> list:
        """Preview the next `count` delays without consuming them (for tests/logs)."""
        d, out = self.min_delay, []
        for _ in range(count):
            out.append(d)
            d = min(d * self.factor, self.max_delay)
        return out


class ReconnectLoop:
    """
    connect -> read -> failure -> backoff -> reconnect

    `connect_fn` returns True on success. `sleep_fn` is injectable so tests
    can run without real waiting.
    """

    def __init__(
        self,
        camera_id: str,
        connect_fn: Callable[[], bool],
        backoff: Optional[ExponentialBackoff] = None,
        sleep_fn: Callable[[float], None] = time.sleep,
        stop_check: Optional[Callable[[], bool]] = None,
    ):
        self.camera_id = camera_id
        self.connect_fn = connect_fn
        self.backoff = backoff or ExponentialBackoff()
        self.sleep_fn = sleep_fn
        self.stop_check = stop_check or (lambda: False)

    def connect_with_backoff(self) -> bool:
        """Try to (re)connect, backing off between attempts. Returns success."""
        while not self.stop_check():
            if self.backoff.exhausted():
                logger.error("[%s] reconnect attempts exhausted", self.camera_id)
                return False
            try:
                if self.connect_fn():
                    if self.backoff.attempts > 0:
                        logger.info(
                            "[%s] connected after %d reconnect attempt(s)",
                            self.camera_id,
                            self.backoff.attempts,
                        )
                    self.backoff.reset()
                    return True
            except Exception as exc:
                logger.warning("[%s] connect attempt raised: %s", self.camera_id, exc)

            delay = self.backoff.next_delay()
            logger.warning(
                "[%s] reconnect in %.1fs (attempt %d)",
                self.camera_id,
                delay,
                self.backoff.attempts,
            )
            self.sleep_fn(delay)
        return False

    def mark_stable(self) -> None:
        """Call after a period of healthy frames to reset backoff state."""
        self.backoff.reset()


class ManagedCapture:
    """
    Wraps a capture object with the connect -> read -> failure -> backoff ->
    reconnect loop (spec §9). Iterating yields FramePackets; None packets
    (transient gaps) are swallowed; reconnects happen automatically.

    Usage:
        managed = ManagedCapture(camera, settings)
        managed.start()
        for packet in managed.packets(stop_event):
            ...
    """

    STABLE_AFTER_FRAMES = 30  # healthy frames before backoff is reset

    def __init__(self, camera, settings, sleep_fn=time.sleep):
        self.camera = camera
        self.settings = settings
        self.sleep_fn = sleep_fn
        self.capture = None
        self.backoff = ExponentialBackoff(
            min_delay=settings.reconnect_min_sec,
            max_delay=settings.reconnect_max_sec,
            factor=settings.reconnect_backoff_factor,
            max_attempts=settings.reconnect_max_attempts,
        )
        self._stop = False
        self._frames_since_connect = 0

    def stop(self) -> None:
        self._stop = True
        if self.capture is not None:
            self.capture.close()

    def _open_capture(self) -> bool:
        from .hls_capture import open_with_fallback

        capture, ok = open_with_fallback(
            self.camera,
            transport=self.settings.rtsp_transport,
            allow_hls_fallback=self.settings.allow_hls_fallback,
            scene_cut_check=self.settings.scene_cut_check,
            scene_cut_diff_threshold=self.settings.scene_cut_diff_threshold,
        )
        self.capture = capture
        if ok:
            self._frames_since_connect = 0
        return ok

    def packets(self, stop_check=None):
        """Generator of FramePackets with automatic reconnection."""
        stop_check = stop_check or (lambda: self._stop)

        if self.capture is None or self.capture.needs_reconnect():
            if not self._connect_with_backoff(stop_check):
                return

        while not stop_check():
            packet = self.capture.read_packet() if self.capture else None
            if packet is not None:
                self._frames_since_connect += 1
                if self._frames_since_connect == self.STABLE_AFTER_FRAMES:
                    self.backoff.reset()
                    logger.info(
                        "[%s] stream stable (%d frames) — backoff reset",
                        self.camera.camera_id,
                        self._frames_since_connect,
                    )
                yield packet
                continue

            if self.capture is None or self.capture.needs_reconnect():
                logger.warning(
                    "[%s] connection lost (%s) — entering reconnect loop",
                    self.camera.camera_id,
                    self.capture.last_error if self.capture else "no capture",
                )
                if self.capture is not None:
                    self.capture.close()
                if not self._connect_with_backoff(stop_check):
                    return
            else:
                # transient empty read — breathe briefly, do not busy-spin
                self.sleep_fn(0.02)

    def _connect_with_backoff(self, stop_check) -> bool:
        while not stop_check():
            if self.backoff.exhausted():
                logger.error(
                    "[%s] reconnect attempts exhausted (%d)",
                    self.camera.camera_id,
                    self.backoff.max_attempts,
                )
                return False
            if self._open_capture():
                if self.backoff.attempts > 0:
                    logger.info(
                        "[%s] reconnected after %d attempt(s)",
                        self.camera.camera_id,
                        self.backoff.attempts,
                    )
                return True
            delay = self.backoff.next_delay()
            logger.warning(
                "[%s] reconnect in %.1fs (attempt %d)",
                self.camera.camera_id,
                delay,
                self.backoff.attempts,
            )
            self.sleep_fn(delay)
        return False
