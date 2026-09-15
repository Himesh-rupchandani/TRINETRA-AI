"""Optional vision stack — the single authority for "can this process see pixels?".

Why this module exists
----------------------
``app.camera.manager`` and the CV services used to do a hard ``import cv2`` /
``import numpy as np`` at module scope. That is fine on a workstation or in the
Docker image, but it means the *whole* API cannot even be imported without the
OpenCV/NumPy stack — and the stack is exactly what a serverless deployment
cannot carry: ``ultralytics`` pulls in ``torch``, which blows past Vercel's
Python bundle limit (500 MB) and adds seconds to every cold start for features
a read-mostly control-room API never calls.

So the heavy imports are resolved *here*, once, and every consumer imports
``cv2``/``np`` from this module instead of from the packages directly:

    from ..core.vision import cv2, np          # module-scope, always importable
    from ..core.vision import require_vision    # route guard, 503 when absent

When the real packages are installed, ``cv2``/``np`` are the real modules and
behaviour is bit-for-bit what it was before. When they are absent, the names
resolve to stubs whose *attribute access* raises :class:`VisionUnavailable`, so
a mistyped ``cv2.imread(...)`` on a vision-less box fails loudly at the call
site instead of silently producing black frames. Type annotations that merely
*name* a numpy type (``def f(frame: np.ndarray)``, a dataclass field) keep
working, because those resolve to ``object`` on the stub.

Nothing here decides policy — it only reports capability and fails honestly.
"""
from __future__ import annotations

import os
import sys
from types import ModuleType
from typing import Any, Dict

__all__ = [
    "cv2",
    "np",
    "CV2_AVAILABLE",
    "NUMPY_AVAILABLE",
    "vision_available",
    "vision_status",
    "require_vision",
    "VisionUnavailable",
]


class VisionUnavailable(RuntimeError):
    """Raised when a CV code path runs on a process without OpenCV/NumPy."""


_MISSING_REASON = (
    "OpenCV/NumPy are not installed in this process, so live frame decoding, "
    "vehicle detection and ANPR are unavailable here. Start the backend with "
    "`pip install -r requirements-ml.txt` (or run the Docker image, which "
    "already includes them) to enable the CV pipeline."
)

# Scalar/array *types* are referenced by annotations at import time, long before
# any pixel is touched. Answering those with ``object`` keeps module loading
# working without pretending numpy exists.
_STUB_TYPES: Dict[str, Any] = {
    "ndarray": object,
    "dtype": object,
    "generic": object,
    "number": object,
    "bool_": bool,
    "bool8": bool,
    "str_": str,
    "bytes_": bytes,
    "object_": object,
    "int8": int,
    "int16": int,
    "int32": int,
    "int64": int,
    "uint8": int,
    "uint16": int,
    "uint32": int,
    "uint64": int,
    "float16": float,
    "float32": float,
    "float64": float,
}


def _unavailable(name: str, pkg: str) -> Any:
    raise VisionUnavailable(f"{pkg}.{name}() called without {pkg} installed. {_MISSING_REASON}")


class _UnavailableModule(ModuleType):
    """Stand-in module: exists, but touching any member of it explains itself."""

    def __init__(self, name: str, type_map: Dict[str, Any] | None = None):
        super().__init__(name)
        self.__doc__ = f"Placeholder for the unavailable `{name}` package."
        self.__trinetra_missing__ = True
        self.__stub_doc__ = _MISSING_REASON
        self._type_map = type_map or {}

    def __getattr__(self, item: str) -> Any:
        if item.startswith("__") and item.endswith("__"):
            raise AttributeError(item)
        if item in self._type_map:
            return self._type_map[item]
        _unavailable(item, self.__name__)

    def __repr__(self) -> str:  # pragma: no cover - diagnostics only
        return f"<{self.__name__} unavailable: vision extras not installed>"


def vision_optional_env() -> bool:
    """Explicit opt-out knob so the serverless path can be tested locally.

    ``TRINETRA_API_ONLY=1`` makes an environment that *has* cv2/numpy behave
    exactly like a Vercel function that does not — which is how the API-only
    code path gets exercised on a developer machine.
    """
    return os.environ.get("TRINETRA_API_ONLY", "").strip().lower() in {"1", "true", "yes", "on"}


_FORCE_API_ONLY = vision_optional_env()

try:  # pragma: no cover - exercised implicitly by whichever branch applies
    if _FORCE_API_ONLY:
        raise ImportError("disabled by TRINETRA_API_ONLY")
    import numpy as np  # type: ignore[import-not-found]

    NUMPY_AVAILABLE = True
except Exception:  # ImportError, or a broken GUI/headless cv2 overlap
    np = _UnavailableModule("numpy", _STUB_TYPES)
    NUMPY_AVAILABLE = False

try:  # pragma: no cover
    if _FORCE_API_ONLY:
        raise ImportError("disabled by TRINETRA_API_ONLY")
    import cv2  # type: ignore[import-not-found]

    CV2_AVAILABLE = True
except Exception:
    cv2 = _UnavailableModule("cv2", {"VideoCapture": object, "Mat": object})
    CV2_AVAILABLE = False


def vision_available() -> bool:
    """True when both OpenCV and NumPy are importable in this process."""
    return bool(CV2_AVAILABLE and NUMPY_AVAILABLE)


def vision_status() -> Dict[str, Any]:
    """Machine-readable capability report (surfaced by ``/api/health``)."""
    return {
        "available": vision_available(),
        "cv2": CV2_AVAILABLE,
        "numpy": NUMPY_AVAILABLE,
        "reason": None if vision_available() else _MISSING_REASON,
    }


def require_vision() -> None:
    """FastAPI dependency: 503 with an actionable message on vision-less hosts.

    Used on the routes that *must* decode frames (camera start/stop, MJPEG
    live view, on-demand detection). Everything else in the API answers normally
    without the CV stack, which is what makes the serverless deployment useful.
    """
    if vision_available():
        return
    # Imported lazily so this module stays importable without FastAPI present.
    from fastapi import HTTPException

    raise HTTPException(
        status_code=503,
        detail={
            "error": "VISION_STACK_UNAVAILABLE",
            "message": _MISSING_REASON,
            "hint": (
                "Registry, events, watchlist, alerts, GIS routes, stats and "
                "reports keep working — only frame-level CV is disabled here."
            ),
        },
    )


def describe_environment() -> str:  # pragma: no cover - log helper
    if vision_available():
        return f"vision stack ready (cv2 {getattr(cv2, '__version__', '?')})"
    return "vision stack absent — API-only mode (no decode, no detection, no ANPR)"


def warn_once(logger) -> None:  # pragma: no cover - boot logging helper
    global _WARNED
    if _WARNED or vision_available():
        return
    _WARNED = True
    logger.warning(f"[TRINETRA] {describe_environment()} | python {sys.version.split()[0]}")


_WARNED = False
