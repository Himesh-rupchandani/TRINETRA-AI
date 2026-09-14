"""Test configuration: put cv-engine modules on sys.path.

IMPORTANT: the backend's `app.core.config.settings` singleton is built at the
first `app.*` import (app/database/__init__ eagerly creates the engine). We
therefore force an isolated throw-away SQLite DB HERE — before any test module
is imported — so no test can ever touch a real backend database.
"""
import os
import sys
import tempfile
from pathlib import Path

_TMP_DB = tempfile.NamedTemporaryFile(suffix=".cvtests.db", delete=False)
_TMP_DB.close()
os.environ["DATABASE_URL"] = f"sqlite:///{_TMP_DB.name}"
os.environ["DEMO_MODE"] = "false"
os.environ["APP_ENV"] = "test"

CV_ROOT = Path(__file__).resolve().parents[1]
if str(CV_ROOT) not in sys.path:
    sys.path.insert(0, str(CV_ROOT))

BACKEND_ROOT = CV_ROOT.parent / "TRINETRAAI" / "backend"
