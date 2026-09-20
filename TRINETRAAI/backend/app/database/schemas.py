from datetime import datetime, timezone
from typing import List, Optional, Generic, TypeVar, Any, Dict
from pydantic import BaseModel, Field, ConfigDict, field_serializer, model_validator

T = TypeVar("T")


def to_utc(dt: datetime) -> datetime:
    """Return ``dt`` as timezone-aware UTC (naive values are assumed to be UTC)."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def iso_utc(dt: datetime) -> str:
    """Browser-safe ISO-8601 UTC: ``2026-09-12T08:17:28.236849Z``."""
    return to_utc(dt).isoformat().replace("+00:00", "Z")


class TRINETRASchema(BaseModel):
    """Base model for every API schema.

    Timestamp contract (pairs with ``app.database.models.UTCDateTime``):

    * **out** — every ``datetime`` is serialized as ISO-8601 UTC with an
      explicit ``Z`` suffix, so ``new Date(value)`` in the browser is the same
      instant the backend stored. A naive value is read as *local* time and
      shifts every clock in the UI by the viewer's UTC offset.
    * **in** — a naive ``datetime`` supplied by a client is interpreted as UTC
      instead of being silently re-labelled later; a value carrying an offset
      (``...Z``, ``+05:30``) is preserved and normalized to UTC.
    """

    @model_validator(mode="after")
    def _normalize_datetimes_to_utc(self):
        for name in type(self).model_fields:
            value = getattr(self, name, None)
            if isinstance(value, datetime) and value.tzinfo is None:
                setattr(self, name, value.replace(tzinfo=timezone.utc))
        return self

    @field_serializer("*", when_used="json")
    def _serialize_datetimes_as_utc(self, value, _info):
        if isinstance(value, datetime):
            return iso_utc(value)
        return value


# --- Base Paginated Response ---
class PaginatedResponse(TRINETRASchema, Generic[T]):
    items: List[T]
    total: int
    page: int
    size: int
    pages: int


# --- Camera Schemas ---
class CameraBase(TRINETRASchema):
    camera_id: str = Field(..., example="CAM04", min_length=2, max_length=50)
    name: str = Field(..., example="North Gate Junction", min_length=2, max_length=100)
    stream_url: str = Field(..., example="rtsp://103.250.160.189:8554/stream/cam04")
    stream_type: str = Field("rtsp", example="rtsp")  # rtsp, hls, file
    latitude: Optional[float] = Field(23.0225, example=23.0225)
    longitude: Optional[float] = Field(72.5714, example=72.5714)
    location: Optional[str] = Field(None, example="Paldi Circle")
    codec: Optional[str] = Field("H264", example="H264")
    width: Optional[int] = Field(1920, example=1920)
    height: Optional[int] = Field(1080, example=1080)


class CameraCreate(CameraBase):
    pass


class CameraUpdate(TRINETRASchema):
    name: Optional[str] = None
    stream_url: Optional[str] = None
    stream_type: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    location: Optional[str] = None
    codec: Optional[str] = None
    width: Optional[int] = None
    height: Optional[int] = None
    status: Optional[str] = None


class CameraResponse(CameraBase):
    id: int
    status: str
    last_seen: Optional[datetime] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CameraItem(TRINETRASchema):
    id: str
    camera_id: Optional[str] = None
    name: str
    location: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    department: Optional[str] = None
    zone: Optional[str] = None
    status: str
    codec: Optional[str] = "H264"
    width: Optional[int] = 1920
    height: Optional[int] = 1080
    fps: Optional[int] = None
    stream_type: str = "HLS"
    stream_url: str
    last_seen: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class CameraListResponse(TRINETRASchema):
    data: List[CameraItem]


class CameraStreamTicket(TRINETRASchema):
    """Browser-safe playback ticket. Contains no credentials and no RTSP URLs."""
    camera_id: str
    stream_type: str = "WEBRTC"
    stream_url: str = ""
    expires_at: datetime
    playable: bool = False
    reason: Optional[str] = None
    # Same-origin MJPEG view of the same camera with real-time OpenCV vehicle
    # detection (green boxes). None when the source cannot be processed.
    detection_url: Optional[str] = None


class CameraStreamInfo(TRINETRASchema):
    camera_id: str
    status: str
    fps: float
    frame_count: int
    is_alive: bool
    last_error: Optional[str] = None


# --- Detection Schemas ---
class DetectionBase(TRINETRASchema):
    camera_id: str
    track_id: Optional[int] = None
    object_type: str  # car, motorcycle, bus, truck, bicycle, person
    confidence: float
    bbox: List[float]  # [x1, y1, x2, y2]
    timestamp: Optional[datetime] = None


class DetectionCreate(DetectionBase):
    pass


class DetectionResponse(DetectionBase):
    id: int
    timestamp: datetime

    model_config = ConfigDict(from_attributes=True)


# --- Vehicle Observation Schemas ---
class VehicleObservationBase(TRINETRASchema):
    camera_id: str
    track_id: Optional[int] = None
    plate_number: Optional[str] = None
    plate_confidence: Optional[float] = None
    vehicle_type: str = "car"
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    timestamp: Optional[datetime] = None


class VehicleObservationCreate(VehicleObservationBase):
    pass


class VehicleObservationResponse(VehicleObservationBase):
    id: int
    timestamp: datetime

    model_config = ConfigDict(from_attributes=True)


# --- Watchlist Schemas ---
class WatchlistBase(TRINETRASchema):
    plate_number: str = Field(..., example="GJ01AB1234")
    category: str = Field(..., example="stolen vehicle")  # stolen vehicle, wanted vehicle, suspicious vehicle, other
    description: Optional[str] = Field(None, example="Reported stolen near SG Highway")
    active: bool = Field(True, example=True)


class WatchlistCreate(WatchlistBase):
    pass


class WatchlistUpdate(TRINETRASchema):
    category: Optional[str] = None
    description: Optional[str] = None
    active: Optional[bool] = None


class WatchlistResponse(WatchlistBase):
    id: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# --- Alert Schemas ---
class AlertBase(TRINETRASchema):
    camera_id: str
    track_id: Optional[int] = None
    plate_number: Optional[str] = None
    alert_type: str  # WATCHLIST_MATCH, CAMERA_OFFLINE, LOW_OCR_CONFIDENCE, SYSTEM_ERROR
    severity: str = "HIGH"  # CRITICAL, HIGH, MEDIUM, LOW, INFO
    message: str
    status: str = "NEW"  # NEW, ACKNOWLEDGED, RESOLVED, DISMISSED


class AlertCreate(AlertBase):
    pass


class AlertUpdate(TRINETRASchema):
    status: Optional[str] = None
    severity: Optional[str] = None


class AlertResponse(AlertBase):
    id: int
    event_id: Optional[int] = None
    watchlist_id: Optional[int] = None
    confidence: Optional[float] = None
    timestamp: datetime
    acknowledged_at: Optional[datetime] = None
    acknowledged_by: Optional[str] = None
    resolved_at: Optional[datetime] = None
    resolved_by: Optional[str] = None
    resolution_note: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class AlertAckRequest(TRINETRASchema):
    operator: Optional[str] = Field(None, description="Operator username or badge ID")
    # Resolve only: free-text note. Stored in Alert.resolution_note, never
    # concatenated into `operator`.
    note: Optional[str] = Field(None, description="Optional resolution note")


# --- Vehicle Event Schemas ---
class VehicleEventCreate(TRINETRASchema):
    camera_id: str = Field(..., example="CAM04")
    vehicle_id: Optional[int] = Field(None, example=101, description="AI track ID")
    plate_raw: Optional[str] = Field(None, example="GJ 01 AB-1234")
    plate: Optional[str] = Field(None, example="GJ01AB1234", description="Normalized or raw plate alias")
    plate_confidence: Optional[float] = Field(None, ge=0.0, le=1.0, example=0.95)
    timestamp_pts: Optional[float] = Field(None, example=123456.78, description="Video PTS timestamp")
    vehicle_class: Optional[str] = Field("car", example="car")
    event_time: Optional[datetime] = Field(None, description="ISO8601 event timestamp, defaults to now")
    latitude: Optional[float] = Field(None, example=23.0338)
    longitude: Optional[float] = Field(None, example=72.585)
    evidence_ref: Optional[str] = Field(None, example="https://s3.example.com/snap/abc.jpg")

    model_config = ConfigDict(extra="ignore")


class VehicleEventResponse(TRINETRASchema):
    id: int
    camera_id: str
    vehicle_track_id: Optional[int] = None
    plate_raw: Optional[str] = None
    plate_number: Optional[str] = None
    plate_confidence: Optional[float] = None
    vehicle_class: Optional[str] = None
    event_time: datetime
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    evidence_ref: Optional[str] = None
    watchlist_match: bool
    plate_status: Optional[str] = None
    vehicle_confidence: Optional[float] = None
    bbox: Optional[List[float]] = None
    # Manually-uploaded CCTV video provenance (None for live-camera sightings).
    video_file: Optional[str] = None
    video_offset_sec: Optional[float] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class VehicleEventIngestResponse(TRINETRASchema):
    event: VehicleEventResponse
    plate_normalized: str
    watchlist_match: bool
    alert_created: bool
    alert_id: Optional[int] = None
    message: str


# --- Route / GIS Schemas ---
class RoutePoint(TRINETRASchema):
    sequence: int
    camera_id: str
    # The sighting behind this hop, so a GIS route point can deep-link to its
    # evidence / detection detail without client-side guesswork.
    event_id: Optional[int] = None
    # Registry metadata is joined here so a GIS route point can render
    # "camera / location / timestamp / confidence" without a second round trip.
    camera_name: Optional[str] = None
    location: Optional[str] = None
    event_time: datetime
    latitude: Optional[float]
    longitude: Optional[float]
    confidence: Optional[float] = None
    # Manually-uploaded CCTV video provenance (None for live-camera sightings).
    video_file: Optional[str] = None
    video_offset_sec: Optional[float] = None


class VehicleRouteResponse(TRINETRASchema):
    plate_number: str
    total_sightings: int
    route: List[RoutePoint]


class VehicleProfileResponse(TRINETRASchema):
    """Investigation profile for one plate: sighting stats + watchlist state."""
    plate_number: str
    vehicle_class: Optional[str] = None
    first_seen: Optional[datetime] = None
    last_seen: Optional[datetime] = None
    total_sightings: int = 0
    cameras_touched: int = 0
    watchlist_match: bool = False
    watchlist: Optional[WatchlistResponse] = None


# --- Officer Schemas ---
class OfficerResponse(TRINETRASchema):
    """One officer's own profile. Figures are scoped to that officer only."""

    officer_id: str
    name: str
    photo_url: str
    police_id: str
    department: str
    designation: str
    vehicles_caught: int
    total_challans: int
    total_challan_amount: int
    total_amount_collected: int
    net_revenue: int
    plates: List[str]


