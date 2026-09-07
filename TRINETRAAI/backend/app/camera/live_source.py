"""
Real live camera source registration (environment-configurable).

The one camera in the registry that is meant to be a REAL live source (e.g.
an authorized Ahmedabad traffic CCTV stream) is defined entirely by
environment variables / ``backend/.env`` — no code changes needed to connect
or replace it later::

    LIVE_CAMERA_ID=CAMLIVE
    LIVE_CAMERA_NAME=SG Highway Junction, Ahmedabad
    LIVE_CAMERA_LOCATION=Ahmedabad, Gujarat
    LIVE_CAMERA_STREAM_TYPE=rtsp          # rtsp | hls | webrtc | whep | file
    LIVE_CAMERA_STREAM_URL=rtsp://...     # server-side authorized URL only
    LIVE_CAMERA_INGEST_URL=rtsp://...     # optional paired CV source for WHEP
    LIVE_CAMERA_INGEST_TYPE=rtsp
    LIVE_CAMERA_STATUS=                   # optional initial status override

Behaviour (honesty rules):

- ``LIVE_CAMERA_STREAM_URL`` EMPTY -> demo mode may show a clearly
  ``NOT_CONFIGURED`` setup slot. In real mode an empty setting does not create
  a placeholder camera row, so the registry contains only authorized catalogue
  cameras and explicitly configured sources.
- ``LIVE_CAMERA_STREAM_URL`` SET -> the camera is registered like any other
  network camera. The database receives only a credential-free reference;
  the original value stays in environment memory and is resolved at connect
  time. With ``AUTO_START_CAMERAS=true`` a stream worker connects at boot and
  the camera shows Working only while frames actually arrive; if the stream is
  unreachable it shows offline honestly.
"""
import logging

from sqlalchemy import func as sa_func
from sqlalchemy.orm import Session

from ..core.config import settings
from ..database.models import Camera
from ..services.sentinel_stream_service import redact

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

    # A fresh real deployment starts with its authorized catalogue, not an
    # invented empty "CAMLIVE" tile. Also leave a pre-existing row untouched
    # when operators removed this optional configuration; it may now belong to
    # a synchronised catalogue rather than this environment-driven slot.
    if not url and not settings.DEMO_MODE and not override:
        logger.info(
            "[%s] no LIVE_CAMERA_STREAM_URL configured; skipping the optional empty live-camera slot in real mode.",
            cam_id,
        )
        return

    if not url:
        # No real source configured: keep the demo/setup slot visible but
        # unplayable when an operator explicitly requested its status.
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

    # Real source configured: register a *safe reference* only. The original
    # authenticated/signed URL remains in the process environment and
    # resolve_ingest_source() retrieves it immediately before OpenCV connects.
    status = override or "OFFLINE"  # flips to ONLINE only when frames actually arrive
    values = dict(
        name=settings.LIVE_CAMERA_NAME.strip() or cam_id.title(),
        location=settings.LIVE_CAMERA_LOCATION.strip() or "—",
        stream_type=stype or "rtsp",
        stream_url=redact(url),
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
        "[%s] real live camera configured from secure environment (%s; source details withheld)",
        cam_id,
        stype or "rtsp",
    )
