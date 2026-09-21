"""Restore the application's known CAM01–CAM30 directory, not its demo dataset.

The old serverless bootstrap combined this directory with synthetic watchlist,
sighting and alert rows. A full ML deployment needs the directory independently.
This operation only inserts missing camera metadata: no existing row is edited,
no video is opened and no detection/alert/watchlist/configuration is generated.
The bundled directory is not a fresh upstream availability or location check.
"""
from __future__ import annotations

from urllib.parse import urlsplit
from sqlalchemy import null
from sqlalchemy.orm import Session

from ..core.config import settings
from .demo_seed import DEMO_CAMERA_SPECS
from .models import Camera


DIRECTORY_HOST = "cctv.corp8.cloud"


def restore_sentinel_directory(db: Session) -> dict:
    if (urlsplit(settings.SENTINEL_HLS_BASE_URL).hostname or "").lower() != DIRECTORY_HOST:
        return {"status": "warning", "added_count": 0, "added_ids": [],
                "total_cameras": db.query(Camera).count(), "grid_cameras": 0,
                "message": "The configured provider differs from the bundled Sentinel directory. Sync your provider's catalogue instead."}
    existing = {value.upper() for (value,) in db.query(Camera.camera_id).all()}
    known_ids = {spec["camera_id"].upper() for spec in DEMO_CAMERA_SPECS}
    added = []
    # One caller-owned transaction. In particular, do not RELEASE a standalone
    # SQLite savepoint here: legacy sqlite transaction control can commit it
    # before the caller has decided whether to keep the changes.
    for spec in DEMO_CAMERA_SPECS:
        key = spec["camera_id"].upper()
        if key in existing:
            continue
        db.add(Camera(
            camera_id=key, name=spec["name"], location=spec["name"],
            stream_url=spec["stream_url"], stream_type=spec["stream_type"],
            codec=spec["codec"], width=spec["width"], height=spec["height"],
            # Do not import invented live state/FPS or fixture GPS into
            # real geographic/speed analysis. Calibrate/sync them separately.
            status="OFFLINE", fps=null(), latitude=null(), longitude=null(),
        ))
        existing.add(key)
        added.append(key)
    db.flush()
    return {
        "status": "success", "source": "bundled_camera_directory", "metadata_only": True,
        "added_count": len(added), "added_ids": added,
        "grid_cameras": len(existing & known_ids), "total_cameras": db.query(Camera).count(),
        "availability_checked": False,
        "message": f"Restored {len(added)} missing camera entries. Existing cameras and saved data were preserved. This restores the list, not a guarantee that every feed is reachable.",
    }
