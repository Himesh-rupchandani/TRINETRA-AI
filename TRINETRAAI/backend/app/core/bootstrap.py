"""Boot-time runtime preparation: storage honesty + demo data on blank installs.

Two jobs, both about "does this process actually have somewhere to live?":

1. ``storage_report()`` — surfaces *where* the writable data lives, so an
   operator reading ``/api/health`` on a read-only-FS platform can see that the
   database is an ephemeral temp file (per instance, gone on the next cold
   start) instead of assuming writes were persisted.

2. ``ensure_demo_dataset()`` — seeds the 30-camera Sentinel grid, watchlist and
   the ``GJ01AB1234`` journey, but **only** when the database is a blank
   install. On a serverless host the database is born empty on every cold
   start, so without this a freshly deployed control room shows an empty
   registry, an empty map and "backend broken" — while on a host with real
   history it never runs. The guard is deliberately conservative: any existing
   event history or any registry bigger than ``init_db``'s 4-camera bootstrap
   means "this is somebody's database", so hands off.
"""
from __future__ import annotations

from typing import Any, Dict

from .config import settings
from .logging_config import logger
from .paths import evidence_root

# ``init_db()`` bootstraps exactly these four identity rows on an empty DB; more
# than that means a real registry was configured on purpose.
INITDB_CAMERA_COUNT = 4


def should_seed_demo(cameras: int, events: int) -> bool:
    """Pure decision function — the only place the "blank install" rule lives."""
    if events > 0:
        return False
    if settings.AUTO_SEED_DEMO:
        return cameras <= max(INITDB_CAMERA_COUNT, 0)
    # Ephemeral storage: the DB starts empty by definition, and whatever we
    # write dies with the instance, so seeding cannot damage anything.
    return bool(settings.ephemeral_storage) and cameras <= INITDB_CAMERA_COUNT


def ensure_demo_dataset(db) -> Dict[str, Any]:
    """Seed the demo dataset when appropriate. Never raises out of boot."""
    from ..database.models import Alert, Camera, VehicleEvent, Watchlist

    report: Dict[str, Any] = {"seeded": False}
    try:
        cameras = db.query(Camera).count()
        events = db.query(VehicleEvent).count()
        if not should_seed_demo(cameras, events):
            report["skipped_reason"] = (
                "registry already populated" if cameras > INITDB_CAMERA_COUNT else "database has event history"
            )
            if cameras and events == 0:
                report["skipped_reason"] = "registry already populated"
            return report

        # Imported lazily: the seeder is a script, and a serverless function
        # bundle that never needs it should not pay for its import.
        from scripts import seed_demo

        for stage in ("seed_cameras", "seed_watchlist", "seed_events", "seed_alerts"):
            getattr(seed_demo, stage)(db)
        db.commit()

        report.update(
            seeded=True,
            cameras=db.query(Camera).count(),
            watchlist=db.query(Watchlist).count(),
            events=db.query(VehicleEvent).count(),
            alerts=db.query(Alert).count(),
        )
        logger.info(
            "Demo dataset seeded on a blank install: "
            f"{report['cameras']} cameras / {report['events']} events / "
            f"{report['alerts']} alerts (demo plate GJ01AB1234)."
        )
        return report
    except Exception as exc:  # pragma: no cover - defensive boot path
        db.rollback()
        logger.error(f"Demo seeding skipped due to error: {exc}")
        report["skipped_reason"] = f"error: {exc}"
        return report


def storage_report() -> Dict[str, Any]:
    """Describe the writable data root and whether it survives a restart."""
    root = settings.RUNTIME_DATA_ROOT
    writable = True
    try:
        evidence_root(create=True)
    except Exception:
        writable = False
    if not root and not writable:
        return {
            "mode": "READ_ONLY",
            "detail": (
                "Storage paths are configured but not writable, and no fallback "
                "could be created. Set DATABASE_URL / EVIDENCE_ROOT (or "
                "TRINETRA_DATA_DIR) to a writable location."
            ),
            "ephemeral": False,
        }
    if root:
        return {
            "mode": "EPHEMERAL",
            "path": root,
            "ephemeral": True,
            "detail": (
                "Read-only code tree detected: the SQLite database and evidence "
                "root live in a temp directory that is discarded when this "
                "instance stops. Writes are per-instance — attach a volume or a "
                "real Postgres for durable storage."
            ),
        }
    return {"mode": "PERSISTENT", "path": str(settings.DATABASE_URL).split("///")[-1], "ephemeral": False}
