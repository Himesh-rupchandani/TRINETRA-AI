import os
import sys
from pathlib import Path

# Allow running this file directly as a script
if __name__ == "__main__" and not __package__:
    project_root = Path(__file__).resolve().parents[3]
    backend_root = Path(__file__).resolve().parents[2]
    for p in [str(project_root), str(backend_root)]:
        if str(p) not in sys.path:
            sys.path.insert(0, str(p))
    __package__ = "backend.app.database"

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from ..core.config import settings
from ..core.logging_config import logger
from .models import Base, Camera, Watchlist, VehicleEvent

# Build engine depending on SQLite vs PostgreSQL
db_url = settings.DATABASE_URL
connect_args = {}

if db_url.startswith("sqlite"):
    connect_args["check_same_thread"] = False

try:
    engine = create_engine(
        db_url,
        connect_args=connect_args,
        pool_pre_ping=True,
    )
except Exception as e:
    logger.error(f"Failed to create database engine with {db_url}: {e}. Falling back to SQLite.")
    db_url = "sqlite:///./trinetra.db"
    engine = create_engine(db_url, connect_args={"check_same_thread": False})

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    """FastAPI database session dependency."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _auto_migrate(target_engine=None):
    """Automatically adds newly added columns to existing tables if missing."""
    eng = target_engine or engine
    with eng.begin() as conn:
        for col, col_def in [
            ("location", "VARCHAR(200)"),
            ("codec", "VARCHAR(50) DEFAULT 'H264'"),
            ("width", "INTEGER DEFAULT 1920"),
            ("height", "INTEGER DEFAULT 1080"),
            ("department", "VARCHAR(100)"),
            ("zone", "VARCHAR(50)"),
            ("fps", "INTEGER"),
        ]:
            try:
                conn.execute(text(f"ALTER TABLE cameras ADD COLUMN {col} {col_def}"))
                logger.info(f"Added missing column cameras.{col}")
            except Exception:
                pass

        for col, col_def in [
            ("event_id", "INTEGER REFERENCES vehicle_events(id)"),
            ("watchlist_id", "INTEGER REFERENCES watchlist(id)"),
            ("confidence", "FLOAT"),
        ]:
            try:
                conn.execute(text(f"ALTER TABLE alerts ADD COLUMN {col} {col_def}"))
                logger.info(f"Added missing column alerts.{col}")
            except Exception:
                pass


def init_db():
    """Create database tables and seed example records only in demo mode.

    A live deployment must begin with an empty registry until it receives the
    authorised catalogue (or an explicitly configured live camera). Otherwise
    four placeholder rows plus an unconfigured slot look like five failed
    official cameras, which is both misleading and difficult for an operator to
    diagnose.
    """
    logger.info("Initializing database tables...")
    Base.metadata.create_all(bind=engine)
    _auto_migrate(engine)

    db = SessionLocal()
    try:
        if not settings.DEMO_MODE:
            logger.info(
                "Live mode: not seeding example cameras, watchlist entries, or synthetic records. "
                "Awaiting an authorised catalogue or LIVE_CAMERA_* configuration."
            )
            return

        # Demo-only starter data. The dedicated seed_demo script remains
        # available for the larger offline demonstration dataset.
        if db.query(Camera).count() == 0:
            logger.info("Demo mode: seeding initial CCTV camera locations...")
            initial_cameras = [
                Camera(
                    camera_id="CAM04",
                    name="Paldi Circle",
                    location="Paldi Circle",
                    stream_url=settings.DEFAULT_CAMERA_STREAM_URL,
                    stream_type=settings.DEFAULT_CAMERA_STREAM_TYPE,
                    latitude=23.0126,
                    longitude=72.5647,
                    status="OFFLINE",
                ),
                Camera(
                    camera_id="CAM01",
                    name="Chiman bhai Bridge",
                    location="Chiman bhai Bridge",
                    stream_url="https://cctv.corp8.cloud/cam01/index.m3u8",
                    stream_type="hls",
                    latitude=23.0730,
                    longitude=72.5920,
                    status="OFFLINE",
                ),
                Camera(
                    camera_id="CAM02",
                    name="Janpath",
                    location="Janpath",
                    stream_url="https://cctv.corp8.cloud/cam02/index.m3u8",
                    stream_type="hls",
                    latitude=23.0225,
                    longitude=72.5625,
                    status="OFFLINE",
                ),
                Camera(
                    camera_id="CAM03",
                    name="O.N.G.C. Office",
                    location="O.N.G.C. Office",
                    stream_url="https://cctv.corp8.cloud/cam03/index.m3u8",
                    stream_type="hls",
                    latitude=23.1070,
                    longitude=72.5950,
                    status="OFFLINE",
                ),
            ]
            db.add_all(initial_cameras)
            db.commit()

        if db.query(Watchlist).count() == 0:
            logger.info("Demo mode: seeding initial watchlist entries...")
            initial_watchlist = [
                Watchlist(
                    plate_number="GJ01AB1234",
                    category="stolen vehicle",
                    description="Silver Sedan - Reported stolen FIR #4812",
                    active=True,
                ),
                Watchlist(
                    plate_number="MH02CD5678",
                    category="wanted vehicle",
                    description="Black SUV - Suspect in inter-state logistics theft",
                    active=True,
                ),
                Watchlist(
                    plate_number="DL08EF9012",
                    category="suspicious vehicle",
                    description="White Hatchback - Multiple toll avoidance flags",
                    active=True,
                ),
            ]
            db.add_all(initial_watchlist)
            db.commit()

    except Exception as e:
        logger.error(f"Error while initializing database: {e}")
        db.rollback()
    finally:
        db.close()


if __name__ == "__main__":
    init_db()

