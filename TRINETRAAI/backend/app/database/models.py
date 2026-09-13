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
from sqlalchemy.types import TypeDecorator

Base = declarative_base()


def get_utc_now():
    return datetime.now(timezone.utc)


class UTCDateTime(TypeDecorator):
    """Timezone-safe ``DateTime`` for every backend timestamp column.

    Problem this solves: SQLite has no timezone-aware datetime type, so a plain
    ``DateTime(timezone=True)`` column round-tripped **naive** values. The API
    then serialized ``2026-09-12T08:17:28`` with no offset and every browser
    read that UTC instant as *local* time, shifting all clocks, timelines and
    "x minutes ago" labels by the viewer's UTC offset.

    Contract enforced here:

    * values are stored as UTC wall time (aware input is converted with
      ``astimezone``; naive input is *assumed* to be UTC, never shifted);
    * values read back are always timezone-aware UTC, so serialization keeps
      the offset and no timezone information is silently dropped.
    """

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)


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
    # Owning agency + operational zone: the CCTV Registry (Model 1) must expose
    # these so the UI never has to guess or hard-code them per component.
    department = Column(String(100), nullable=True)
    zone = Column(String(50), nullable=True)
    codec = Column(String(50), nullable=True, default="H264")
    width = Column(Integer, nullable=True, default=1920)
    height = Column(Integer, nullable=True, default=1080)
    fps = Column(Integer, nullable=True)
    status = Column(String(20), default="OFFLINE", index=True)  # ONLINE, OFFLINE, CONNECTING, ERROR
    last_seen = Column(UTCDateTime(), nullable=True)
    created_at = Column(UTCDateTime(), default=get_utc_now, nullable=False)

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
    timestamp = Column(UTCDateTime(), default=get_utc_now, index=True, nullable=False)
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
    timestamp = Column(UTCDateTime(), default=get_utc_now, index=True, nullable=False)
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
    created_at = Column(UTCDateTime(), default=get_utc_now, nullable=False)

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
    event_time = Column(UTCDateTime(), default=get_utc_now, index=True, nullable=False)
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    evidence_ref = Column(String(500), nullable=True)  # S3/URL reference to snapshot/clip
    # The plate crop that produced this read, when one could be cut. Kept
    # separate from ``evidence_ref`` (the vehicle) because the two answer
    # different questions: "what vehicle was this" vs "what did the plate say".
    plate_evidence_ref = Column(String(500), nullable=True)
    watchlist_match = Column(Boolean, default=False, index=True, nullable=False)
    # Manually-uploaded CCTV video provenance (NULL for live-camera sightings).
    video_file = Column(String(255), nullable=True)      # uploaded filename, e.g. cam1.mp4
    video_offset_sec = Column(Float, nullable=True)      # position inside the video, in seconds
    # --- Multi-video analysis provenance (NULL for live-camera sightings) ---
    # Set by the multi-video analysis pipeline so every sighting can be traced
    # back to the exact source video, frame and box it came from.
    video_id = Column(String(64), index=True, nullable=True)   # video_sources.video_id
    frame_number = Column(Integer, nullable=True)              # frame index inside the video
    vehicle_confidence = Column(Float, nullable=True)          # detector confidence 0.0-1.0
    bbox_json = Column(String(200), nullable=True)             # "[x1, y1, x2, y2]" in pixels
    # HIGH | LOW_CONFIDENCE | UNKNOWN — an uncertain read is never promoted to
    # a confident plate; it is labelled instead.
    plate_status = Column(String(20), nullable=True)
    created_at = Column(UTCDateTime(), default=get_utc_now, nullable=False)

    @property
    def bbox(self):
        try:
            return json.loads(self.bbox_json) if self.bbox_json else None
        except Exception:
            return None

    @bbox.setter
    def bbox(self, value):
        self.bbox_json = json.dumps([round(float(v), 1) for v in value]) if value else None

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
    timestamp = Column(UTCDateTime(), default=get_utc_now, index=True, nullable=False)
    status = Column(String(20), default="NEW", index=True)  # NEW, ACKNOWLEDGED, RESOLVED, DISMISSED
    acknowledged_at = Column(UTCDateTime(), nullable=True)
    acknowledged_by = Column(String(100), nullable=True)
    resolved_at = Column(UTCDateTime(), nullable=True)
    resolved_by = Column(String(100), nullable=True)
    # Free-text resolution note. Kept OUT of resolved_by so the resolving
    # officer's identity stays a clean person/badge value.
    resolution_note = Column(Text, nullable=True)

    __table_args__ = (
        Index("idx_alerts_severity_time", "severity", "timestamp"),
        Index("idx_alerts_camera_time", "camera_id", "timestamp"),
        Index("idx_alerts_plate", "plate_number"),
    )


