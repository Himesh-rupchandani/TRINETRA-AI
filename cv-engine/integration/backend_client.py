"""Backend event client: ``POST /api/events`` with bounded retry.

Design rules from the integration spec:

* One backend failure must not stall the CV pipeline, so events go onto an
  internal queue drained by a background thread.
* Retry with exponential backoff, but never forever: after ``backend_max_retries``
  an event is appended to a dead-letter file and dropped from the queue.
* ``post_now`` is the synchronous path used by the integration test and the
  demo, which want an immediate verdict.
"""

from __future__ import annotations

import json
import logging
import queue
import threading
import time
from pathlib import Path
from typing import Optional

import requests

from config.settings import Settings
from events.event_schema import validate_payload
from logging_setup import log_event

log = logging.getLogger("trinetra.backend")


class BackendClient:
    def __init__(self, settings: Settings, session: Optional[requests.Session] = None) -> None:
        self.settings = settings
        self.session = session or requests
        self._queue: queue.Queue = queue.Queue(maxsize=settings.backend_queue_size)
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self.sent = 0
        self.failed = 0
        self.invalid = 0
        self.dead_lettered = 0

    # -- synchronous path ---------------------------------------------------
    def post_now(self, payload: dict) -> tuple[bool, Optional[int], str]:
        """One attempt (with the configured retries). Returns (ok, status, error)."""
        problems = validate_payload(payload)
        if problems:
            self.invalid += 1
            log_event(
                log,
                "event_rejected_by_schema",
                level=logging.ERROR,
                problems=";".join(problems[:4]),
                camera=payload.get("camera_id"),
            )
            return False, None, "schema: " + ";".join(problems)

        delay = self.settings.backend_retry_base_s
        last_error = ""
        status: Optional[int] = None
        for attempt in range(1, self.settings.backend_max_retries + 1):
            try:
                response = self.session.post(
                    self.settings.events_url,
                    json=payload,
                    timeout=self.settings.backend_timeout_s,
                )
                status = response.status_code
                if 200 <= status < 300:
                    self.sent += 1
                    log_event(
                        log,
                        "event_posted",
                        camera=payload.get("camera_id"),
                        plate=payload.get("plate"),
                        status=status,
                        attempt=attempt,
                    )
                    return True, status, ""
                last_error = f"http {status}"
                if 400 <= status < 500 and status not in (408, 429):
                    # The backend understood us and said no: retrying is pointless.
                    return False, status, last_error
            except requests.RequestException as exc:
                last_error = f"{type(exc).__name__}: {exc}"
                status = None
            log_event(
                log,
                "backend_request_failed",
                level=logging.WARNING,
                attempt=attempt,
                error=last_error,
                retry_in_s=delay,
            )
            time.sleep(min(delay, self.settings.backend_retry_max_s))
            delay = min(delay * 2, self.settings.backend_retry_max_s)
        self.failed += 1
        return False, status, last_error

    # -- queued path --------------------------------------------------------
    def enqueue(self, payload: dict) -> bool:
        try:
            self._queue.put_nowait(payload)
            return True
        except queue.Full:
            log_event(log, "event_queue_full_dropped", level=logging.ERROR, camera=payload.get("camera_id"))
            return False

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._worker, name="trinetra-backend", daemon=True)
        self._thread.start()

    def stop(self, drain_timeout_s: float = 5.0) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=drain_timeout_s)
            self._thread = None

    def _worker(self) -> None:
        while not self._stop.is_set():
            try:
                payload = self._queue.get(timeout=0.5)
            except queue.Empty:
                continue
            ok, _status, _error = self.post_now(payload)
            if not ok:
                self._dead_letter(payload)

    def _dead_letter(self, payload: dict) -> None:
        path = Path(self.settings.dead_letter_path)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps({"payload": payload, "ts": time.time()}) + "\n")
            self.dead_lettered += 1
            log_event(
                log,
                "event_dead_lettered",
                level=logging.ERROR,
                camera=payload.get("camera_id"),
                plate=payload.get("plate"),
                path=str(path),
            )
        except Exception as exc:  # noqa: BLE001
            log_event(
                log,
                "dead_letter_write_failed",
                level=logging.ERROR,
                error=f"{type(exc).__name__}: {exc}",
            )

    @property
    def pending(self) -> int:
        return self._queue.qsize()
