"""
Internal API Endpoints
======================
Handles backend operations, subsystem sync, and administrative maintenance.
Includes:
- POST /api/internal/sentinel/catalogue/sync
"""
import logging
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Header, Query, Body, status
from sqlalchemy.orm import Session
from pydantic import BaseModel

from ..core.config import settings
from ..database.database import get_db
from ..services.sentinel_catalogue_service import sync_sentinel_catalogue

logger = logging.getLogger("trinetra")

router = APIRouter(prefix="/internal", tags=["Internal"])


class SentinelSyncRequest(BaseModel):
    catalogue_url: Optional[str] = None
    cameras: Optional[List[Dict[str, Any]]] = None


def verify_internal_auth(
    x_internal_token: Optional[str] = Header(None),
    auth_token: Optional[str] = Query(None),
):
    """
    Validates internal authentication token.
    Allows demo/dev mode bypass when in local development.
    """
    # No default token here on purpose: a secret committed to a public repo is
    # public, and this endpoint can rewrite the whole camera registry.
    configured_token = (getattr(settings, "INTERNAL_API_KEY", "") or "").strip()
    provided_token = x_internal_token or auth_token

    # In development/demo mode without configured restriction, allow internal requests
    if settings.APP_ENV in ("development", "test") or settings.DEMO_MODE:
        return True

    if not configured_token:
        logger.warning(
            "[INTERNAL AUTH] INTERNAL_API_KEY is not configured — internal sync is "
            "disabled in production rather than falling back to a committed default."
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Internal endpoints disabled: set INTERNAL_API_KEY to authorize syncs.",
        )

    if not provided_token or provided_token != configured_token:
        logger.warning("[INTERNAL AUTH] Unauthorized internal sync attempt.")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized: Valid internal authorization token required.",
        )
    return True


@router.post(
    "/sentinel/catalogue/sync",
    summary="Synchronize Sentinel Camera Catalogue",
    description="Fetches and synchronizes cameras from the Sentinel catalogue (https://cctv.corp8.cloud/cameras.json).",
)
def sync_catalogue(
    payload: Optional[SentinelSyncRequest] = Body(default=None),
    authorized: bool = Depends(verify_internal_auth),
    db: Session = Depends(get_db),
):
    """Triggers camera catalogue ingestion and normalization from Sentinel."""
    catalogue_url = payload.catalogue_url if payload else None
    raw_payload = payload.cameras if payload else None

    result = sync_sentinel_catalogue(db, catalogue_url=catalogue_url, raw_payload=raw_payload)
    return result
