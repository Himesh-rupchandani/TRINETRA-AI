import sys
from pathlib import Path
from typing import Optional

# Allow running this file directly as a script
if __name__ == "__main__" and not __package__:
    project_root = Path(__file__).resolve().parents[3]
    backend_root = Path(__file__).resolve().parents[2]
    for p in [str(project_root), str(backend_root)]:
        if str(p) not in sys.path:
            sys.path.insert(0, str(p))
    __package__ = "backend.app.api"

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session

from ..database.database import get_db
from ..database.models import Watchlist
from ..database.schemas import (
    WatchlistResponse,
    WatchlistCreate,
    WatchlistUpdate,
    PaginatedResponse,
)

router = APIRouter(prefix="/watchlist", tags=["Watchlist"])


@router.get("", response_model=PaginatedResponse[WatchlistResponse])
def list_watchlist(
    active_only: bool = Query(True, description="Filter only active watchlist entries"),
    category: Optional[str] = Query(None, description="Filter by category"),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """List watchlist license plates with optional category filtering."""
    query = db.query(Watchlist)
    if active_only:
        query = query.filter(Watchlist.active == True)
    if category:
        query = query.filter(Watchlist.category.ilike(f"%{category}%"))

    total = query.count()
    items = query.order_by(Watchlist.created_at.desc()).offset((page - 1) * size).limit(size).all()
    pages = (total + size - 1) // size if total > 0 else 1

    return PaginatedResponse[WatchlistResponse](
        items=items,
        total=total,
        page=page,
        size=size,
        pages=pages,
    )


@router.post("", response_model=WatchlistResponse, status_code=status.HTTP_201_CREATED)
def add_to_watchlist(payload: WatchlistCreate, db: Session = Depends(get_db)):
    """Add a vehicle license plate to the active surveillance watchlist."""
    plate_norm = payload.plate_number.strip().upper().replace(" ", "")
    existing = db.query(Watchlist).filter(Watchlist.plate_number == plate_norm).first()
    if existing:
        if not existing.active:
            existing.active = True
            existing.category = payload.category
            existing.description = payload.description
            db.commit()
            db.refresh(existing)
            return existing
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Plate '{plate_norm}' is already in the watchlist.",
        )

    entry = Watchlist(
        plate_number=plate_norm,
        category=payload.category,
        description=payload.description,
        active=payload.active,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


@router.put("/{plate_number}", response_model=WatchlistResponse)
def update_watchlist(plate_number: str, payload: WatchlistUpdate, db: Session = Depends(get_db)):
    """Update watchlist entry details or active status."""
    plate_norm = plate_number.strip().upper().replace(" ", "")
    entry = db.query(Watchlist).filter(Watchlist.plate_number == plate_norm).first()
    if not entry:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Plate '{plate_number}' not found in watchlist.",
        )

    if payload.category is not None:
        entry.category = payload.category
    if payload.description is not None:
        entry.description = payload.description
    if payload.active is not None:
        entry.active = payload.active

    db.commit()
    db.refresh(entry)
    return entry


@router.delete("/{plate_number}", status_code=status.HTTP_204_NO_CONTENT)
def delete_from_watchlist(plate_number: str, db: Session = Depends(get_db)):
    """Remove a vehicle from the watchlist."""
    plate_norm = plate_number.strip().upper().replace(" ", "")
    entry = db.query(Watchlist).filter(Watchlist.plate_number == plate_norm).first()
    if not entry:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Plate '{plate_number}' not found in watchlist.",
        )

    db.delete(entry)
    db.commit()
    return None
