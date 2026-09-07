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
    YOLO_MODEL_PATH: str = "models/yolo11s.pt"
    PREFER_TRAINED_MODEL: bool = True
    CONFIDENCE_THRESHOLD: float = 0.45
    DETECTION_IOU: float = 0.50
    PROCESS_EVERY_N_FRAMES: int = 3
    OCR_ENABLED: bool = True
    OCR_MIN_CONFIDENCE: float = 0.60
    TRACK_BUFFER: int = 30
    # Real-time vehicle detection on the live view (green boxes). Model is
    # YOLO_MODEL_PATH, detections below CONFIDENCE_THRESHOLD are dropped.
    # Fine-tuned weights at models/trained/vehicles/best.pt are preferred when
    # PREFER_TRAINED_MODEL is true; the stock file is never overwritten.
    VEHICLE_DETECTION_ENABLED: bool = True
    DETECTION_IMGSZ: int = 640            # live view (speed). Uploaded videos use 960 when set.
    UPLOAD_DETECTION_IMGSZ: int = 960     # small/far vehicles in CCTV uploads
    DETECTION_EVERY_N_FRAMES: int = 2     # run the model every Nth live frame
    PLATE_MODEL_PATH: str = "models/trained/plates/best.pt"

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
    LIVE_CAMERA_STREAM_TYPE: str = ""   # rtsp | hls | webrtc | file
    LIVE_CAMERA_STREAM_URL: str = ""    # authorized stream URL
    LIVE_CAMERA_STATUS: str = ""        # optional initial registry status override
    LIVE_CAMERA_LATITUDE: float = 23.0225
    LIVE_CAMERA_LONGITUDE: float = 72.5714

    # Alert deduplication cooldown window (seconds)
    ALERT_DEDUP_COOLDOWN_SECONDS: int = 180

    # Sentinel CCTV catalogue sync URL
    SENTINEL_CATALOGUE_URL: str = "https://cctv.corp8.cloud/cameras.json"

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
