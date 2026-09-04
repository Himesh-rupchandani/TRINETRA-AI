"""
Real live camera source registration (environment-configurable).

The one camera in the registry that is meant to be a REAL live source (e.g.
an authorized Ahmedabad traffic CCTV stream) is defined entirely by
environment variables / ``backend/.env`` — no code changes needed to connect
or replace it later::

    LIVE_CAMERA_ID=CAMLIVE
    LIVE_CAMERA_NAME=SG Highway Junction, Ahmedabad
    LIVE_CAMERA_LOCATION=Ahmedabad, Gujarat
    LIVE_CAMERA_STREAM_TYPE=rtsp          # rtsp | hls | webrtc | file
    LIVE_CAMERA_STREAM_URL=rtsp://...     # authorized URL only
    LIVE_CAMERA_STATUS=                   # optional initial status override

Behaviour (honesty rules):

- ``LIVE_CAMERA_STREAM_URL`` EMPTY -> the slot is registered with an empty
  source and resolves to ``NOT_CONFIGURED`` ("Camera source not configured").
  No recorded/demo video is ever used as a stand-in for the live source.
- ``LIVE_CAMERA_STREAM_URL`` SET -> the camera is registered like any other
  network camera. With ``AUTO_START_CAMERAS=true`` a stream worker connects
  at boot and the camera shows Working only while frames actually arrive;
  if the stream is unreachable it shows offline honestly.
"""
import logging

from sqlalchemy import func as sa_func
from sqlalchemy.orm import Session

from ..core.config import settings
from ..database.models import Camera

logger = logging.getLogger("trinetra")


def sync_live_camera(db: Session) -> None:
    """Create or update the env-configured real-live-camera registry entry.

    Called once at backend startup. Idempotent: the same env values always
    produce the same registry row, so changing ``.env`` + restarting is all
    that is needed to point the system at a new authorized stream.
    """
    cam_id = settings.LIVE_CAMERA_ID.strip().upper()
    url = settings.LIVE_CAMERA_STREAM_URL.strip()
    stype = settings.LIVE_CAMERA_STREAM_TYPE.strip().lower()
    override = settings.LIVE_CAMERA_STATUS.strip().upper()

    cam = db.query(Camera).filter(sa_func.upper(Camera.camera_id) == cam_id).first()

    if not url:
        # No real source configured: keep the slot visible but unplayable.
        status = override or "NOT_CONFIGURED"
        values = dict(
            name=settings.LIVE_CAMERA_NAME.strip() or "Live Traffic Camera (source not configured)",
            location=settings.LIVE_CAMERA_LOCATION.strip() or "—",
            stream_type=stype or "rtsp",
            stream_url="",
            status=status,
        )
        if cam is None:
            db.add(Camera(
                camera_id=cam_id,
                latitude=settings.LIVE_CAMERA_LATITUDE,
                longitude=settings.LIVE_CAMERA_LONGITUDE,
                **values,
            ))
        else:
            for k, v in values.items():
                setattr(cam, k, v)
        db.commit()
        logger.info(
            "[%s] live camera slot registered WITHOUT a source (NOT_CONFIGURED). "
            "Set LIVE_CAMERA_STREAM_URL/... in backend/.env to connect a real stream.",
            cam_id,
        )
        return

    # Real source configured: register it like any other network camera.
    status = override or "OFFLINE"  # flips to ONLINE only when frames actually arrive
    values = dict(
        name=settings.LIVE_CAMERA_NAME.strip() or cam_id.title(),
        location=settings.LIVE_CAMERA_LOCATION.strip() or "—",
        stream_type=stype or "rtsp",
        stream_url=url,
        status=status,
    )
    if cam is None:
        db.add(Camera(
            camera_id=cam_id,
            latitude=settings.LIVE_CAMERA_LATITUDE,
            longitude=settings.LIVE_CAMERA_LONGITUDE,
            **values,
        ))
    else:
        for k, v in values.items():
            setattr(cam, k, v)
    db.commit()
    logger.info("[%s] real live camera configured: %s %s", cam_id, stype or "rtsp", url)
