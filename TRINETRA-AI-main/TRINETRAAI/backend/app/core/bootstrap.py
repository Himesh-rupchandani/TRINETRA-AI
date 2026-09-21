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
   history it never runs. The guard is deliberately strict: any existing
   event history or any camera row means "this is somebody's database", so
   hands off.  Boot seeding is atomic — a failure rolls back to the savepoint
   and leaves the DB exactly as it was before boot (the 4 init_db bootstrap
   cameras remain).
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from .config import is_serverless_environment, settings
from .logging_config import logger
from .paths import evidence_root

# ``init_db()`` bootstraps exactly these four identity rows on an empty DB; more
# than that means a real registry was configured on purpose.  Kept for
# documentation, but the boot-seed guard no longer uses the <=4 allowance —
# that allowance could wipe a small real registry once a persistent DB is
# attached.
INITDB_CAMERA_COUNT = 4

# Last boot seeding outcome — surfaced by /api/health as components.demo_data
# so the state is debuggable from the browser without reading function logs.
_LAST_DEMO_REPORT: Optional[Dict[str, Any]] = None


def get_demo_seed_report() -> Optional[Dict[str, Any]]:
    """Return the last ``ensure_demo_dataset`` report (None before boot)."""
    return _LAST_DEMO_REPORT


def _format_demo_data(report: Optional[Dict[str, Any]]) -> str:
    """Translate the internal report dict into the user-visible components.demo_data string."""
    if report is None:
        return "SKIPPED: no boot report yet"
    if report.get("seeded"):
        c = report.get("cameras", "?")
        e = report.get("events", "?")
        a = report.get("alerts", "?")
        return f"SEEDED {c}/{e}/{a}"
    if "error" in report:
        return f"FAILED: {report['error']}"
    reason = report.get("skipped_reason", "unknown")
    # Normalise already-prefixed FAILED strings.
    if isinstance(reason, str) and reason.startswith("FAILED:"):
        return reason
    if isinstance(reason, str) and reason.startswith("error:"):
        return f"FAILED: {reason[len('error:'):].strip()}"
    return f"SKIPPED: {reason}"


def should_seed_demo(cameras: int, events: int) -> bool:
    """Pure decision function — the only place the "blank install" rule lives.

    New rule (atomic, insert-only): seed ONLY when the DB is completely blank
    (0 cameras AND 0 events).  The old ``cameras <= 4`` allowance could wipe a
    small real registry once a durable Postgres is attached, so it is gone.
    Explicit ``AUTO_SEED_DEMO=true`` still overrides; otherwise seeding only
    happens on an ephemeral / serverless host where a blank DB can only be
    demo data.
    """
    if events > 0:
        return False
    if cameras != 0:
        return False
    if settings.AUTO_SEED_DEMO:
        return True
    # Ephemeral storage: the DB starts empty by definition, and whatever we
    # write dies with the instance, so seeding cannot damage anything.
    # ``ephemeral_storage`` is True when RUNTIME_DATA_ROOT was relocated OR
    # when we are on a serverless host (VERCEL / Cloud Run / Lambda) where the
    # filesystem is per-instance ephemeral even though the code tree is writable.
    return bool(settings.ephemeral_storage)


def ensure_demo_dataset(db) -> Dict[str, Any]:
    """Seed the demo dataset when appropriate. Never raises out of boot."""
    from ..database.models import Alert, Camera, VehicleEvent, Watchlist

    global _LAST_DEMO_REPORT
    report: Dict[str, Any] = {"seeded": False}
    try:
        cameras = db.query(Camera).count()
        events = db.query(VehicleEvent).count()
        if not should_seed_demo(cameras, events):
            # Provide an honest reason for health.
            if events > 0:
                report["skipped_reason"] = "database has event history"
            elif cameras != 0:
                report["skipped_reason"] = "registry already populated"
            else:
                # Blank but not ephemeral and not explicitly requested.
                report["skipped_reason"] = "persistent blank DB — set AUTO_SEED_DEMO=true to seed"
            _LAST_DEMO_REPORT = report
            return report

        # Imported lazily from the single source of truth — never from
        # ``scripts.seed_demo`` which may be excluded from the serverless bundle.
        from ..database import demo_seed

        # Atomic: SAVEPOINT so a failure rolls back everything added in this
        # boot's attempt and leaves the 4 init_db rows intact.
        savepoint = None
        try:
            savepoint = db.begin_nested()
        except Exception:
            # If the session is already in a failed state, fallback to no savpoint
            savepoint = None

        try:
            demo_seed.seed_cameras(db)
            demo_seed.seed_watchlist(db)
            demo_seed.seed_events(db)
            demo_seed.seed_alerts(db)
            if savepoint is not None:
                savepoint.commit()
            db.commit()
        except Exception:
            if savepoint is not None:
                try:
                    savepoint.rollback()
                except Exception:
                    pass
            raise

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
        _LAST_DEMO_REPORT = report
        return report
    except Exception as exc:  # pragma: no cover - defensive boot path
        try:
            db.rollback()
        except Exception:
            pass
        logger.error(f"Demo seeding skipped due to error: {exc}")
        report["error"] = str(exc)
        report["skipped_reason"] = f"FAILED: {exc}"
        _LAST_DEMO_REPORT = report
        return report


def storage_report() -> Dict[str, Any]:
    """Describe the writable data root and whether it survives a restart."""
    root = settings.RUNTIME_DATA_ROOT
    serverless = is_serverless_environment()
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
    if root or serverless:
        # Serverless hosts are ephemeral even though their cwd IS writable —
        # Vercel's working dir accepts writes but the entire filesystem dies
        # with the function instance.  Report honestly so the UI can show
        # per-instance storage rather than pretending it is persistent.
        detail = (
            "Read-only code tree detected: the SQLite database and evidence "
            "root live in a temp directory that is discarded when this "
            "instance stops. Writes are per-instance — attach a volume or a "
            "real Postgres for durable storage."
        )
        if serverless and not root:
            detail = (
                "Serverless environment detected (VERCEL / Cloud Run / Lambda): "
                "the filesystem is ephemeral and the database is per-instance. "
                "Attach a real Postgres (DATABASE_URL) for durable storage."
            )
        return {
            "mode": "EPHEMERAL",
            "path": root or str(settings.DATABASE_URL).split("///")[-1],
            "ephemeral": True,
            "detail": detail,
        }
    return {"mode": "PERSISTENT", "path": str(settings.DATABASE_URL).split("///")[-1], "ephemeral": False}
