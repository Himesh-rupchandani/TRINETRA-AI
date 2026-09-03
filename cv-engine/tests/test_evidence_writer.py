"""Evidence capture (spec §20): deterministic safe filenames, no frame dumping."""
import os

import numpy as np

from evidence.evidence_writer import EvidenceWriter, sanitize


def test_sanitize_removes_unsafe_chars():
    assert sanitize("GJ 01 AB-1234") == "GJ-01-AB-1234"
    assert sanitize("../../etc/passwd") == "etc-passwd"
    assert sanitize("") == "unknown"
    assert len(sanitize("x" * 500)) <= 48


def test_evidence_filenames_deterministic(tmp_path):
    w = EvidenceWriter(base_dir=str(tmp_path), jpeg_quality=80)
    frame = np.full((120, 160, 3), 50, dtype=np.uint8)
    crop = np.full((30, 80, 3), 200, dtype=np.uint8)

    ref1 = w.save_event_evidence(frame, "cam04", 17, 123456.78, "GJ01AB1234", crop)
    ref2 = w.save_event_evidence(frame, "cam04", 17, 123456.78, "GJ01AB1234", crop)
    assert ref1 == ref2, "same inputs must produce the same evidence path"
    assert ref1 == os.path.join("cam04", "cam04_17_123456ms_GJ01AB1234.jpg")
    assert os.path.exists(os.path.join(str(tmp_path), ref1))
    plate_path = os.path.join(str(tmp_path), "cam04", "cam04_17_123456ms_GJ01AB1234_plate.jpg")
    assert os.path.exists(plate_path)


def test_evidence_respects_storage_flags(tmp_path):
    w = EvidenceWriter(base_dir=str(tmp_path))
    frame = np.zeros((60, 80, 3), dtype=np.uint8)
    ref = w.save_event_evidence(
        frame, "cam01", 3, 500.0, None, None,
        store_full_frame=False, store_plate_crop=False,
    )
    assert ref is None
    assert w.files_written == 0  # nothing stored -> no evidence spam


def test_evidence_only_written_when_called(tmp_path):
    """Writer never stores frames on its own; the pipeline decides (spec §20)."""
    w = EvidenceWriter(base_dir=str(tmp_path))
    assert w.files_written == 0
    assert os.listdir(str(tmp_path)) == []
