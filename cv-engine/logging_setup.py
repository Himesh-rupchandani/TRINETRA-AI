"""Structured logging for the CV engine.

One helper, :func:`log_event`, emits ``event=<name> key=value`` lines (or JSON
when ``LOG_JSON=1``). Credentials are never passed through here, and the
formatter redacts anything that looks like a secret as a second line of
defence.
"""

from __future__ import annotations

import json
import logging
import os
import re
import sys

_REDACT_PATTERN = re.compile(
    r"(?i)(password|passwd|pwd|token|secret|api[_-]?key|authorization|credential)([\"']?\s*[:=]\s*)([^\s,;\"']+)"
)
_RTSP_CRED_PATTERN = re.compile(r"(?i)(rtsp://)([^:/@\s]+):([^@\s]+)@")


class RedactingFormatter(logging.Formatter):
    """Keeps accidental credentials out of logs and log files."""

    def __init__(self, as_json: bool = False) -> None:
        super().__init__(fmt="%(asctime)s %(levelname)-7s %(name)s | %(message)s")
        self.as_json = as_json

    def format(self, record: logging.LogRecord) -> str:
        text = super().format(record)
        text = _RTSP_CRED_PATTERN.sub(r"\1***:***@", text)
        text = _REDACT_PATTERN.sub(r"\1\2***", text)
        if self.as_json:
            payload = {
                "ts": record.created,
                "level": record.levelname,
                "logger": record.name,
                "message": text.split("| ", 1)[-1],
            }
            extra = getattr(record, "fields", None)
            if isinstance(extra, dict):
                payload.update(extra)
            return json.dumps(payload, default=str)
        return text


def setup_logging(level: str = "INFO", as_json: bool | None = None) -> None:
    """Configure the root logger once. Safe to call repeatedly."""
    if as_json is None:
        as_json = os.environ.get("LOG_JSON", "").lower() in {"1", "true", "yes"}
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(RedactingFormatter(as_json=as_json))
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level.upper())
    # Third-party libraries are noisy at INFO on a 2-core box.
    for noisy in ("ultralytics", "PIL", "urllib3", "filelock"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def log_event(logger: logging.Logger, event: str, level: int = logging.INFO, **fields) -> None:
    """Emit one structured event: ``log_event(log, "camera_connected", cam="cam04")``."""
    parts = [f"event={event}"] + [f"{k}={_fmt(v)}" for k, v in fields.items() if v is not None]
    logger.log(level, " ".join(parts), extra={"fields": {"event": event, **fields}})


def _fmt(value) -> str:
    if isinstance(value, float):
        return f"{value:.3f}"
    return str(value)
