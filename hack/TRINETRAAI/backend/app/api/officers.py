"""
Officers API — Officer Profile section.

GET /api/officers/me       — profile of the signed-in Senior Officer
GET /api/officers          — every officer available for selection
GET /api/officers/{officer_id} — one officer's own profile

Every figure is scoped to a single officer; figures for different officers
are never mixed.
"""
from typing import List

from fastapi import APIRouter, HTTPException, status

from ..database.schemas import OfficerResponse
from ..services import officer_service

router = APIRouter(prefix="/officers", tags=["Officers"])


@router.get("/me", response_model=OfficerResponse, summary="Current officer profile")
def get_current_officer():
    """Profile of the officer signed into the control room."""
    return officer_service.get_current_officer()


@router.get("", response_model=List[OfficerResponse], summary="List officers")
def list_officers():
    """Every officer available for selection in the Profile section."""
    return officer_service.list_officers()


@router.get("/{officer_id}", response_model=OfficerResponse, summary="Get officer profile")
def get_officer(officer_id: str):
    """One officer's own profile (their data only)."""
    officer = officer_service.get_officer(officer_id)
    if not officer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Officer '{officer_id}' not found.",
        )
    return officer
