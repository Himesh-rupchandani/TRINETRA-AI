"""Pytest-wide test isolation.

Every test session runs against its own temporary SQLite database so the
suite never reads or pollutes the real ``trinetra.db`` (which the live
backend and the dashboard use). The env var must be set BEFORE any test
module imports ``app.database.database`` — conftest.py is imported first
by pytest, which guarantees that ordering.

``init_db()`` (called by the fixtures) seeds a fresh demo dataset into the
empty database, so tests that rely on seeded cameras keep working.
"""
import os
import tempfile

_TMPDIR = tempfile.mkdtemp(prefix="trinetra-tests-")
os.environ.setdefault("DATABASE_URL", f"sqlite:///{_TMPDIR}/test.db")
os.environ.setdefault("UPLOAD_DIR", f"{_TMPDIR}/uploads")
os.environ.setdefault("EVIDENCE_ROOT", f"{_TMPDIR}/evidence")
os.environ.setdefault("ANALYSIS_DIR", f"{_TMPDIR}/analysis")
