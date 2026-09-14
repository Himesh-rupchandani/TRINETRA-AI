import sys
from pathlib import Path
import time
import threading
from typing import Callable, Optional

# Allow running this file directly as a script
if __name__ == "__main__" and not __package__:
    project_root = Path(__file__).resolve().parents[3]
    backend_root = Path(__file__).resolve().parents[2]
    for p in [str(project_root), str(backend_root)]:
        if str(p) not in sys.path:
            sys.path.insert(0, str(p))
    __package__ = "backend.app.camera"

from ..core.logging_config import logger


class StreamReconnectHandler:
    """
    Handles robust reconnection logic and exponential backoff for CCTV streams.
    Conforms to Mandatory Rule 5 (2s -> 4s -> 8s -> 16s -> 30s max, never tight loop)
    and Mandatory Rule 13 (isolated camera-prefixed logging).
    """

    def __init__(
        self,
        camera_id: str,
        reconnect_callback: Callable[[], bool],
        initial_delay: float = 2.0,
        max_delay: float = 30.0,
        backoff_factor: float = 2.0,
        max_attempts: Optional[int] = None,
    ):
        self.camera_id = camera_id
        self.reconnect_callback = reconnect_callback
        self.initial_delay = initial_delay
        self.max_delay = max_delay
        self.backoff_factor = backoff_factor
        self.max_attempts = max_attempts

        self.current_delay = initial_delay
        self.attempts = 0
        self.last_attempt_time: float = 0.0
        self._is_reconnecting = False
        self._lock = threading.Lock()

    def reset(self):
        """Reset the reconnect backoff state after a successful connection."""
        with self._lock:
            if self.attempts > 0:
                logger.info(f"[{self.camera_id}] Reconnection backoff reset after successful stream ingestion.")
            self.current_delay = self.initial_delay
            self.attempts = 0
            self._is_reconnecting = False

    def get_next_delay(self) -> float:
        """Calculate and return the current delay before advancing backoff factor."""
        with self._lock:
            delay = self.current_delay
            self.current_delay = min(self.current_delay * self.backoff_factor, self.max_delay)
            return delay

    def should_attempt(self) -> bool:
        """Check if enough backoff time has elapsed since the last attempt."""
        with self._lock:
            if self.last_attempt_time == 0.0:
                return True
            return (time.time() - self.last_attempt_time) >= self.current_delay

    def attempt_reconnect_sync(self, interrupt_event: Optional[threading.Event] = None) -> bool:
        """
        Perform one reconnect cycle with backoff wait.
        Supports interruptible sleep via threading.Event.
        """
        with self._lock:
            self.attempts += 1
            if self.max_attempts and self.attempts > self.max_attempts:
                logger.error(
                    f"[{self.camera_id}] Exceeded maximum reconnect attempts ({self.max_attempts})."
                )
                return False

            delay = self.current_delay
            # Advance delay for subsequent attempt (2s -> 4s -> 8s -> 16s -> 30s)
            self.current_delay = min(self.current_delay * self.backoff_factor, self.max_delay)
            self._is_reconnecting = True

        logger.warning(
            f"[{self.camera_id}] Reconnecting in {delay:.1f}s (attempt #{self.attempts}, next delay {self.current_delay:.1f}s)..."
        )

        # Sleep with interruption support
        if interrupt_event is not None:
            if interrupt_event.wait(timeout=delay):
                logger.info(f"[{self.camera_id}] Reconnect wait interrupted by stop signal.")
                return False
        else:
            time.sleep(delay)

        self.last_attempt_time = time.time()

        try:
            success = self.reconnect_callback()
            if success:
                logger.info(f"[{self.camera_id}] Successfully reconnected on attempt #{self.attempts}.")
                self.reset()
                return True
            else:
                logger.warning(f"[{self.camera_id}] Reconnect attempt #{self.attempts} failed.")
                return False
        except Exception as e:
            logger.error(f"[{self.camera_id}] Exception during reconnection attempt #{self.attempts}: {e}")
            return False
