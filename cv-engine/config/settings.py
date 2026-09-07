"""
cv-engine configuration.

Every knob is environment-driven (spec §33). Nothing is hard-coded to a
particular camera set; camera identity always comes from the Sentinel
catalogue unless explicitly overridden on the CLI for single-camera testing.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Optional


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _env_int(name: str, default: int) -> int:
    return int(_env_float(name, float(default)))


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_str(name: str, default: str) -> str:
    raw = os.environ.get(name)
    return default if raw is None or raw == "" else raw


@dataclass
class Settings:
    # --- Sentinel catalogue ---------------------------------------------
    sentinel_catalogue_url: str = "https://cctv.corp8.cloud/cameras.json"
    catalogue_timeout_sec: float = 10.0
    # Credentials come from the environment ONLY (never hard-coded, never
    # logged). The '@' in the email is percent-encoded (%40) in URLs.
    sentinel_email: str = ""
    sentinel_password: str = ""
    sentinel_hls_base_url: str = "https://cctv.corp8.cloud"
    sentinel_rtsp_host: str = "103.250.160.189"
    sentinel_rtsp_port: int = 8554

    # --- Backend integration --------------------------------------------
    backend_base_url: str = "http://localhost:8000"
    backend_timeout_sec: float = 5.0
    backend_max_retries: int = 3
    backend_queue_size: int = 1000

    # --- Models / detection ----------------------------------------------
    # Default name is the stock COCO YOLO11s. At load time the detector
    # prefers models/trained/vehicles/best.pt when present so a fine-tune
    # is picked up without rewriting callers. The original file is never
    # overwritten (see detection/model_paths.py).
    model_path: str = "yolo11s.pt"
    prefer_trained_model: bool = True
    conf_threshold: float = 0.35
    iou_threshold: float = 0.50     # NMS; 0.50 keeps overlapping vehicles in dense Gujarat traffic
    inference_imgsz: int = 640      # live CPU default; uploaded / ANPR jobs should use 960
    device: str = "cpu"  # "cpu" | "cuda" | "0" ...
    plate_model_path: str = ""      # empty -> models/trained/plates/best.pt if it exists

    # --- Capture / pacing -------------------------------------------------
    frame_skip: int = 1            # process every Nth frame (1 = every frame)
    process_interval_ms: float = 0.0  # min PTS delta between inference runs (0=off)
    rtsp_transport: str = "tcp"
    allow_hls_fallback: bool = True

    # --- Reconnect backoff -------------------------------------------------
    reconnect_min_sec: float = 2.0
    reconnect_max_sec: float = 30.0
    reconnect_backoff_factor: float = 2.0
    reconnect_max_attempts: int = 0  # 0 = retry forever (never tight-loop: backoff applies)

    # --- Tracking ----------------------------------------------------------
    track_max_age_sec: float = 1.5      # keep lost tracks this long (PTS-based)
    track_min_hits: int = 2             # detections before a track is confirmed
    track_iou_threshold: float = 0.25

    # --- ANPR ----------------------------------------------------------------
    anpr_enabled: bool = True
    anpr_conf_threshold: float = 0.60   # below this: reject the reading entirely
    anpr_low_conf_mark: float = 0.80    # below this: keep event but flag low confidence
    anpr_max_reads_per_frame: int = 1   # OCR crop budget per processed frame
    anpr_min_agree_reads: int = 2       # agreeing reads before a stable candidate
    anpr_interval_ms: float = 500.0     # min PTS gap between OCR attempts

    # --- Events / dedup -------------------------------------------------------
    event_suppression_sec: float = 30.0   # same camera+track+plate window
    event_max_track_hold_sec: float = 20.0  # emit long-lived tracks periodically
    event_on_track_loss_sec: float = 1.5    # emit when track silent this long

    # --- Evidence ---------------------------------------------------------
    evidence_dir: str = "evidence_out"   # NOT "evidence/" — that is the source package
    evidence_jpeg_quality: int = 90
    evidence_max_files: int = 4000   # retention cap for the evidence dir (0 = off)
    evidence_store_full_frame: bool = True
    evidence_store_plate_crop: bool = True

    # --- Scene discontinuity (content-based hard cut) -----------------------
    scene_cut_check: bool = True
    scene_cut_diff_threshold: float = 42.0  # mean abs diff on 64x36 grayscale

    # --- Demo / logging -----------------------------------------------------
    demo_mode: bool = False
    log_level: str = "INFO"

    @classmethod
    def from_env(cls) -> "Settings":
        """Build Settings from environment variables (spec §33 names)."""
        return cls(
            sentinel_catalogue_url=_env_str(
                "SENTINEL_CATALOGUE_URL", cls.sentinel_catalogue_url
            ),
            sentinel_email=_env_str("SENTINEL_EMAIL", ""),
            sentinel_password=_env_str("SENTINEL_PASSWORD", ""),
            sentinel_hls_base_url=_env_str("SENTINEL_HLS_BASE_URL", cls.sentinel_hls_base_url),
            sentinel_rtsp_host=_env_str("SENTINEL_RTSP_HOST", cls.sentinel_rtsp_host),
            sentinel_rtsp_port=_env_int("SENTINEL_RTSP_PORT", cls.sentinel_rtsp_port),
            catalogue_timeout_sec=_env_float("CATALOGUE_TIMEOUT", 10.0),
            backend_base_url=_env_str("BACKEND_BASE_URL", "http://localhost:8000"),
            backend_timeout_sec=_env_float("BACKEND_TIMEOUT", 5.0),
            backend_max_retries=_env_int("BACKEND_MAX_RETRIES", 3),
            backend_queue_size=_env_int("BACKEND_QUEUE_SIZE", 1000),
            model_path=_env_str("MODEL_PATH", "yolo11s.pt"),
            prefer_trained_model=_env_bool("PREFER_TRAINED_MODEL", True),
            conf_threshold=_env_float("CONF_THRESHOLD", 0.35),
            iou_threshold=_env_float("IOU_THRESHOLD", 0.50),
            inference_imgsz=_env_int("INFERENCE_IMGSZ", 640),
            device=_env_str("CV_DEVICE", "cpu"),
            plate_model_path=_env_str("PLATE_MODEL_PATH", ""),
            frame_skip=_env_int("FRAME_SKIP", 1),
            process_interval_ms=_env_float("PROCESS_INTERVAL_MS", 0.0),
            rtsp_transport=_env_str("RTSP_TRANSPORT", "tcp"),
            allow_hls_fallback=_env_bool("ALLOW_HLS_FALLBACK", True),
            reconnect_min_sec=_env_float("RECONNECT_MIN", 2.0),
            reconnect_max_sec=_env_float("RECONNECT_MAX", 30.0),
            reconnect_backoff_factor=_env_float("RECONNECT_FACTOR", 2.0),
            reconnect_max_attempts=_env_int("RECONNECT_MAX_ATTEMPTS", 0),
            track_max_age_sec=_env_float("TRACK_MAX_AGE_SEC", 1.5),
            track_min_hits=_env_int("TRACK_MIN_HITS", 2),
            track_iou_threshold=_env_float("TRACK_IOU_THRESHOLD", 0.25),
            anpr_enabled=_env_bool("ANPR_ENABLED", True),
            anpr_conf_threshold=_env_float("ANPR_CONF_THRESHOLD", 0.60),
            anpr_low_conf_mark=_env_float("ANPR_LOW_CONF_MARK", 0.80),
            anpr_max_reads_per_frame=_env_int("ANPR_MAX_READS_PER_FRAME", 1),
            anpr_min_agree_reads=_env_int("ANPR_MIN_AGREE_READS", 2),
            anpr_interval_ms=_env_float("ANPR_INTERVAL_MS", 500.0),
            event_suppression_sec=_env_float("EVENT_SUPPRESSION_SEC", 30.0),
            event_max_track_hold_sec=_env_float("EVENT_MAX_TRACK_HOLD_SEC", 20.0),
            event_on_track_loss_sec=_env_float("EVENT_ON_TRACK_LOSS_SEC", 1.5),
            evidence_dir=_env_str("EVIDENCE_DIR", "evidence_out"),
            evidence_jpeg_quality=_env_int("EVIDENCE_JPEG_QUALITY", 90),
            evidence_max_files=_env_int("EVIDENCE_MAX_FILES", 4000),
            evidence_store_full_frame=_env_bool("EVIDENCE_FULL_FRAME", True),
            evidence_store_plate_crop=_env_bool("EVIDENCE_PLATE_CROP", True),
            scene_cut_check=_env_bool("SCENE_CUT_CHECK", True),
            scene_cut_diff_threshold=_env_float("SCENE_CUT_DIFF_THRESHOLD", 42.0),
            demo_mode=_env_bool("DEMO_MODE", False),
            log_level=_env_str("LOG_LEVEL", "INFO"),
        )


# Module-level convenience: lazily built so tests can patch env first.
_settings: Optional[Settings] = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings.from_env()
    return _settings


def reset_settings_cache() -> None:
    global _settings
    _settings = None
