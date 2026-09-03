"""Multi-frame plate accumulation and stability (spec §18)."""
from anpr.confidence import PlateReading
from anpr.plate_memory import PlateMemory


def _r(conf, plate="GJ01AB1234", raw="GJ 01 AB-1234", pts=0.0):
    return PlateReading(plate_raw=raw, plate_normalized=plate, confidence=conf, pts_ms=pts)


def test_readings_aggregate_into_stable_candidate():
    mem = PlateMemory("cam04", reject_threshold=0.60, min_agree_reads=2)
    for conf, pts in [(0.81, 100), (0.91, 200), (0.95, 300)]:
        mem.add_reading(17, _r(conf, pts=pts))
    best = mem.best(17)
    assert best is not None
    assert best["plate"] == "GJ01AB1234"
    assert abs(best["confidence"] - 0.92) < 0.01
    assert best["n_readings"] == 3
    assert mem.is_stable(17)


def test_single_reading_not_stable():
    mem = PlateMemory("cam04", reject_threshold=0.60, min_agree_reads=2)
    mem.add_reading(1, _r(0.99))
    assert mem.best(1) is not None
    assert not mem.is_stable(1)


def test_rejected_readings_never_stored():
    mem = PlateMemory("cam04", reject_threshold=0.60)
    mem.add_reading(1, _r(0.59))  # below reject threshold
    assert mem.best(1) is None


def test_empty_normalized_never_stored():
    mem = PlateMemory("cam04")
    mem.add_reading(1, PlateReading(plate_raw="x", plate_normalized="", confidence=0.99))
    assert mem.best(1) is None


def test_reset_clears_all_tracks():
    mem = PlateMemory("cam04")
    mem.add_reading(1, _r(0.9))
    mem.add_reading(2, _r(0.9, plate="MH02CD5678", raw="MH 02 CD-5678"))
    mem.reset()
    assert mem.best(1) is None and mem.best(2) is None
    assert mem.track_ids() == []


def test_drop_track():
    mem = PlateMemory("cam04")
    mem.add_reading(5, _r(0.9))
    mem.drop(5)
    assert mem.best(5) is None