# --- Uploaded CCTV Video Schemas ---
class UploadedVideoResponse(TRINETRASchema):
    camera_id: str
    name: str
    location: Optional[str] = None
    video_file: str
    status: str
    # Processing job state (IDLE when never processed).
    job_status: str = "IDLE"
    progress_pct: float = 0.0
    frames_total: int = 0
    frames_processed: int = 0
    vehicles_seen: int = 0
    plates_read: int = 0
    job_error: Optional[str] = None
    note: Optional[str] = None
    last_processed_at: Optional[datetime] = None


class UploadedVideoDetailResponse(UploadedVideoResponse):
    recent_plates: List[VehicleEventResponse] = []


# --- System Health Schema ---
class HealthResponse(TRINETRASchema):
    status: str
    app_name: str
    version: str
    environment: str
    database_connected: bool
    active_cameras: int
    total_cameras: int
    demo_mode: bool
    timestamp: datetime
    components: Optional[Dict[str, Any]] = None
    vision: Optional[Dict[str, Any]] = None


# --- Camera stream ticket ----------------------------------------------------
# --- Vehicle profile (investigation header) ----------------------------------
# --- Dashboard KPIs ----------------------------------------------------------
class KpisResponse(TRINETRASchema):
    total_cameras: int
    cameras_online: int
    cameras_degraded: int
    cameras_offline: int
    active_alerts: int
    vehicle_detections_24h: int
    anpr_reads_24h: int
    watchlist_matches_24h: int


VehicleProfileResponse.model_rebuild()
