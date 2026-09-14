"""Live-view quality for cv-engine's own viewers.

The live feed used to be the coarse view: the on-demand viewer in
``scripts/run_feed_demo.py`` built its detector with a hard-coded
``imgsz=416`` while an offline analysis of the same recording ran at 640+, so
the boxes a person WATCHING were looser and rarer than the boxes stored in the
database. Both now follow the settings, with a dedicated resolution for frames
somebody is looking at.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from config.settings import Settings

CV_ROOT = Path(__file__).resolve().parents[1]


def _feed_demo_module():
    spec = importlib.util.spec_from_file_location(
        "run_feed_demo", CV_ROOT / "scripts" / "run_feed_demo.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_settings_expose_a_live_inference_resolution():
    s = Settings.from_env()
    # 960: at 640 a distant car is a few pixels wide, which is what made the
    # live view look coarser than the recorded analysis.
    assert s.live_imgsz >= 640
    # the ingest pipeline keeps its own (cheaper) resolution
    assert s.inference_imgsz <= s.live_imgsz


def test_live_resolution_is_configurable(monkeypatch):
    monkeypatch.setenv("LIVE_IMGSZ", "1280")
    assert Settings.from_env().live_imgsz == 1280
    monkeypatch.setenv("LIVE_IMGSZ", "640")          # weak CPU escape hatch
    assert Settings.from_env().live_imgsz == 640


def test_ondemand_live_viewer_follows_the_settings(monkeypatch):
    """The viewer somebody is watching must not run at a secretly lower size."""
    captured = {}

    class FakeDetector:
        def __init__(self, **kw):
            captured.update(kw)

    module = _feed_demo_module()
    monkeypatch.setattr(module, "VehicleDetector", FakeDetector)
    monkeypatch.setattr(module, "_ONDEMAND_DETECTOR", None, raising=False)

    settings = Settings.from_env()
    module._ondemand_detector(settings)

    assert captured, "the on-demand viewer never built a detector"
    assert captured["imgsz"] == settings.live_imgsz, "live view is not at the live resolution"
    assert captured["imgsz"] != 416
    assert captured["conf_threshold"] == settings.conf_threshold
    assert captured["nms_iou"] == settings.nms_iou
    # the shared instance is reused, so a second viewer costs no extra model
    assert module._ondemand_detector(settings) is not None
