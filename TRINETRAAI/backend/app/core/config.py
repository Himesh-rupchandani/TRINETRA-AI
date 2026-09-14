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
    # Threshold for the LIVE view. It used to be 0.45 while offline analysis ran
    # at 0.35, so the same vehicle was boxed in the recording but not in the
    # live stream; 0.35 is what the measured sweep on this repo's own footage
    # picked (0.45 loses roughly a quarter of the distant vehicles). Raise it to
    # 0.45+ if a false positive on a pedestrian matters more than a distant car.
    CONFIDENCE_THRESHOLD: float = 0.35
    PROCESS_EVERY_N_FRAMES: int = 3
    OCR_ENABLED: bool = True
    OCR_MIN_CONFIDENCE: float = 0.60
    # Above this the plate is trusted (HIGH); between OCR_MIN_CONFIDENCE and
    # this mark it is kept but labelled LOW_CONFIDENCE — never silently upgraded.
    OCR_LOW_CONFIDENCE_MARK: float = 0.80
    # Agreeing multi-frame reads before a track's plate can be called HIGH.
    ANPR_MIN_AGREE_READS: int = 2
    TRACK_BUFFER: int = 30
    # Real-time vehicle detection on the live view (green boxes). Model is
    # YOLO_MODEL_PATH; detections below CONFIDENCE_THRESHOLD are dropped. These
    # are the LIVE knobs - the offline video pass has its own ANALYSIS_* pair.
    VEHICLE_DETECTION_ENABLED: bool = True
    # Inference resolution for the live view, now the SAME 960 the offline pass
    # uses: 640 was what left distant cars undetected and small boxes coarse.
    # On a slow CPU the auto-pacing governor below walks this back down to
    # LIVE_IMGSZ_FLOOR instead of dropping frames, so the stream stays smooth.
    DETECTION_IMGSZ: int = 960
    # Run the model every Nth LIVE frame; the frames in between are drawn with
    # the last real detections so the overlay stays put at full stream rate.
    # 2 doubles the frame rate for ~200 ms of box lag on a fast-moving vehicle.
    # Set 1 to annotate every displayed frame (no lag, lower frame rate), 3+ if
    # the CPU is shared with the ingest workers.
    DETECTION_EVERY_N_FRAMES: int = 2
    # ---- live auto-pacing ---------------------------------------------------
    # Keep the live stream responsive without asking the operator to guess a
    # resolution: the detector times its own inferences and steps imgsz down the
    # 1280/960/768/640/512 ladder when the median run exceeds the budget, and
    # back up when it is comfortably under it. Only boxes get coarser, never
    # more boxes or bigger ones - geometry always stays the model's own.
    LIVE_ADAPTIVE_IMGSZ: bool = True
    LIVE_INFER_BUDGET_MS: float = 450.0   # per-inference time the stream may pay
    LIVE_IMGSZ_FLOOR: int = 640           # never go below this on the live view
    # Quality policy for the live view. "auto" lets the governor choose from the
    # ladder (single passes up to DETECTION_IMGSZ, then the same plus native
    # strips); "eco" never spends a second pass; "max" always looks twice. An
    # unrecognised value is logged once and treated as "auto", because a typo here
    # would otherwise change box quality in silence.
    LIVE_QUALITY: str = "auto"
    # How a frame is looked at a second time. Vertical strips at native
    # resolution: on 1280x720 footage this took live recall from 48% to 88% of
    # what the best multi-scale pass finds, at 3.2x the CPU of one 768 pass.
    DETECTION_STRIPS: int = 2             # 2 = left/right halves, overlapping
    DETECTION_TILE: int = 640             # square-grid tiles for very tall frames
    DETECTION_MAX_TILES: int = 6          # ceiling, so 4K cannot mean 40 passes
    # Duplicate suppression beyond IoU: a box almost INSIDE another one is the
    # same vehicle seen through a crop edge. The area guard is what stops that
    # rule from deleting a motorcycle legitimately hidden inside a bus's box.
    DETECTION_CONTAINMENT_THR: float = 0.60
    DETECTION_CONTAINMENT_AREA_GUARD: float = 3.0
    # Offline video analysis: quality is not traded for latency there, so it
    # always gets the second look. Set false to halve analysis CPU at ~25-40%
    # fewer vehicles.
    ANALYSIS_MULTISCALE: bool = True
    # ---- live overlay delivery -------------------------------------------------
    # Detect on a background worker per camera instead of inline in the MJPEG
    # loop. The stream then always renders at its own rate with the freshest real
    # boxes, and the detector is free to look as deep as the CPU allows: extra
    # work buys detection latency, never dropped frames. Measured on this box:
    # inline at 768 gave 4.7 fps / 11.8 vehicles; async multi-scale keeps the
    # stream smooth and roughly doubles the vehicles it can afford to find.
    LIVE_ASYNC_DETECT: bool = True
    # Boxes older than this are dropped instead of drawn. Without it a camera
    # whose detector stalled would keep a vehicle boxed in front of an empty
    # road; with it the worst case is a brief gap, never a wrong box.
    # This is a FLOOR, not a fixed window: it widens to two passes of the
    # detector's measured cadence (bounded by LIVE_STALENESS_CEILING_MS), because
    # on a weak CPU a deep pass costs about this much and a cap equal to the
    # refresh interval makes the overlay flicker - measured: 17.2% of a live
    # stream's frames drew no boxes at all with a fixed 900 ms cap at
    # LIVE_QUALITY=max, 0% with the window following cadence. 0 disables ageing.
    LIVE_BOX_MAX_AGE_MS: float = 900.0
    # Hard limit on that widening. Beyond it the boxes are wrong wherever they
    # are, so a detector slower than this loses its overlay instead of lying.
    LIVE_STALENESS_CEILING_MS: float = 2500.0

    # NMS IoU used by the detector. Ultralytics' default is 0.7, which let one
    # motorcycle be boxed two or three times over; 0.45 keeps the best box per
    # vehicle while still separating genuinely adjacent vehicles (their mutual
    # IoU is far below 0.45, so two neighbouring cars never merge into one box).
    DETECTION_IOU: float = 0.45
    # Class-agnostic NMS: one vehicle gets ONE box even when the model hedges
    # between labels (car vs bus vs truck for the same vehicle). Suppression is
    # still IoU-based, so separate vehicles are never merged by this.
    DETECTION_AGNOSTIC_NMS: bool = True
    # A very light tint inside the box (0.0 = pure outline). The previous 0.55
    # painted every vehicle solid green, which made even honest padding read as
    # "a huge green area over the road" — the exact complaint the tightening
    # below is meant to remove.
    DETECTION_BOX_FILL_ALPHA: float = 0.0
    # ---- Offline video analysis (uploads / Drive): quality over latency -----
    # A larger inference size is what separates parked vehicles that overlap in
    # the frame and finds the small distant ones. Measured on this repo's own
    # traffic stills with the same weight: a night traffic scene went from 0
    # vehicles at imgsz 640 to 27 at 960, mean box area 3.8% -> 2.2% of the
    # frame, duplicate boxes on one vehicle ~0. The live view now runs the same
    # values and protects its frame rate with LIVE_ADAPTIVE_IMGSZ instead.
    ANALYSIS_CONFIDENCE_THRESHOLD: float = 0.35
    ANALYSIS_DETECTION_IMGSZ: int = 960

    # ---- Number-plate detection (new pipeline stage) ----
    # A fine-tuned plate detector produced by training/train_plate_detector.py.
    # The tracked weight ships under models/license-plate-finetune-v1n.pt
    # (single "License_Plate" class). When the file is absent the pipeline
    # falls back to a classical OpenCV plate proposer, so ANPR works out of the
    # box either way.
    PLATE_MODEL_PATH: str = "models/license-plate-finetune-v1n.pt"
    PLATE_DETECTION_IMGSZ: int = 320
    PLATE_CONF_THRESHOLD: float = 0.25

    # ---- Multi-video analysis ----
    ANALYSIS_DIR: str = "uploads/analysis"      # downloaded / uploaded analysis videos
    ANALYSIS_EVERY_N_FRAMES: int = 5            # frame sampling for offline analysis
    ANALYSIS_MAX_WORKERS: int = 2               # videos analysed in parallel
    ANALYSIS_OCR_COOLDOWN_STEPS: int = 3        # detection steps between OCR attempts per track
    ANALYSIS_MIN_TRACK_HITS: int = 2            # ignore single-frame detector flicker
    ANALYSIS_MIN_VEHICLE_AREA: int = 1200       # px^2; smaller boxes are not OCR-able
    # Seconds allowed to re-encode a clip OpenCV cannot decode (.dav/.wmv/odd
    # profiles) into H.264 MP4 before the file is rejected with the reason.
    ANALYSIS_CONVERT_TIMEOUT_SEC: int = 1800
    # Cross-video fuzzy matching: only plates of equal length differing by at
    # most this many *visually confusable* characters may be flagged as a
    # possible match (never merged automatically).
    MATCH_FUZZY_MAX_DISTANCE: int = 1
    MATCH_MIN_CONFIDENCE: float = 0.60          # below this a read never joins a match group

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

    # CORS
    CORS_ORIGINS: Union[List[str], str] = [
        "http://localhost:3000",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:3000",
    ]

    # File uploads
    # CCTV/DVR clips are big; 250 MB silently refused common exports, which is
    # part of why batches arrived incomplete. Per-file, not per-request.
    MAX_UPLOAD_SIZE_MB: int = 1024
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
