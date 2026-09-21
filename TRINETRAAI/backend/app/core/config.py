import os
import tempfile
from pathlib import Path
from typing import List, Union, Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# app/core/config.py -> parents[2] == TRINETRAAI/backend. Mirrors the anchor
# rule in app/core/paths.py; repeated here because that module imports this one
# (and this check runs while `settings` is still being constructed).
_BACKEND_ROOT = Path(__file__).resolve().parents[2]

# Serverless platform markers — any one present means the filesystem is
# ephemeral even when the code tree is technically writable (Vercel's cwd IS
# writable, so the read-only probe alone would report PERSISTENT).
_SERVERLESS_ENV_VARS = (
    "VERCEL",
    "VERCEL_ENV",
    "VERCEL_REGION",
    "AWS_LAMBDA_FUNCTION_NAME",
    "FUNCTION_TARGET",
    "K_SERVICE",
)


def is_serverless_environment() -> bool:
    """True when running inside a serverless function (Vercel / Cloud Run / Lambda)."""
    return any(os.environ.get(k) for k in _SERVERLESS_ENV_VARS)


def _writable(dirpath: Path) -> bool:
    """True when `dirpath` exists (or can be created) and accepts writes."""
    probe = None
    try:
        dirpath.mkdir(parents=True, exist_ok=True)
        probe = dirpath / ".trinetra-write-probe"
        probe.write_text("ok", encoding="utf-8")
        return True
    except Exception:
        return False
    finally:
        if probe is not None:
            try:
                probe.unlink()
            except Exception:
                pass


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
    CONFIDENCE_THRESHOLD: float = 0.45
    PROCESS_EVERY_N_FRAMES: int = 3
    # Bound native inference thread pools too, leaving CPU for video decoding.
    CV_CPU_THREADS: int = Field(2, ge=1, le=16)
    CV_MEMORY_GUARD_ENABLED: bool = True
    # Admission policy for this combined Torch + detector + OCR stack, not a
    # universal model requirement or throughput guarantee.
    CV_MIN_MEMORY_MB: int = Field(1024, ge=0, le=65536)
    CV_MEMORY_RESERVE_MB: int = Field(160, ge=32, le=4096)
    OCR_ENABLED: bool = True
    OCR_MIN_CONFIDENCE: float = 0.60
    # Above this the plate is trusted (HIGH); between OCR_MIN_CONFIDENCE and
    # this mark it is kept but labelled LOW_CONFIDENCE — never silently upgraded.
    OCR_LOW_CONFIDENCE_MARK: float = 0.80
    # Agreeing multi-frame reads before a track's plate can be called HIGH.
    ANPR_MIN_AGREE_READS: int = 2
    TRACK_BUFFER: int = 30
    # Real-time vehicle detection on the live view (green boxes). Model is
    # YOLO_MODEL_PATH, detections below CONFIDENCE_THRESHOLD are dropped.
    VEHICLE_DETECTION_ENABLED: bool = True
    DETECTION_IMGSZ: int = 640            # inference resolution (speed vs accuracy)
    DETECTION_EVERY_N_FRAMES: int = 2     # run the model every Nth live frame
    # NMS IoU used by the detector. Ultralytics' default is 0.7; 0.55 separates
    # overlapping vehicles in dense traffic without dropping real boxes.
    DETECTION_IOU: float = 0.55
    # When AI detection is ON, each detected vehicle is COVERED with a
    # semi-transparent green box fill (OpenCV), not just a thin outline —
    # matching the reference look where the whole vehicle reads as green.
    # 0.0 = outline only (old look); 1.0 = solid green.
    DETECTION_BOX_FILL_ALPHA: float = 0.55

    # Live ANPR is independent of playback: one latest-frame mailbox per camera,
    # a bounded worker pool, and a configurable number of vehicles OCR'd in a
    # sampled frame. Ten covers busy scenes while remaining bounded for smooth
    # playback; increase only when the host has sufficient memory.
    LIVE_ANPR_ENABLED: bool = True
    # Optional unattended/resident OCR is separate from a viewer opting in.
    # Default OFF: merely starting a decoder must not load the ML models.
    LIVE_ANPR_RESIDENT_ENABLED: bool = False
    LIVE_ANPR_MAX_VEHICLES: int = Field(10, ge=1, le=32)
    LIVE_ANPR_TRACKER: Literal["motion", "iou"] = "motion"
    LIVE_ANPR_MAX_TRACKED_VEHICLES: int = Field(32, ge=3, le=128)
    LIVE_ANPR_SAMPLE_SECONDS: float = Field(1.0, ge=0.25, le=30)
    LIVE_ANPR_WORKERS: int = Field(1, ge=1, le=4)
    LIVE_ANPR_MAX_CAMERAS: int = Field(32, ge=1, le=128)
    LIVE_ANPR_DEDUP_SECONDS: int = Field(60, ge=1, le=3600)
    LIVE_ANPR_OVERLAY_TTL_SECONDS: float = Field(3.0, ge=0.5, le=10)
    LIVE_ANPR_IDLE_SECONDS: int = Field(60, ge=10, le=600)

    # ---- Number-plate detection (new pipeline stage) ----
    # A fine-tuned plate detector produced by training/train_plate_detector.py.
    # When the file is absent the pipeline falls back to a classical OpenCV
    # plate proposer, so ANPR works out of the box either way.
    PLATE_MODEL_PATH: str = "models/plate_detector.pt"
    PLATE_DETECTION_IMGSZ: int = 320
    PLATE_CONF_THRESHOLD: float = 0.25

    # ---- Multi-video analysis ----
    ANALYSIS_DIR: str = "uploads/analysis"      # downloaded / uploaded analysis videos
    ANALYSIS_EVERY_N_FRAMES: int = 5            # frame sampling for offline analysis
    ANALYSIS_MAX_WORKERS: int = 2               # videos analysed in parallel
    ANALYSIS_OCR_COOLDOWN_STEPS: int = 3        # detection steps between OCR attempts per track
    ANALYSIS_MIN_TRACK_HITS: int = 2            # ignore single-frame detector flicker
    ANALYSIS_MIN_VEHICLE_AREA: int = 1200       # px^2; smaller boxes are not OCR-able
    # Cross-video fuzzy matching: only plates of equal length differing by at
    # most this many *visually confusable* characters may be flagged as a
    # possible match (never merged automatically).
    MATCH_FUZZY_MAX_DISTANCE: int = 1
    MATCH_MIN_CONFIDENCE: float = 0.60          # below this a read never joins a match group

    # Demo Mode
    DEMO_MODE: bool = True
    # Synthetic scheduled alerts require a separate, explicit opt-in. Never
    # generate invented sightings merely because real cameras are unavailable.
    DEMO_ALERTS_ENABLED: bool = False
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

    # Shared secret for POST /api/internal/* (Sentinel catalogue sync etc.).
    # Empty means "not configured". There is deliberately NO default token in
    # the source: a value committed to a public repository is public. In
    # development/demo mode internal endpoints stay open for local tooling; in
    # production an unconfigured key disables them (see app/api/internal.py).
    INTERNAL_API_KEY: str = ""

    # Sentinel CCTV catalogue sync URL
    SENTINEL_CATALOGUE_URL: str = "https://cctv.corp8.cloud/cameras.json"

    # Sentinel credentials & stream hosts.
    # Credentials are NEVER hardcoded here: they are read from the environment
    # or the untracked backend `.env` (copy `.env.example` and fill it in).
    # Empty means "gateway credentials not configured" — the camera layer says
    # so explicitly instead of attempting an auth it cannot win.
    SENTINEL_EMAIL: str = ""
    SENTINEL_PASSWORD: str = ""
    SENTINEL_HLS_BASE_URL: str = "https://cctv.corp8.cloud"
    SENTINEL_RTSP_HOST: str = "103.250.160.189"
    SENTINEL_RTSP_PORT: int = 8554
    # Same-origin /sentinel media proxy (browser playback on deployed origins).
    # The proxy forwards /sentinel/* to these origins with the Basic auth above
    # and never returns them to the client. Default mirrors the dev proxy in
    # trinetra-ai/vite.config.ts: WHEP signalling on the gateway's WebRTC port,
    # HLS on the same host's HTTP port.
    SENTINEL_WHEP_ORIGIN: str = "http://103.250.160.189:8889"
    SENTINEL_HLS_ORIGIN: str = ""   # empty -> http://<WHEP host>

    # CORS
    CORS_ORIGINS: Union[List[str], str] = ["*"]

    # File uploads
    MAX_UPLOAD_SIZE_MB: int = 250
    UPLOAD_DIR: str = "uploads"

    # ---- Serverless / read-only-filesystem behaviour -----------------------
    # When the code directory cannot be written to (Vercel/Cloud Run mount the
    # function bundle read-only), every writable path is relocated under
    # RUNTIME_FALLBACK_DIR automatically. Empty means "nothing was relocated".
    RUNTIME_DATA_ROOT: str = ""
    RUNTIME_FALLBACK_DIR: str = ""   # empty -> <tempdir>/trinetra
    # Seed the 30-camera demo grid + GJ01AB1234 journey when the database is
    # born empty. Explicit opt-in for persistent hosts; on an ephemeral
    # serverless filesystem (see RUNTIME_DATA_ROOT below) it happens
    # automatically, because a database that starts blank and dies with the
    # instance can only ever be demo data — nothing of the operator's is at
    # risk. A populated registry is never rewritten.
    AUTO_SEED_DEMO: bool = False
    # Camera directory only: no example events, alerts or watchlist entries.
    # The Render image enables this for the existing 30-camera Sentinel grid.
    AUTO_REGISTER_SENTINEL_GRID: bool = False

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

    @model_validator(mode="after")
    def _relocate_unwritable_storage(self) -> "Settings":
        """Move every writable path under a temp root when the code tree is read-only.

        Serverless platforms (Vercel, Cloud Run, AWS Lambda) mount the deployed
        bundle read-only: only their temp directory accepts writes. Without this
        the first SQLite write of the boot sequence raises `attempt to write a
        readonly database`, which looks exactly like a broken API. So each
        configured storage location is probed once, and on failure all of them
        are relocated together — the read side (`/api/evidence/...`) and the
        write side (pipelines) then still agree, because they re-read these
        values through `app.core.paths`.
        """
        def sqlite_file(url: str) -> Path | None:
            if not url.startswith("sqlite"):
                return None
            raw = url.split("///", 1)[1] if "///" in url else ""
            if not raw:
                return None
            p = Path(raw).expanduser()
            # SQLAlchemy resolves a relative SQLite path against the CWD.
            return p if p.is_absolute() else (Path.cwd() / p)

        candidates = [sqlite_file(self.DATABASE_URL)]
        for raw in (self.EVIDENCE_ROOT, self.UPLOAD_DIR, self.ANALYSIS_DIR):
            p = Path(str(raw)).expanduser()
            candidates.append(p if p.is_absolute() else (_BACKEND_ROOT / p))

        if all(c is None or _writable(c.parent) for c in candidates):
            return self

        raw_root = (self.RUNTIME_FALLBACK_DIR or os.environ.get("TRINETRA_DATA_DIR") or "").strip()
        root = Path(raw_root).expanduser() if raw_root else Path(tempfile.gettempdir()) / "trinetra"
        if not _writable(root):
            # The configured/explicit fallback is not usable either — take the
            # one location serverless platforms guarantee is writable.
            root = Path(tempfile.gettempdir()) / "trinetra"
        try:
            root.mkdir(parents=True, exist_ok=True)
        except Exception:
            # Nowhere writable at all: leave the config untouched and let the
            # failure surface at its real source instead of hiding it here.
            return self

        root = root.resolve()
        if self.DATABASE_URL.startswith("sqlite"):
            name = Path(sqlite_file(self.DATABASE_URL) or "trinetra.db").name
            self.DATABASE_URL = f"sqlite:///{root / name}"
        self.EVIDENCE_ROOT = str(root / "evidence")
        self.UPLOAD_DIR = str(root / "uploads")
        self.ANALYSIS_DIR = str(root / "uploads" / "analysis")
        self.RUNTIME_DATA_ROOT = str(root)
        return self

    @property
    def ephemeral_storage(self) -> bool:
        """True when storage was relocated to a temp dir or we are on a serverless host."""
        return bool(self.RUNTIME_DATA_ROOT or is_serverless_environment())

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=True,
    )


settings = Settings()
