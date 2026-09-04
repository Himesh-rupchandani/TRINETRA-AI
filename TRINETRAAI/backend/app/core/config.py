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
    CONFIDENCE_THRESHOLD: float = 0.45
    PROCESS_EVERY_N_FRAMES: int = 3
    OCR_ENABLED: bool = True
    OCR_MIN_CONFIDENCE: float = 0.60
    TRACK_BUFFER: int = 30

    # Demo Mode
    DEMO_MODE: bool = True

    # Alert deduplication cooldown window (seconds)
    ALERT_DEDUP_COOLDOWN_SECONDS: int = 180

    # Sentinel CCTV catalogue sync URL
    SENTINEL_CATALOGUE_URL: str = "https://cctv.corp8.cloud/cameras.json"

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

    # Evidence store written by the CV engine and served (read-only) at
    # /api/evidence — the CV engine should point EVIDENCE_DIR here too.
    EVIDENCE_DIR: str = "uploads/evidence"

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
