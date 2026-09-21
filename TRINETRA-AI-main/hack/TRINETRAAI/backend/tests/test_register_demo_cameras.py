"""register_demo_cameras — registry rows for the CAMD demo feeds.

The README used to register CAMD01/CAMD02 with a bash heredoc, which cannot
run on Windows PowerShell — so Windows operators had no supported way to get
the DEMO FEED cameras into the registry (and the Cameras page silently missed
them). ``scripts/register_demo_cameras.py`` is the cross-platform replacement:
idempotent upsert with metadata mirroring run_feed_demo.py::FEEDS.
"""
import sys
from pathlib import Path

backend_root = Path(__file__).resolve().parents[1]
if str(backend_root) not in sys.path:
    sys.path.insert(0, str(backend_root))

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database.models import Base, Camera
from scripts.register_demo_cameras import DEMO_CAMERAS, register_demo_cameras


@pytest.fixture()
def db_session(tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'register_demo.db'}",
        connect_args={"check_same_thread": False, "timeout": 15},
    )
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = Session()
    yield session
    session.close()
    engine.dispose()


@pytest.fixture()
def feeds_dir(tmp_path):
    for cam in DEMO_CAMERAS:
        (tmp_path / cam["video"]).write_bytes(b"fake-mp4")
    return tmp_path


def test_registers_both_demo_cameras(db_session, feeds_dir):
    cams = register_demo_cameras(db_session, feeds_dir=feeds_dir)
    assert [c["camera_id"] for c in cams] == ["CAMD01", "CAMD02"]

    rows = db_session.query(Camera).filter(Camera.camera_id.like("CAMD%")).all()
    assert len(rows) == 2
    by_id = {r.camera_id: r for r in rows}
    for cam in DEMO_CAMERAS:
        row = by_id[cam["camera_id"]]
        assert row.stream_type == "file"
        assert row.status == "ONLINE"
        assert row.stream_url == str((feeds_dir / cam["video"]).resolve())
        assert row.name == cam["name"]
        assert row.location == cam["location"]
        assert row.latitude == cam["latitude"]
        assert row.longitude == cam["longitude"]


def test_idempotent_and_refreshes_feed_paths(db_session, feeds_dir, tmp_path):
    register_demo_cameras(db_session, feeds_dir=feeds_dir)

    # clips moved to a new folder (e.g. repo relocated): re-run must update,
    # not duplicate
    new_dir = tmp_path / "feeds2"
    new_dir.mkdir()
    for cam in DEMO_CAMERAS:
        (new_dir / cam["video"]).write_bytes(b"fake-mp4")
    register_demo_cameras(db_session, feeds_dir=new_dir)

    rows = db_session.query(Camera).filter(Camera.camera_id.like("CAMD%")).all()
    assert len(rows) == 2
    assert all(r.stream_url.startswith(str(new_dir.resolve())) for r in rows)


def test_missing_feeds_actionable_error(db_session, tmp_path):
    with pytest.raises(FileNotFoundError) as excinfo:
        register_demo_cameras(db_session, feeds_dir=tmp_path / "empty")
    assert "make_local_feeds" in str(excinfo.value)
    # nothing was committed on failure
    assert db_session.query(Camera).filter(Camera.camera_id.like("CAMD%")).count() == 0
