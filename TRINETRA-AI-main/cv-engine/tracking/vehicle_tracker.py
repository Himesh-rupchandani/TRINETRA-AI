"""Compatibility import for the shared in-repository motion tracker.

The canonical implementation now lives in the backend package so API-only and
backend Docker distributions include it. The standalone cv-engine still uses
the same code, without importing FastAPI, database settings or application state.
"""
import importlib.util
from pathlib import Path
import sys

_name = "trinetra_motion_tracker_core"
_path = Path(__file__).resolve().parents[2] / "TRINETRAAI/backend/app/services/motion_tracker_core.py"
if _name not in sys.modules:
    _spec = importlib.util.spec_from_file_location(_name, _path)
    _module = importlib.util.module_from_spec(_spec)
    sys.modules[_name] = _module
    try:
        _spec.loader.exec_module(_module)
    except Exception:
        sys.modules.pop(_name, None)
        raise
_core = sys.modules[_name]
VehicleTracker = _core.VehicleTracker
Track = _core.Track
iou_matrix = _core.iou_matrix


def __getattr__(name):
    return getattr(_core, name)
