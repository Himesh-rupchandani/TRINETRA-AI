"""
Backend integration client (spec §23).

POST /api/events with:
- timeout
- bounded retries with exponential backoff (never infinite)
- non-blocking submit via internal queue + worker thread (a slow/dead backend
  must not stall the CV pipeline)
- dead-letter file for events that exhausted retries or were rejected
- structured logging
"""
from __future__ import annotations

import json
import logging
import os
import queue
import threading
import time
from typing import Dict, Optional

logger = logging.getLogger("cv_engine.backend")


class BackendClient:
    def __init__(
        self,
        base_url: str = "http://localhost:8000",
        timeout_sec: float = 5.0,
        max_retries: int = 3,
        backoff_base_sec: float = 1.0,
        backoff_cap_sec: float = 10.0,
        queue_size: int = 1000,
        dead_letter_path: Optional[str] = "evidence_out/dead_letter_events.jsonl",
        sleep_fn=time.sleep,
    ):
        self.base_url = base_url.rstrip("/")
        self.events_url = f"{self.base_url}/api/events"
        self.timeout_sec = timeout_sec
        self.max_retries = max_retries
        self.backoff_base_sec = backoff_base_sec
        self.backoff_cap_sec = backoff_cap_sec
        self.dead_letter_path = dead_letter_path
        self.sleep_fn = sleep_fn

        self._queue: "queue.Queue[Optional[dict]]" = queue.Queue(maxsize=queue_size)
        self._worker: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._lock = threading.Lock()

        self.stats = {
            "submitted": 0,
            "accepted": 0,
            "failed_after_retries": 0,
            "rejected_4xx": 0,
            "dropped_queue_full": 0,
            "backend_last_status": None,
        }

    # ------------------------------------------------------------------
    def start(self) -> None:
        with self._lock:
            if self._worker is None or not self._worker.is_alive():
                self._stop.clear()
                self._worker = threading.Thread(target=self._run, name="backend-client", daemon=True)
                self._worker.start()

    def submit(self, event: dict) -> bool:
        """
        Non-blocking. Returns False only when the queue is full (event dropped
        and counted — the pipeline must never block on the backend).
        """
        try:
            self._queue.put_nowait(event)
            self.stats["submitted"] += 1
            return True
        except queue.Full:
            self.stats["dropped_queue_full"] += 1
            self._dead_letter(event, reason="queue_full")
            logger.error("[BACKEND] queue full — event dead-lettered")
            return False

    def send_now(self, event: dict) -> bool:
        """Synchronous send with retries (used by tests/scripts)."""
        return self._send_with_retries(event)

    # ------------------------------------------------------------------
    def _send_with_retries(self, event: dict) -> bool:
        import httpx

        attempt = 0
        while True:
            attempt += 1
            try:
                resp = httpx.post(self.events_url, json=event, timeout=self.timeout_sec)
                self.stats["backend_last_status"] = resp.status_code
                if 200 <= resp.status_code < 300:
                    self.stats["accepted"] += 1
                    logger.info(
                        "[BACKEND] event accepted (%s) cam=%s plate=%s",
                        resp.status_code,
                        event.get("camera_id"),
                        event.get("plate"),
                    )
                    return True
                if 400 <= resp.status_code < 500:
                    # Validation/contract error: retrying will never help.
                    self.stats["rejected_4xx"] += 1
                    logger.error(
                        "[BACKEND] event rejected HTTP %s: %s",
                        resp.status_code,
                        resp.text[:300],
                    )
                    self._dead_letter(event, reason=f"http_{resp.status_code}")
                    return False
                # 5xx / other: retry with backoff
                logger.warning("[BACKEND] HTTP %s (attempt %d/%d)", resp.status_code, attempt, self.max_retries + 1)
            except Exception as exc:
                logger.warning("[BACKEND] request failed (attempt %d/%d): %s", attempt, self.max_retries + 1, exc)

            if attempt > self.max_retries:
                self.stats["failed_after_retries"] += 1
                self._dead_letter(event, reason="retries_exhausted")
                logger.error("[BACKEND] giving up on event after %d attempts", attempt)
                return False

            delay = min(self.backoff_base_sec * (2 ** (attempt - 1)), self.backoff_cap_sec)
            self.sleep_fn(delay)

    def _dead_letter(self, event: dict, reason: str) -> None:
        if not self.dead_letter_path:
            return
        try:
            os.makedirs(os.path.dirname(self.dead_letter_path) or ".", exist_ok=True)
            with open(self.dead_letter_path, "a", encoding="utf-8") as fh:
                fh.write(json.dumps({"reason": reason, "ts": time.time(), "event": event}) + "\n")
        except Exception as exc:
            logger.error("[BACKEND] dead-letter write failed: %s", exc)

    # ------------------------------------------------------------------
    def _run(self) -> None:
        logger.info("[BACKEND] worker started -> %s", self.events_url)
        while not self._stop.is_set():
            try:
                event = self._queue.get(timeout=0.5)
            except queue.Empty:
                continue
            if event is None:
                break
            self._send_with_retries(event)
            self._queue.task_done()

    def flush(self, timeout_sec: float = 10.0) -> bool:
        """Wait until the queue drains (best-effort)."""
        deadline = time.monotonic() + timeout_sec
        while time.monotonic() < deadline:
            if self._queue.unfinished_tasks == 0:
                return True
            time.sleep(0.05)
        return self._queue.unfinished_tasks == 0

    def close(self, timeout_sec: float = 5.0) -> None:
        self._stop.set()
        try:
            self._queue.put_nowait(None)
        except queue.Full:
            pass
        if self._worker is not None:
            self._worker.join(timeout=timeout_sec)

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *exc):
        self.close()
