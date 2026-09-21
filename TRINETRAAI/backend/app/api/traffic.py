"""Camera counting configuration and current observation-session statistics.

Counting is not a plate sighting, a violation or a complete census. This router
never opens a stream, runs a detector, or creates an alert/Vehicle Log entry.
"""
from datetime import datetime, timezone
from uuid import uuid4
from threading import Lock

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..database.database import get_db
from ..database.models import Camera, CameraTrafficConfig
from ..services.live_anpr_service import live_anpr_service
from ..services.traffic_counting import TrafficConfig
from .live_anpr import registered_camera

router = APIRouter(tags=["Traffic observations"])
# Same single-process contract as the frame scheduler. Commit + notification
# order must agree when two operators save settings concurrently.
_config_write_lock = Lock()


def config_row(db, camera_id):
    return db.query(CameraTrafficConfig).filter(func.upper(CameraTrafficConfig.camera_id) == camera_id.upper()).first()


@router.get("/cameras/{camera_id}/traffic-config")
def get_config(camera_id: str, db: Session = Depends(get_db)):
    camera = registered_camera(camera_id, db)
    row = config_row(db, camera.camera_id)
    try:
        config = TrafficConfig.model_validate_json(row.config_json) if row else TrafficConfig()
    except ValueError:
        raise HTTPException(500, "Stored traffic settings are invalid. Save a valid configuration to repair them.")
    return {"camera_id": camera.camera_id.lower(), "config": config.model_dump(),
            "revision": row.revision if row else "default"}


@router.put("/cameras/{camera_id}/traffic-config")
def put_config(camera_id: str, config: TrafficConfig, db: Session = Depends(get_db)):
    with _config_write_lock:
        camera = registered_camera(camera_id, db)
        row = config_row(db, camera.camera_id)
        if row is None:
            row = CameraTrafficConfig(camera_id=camera.camera_id)
            db.add(row)
        row.config_json = config.model_dump_json()
        row.revision = uuid4().hex
        row.updated_at = datetime.now(timezone.utc)
        db.commit()
        live_anpr_service.configure_traffic(camera.camera_id, config, row.revision)
        return {"camera_id": camera.camera_id.lower(), "config": config.model_dump(), "revision": row.revision}


@router.post("/cameras/{camera_id}/traffic-reset")
def reset_session(camera_id: str, db: Session = Depends(get_db)):
    camera = registered_camera(camera_id, db)
    live_anpr_service.reset_traffic(camera.camera_id)
    return {"camera_id": camera.camera_id.lower(), "reset": "next sample", "saved_sightings_changed": False}


@router.get("/traffic/sessions")
def traffic_sessions(db: Session = Depends(get_db)):
    items = []
    for camera in db.query(Camera).all():
        snapshot = live_anpr_service.snapshot(camera.camera_id)
        traffic = snapshot.get("traffic")
        if not traffic:
            continue
        items.append({
            **traffic, "camera_id": camera.camera_id.lower(), "camera_name": camera.name,
            "recorded": (camera.stream_type or "").lower() == "file",
            "status": snapshot["status"], "age_ms": snapshot["result_age_ms"],
        })
    return {"items": items, "scope": "current observation sessions",
            "note": "Sampled track counts; not total traffic, unique registered vehicles, or violations."}
