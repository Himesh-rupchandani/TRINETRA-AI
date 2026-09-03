"""Shared sys.path + logging bootstrap for CLI scripts."""

from __future__ import annotations

import pathlib
import sys

CV_ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(CV_ROOT) not in sys.path:
    sys.path.insert(0, str(CV_ROOT))

from logging_setup import setup_logging  # noqa: E402


def boot(level: str = "INFO") -> None:
    setup_logging(level=level)
