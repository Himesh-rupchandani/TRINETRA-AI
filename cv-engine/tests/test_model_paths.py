"""Trained weights are preferred; the original file is never overwritten."""
from pathlib import Path

from detection.model_paths import (
    backup_original,
    resolve_plate_model_path,
    resolve_vehicle_model_path,
)


def test_explicit_file_wins(tmp_path: Path):
    f = tmp_path / "custom.pt"
    f.write_bytes(b"x" * 2048)
    assert resolve_vehicle_model_path(str(f), prefer_trained=True) == str(f.resolve())


def test_trained_preferred_over_original(tmp_path: Path):
    orig = tmp_path / "models" / "original" / "yolo11s.pt"
    trained = tmp_path / "models" / "trained" / "vehicles" / "best.pt"
    orig.parent.mkdir(parents=True)
    trained.parent.mkdir(parents=True)
    orig.write_bytes(b"o" * 2048)
    trained.write_bytes(b"t" * 2048)
    got = resolve_vehicle_model_path("yolo11s.pt", prefer_trained=True, search_roots=[tmp_path])
    assert got == str(trained.resolve())
    got = resolve_vehicle_model_path("yolo11s.pt", prefer_trained=False, search_roots=[tmp_path])
    assert got == str(orig.resolve())


def test_backup_original_does_not_overwrite(tmp_path: Path):
    src = tmp_path / "yolo11s.pt"
    dest = tmp_path / "original" / "yolo11s.pt"
    src.write_bytes(b"NEW" * 1000)
    dest.parent.mkdir()
    dest.write_bytes(b"OLD" * 1000)
    backup_original(src, dest)
    assert dest.read_bytes().startswith(b"OLD")


def test_plate_path_none_when_missing(tmp_path: Path):
    assert resolve_plate_model_path("", search_roots=[tmp_path]) is None
