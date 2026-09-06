import os
from typing import List, Union
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    PROJECT_NAME: str = "TRINETRA AI - Intelligent CCTV Surveillance"
    APP_ENV: str = "development"
    DEBUG: bool = True
    PORT: int = 8000
    HOST: str = "0.0.0.0"

    # Database
    DATABASE_URL: str = "sqlite:///./trinetra.db"

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # CCTV Default Streams
    DEFAULT_CAMERA_STREAM_URL: str = "https://cctv.corp8.cloud/cam04/index.m3u8"
    DEFAULT_CAMERA_STREAM_TYPE: str = "hls"
    RTSP_TRANSPORT: str = "tcp"

    # AI & Computer Vision Settings
    YOLO_MODEL_PATH: str = "models/yolo11n.pt"
    # The visual detector uses a lower-confidence association tier to retain
    # partially occluded vehicles, but only detections at this threshold may
    # start a track immediately. Lower candidates must be confirmed over time.
    CONFIDENCE_THRESHOLD: float = 0.35
    PROCESS_EVERY_N_FRAMES: int = 3
    OCR_ENABLED: bool = True
    OCR_MIN_CONFIDENCE: float = 0.60
    TRACK_BUFFER: int = 30

    # Real-time OpenCV + YOLO vehicle detection shown on /live/detect.
    # These settings are server-side only. A 960-pixel inference size gives
    # distant road vehicles more usable pixels than the previous 640 default;
    # deployers can lower it on CPU-only hardware or use a larger model/GPU.
    VEHICLE_DETECTION_ENABLED: bool = True
    DETECTION_IMGSZ: int = 960
    DETECTION_DEVICE: str = "cpu"         # cpu | 0 | cuda:0 (Ultralytics syntax)
    DETECTION_EVERY_N_FRAMES: int = 2      # tracker still advances on every frame
    DETECTION_LOW_CONFIDENCE: float = 0.20
    DETECTION_NMS_IOU_THRESHOLD: float = 0.70
    DETECTION_DUPLICATE_IOU_THRESHOLD: float = 0.82
    DETECTION_MAX_DETECTIONS: int = 300
    DETECTION_MIN_BOX_AREA: float = 9.0
    DETECTION_INCLUDE_BICYCLES: bool = True
    DETECTION_TRACK_MAX_AGE_SEC: float = 1.25
    DETECTION_TRACK_MIN_HITS: int = 1
    DETECTION_LOW_CONFIDENCE_CONFIRM_HITS: int = 2
    DETECTION_TRACK_IOU_THRESHOLD: float = 0.18
    DETECTION_TRACK_CENTER_DISTANCE: float = 1.35
    # Optional high-resolution tiled pass. Keep grid=1 for the default
    # real-time path; use grid=2 (preferably on a GPU) for dense, distant
    # traffic where maximum small-object recall matters more than throughput.
    DETECTION_TILE_GRID: int = 1
    DETECTION_TILE_OVERLAP: float = 0.20
    DETECTION_TILE_MIN_FRAME_EDGE: int = 1400
    DETECTION_TILE_EVERY_N_INFERENCES: int = 4
    DETECTION_SHOW_TRACK_IDS: bool = False

    # Demo Mode
    DEMO_MODE: bool = True
    # Start stream ingestion for every registered camera at boot? Off by
    # default: a control room opens the streams it is actually looking at
    # (POST /cameras/{id}/start). Set true to ingest the whole grid.
    AUTO_START_CAMERAS: bool = False
    # Root of the CV engine's evidence crops (served by /api/evidence/...).
    EVIDENCE_ROOT: str = "../../cv-engine/evidence"

    # ---- REAL live camera source (configure in TRINETRAAI/backend/.env) ----
    # When LIVE_CAMERA_STREAM_URL is set, the backend registers/updates a real
    # camera (default id CAMLIVE) in the registry at startup. Supported types:
    # rtsp | hls | webrtc | file. Leave STREAM_URL empty to keep the slot
    # visible as "NOT_CONFIGURED" ("Camera source not configured") — a
    # recorded video is never presented as a live source.
    LIVE_CAMERA_ID: str = "CAMLIVE"
    LIVE_CAMERA_NAME: str = "Ahmedabad Live Traffic Camera"
    LIVE_CAMERA_LOCATION: str = "Ahmedabad, Gujarat"
    LIVE_CAMERA_STREAM_TYPE: str = ""   # rtsp | hls | webrtc | whep | file
    # Keep the authorized source only in the server environment. It is
    # sanitized before the registry is written and never returned by an API.
    LIVE_CAMERA_STREAM_URL: str = ""
    # Optional paired, server-only decoder source. Set this for a WHEP/WebRTC
    # viewing feed because OpenCV/FFmpeg cannot negotiate WHEP directly.
    LIVE_CAMERA_INGEST_URL: str = ""
    LIVE_CAMERA_INGEST_TYPE: str = ""    # rtsp | hls | file
    LIVE_CAMERA_STATUS: str = ""         # optional initial registry status override
    LIVE_CAMERA_LATITUDE: float = 23.0225
    LIVE_CAMERA_LONGITUDE: float = 72.5714

    # Alert deduplication cooldown window (seconds)
    ALERT_DEDUP_COOLDOWN_SECONDS: int = 180

    # Sentinel CCTV catalogue sync URL. In real mode the backend refreshes this
    # at startup only when a server-side approved account is configured.
    SENTINEL_CATALOGUE_URL: str = "https://cctv.corp8.cloud/cameras.json"
    SENTINEL_AUTO_SYNC: bool = True

    # Sentinel credentials & stream hosts (NEVER hard-code real values here;
    # set them in backend/.env — see .env.example. The @ in the registered
    # email is percent-encoded as %40 when URLs are built at connect time.)
    SENTINEL_EMAIL: str = ""
    SENTINEL_PASSWORD: str = ""
    SENTINEL_HLS_BASE_URL: str = "https://cctv.corp8.cloud"
    SENTINEL_RTSP_HOST: str = "103.250.160.189"
    SENTINEL_RTSP_PORT: int = 8554

    # CORS
    CORS_ORIGINS: Union[List[str], str] = [
        "http://localhost:3000",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:3000",
    ]

    # File uploads
    MAX_UPLOAD_SIZE_MB: int = 250
    UPLOAD_DIR: str = "uploads"

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def assemble_cors_origins(cls, v: Union[str, List[str]]) -> List[str]:
        if isinstance(v, str) and not v.startswith("["):
            return [i.strip() for i in v.split(",")]
        elif isinstance(v, str) and v.startswith("["):
            import json
            try:
                return json.loads(v)
            except Exception:
                return ["*"]
        elif isinstance(v, list):
            return v
        return ["*"]

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=True,
    )


settings = Settings()
