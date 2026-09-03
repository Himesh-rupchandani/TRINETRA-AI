"""
Sentinel Catalogue Integration Service
======================================
Synchronizes CCTV camera metadata from the external Sentinel catalogue:
  Source: https://cctv.corp8.cloud/cameras.json

Key Responsibilities:
- Fetch and validate catalogue payload
- Normalize camera attributes into internal TRINETRA schema
- Upsert camera records in the database (avoiding duplicates)
- Register/update streams dynamically in CameraManager
- Gracefully handle network/DNS failures without taking down the service
- Strip credentials and sanitize metadata
"""
import logging
from typing import Dict, Any, List, Optional
import httpx
from sqlalchemy.orm import Session
from sqlalchemy import func

from ..core.config import settings
from ..database.models import Camera
from ..camera.manager import camera_manager

logger = logging.getLogger("trinetra")


def _sanitize_url(url: str) -> str:
    """Strips credentials or passwords from URLs if present."""
    if not url:
        return ""
    # Example: rtsp://user:pass@host:port/path -> rtsp://host:port/path
    if "@" in url and "://" in url:
        scheme, rest = url.split("://", 1)
        _, host_path = rest.split("@", 1)
        return f"{scheme}://{host_path}"
    return url


def normalize_sentinel_camera(raw: Dict[str, Any]) -> Dict[str, Any]:
    """
    Normalizes arbitrary Sentinel camera JSON entries into the standard schema.
    Supports varied keys: id/camera_id, lat/latitude, lon/lng/longitude, etc.
    """
    # 1. Normalize ID
    cam_id = str(raw.get("camera_id") or raw.get("id") or "").strip()
    if not cam_id:
        cam_id = f"CAM_{raw.get('name', 'UNKNOWN').replace(' ', '_')}"
    # Standardize to uppercase for consistency (e.g. cam04 -> CAM04)
    normalized_id = cam_id.upper()

    # 2. Coordinates
    lat = raw.get("latitude")
    if lat is None:
        lat = raw.get("lat")
    try:
        lat = float(lat) if lat is not None else 23.0225
    except (ValueError, TypeError):
        lat = 23.0225

    lon = raw.get("longitude")
    if lon is None:
        lon = raw.get("lon") or raw.get("lng")
    try:
        lon = float(lon) if lon is not None else 72.5714
    except (ValueError, TypeError):
        lon = 72.5714

    # 3. Stream info
    stream_url = str(raw.get("stream_url") or raw.get("url") or "").strip()
    if not stream_url:
        stream_url = f"https://cctv.corp8.cloud/{cam_id.lower()}/index.m3u8"
    stream_url = _sanitize_url(stream_url)

    stream_type = str(raw.get("stream_type") or ("hls" if ".m3u8" in stream_url else "rtsp")).lower()

    # 4. Location & Name
    name = str(raw.get("name") or f"Camera {normalized_id}").strip()
    location = str(raw.get("location") or raw.get("location_name") or raw.get("area") or name).strip()

    # 5. Technical specs
    codec = str(raw.get("codec") or "H264").upper()
    try:
        width = int(raw.get("width") or 1920)
    except (ValueError, TypeError):
        width = 1920
    try:
        height = int(raw.get("height") or 1080)
    except (ValueError, TypeError):
        height = 1080

    status = str(raw.get("status") or "ONLINE").upper()

    return {
        "camera_id": normalized_id,
        "name": name,
        "location": location,
        "stream_url": stream_url,
        "stream_type": stream_type,
        "latitude": lat,
        "longitude": lon,
        "status": status,
        "codec": codec,
        "width": width,
        "height": height,
    }


