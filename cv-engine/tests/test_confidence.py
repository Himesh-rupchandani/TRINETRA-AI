"""Plate confidence boundaries (spec §17, §30) and multi-frame aggregation (§18)."""
from anpr.confidence import (
    ConfidenceTier,
    PlateReading,
    aggregate_readings,
    classify_confidence,
    is_usable,
)


def test_confidence_boundaries():
    # defaults: reject < 0.60 <= low band < 0.80 <= high
    assert classify_confidence(0.95) == ConfidenceTier.HIGH
    assert classify_confidence(0.80) == ConfidenceTier.HIGH
    assert classify_confidence(0.7999) == ConfidenceTier.MEDIUM
    assert classify_confidence(0.70) == ConfidenceTier.MEDIUM
    assert classify_confidence(0.65) == ConfidenceTier.LOW
    assert classify_confidence(0.60) == ConfidenceTier.LOW
    assert classify_confidence(0.5999) == ConfidenceTier.REJECT
    assert classify_confidence(0.0) == ConfidenceTier.REJECT
    assert classify_confidence(1.0) == ConfidenceTier.HIGH


def test_custom_thresholds():
    assert classify_confidence(0.45, reject_threshold=0.4, low_mark=0.6) == ConfidenceTier.LOW
    assert classify_confidence(0.55, reject_threshold=0.4, low_mark=0.6) == ConfidenceTier.MEDIUM
    assert classify_confidence(0.61, reject_threshold=0.4, low_mark=0.6) == ConfidenceTier.HIGH
    assert classify_confidence(0.39, reject_threshold=0.4, low_mark=0.6) == ConfidenceTier.REJECT


def test_low_confidence_kept_but_marked_not_upgraded():
    """Low confidence must stay low — never silently turned into high."""
    tier = classify_confidence(0.62)  # usable but below low_mark
    assert is_usable(tier)
    assert tier != ConfidenceTier.HIGH


def test_rejected_is_not_usable():
    assert not is_usable(ConfidenceTier.REJECT)


def _r(conf, plate="GJ01AB1234", raw="GJ 01 AB-1234", pts=0.0):
    return PlateReading(plate_raw=raw, plate_normalized=plate, confidence=conf, pts_ms=pts)


def test_aggregate_spec_example():
    """Spec §18: [0.81, 0.91, 0.95] -> GJ01AB1234 @ ~0.92."""
    readings = [_r(0.81, pts=100), _r(0.91, pts=200), _r(0.95, pts=300)]
    plate, conf, raw = aggregate_readings(readings)
    assert plate == "GJ01AB1234"
    assert abs(conf - 0.92) < 0.01
    assert raw == "GJ 01 AB-1234"


def test_aggregate_prefers_consistent_cluster_over_single_high():
    """One 0.99 outlier must not beat three agreeing 0.85 reads."""
    readings = [
        _r(0.85, plate="GJ01AB1234", pts=100),
        _r(0.86, plate="GJ01AB1234", pts=200),
        _r(0.84, plate="GJ01AB1234", pts=300),
        _r(0.99, plate="GJ01XB9999", pts=400),
    ]
    plate, conf, _ = aggregate_readings(readings)
    assert plate == "GJ01AB1234"
    assert 0.84 <= conf <= 0.90


def test_aggregate_empty_and_none():
    assert aggregate_readings([]) is None
    # readings with empty normalized plate are ignored
    r = PlateReading(plate_raw="???", plate_normalized="", confidence=0.9)
    assert aggregate_readings([r]) is None


def test_aggregate_conf_capped_at_one():
    readings = [_r(1.0), _r(1.0)]
    _, conf, _ = aggregate_readings(readings)
    assert conf <= 1.0
