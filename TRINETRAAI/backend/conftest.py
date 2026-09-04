"""Pytest bootstrap for the Trinetra backend test-suite.

Some test modules import ``app.*`` (backend root on sys.path) while others
import ``backend.app.*`` (repository ``TRINETRAAI/`` root on sys.path).
Both roots are registered here so either import style collects cleanly.
"""
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = BACKEND_ROOT.parent

for _p in (str(BACKEND_ROOT), str(PROJECT_ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)
