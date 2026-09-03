import json
from datetime import datetime, timezone
from sqlalchemy import (
    Column,
    Integer,
    String,
    Float,
    Boolean,
    DateTime,
    Text,
    Index,
    ForeignKey,
)
from sqlalchemy.orm import declarative_base

Base = declarative_base()


def get_utc_now():
    return datetime.now(timezone.utc)


class Camera(Base):
    __tablename__ = "cameras"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    camera_id = Column(String(50), unique=True, index=True, nullable=False)
    name = Column(String(100), nullable=False)
    stream_url = Column(String(500), nullable=False)
    stream_type = Column(String(20), default="rtsp", nullable=False)  # rtsp, hls, file
    latitude = Column(Float, nullable=True, default=23.0225)
    longitude = Column(Float, nullable=True, default=72.5714)
    location = Column(String(200), nullable=True)
    codec = Column(String(50), nullable=True, default="H264")
    width = Column(Integer, nullable=True, default=1920)
    height = Column(Integer, nullable=True, default=1080)
    status = Column(String(20), default="OFFLINE", index=True)  # ONLINE, OFFLINE, CONNECTING, ERROR
    last_seen = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=get_utc_now, nullable=False)

    __table_args__ = (
        Index("idx_cameras_status", "status"),
        Index("idx_cameras_last_seen", "last_seen"),
    )


class Detection(Base):
    __tablename__ = "detections"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    camera_id = Column(String(50), index=True, nullable=False)
    track_id = Column(Integer, index=True, nullable=True)
    object_type = Column(String(50), index=True, nullable=False)  # car, motorcycle, bus, truck, person, bicycle
    confidence = Column(Float, nullable=False)
    timestamp = Column(DateTime(timezone=True), default=get_utc_now, index=True, nullable=False)
    bbox_json = Column(Text, nullable=False)  # JSON string: [x1, y1, x2, y2]

    @property
    def bbox(self):
        try:
            return json.loads(self.bbox_json)
        except Exception:
            return []

    @bbox.setter
    def bbox(self, value):
        self.bbox_json = json.dumps(value)

    __table_args__ = (
        Index("idx_detections_cam_time", "camera_id", "timestamp"),
        Index("idx_detections_track", "track_id"),
    )


class VehicleObservation(Base):
    __tablename__ = "vehicle_observations"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    camera_id = Column(String(50), index=True, nullable=False)
    track_id = Column(Integer, index=True, nullable=True)
    plate_number = Column(String(30), index=True, nullable=True)
    plate_confidence = Column(Float, nullable=True)
    vehicle_type = Column(String(50), nullable=False, default="car")
    timestamp = Column(DateTime(timezone=True), default=get_utc_now, index=True, nullable=False)
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)

    __table_args__ = (
        Index("idx_veh_obs_plate", "plate_number"),
        Index("idx_veh_obs_camera_time", "camera_id", "timestamp"),
        Index("idx_veh_obs_track", "track_id"),
    )


class Watchlist(Base):
    __tablename__ = "watchlist"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    plate_number = Column(String(30), unique=True, index=True, nullable=False)
    category = Column(String(50), nullable=False)  # stolen vehicle, wanted vehicle, suspicious vehicle, other
    description = Column(String(255), nullable=True)
    active = Column(Boolean, default=True, index=True, nullable=False)
    created_at = Column(DateTime(timezone=True), default=get_utc_now, nullable=False)

    __table_args__ = (
        Index("idx_watchlist_plate_active", "plate_number", "active"),
    )


class VehicleEvent(Base):
    """Core vehicle event record produced by the AI ingestion pipeline."""
    __tablename__ = "vehicle_events"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    camera_id = Column(String(50), index=True, nullable=False)  # FK-like reference to cameras.camera_id
    vehicle_track_id = Column(Integer, index=True, nullable=True)  # AI track ID within camera session
    plate_raw = Column(String(100), nullable=True)   # Raw OCR string from camera
    plate_number = Column(String(30), index=True, nullable=True)  # Normalized plate
    plate_confidence = Column(Float, nullable=True)  # OCR confidence 0.0 – 1.0
    vehicle_class = Column(String(50), nullable=True, default="car")
    event_time = Column(DateTime(timezone=True), default=get_utc_now, index=True, nullable=False)
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    evidence_ref = Column(String(500), nullable=True)  # S3/URL reference to snapshot/clip
    watchlist_match = Column(Boolean, default=False, index=True, nullable=False)
    created_at = Column(DateTime(timezone=True), default=get_utc_now, nullable=False)

    __table_args__ = (
        Index("idx_ve_plate_cam_time", "plate_number", "camera_id", "event_time"),
        Index("idx_ve_watchlist", "watchlist_match"),
        Index("idx_ve_plate_time", "plate_number", "event_time"),
    )


class Alert(Base):
    __tablename__ = "alerts"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    event_id = Column(Integer, ForeignKey("vehicle_events.id"), index=True, nullable=True)
    watchlist_id = Column(Integer, ForeignKey("watchlist.id"), index=True, nullable=True)
    confidence = Column(Float, nullable=True)
    camera_id = Column(String(50), index=True, nullable=False)
    track_id = Column(Integer, index=True, nullable=True)
    plate_number = Column(String(30), index=True, nullable=True)
    alert_type = Column(String(50), index=True, nullable=False)  # WATCHLIST_MATCH, CAMERA_OFFLINE, LOW_OCR_CONFIDENCE, SYSTEM_ERROR
    severity = Column(String(20), default="HIGH", index=True)  # CRITICAL, HIGH, MEDIUM, LOW, INFO
    message = Column(Text, nullable=False)
    timestamp = Column(DateTime(timezone=True), default=get_utc_now, index=True, nullable=False)
    status = Column(String(20), default="NEW", index=True)  # NEW, ACKNOWLEDGED, RESOLVED, DISMISSED
    acknowledged_at = Column(DateTime(timezone=True), nullable=True)
    acknowledged_by = Column(String(100), nullable=True)
    resolved_at = Column(DateTime(timezone=True), nullable=True)
    resolved_by = Column(String(100), nullable=True)

    __table_args__ = (
        Index("idx_alerts_severity_time", "severity", "timestamp"),
        Index("idx_alerts_camera_time", "camera_id", "timestamp"),
        Index("idx_alerts_plate", "plate_number"),
    )
