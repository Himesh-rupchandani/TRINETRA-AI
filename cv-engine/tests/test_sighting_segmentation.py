"""
Sighting segmentation tests — the core of the Faculty-Parking brief:

    many frames -> one track -> ONE sighting
    vehicle leaves and returns -> a NEW sighting

Also covers multi-frame OCR voting, ID-switch merging (duplicate suppression)
and the short-track false-positive filter.
"""
from __future__ import annotations

import pytest

from sightings.segmenter import (
    PLATE_DETECTED,
    PLATE_NOT_DETECTED,
    PLATE_UNCERTAIN,
    PlateObservation,
    SightingSegmenter,
)


def seg(**kw) -> SightingSegmenter:
    params = dict(
        camera_id="faculty_parking",
        video_id="faculty_parking_01",
        track_end_gap_sec=2.0,
        sighting_cooldown_sec=3.0,
        min_frames=3,
        min_duration_sec=0.3,
        reject_threshold=0.60,
        min_agree_reads=2,
        keep_evidence_frames=False,
    )
    params.update(kw)
    return SightingSegmenter(**params)


def observe_span(s: SightingSegmenter, track_id, start_ms, end_ms, step_ms=100, cls="car"):
    idx = int(start_ms // step_ms)
    t = start_ms
    while t <= end_ms:
        s.observe_track(track_id, t, idx, cls, 0.9, [100, 100, 200, 200])
        s.tick(t)
        t += step_ms
        idx += 1


def add_read(s, track_id, pts, plate, conf, raw=None):
    s.add_plate_observation(
        track_id,
        PlateObservation(
            pts_ms=pts, frame_index=int(pts // 40), plate_raw=raw or plate,
            plate_normalized=plate, ocr_confidence=conf, plate_det_confidence=0.8,
            plate_bbox=[10, 10, 60, 26], plate_area_px=800.0, sharpness=120.0,
            quality=conf,
        ),
    )


# --------------------------------------------------------------- core rule
def test_continuous_appearance_is_one_sighting_not_many_frames():
    s = seg()
    observe_span(s, 7, 0, 8000)  # 8 seconds, ~81 frames
    out = s.finalize()
    assert len(out) == 1
    assert out[0].frames_observed > 50
    assert out[0].duration_sec == pytest.approx(8.0, abs=0.2)
    assert out[0].track_ids == [7]


def test_leaving_and_returning_creates_a_second_sighting():
    s = seg()
    observe_span(s, 7, 0, 3000)
    observe_span(s, 9, 12000, 15000)  # same vehicle back later, new track id
    out = s.finalize()
    assert len(out) == 2
    assert out[0].start_pts_ms == 0
    assert out[1].start_pts_ms == 12000


def test_five_separate_visits_produce_exactly_five_sightings():
    s = seg()
    for i, start in enumerate([0, 20000, 45000, 70000, 95000]):
        observe_span(s, 10 + i, start, start + 4000)
        for pts in range(start + 500, start + 3500, 1000):
            add_read(s, 10 + i, pts, "GJ03AB1234", 0.9)
    out = s.finalize()
    assert len(out) == 5
    assert {x.plate_result()[0] for x in out} == {"GJ03AB1234"}
    assert [x.sighting_index_for_plate for x in out] == [1, 2, 3, 4, 5]


def test_short_flicker_track_is_dropped():
    s = seg()
    observe_span(s, 3, 0, 100)  # 2 frames, 0.1 s
    out = s.finalize()
    assert out == []
    assert s.dropped_short == 1


def test_track_end_gap_is_configurable():
    """A 2.5 s gap splits with a 2 s end-gap, but not with a 5 s end-gap."""
    a = seg(track_end_gap_sec=2.0, sighting_cooldown_sec=0.0)
    observe_span(a, 1, 0, 2000)
    observe_span(a, 2, 4500, 6500)
    assert len(a.finalize()) == 2

    b = seg(track_end_gap_sec=5.0, sighting_cooldown_sec=0.0)
    observe_span(b, 1, 0, 2000)
    b.observe_track(1, 4500, 45, "car", 0.9, [100, 100, 200, 200])
    observe_span(b, 1, 4600, 6500)
    assert len(b.finalize()) == 1


# ------------------------------------------------------- OCR aggregation
def test_multi_frame_voting_prefers_the_supported_candidate():
    s = seg()
    observe_span(s, 4, 0, 3000)
    add_read(s, 4, 500, "GJ01AB1234", 0.81)
    add_read(s, 4, 1000, "GJ01AB1234", 0.94)
    add_read(s, 4, 1500, "GJ01AB1234", 0.91)
    add_read(s, 4, 2000, "GJ01A81234", 0.72)  # single noisy outlier
    out = s.finalize()
    plate, raw, conf, support, status = out[0].plate_result()
    assert plate == "GJ01AB1234"
    assert support == 3
    assert status == PLATE_DETECTED
    assert 0.88 <= conf <= 0.95
    # every competing candidate stays visible for audit
    assert {c["plate"] for c in out[0].candidate_summary()} == {"GJ01AB1234", "GJ01A81234"}


def test_single_low_confidence_read_is_marked_uncertain_not_promoted():
    s = seg()
    observe_span(s, 5, 0, 3000)
    add_read(s, 5, 500, "GJ01AB1234", 0.42)
    plate, _raw, conf, support, status = s.finalize()[0].plate_result()
    assert plate == "GJ01AB1234"
    assert support == 1
    assert status == PLATE_UNCERTAIN  # kept, flagged, never silently accepted
    assert conf < 0.60


def test_sighting_without_any_read_reports_not_detected():
    s = seg()
    observe_span(s, 6, 0, 3000)
    plate, raw, conf, support, status = s.finalize()[0].plate_result()
    assert (plate, raw, conf, support) == (None, None, None, 0)
    assert status == PLATE_NOT_DETECTED


def test_raw_ocr_text_is_preserved_alongside_normalized():
    s = seg()
    observe_span(s, 8, 0, 3000)
    add_read(s, 8, 400, "GJ01AB1234", 0.9, raw="GJ 01 AB-1234")
    add_read(s, 8, 900, "GJ01AB1234", 0.95, raw="GJ 01 AB 1234")
    plate, raw, _c, _s, _st = s.finalize()[0].plate_result()
    assert plate == "GJ01AB1234"
    assert raw == "GJ 01 AB 1234"  # raw of the best read, never invented


# -------------------------------------------------- duplicate suppression
def test_id_switch_within_cooldown_is_merged_into_one_sighting():
    s = seg(track_end_gap_sec=1.0, sighting_cooldown_sec=3.0)
    observe_span(s, 11, 0, 2000)
    for pts in (500, 1000, 1500):
        add_read(s, 11, pts, "MH12MV8899", 0.9)
    # occlusion -> tracker restarts the same vehicle as a new id 1.5 s later
    observe_span(s, 12, 3500, 5500)
    for pts in (4000, 4500, 5000):
        add_read(s, 12, pts, "MH12MV8899", 0.92)
    out = s.finalize()
    assert len(out) == 1
    assert out[0].track_ids == [11, 12]
    assert out[0].merged_from == 2
    assert out[0].end_pts_ms == 5500


def test_two_overlapping_tracks_with_the_same_plate_are_one_sighting():
    """Duplicate suppression: one physical vehicle held by two track ids at
    the same time must not count twice (Phase 20)."""
    s = seg(track_end_gap_sec=1.0, sighting_cooldown_sec=3.0)
    observe_span(s, 31, 0, 4000)
    observe_span(s, 32, 1500, 5000)  # overlapping duplicate box
    for pts in (500, 1000, 1500):
        add_read(s, 31, pts, "GJ05XY4321", 0.9)
    for pts in (2000, 2500, 3000):
        add_read(s, 32, pts, "GJ05XY4321", 0.88)
    out = s.finalize()
    assert len(out) == 1
    assert sorted(out[0].track_ids) == [31, 32]


def test_reappearance_after_cooldown_is_a_new_sighting():
    s = seg(track_end_gap_sec=1.0, sighting_cooldown_sec=3.0)
    observe_span(s, 11, 0, 2000)
    for pts in (500, 1000, 1500):
        add_read(s, 11, pts, "MH12MV8899", 0.9)
    observe_span(s, 12, 30000, 32000)
    for pts in (30500, 31000, 31500):
        add_read(s, 12, pts, "MH12MV8899", 0.92)
    out = s.finalize()
    assert len(out) == 2
    assert [x.sighting_index_for_plate for x in out] == [1, 2]


def test_plate_reads_never_leak_to_another_track():
    s = seg()
    observe_span(s, 21, 0, 2000)
    observe_span(s, 22, 0, 2000)
    for pts in (500, 1000, 1500):
        add_read(s, 21, pts, "GJ03CD4444", 0.9)
    s.add_plate_observation(999, PlateObservation(  # unknown track: ignored
        pts_ms=800, frame_index=8, plate_raw="XX", plate_normalized="GJ99ZZ9999",
        ocr_confidence=0.99,
    ))
    out = s.finalize()
    plates = {x.track_id: x.plate_result()[0] for x in out}
    assert plates[21] == "GJ03CD4444"
    assert plates[22] is None
