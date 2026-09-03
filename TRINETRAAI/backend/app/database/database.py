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
    """Create all database tables and seed default mock / initial cameras & watchlist if empty."""
    logger.info("Initializing database tables...")
    Base.metadata.create_all(bind=engine)
    _auto_migrate(engine)

    # Seed default data if database is empty
    db = SessionLocal()
    try:
        # Check cameras
        if db.query(Camera).count() == 0:
            logger.info("Seeding initial CCTV camera locations...")
            initial_cameras = [
                Camera(
                    camera_id="CAM04",
                    name="North Gate Junction (HLS / RTSP)",
                    stream_url=settings.DEFAULT_CAMERA_STREAM_URL,
                    stream_type=settings.DEFAULT_CAMERA_STREAM_TYPE,
                    latitude=23.0338,
                    longitude=72.5850,
                    status="OFFLINE",
                ),
                Camera(
                    camera_id="CAM01",
                    name="Central Expressway Toll Plaza",
                    stream_url="https://cctv.corp8.cloud/cam01/index.m3u8",
                    stream_type="hls",
                    latitude=23.0225,
                    longitude=72.5714,
                    status="OFFLINE",
                ),
                Camera(
                    camera_id="CAM02",
                    name="Metro Station Interchange Cam",
                    stream_url="https://cctv.corp8.cloud/cam02/index.m3u8",
                    stream_type="hls",
                    latitude=23.0410,
                    longitude=72.5620,
                    status="OFFLINE",
                ),
                Camera(
                    camera_id="CAM03",
                    name="SG Highway Ring Road West",
                    stream_url="https://cctv.corp8.cloud/cam03/index.m3u8",
                    stream_type="hls",
                    latitude=23.0150,
                    longitude=72.5110,
                    status="OFFLINE",
                ),
            ]
            db.add_all(initial_cameras)
            db.commit()

        # Check watchlist
        if db.query(Watchlist).count() == 0:
            logger.info("Seeding initial watchlist entries for demonstration...")
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
        logger.error(f"Error while seeding database: {e}")
        db.rollback()
    finally:
        db.close()


if __name__ == "__main__":
    init_db()

