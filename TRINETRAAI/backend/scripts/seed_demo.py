"""
TRINETRA AI Demo Seed Script
============================
Seeds the database with:
  - 30 realistic CCTV cameras across Ahmedabad/Gujarat
  - 10 watchlist entries (including GJ01AB1234 as STOLEN / CRITICAL)
  - 20+ vehicle events including the primary demo journey:
      GJ01AB1234: CAM04 → CAM17 → CAM08 → CAM07
  - 5 realistic alerts

Usage:
    cd backend
    python -m scripts.seed_demo

This is the CLI entry point — it imports the canonical fixture from
``app.database.demo_seed`` (the single source of truth) and adds the
CLI-friendly "already seeded? skip / stale? clear and reseed" UX on top of
the atomic, insert-only helpers that the serverless boot path uses.
"""
import sys
import io
from pathlib import Path

# Force UTF-8 on Windows stdout/stderr to prevent charmap encoding errors
if sys.platform == "win32":
    try:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        elif hasattr(sys.stdout, "buffer"):
            sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
            sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
    except Exception:
        pass

# Ensure backend root is in sys.path when running as script
backend_root = Path(__file__).resolve().parents[1]
project_root = Path(__file__).resolve().parents[2]
for p in [str(project_root), str(backend_root)]:
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from app.database.database import SessionLocal, engine
from app.database.models import Base, Camera, Watchlist, VehicleEvent, Alert

# Canonical fixture — single source of truth.
from app.database.demo_seed import (
    demo_base_time,
    seed_alerts as _seed_alerts_insert,
    seed_cameras as _seed_cameras_insert,
    seed_events as _seed_events_insert,
    seed_watchlist as _seed_watchlist_insert,
)

# Create tables if not yet created
Base.metadata.create_all(bind=engine)


def seed_cameras(db):
    count = db.query(Camera).count()
    # Fix for stale local DBs (e.g. 4 cameras OFFLINE) — reseed if not 30
    if count == 30:
        print("  → Cameras already seeded (30), skipping.")
        return
    if count > 0 and count != 30:
        print(f"  → Found {count} cameras (stale/partial), clearing and reseeding 30...")
        db.query(Camera).delete()
        db.commit()

    inserted = _seed_cameras_insert(db)
    db.commit()
    # _seed_cameras_insert skips existing camera_id, so if we started from
    # 0 (fresh) it inserted 30, if we started from 4 bootstrap it inserted 26
    # to reach 30.  Report the final registry size for UX parity with old script.
    final = db.query(Camera).count()
    print(f"  → Seeded {final} cameras." + (f" ({inserted} new)" if inserted != final else ""))


def seed_watchlist(db):
    # _seed_watchlist_insert already de-duplicates on plate_number and is
    # insert-only, so the CLI can just call it.
    existing = db.query(Watchlist).count()
    inserted = _seed_watchlist_insert(db)
    if inserted == 0 and existing > 0:
        print("  → Watchlist already seeded, skipping.")
        return
    db.commit()
    print(f"  → Seeded {inserted} new watchlist entries.")


def seed_events(db):
    count = db.query(VehicleEvent).count()
    if count > 0:
        # If cameras were stale, events are also stale — reseed
        cam_count = db.query(Camera).count()
        if cam_count == 30 and count >= 20:
            print("  → Vehicle events already seeded, skipping.")
            return
        print(f"  → Found {count} events with {cam_count} cameras, clearing and reseeding...")
        db.query(VehicleEvent).delete()
        db.commit()

    inserted = _seed_events_insert(db)
    db.commit()
    print(f"  → Seeded {inserted} vehicle events.")


def seed_alerts(db):
    count = db.query(Alert).count()
    if count > 0:
        cam_count = db.query(Camera).count()
        if cam_count == 30 and count >= 5:
            print("  → Alerts already seeded, skipping.")
            return
        print(f"  → Found {count} alerts, clearing and reseeding...")
        db.query(Alert).delete()
        db.commit()

    inserted = _seed_alerts_insert(db)
    db.commit()
    # Count linked rows for the same diagnostic the old script printed.
    # Re-query to get post-link state.
    linked_watchlist = db.query(Alert).filter(Alert.watchlist_id.isnot(None)).count()
    linked_events = db.query(Alert).filter(Alert.event_id.isnot(None)).count()
    print(f"  → Seeded {inserted} alerts.")
    print(f"    ↳ linked to events: {linked_events}/{inserted}, "
          f"watchlist records: {linked_watchlist}/{inserted}")


def main():
    print("\n[TRINETRA AI] Running Demo Seed Script")
    print("=" * 50)
    db = SessionLocal()
    try:
        print("\n[1/4] Seeding cameras...")
        seed_cameras(db)

        print("\n[2/4] Seeding watchlist...")
        seed_watchlist(db)

        print("\n[3/4] Seeding vehicle events...")
        seed_events(db)

        print("\n[4/4] Seeding alerts...")
        seed_alerts(db)

        print("\n[OK] Demo seed complete!")
        print("=" * 50)
        print("Demo plate: GJ01AB1234 -> CAM04 -> CAM17 -> CAM08 -> CAM07")
        print("API docs:   http://127.0.0.1:8000/docs")
        print("Health:     http://127.0.0.1:8000/health")
        print("WS stream:  ws://127.0.0.1:8000/api/v1/ws/events\n")
    except Exception as e:
        print(f"\n[ERROR] Seed failed: {e}")
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