class VideoSource(Base):
    """
    One video submitted to the multi-video analysis feature.

    A video source is always paired with a row in ``cameras`` (stream_type
    'file') so every existing camera/vehicle/GIS endpoint keeps working
    unchanged; this table only adds what the registry cannot express:
    where the video came from, and how far its analysis has got.
    """

    __tablename__ = "video_sources"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    video_id = Column(String(64), unique=True, index=True, nullable=False)
    batch_id = Column(String(64), index=True, nullable=True)
    camera_id = Column(String(50), index=True, nullable=False)  # CAM1, CAM2, ...
    source_type = Column(String(20), nullable=False, default="UPLOAD")  # UPLOAD | GDRIVE
    source_name = Column(String(255), nullable=False)   # original filename / Drive file name
    source_ref = Column(String(1000), nullable=True)    # original Drive URL (NULL for uploads)
    file_path = Column(String(1000), nullable=True)     # absolute path on disk

    # PENDING | DOWNLOADING | READY | QUEUED | PROCESSING | DONE | FAILED
    status = Column(String(20), nullable=False, default="PENDING", index=True)
    error = Column(Text, nullable=True)
    progress_pct = Column(Float, nullable=False, default=0.0)

    # Probed with OpenCV at registration time (never guessed).
    fps = Column(Float, nullable=True)
    width = Column(Integer, nullable=True)
    height = Column(Integer, nullable=True)
    duration_sec = Column(Float, nullable=True)
    size_bytes = Column(Integer, nullable=True)

    frames_total = Column(Integer, nullable=False, default=0)
    frames_read = Column(Integer, nullable=False, default=0)
    frames_analyzed = Column(Integer, nullable=False, default=0)
    vehicles_detected = Column(Integer, nullable=False, default=0)
    plates_read = Column(Integer, nullable=False, default=0)
    unknown_plates = Column(Integer, nullable=False, default=0)

    created_at = Column(UTCDateTime(), default=get_utc_now, nullable=False)
    started_at = Column(UTCDateTime(), nullable=True)
    completed_at = Column(UTCDateTime(), nullable=True)

    __table_args__ = (
        Index("idx_video_sources_status", "status"),
        Index("idx_video_sources_batch", "batch_id"),
    )


class EvidenceRecord(Base):
    """One sealed link in the SHA-256 evidence hash chain (BSA 2023 §63).

    Sealed at capture time from the event's immutable fields. Verification
    recomputes the hash from (a) the stored canonical payload and (b) the live
    row, so both a doctored record and a doctored sighting are detected — the
    old ``/reports/evidence/{id}/verify`` endpoint recomputed a hash from the
    *current* row and unconditionally answered VALID.
    """

    __tablename__ = "evidence_records"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    # One sealed record per sighting.
    event_id = Column(
        Integer, ForeignKey("vehicle_events.id"), unique=True, index=True, nullable=False
    )
    camera_id = Column(String(50), index=True, nullable=False)

    # Position in the chain; `previous_hash` is the hash of chain_index - 1
    # (or GENESIS for the first record).
    chain_index = Column(Integer, nullable=False, default=0, index=True)
    hash = Column(String(64), nullable=False, index=True)
    previous_hash = Column(String(64), nullable=True)

    # Canonical JSON snapshot of the immutable fields at seal time.
    payload_json = Column(Text, nullable=False)

    # CAPTURE  — sealed by the ingestion pipeline when the sighting was created
    # BACKFILL — sealed on first certificate/verification request (pre-existing
    #            rows from before the vault existed); reported transparently.
    seal_source = Column(String(20), nullable=False, default="CAPTURE")
    sealed_at = Column(UTCDateTime(), default=get_utc_now, nullable=False)

    def payload(self) -> dict:
        """The sealed snapshot as a dict ({} when unreadable)."""
        try:
            return json.loads(self.payload_json) if self.payload_json else {}
        except (TypeError, ValueError):
            return {}