def sync_sentinel_catalogue(
    db: Session,
    catalogue_url: Optional[str] = None,
    raw_payload: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """
    Synchronizes the camera catalogue with Sentinel.
    If raw_payload is provided, uses it directly (useful for testing or cached feeds).
    Otherwise fetches from catalogue_url (or settings.SENTINEL_CATALOGUE_URL).
    
    Returns sync metrics and normalized cameras.
    """
    url = catalogue_url or settings.SENTINEL_CATALOGUE_URL
    camera_entries: List[Dict[str, Any]] = []
    fetch_success = False
    error_detail: Optional[str] = None

    if raw_payload is not None:
        camera_entries = raw_payload
        fetch_success = True
    else:
        try:
            logger.info(f"[SENTINEL SYNC] Fetching camera catalogue from {url}...")
            with httpx.Client(timeout=2.0, follow_redirects=True) as client:
                resp = client.get(url)
                if resp.status_code == 200:
                    data = resp.json()
                    if isinstance(data, list):
                        camera_entries = data
                    elif isinstance(data, dict):
                        camera_entries = data.get("cameras") or data.get("data") or [data]
                    fetch_success = True
                    logger.info(f"[SENTINEL SYNC] Successfully retrieved {len(camera_entries)} cameras from Sentinel.")
                else:
                    error_detail = f"Sentinel returned HTTP {resp.status_code}"
                    logger.warning(f"[SENTINEL SYNC] {error_detail}")
        except Exception as exc:
            error_detail = f"Catalogue fetch failed: {exc}"
            logger.warning(f"[SENTINEL SYNC] {error_detail}. Proceeding with existing camera registry.")

    # If fetch failed and we have no payload, fall back to existing database cameras
    if not fetch_success and not camera_entries:
        existing_cams = db.query(Camera).all()
        return {
            "status": "warning",
            "message": f"{error_detail} (using {len(existing_cams)} existing registry cameras)",
            "synced_count": 0,
            "total_cameras": len(existing_cams),
            "source_url": url,
            "cameras": [
                {
                    "id": c.camera_id.lower(),
                    "camera_id": c.camera_id,
                    "name": c.name,
                    "location": c.location or c.name,
                    "latitude": c.latitude,
                    "longitude": c.longitude,
                    "status": c.status,
                    "codec": c.codec or "H264",
                    "width": c.width or 1920,
                    "height": c.height or 1080,
                    "stream_type": c.stream_type.upper(),
                    "stream_url": c.stream_url,
                }
                for c in existing_cams
            ],
        }

    # Upsert normalized cameras
    upserted: List[Camera] = []
    for raw_cam in camera_entries:
        if not isinstance(raw_cam, dict):
            continue
        norm = normalize_sentinel_camera(raw_cam)
        cam_id = norm["camera_id"]

        # Case-insensitive query
        existing = db.query(Camera).filter(func.upper(Camera.camera_id) == cam_id.upper()).first()
        if existing:
            existing.name = norm["name"]
            existing.location = norm["location"]
            existing.stream_url = norm["stream_url"]
            existing.stream_type = norm["stream_type"]
            existing.latitude = norm["latitude"]
            existing.longitude = norm["longitude"]
            existing.codec = norm["codec"]
            existing.width = norm["width"]
            existing.height = norm["height"]
            if norm["status"]:
                existing.status = norm["status"]
            upserted.append(existing)
        else:
            new_cam = Camera(
                camera_id=cam_id,
                name=norm["name"],
                location=norm["location"],
                stream_url=norm["stream_url"],
                stream_type=norm["stream_type"],
                latitude=norm["latitude"],
                longitude=norm["longitude"],
                status=norm["status"],
                codec=norm["codec"],
                width=norm["width"],
                height=norm["height"],
            )
            db.add(new_cam)
            upserted.append(new_cam)

        # Update or register in CameraManager runtime
        try:
            camera_manager.add_camera(
                camera_id=cam_id,
                source=norm["stream_url"],
                source_type=norm["stream_type"],
                auto_start=False,
            )
        except Exception as cm_err:
            logger.debug(f"CameraManager registration for {cam_id}: {cm_err}")

    db.commit()
    for c in upserted:
        db.refresh(c)

    logger.info(f"[SENTINEL SYNC] Successfully upserted {len(upserted)} cameras in registry.")

    return {
        "status": "success",
        "message": f"Successfully synchronized {len(upserted)} cameras from Sentinel catalogue.",
        "synced_count": len(upserted),
        "total_cameras": db.query(Camera).count(),
        "source_url": url,
        "cameras": [
            {
                "id": c.camera_id.lower(),
                "camera_id": c.camera_id,
                "name": c.name,
                "location": c.location or c.name,
                "latitude": c.latitude,
                "longitude": c.longitude,
                "status": c.status,
                "codec": c.codec or "H264",
                "width": c.width or 1920,
                "height": c.height or 1080,
                "stream_type": c.stream_type.upper(),
                "stream_url": c.stream_url,
            }
            for c in upserted
        ],
    }
