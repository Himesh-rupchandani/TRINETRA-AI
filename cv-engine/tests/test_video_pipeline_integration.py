"""
End-to-end pipeline test on a REAL short clip.

Marked ``integration``: it needs the model weights and a sample clip, so it is
skipped automatically in a bare checkout and never runs as part of the default
unit-test pass. It is NOT dependent on the large Faculty Parking video.

    pytest tests/test_video_pipeline_integration.py -m integration
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

CV_ROOT = Path(__file__).resolve().parents[1]


def _find(name: str):
    for base in (
        Path(os.environ.get("TRINETRA_MODELS_DIR", "")) if os.environ.get("TRINETRA_MODELS_DIR") else None,
        CV_ROOT / "models_dev",
        Path.home() / "models",
    ):
        if base and (base / name).exists():
            return base / name
    return None


VEHICLE_MODEL = _find("yolo11n.pt")
PLATE_MODEL = _find("license_plate_detector.pt")
SAMPLE = next((p for p in (CV_ROOT / "samples").glob("*.mp4")), None) if (CV_ROOT / "samples").exists() else None

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        VEHICLE_MODEL is None or SAMPLE is None,
        reason="needs model weights (scripts/setup_video_env.sh) and a sample clip",
    ),
]


def test_pipeline_produces_real_sightings_from_a_real_clip(tmp_path):
    from pipeline.video_pipeline import VideoAnalysisPipeline, VideoPipelineConfig
    from sightings.reporting import ReportContext, build_events, write_evidence, write_sightings

    cfg = VideoPipelineConfig(
        video_id="itest",
        camera_id="itest_cam",
        location_name="Integration Test",
        vehicle_model=str(VEHICLE_MODEL),
        plate_model=str(PLATE_MODEL) if PLATE_MODEL else None,
        frame_skip=5,
        duration_sec=3.0,
        annotate=True,
    )
    pipe = VideoAnalysisPipeline(
        str(SAMPLE), cfg, annotated_path=str(tmp_path / "annotated.mp4")
    )
    sightings = pipe.run()

    # Real inference actually ran on real frames.
    assert pipe.stats.frames_processed > 0
    assert pipe.stats.detections > 0, "no vehicles detected in a real traffic clip"
    assert pipe.stats.frame_failures == 0
    assert (tmp_path / "annotated.mp4").exists()

    ctx = ReportContext(video_id="itest", camera_id="itest_cam", location_name="Integration Test")
    write_evidence(sightings, tmp_path / "evidence")
    rows = write_sightings(sightings, ctx, tmp_path)
    events = build_events(sightings, ctx)

    assert len(rows) == len(sightings) == len(events)
    # One sighting per vehicle appearance — never one per frame.
    assert len(rows) < pipe.stats.frames_processed
    for r in rows:
        assert r["plate_status"] in {"DETECTED", "UNCERTAIN", "NOT_DETECTED"}
        assert r["frames_observed"] >= cfg.min_sighting_frames
        if r["evidence_ref"]:
            assert (tmp_path / r["evidence_ref"]).exists()
