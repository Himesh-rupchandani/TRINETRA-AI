"""Runtime configuration for the Trinetra CV engine.

Every value is read from the environment (or an optional ``.env`` file) so that
nothing environment-specific — and above all no secret — is baked into source.

Convention: the field ``conf_threshold`` is read from the environment variable
``CONF_THRESHOLD``. Only the *names* live here; the defaults are chosen for
hackathon hardware (one camera, CPU inference, conservative ANPR thresholds).
"""

from __future__ import annotations

import os
from dataclasses import MISSING, fields, is_dataclass
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

CV_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = CV_ROOT.parent

DEFAULT_CATALOGUE_URL = "https://cctv.corp8.cloud/cameras.json"


def load_dotenv(path: Path | str | None = None) -> None:
    """Populate ``os.environ`` from a simple ``KEY=VALUE`` file.

    Existing environment variables always win, so a real deployment is never
    silently overridden by a checked-in file. Four lines of parsing beat adding
    a python-dotenv dependency.
    """
    candidates = [Path(path)] if path else [CV_ROOT / ".env", REPO_ROOT / ".env"]
    for candidate in candidates:
        if not candidate.is_file():
            continue
        for raw in candidate.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            if not key or key.startswith("export "):
                key = key.replace("export ", "", 1).strip()
            os.environ.setdefault(key, value.strip().strip('"').strip("'"))
        break


def _cast(kind: str, raw: str, default: Any) -> Any:
    try:
        if kind == "bool":
            return raw.strip().lower() in {"1", "true", "yes", "on"}
        if kind == "int":
            return int(float(raw))
        if kind == "float":
            return float(raw)
        if kind == "list":
            return [item.strip() for item in raw.split(",") if item.strip()]
        return raw
    except (TypeError, ValueError):
        return default


@dataclass
class Settings:
    """All knobs the CV pipeline exposes."""

    # --- Sentinel feed -----------------------------------------------------
    sentinel_catalogue_url: str = DEFAULT_CATALOGUE_URL
    catalogue_timeout_s: float = 8.0
    catalogue_cache_ttl_s: float = 300.0
    #: Preferred transport for AI inference. Sentinel guidance: RTSP over TCP.
    preferred_transport: str = "rtsp"
    #: Fall back to HLS when RTSP cannot be opened.
    allow_hls_fallback: bool = True
    capture_backend: str = "auto"  # auto | opencv | pyav
    capture_open_timeout_s: float = 12.0
    read_timeout_s: float = 8.0

    # --- Reconnect ---------------------------------------------------------
    reconnect_min_s: float = 2.0
    reconnect_max_s: float = 30.0
    reconnect_multiplier: float = 2.0
    reconnect_jitter: float = 0.15
    #: Seconds of healthy frames after which backoff is considered recovered.
    stable_connection_s: float = 15.0

    # --- Detection ---------------------------------------------------------
    model_path: str = "yolo11n.pt"
    device: str = "auto"  # auto | cpu | cuda | cuda:0
    conf_threshold: float = 0.35
    iou_threshold: float = 0.5
    imgsz: int = 640
    frame_skip: int = 0  # run inference on 1 of every N+1 decoded frames
    inference_interval_s: float = 0.0  # min seconds between inferences
    max_detections: int = 40

    # --- Tracking ----------------------------------------------------------
    tracker_config: str = "bytetrack.yaml"
    track_max_age_s: float = 6.0
    #: Normalised mean-abs-difference above which a frame is a hard scene cut.
    scene_cut_threshold: float = 0.45

    # --- ANPR --------------------------------------------------------------
    ocr_engine: str = "auto"  # auto | easyocr | rapidocr | none
    ocr_languages: list[str] = field(default_factory=lambda: ["en"])
    ocr_gpu: bool = False
    anpr_conf_threshold: float = 0.30
    #: Below this the event is still emitted, but flagged low-confidence.
    anpr_low_confidence: float = 0.55
    anpr_min_plate_len: int = 8
    anpr_max_plate_len: int = 13
    #: OCR runs at most once per track every N seconds (CPU budget guard).
    anpr_interval_s: float = 1.0
    anpr_max_vehicles_per_frame: int = 3

    # --- Events ------------------------------------------------------------
    #: Same camera+track+plate inside this window collapses into one sighting.
    dedup_window_s: float = 45.0
    dedup_unplated_window_s: float = 20.0
    emit_unplated_events: bool = True

    # --- Backend -----------------------------------------------------------
    backend_base_url: str = "http://127.0.0.1:8000"
    events_path: str = "/api/events"
    backend_timeout_s: float = 5.0
    backend_max_retries: int = 3
    backend_retry_base_s: float = 1.0
    backend_retry_max_s: float = 8.0
    backend_queue_size: int = 1000
    #: Events that exhausted their retries land here — never silently dropped.
    dead_letter_path: str = str(CV_ROOT / "var" / "dead_letter_events.jsonl")

    # --- Evidence ----------------------------------------------------------
    evidence_dir: str = str(CV_ROOT / "var" / "evidence")
    evidence_jpeg_quality: int = 88
    evidence_min_confidence: float = 0.45
    evidence_keep_frames: bool = True

    # --- Runtime -----------------------------------------------------------
    log_level: str = "INFO"
    log_json: bool = False
    max_cameras: int = 1
    metrics_report_interval_s: float = 30.0

    # --- helpers -----------------------------------------------------------
    @property
    def events_url(self) -> str:
        base = self.backend_base_url.rstrip("/")
        path = self.events_path if self.events_path.startswith("/") else f"/{self.events_path}"
        return f"{base}{path}"

    def as_dict(self) -> dict:
        """Serialisable snapshot for the startup log line (no secrets by design)."""
        return {f.name: getattr(self, f.name) for f in fields(self)}


