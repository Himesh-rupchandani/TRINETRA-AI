"""
Resolve vehicle / plate weight paths without overwriting the original model.

Search order (vehicle):
  1. Explicit configured path if it exists on disk
  2. models/trained/vehicles/best.pt   (fine-tuned, never the only copy)
  3. models/original/yolo11s.pt        (backup of the stock COCO weights)
  4. models/yolo11s.pt
  5. the bare name (lets Ultralytics auto-download as a last resort)
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

CV_ROOT = Path(__file__).resolve().parents[1]

ORIGINAL_VEHICLE = CV_ROOT / "models" / "original" / "yolo11s.pt"
TRAINED_VEHICLE = CV_ROOT / "models" / "trained" / "vehicles" / "best.pt"
TRAINED_PLATE = CV_ROOT / "models" / "trained" / "plates" / "best.pt"
STOCK_VEHICLE = CV_ROOT / "models" / "yolo11s.pt"


def _is_file(path: Path | str) -> bool:
    try:
        return Path(path).is_file() and Path(path).stat().st_size > 1024
    except OSError:
        return False


def resolve_vehicle_model_path(
    configured: str = "yolo11s.pt",
    prefer_trained: bool = True,
    search_roots: Optional[list] = None,
) -> str:
    configured = (configured or "yolo11s.pt").strip()
    if _is_file(configured):
        return str(Path(configured).resolve())

    roots = [Path(r) for r in (search_roots or [CV_ROOT])]
    rel_candidates = []
    if configured:
        rel_candidates.append(configured)
    if prefer_trained:
        rel_candidates.append("models/trained/vehicles/best.pt")
    rel_candidates.extend(
        [
            "models/original/yolo11s.pt",
            "models/yolo11s.pt",
        ]
    )
    seen = set()
    for root in roots:
        for rel in rel_candidates:
            p = Path(rel) if os.path.isabs(rel) else (root / rel)
            key = str(p)
            if key in seen:
                continue
            seen.add(key)
            if _is_file(p):
                return str(p.resolve())
    return os.path.basename(configured) or "yolo11s.pt"


def resolve_plate_model_path(
    configured: str = "",
    search_roots: Optional[list] = None,
) -> Optional[str]:
    """Return a plate-detector weight path, or None if none is installed."""
    configured = (configured or "").strip()
    if configured and _is_file(configured):
        return str(Path(configured).resolve())
    roots = [Path(r) for r in (search_roots or [CV_ROOT])]
    rels = []
    if configured:
        rels.append(configured)
    rels.extend(
        [
            "models/trained/plates/best.pt",
            "models/original/plate_yolo11n.pt",
            "models/plate_yolo11n.pt",
        ]
    )
    for root in roots:
        for rel in rels:
            p = Path(rel) if os.path.isabs(rel) else (root / rel)
            if _is_file(p):
                return str(p.resolve())
    return None


def backup_original(src: Path, dest: Path = ORIGINAL_VEHICLE) -> Optional[Path]:
    """Copy stock weights to models/original/ once. Never overwrites a backup."""
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.is_file():
        return dest
    src = Path(src)
    if not src.is_file():
        return None
    import shutil

    shutil.copy2(src, dest)
    return dest
