"""make_local_feeds must work outside Linux (Windows/macOS local runs).

The plate-sprite renderer used to hard-code
``/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf`` — on Windows that
crashed with an opaque ``OSError: cannot open resource`` before a single feed
was written. ``find_font()`` now picks the first INSTALLED candidate across
Linux/Windows/macOS and fails with an actionable message when none exists.
"""
import sys
from pathlib import Path

import pytest

scripts_dir = Path(__file__).resolve().parents[1] / "scripts"
if str(scripts_dir) not in sys.path:
    sys.path.insert(0, str(scripts_dir))

import make_local_feeds  # noqa: E402


def test_find_font_returns_an_existing_file():
    font = make_local_feeds.find_font()
    assert Path(font).is_file()


def test_font_candidates_cover_windows_and_linux():
    candidates = make_local_feeds.FONT_CANDIDATES
    assert any(c.startswith("C:/Windows/Fonts/") for c in candidates)
    assert any("DejaVuSans-Bold.ttf" in c for c in candidates)


def test_find_font_actionable_error_when_nothing_installed(monkeypatch):
    monkeypatch.setattr(make_local_feeds, "FONT_CANDIDATES", ["/nonexistent/font.ttf"])
    with pytest.raises(SystemExit) as excinfo:
        make_local_feeds.find_font()
    assert "font" in str(excinfo.value).lower()