#: Aliases so the documented variable names work verbatim (brief section 33):
#: RECONNECT_MIN / RECONNECT_MAX rather than the internal *_S field names.
ENV_ALIASES = {
    "RECONNECT_MIN": "reconnect_min_s",
    "RECONNECT_MAX": "reconnect_max_s",
    "EVENTS_PATH": "events_path",
    "CATALOGUE_URL": "sentinel_catalogue_url",
    "ANPR_ENGINE": "ocr_engine",
    "OCR_ENGINE": "ocr_engine",
    "DEDUP_WINDOW": "dedup_window_s",
}


def _kind(f) -> str:
    t = f.type if isinstance(f.type, str) else getattr(f.type, "__name__", str(f.type))
    if t in ("bool",):
        return "bool"
    if t in ("int",):
        return "int"
    if t in ("float",):
        return "float"
    if t.startswith("list"):
        return "list"
    return "str"


def _dataclass_default(f) -> Any:
    if f.default is not MISSING:
        return f.default
    if f.default_factory is not MISSING:  # type: ignore[misc]
        return f.default_factory()  # type: ignore[misc]
    return None


def load_settings(env: dict[str, str] | None = None, **overrides: Any) -> Settings:
    """Build :class:`Settings` from ``env`` (defaults: ``os.environ``) + overrides.

    Values absent from the environment keep the dataclass default, so partial
    configuration is always valid.
    """
    load_dotenv()
    source = os.environ if env is None else env
    # Resolve aliases first so the canonical name always wins on a conflict.
    resolved: dict[str, str] = {}
    for env_name, field_name in ENV_ALIASES.items():
        if source.get(env_name):
            resolved[field_name] = env_name
    kwargs: dict[str, Any] = {}
    for f in fields(Settings):
        env_name = resolved.get(f.name, f.name.upper())
        if env_name not in source or source[env_name] == "":
            continue
        kwargs[f.name] = _cast(_kind(f), source[env_name], _dataclass_default(f))
    settings = Settings(**kwargs)
    for key, value in overrides.items():
        if not hasattr(settings, key):
            raise KeyError(f"unknown setting: {key}")
        setattr(settings, key, value)
    return settings


def describe_settings(settings: Settings) -> dict:
    """Settings snapshot safe to log (nothing here is a credential)."""
    return {f.name: getattr(settings, f.name) for f in fields(settings)}
