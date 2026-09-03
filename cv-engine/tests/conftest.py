"""Shared pytest configuration: make ``cv-engine`` importable as a root."""

from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pytest  # noqa: E402

from config.settings import Settings, load_settings  # noqa: E402


@pytest.fixture
def settings() -> Settings:
    """A settings object with deterministic, offline-friendly defaults."""
    return load_settings(
        env={},
        capture_backend="opencv",
        ocr_engine="rapidocr",
        model_path=str(ROOT / "models" / "yolo11n.pt"),
        evidence_dir=str(ROOT / "var" / "test_evidence"),
        dead_letter_path=str(ROOT / "var" / "test_dead_letter.jsonl"),
    )


@pytest.fixture
def offline_settings() -> Settings:
    """Settings that must never touch the network."""
    return load_settings(env={}, sentinel_catalogue_url="https://invalid.example/cameras.json")
