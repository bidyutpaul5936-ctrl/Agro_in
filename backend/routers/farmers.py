"""
routers/farmers.py – CRUD for farmer profiles.

These endpoints are not rover-authenticated; in production they would sit
behind a separate admin or internal-service auth layer.
"""

from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models import FarmerProfile
from backend.schemas import (
    FarmerProfileCreate,
    FarmerProfileRead,
    FarmerProfileUpdate,
    MessageResponse,
)

router = APIRouter(prefix="/farmers", tags=["Farmers"])


# ── Helpers ────────────────────────────────────────────────────────────────

def _get_or_404(farmer_id: int, db: Session) -> FarmerProfile:
    farmer = db.get(FarmerProfile, farmer_id)
    if not farmer:
        raise HTTPException(status_code=404, detail=f"Farmer {farmer_id} not found.")
    return farmer


# ── Routes ─────────────────────────────────────────────────────────────────

@router.post(
    "/",
    response_model=FarmerProfileRead,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new farmer",
)
def create_farmer(payload: FarmerProfileCreate, db: Session = Depends(get_db)):
    # Guard duplicate phone
    existing = db.query(FarmerProfile).filter(FarmerProfile.phone == payload.phone).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"A farmer with phone '{payload.phone}' is already registered.",
        )
    farmer = FarmerProfile(**payload.model_dump())
    db.add(farmer)
    db.commit()
    db.refresh(farmer)
    return farmer


@router.get(
    "/",
    response_model=List[FarmerProfileRead],
    summary="List all farmers (paginated)",
)
def list_farmers(
    skip:      int = Query(0,   ge=0),
    limit:     int = Query(20,  ge=1, le=200),
    is_active: bool | None = Query(None, description="Filter by active status"),
    db: Session = Depends(get_db),
):
    q = db.query(FarmerProfile)
    if is_active is not None:
        q = q.filter(FarmerProfile.is_active == is_active)
    return q.order_by(FarmerProfile.id).offset(skip).limit(limit).all()


@router.get(
    "/{farmer_id}",
    response_model=FarmerProfileRead,
    summary="Get a single farmer by ID",
)
def get_farmer(farmer_id: int, db: Session = Depends(get_db)):
    return _get_or_404(farmer_id, db)


@router.patch(
    "/{farmer_id}",
    response_model=FarmerProfileRead,
    summary="Partially update a farmer profile",
)
def update_farmer(
    farmer_id: int,
    payload: FarmerProfileUpdate,
    db: Session = Depends(get_db),
):
    farmer = _get_or_404(farmer_id, db)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(farmer, field, value)
    db.commit()
    db.refresh(farmer)
    return farmer


@router.delete(
    "/{farmer_id}",
    response_model=MessageResponse,
    summary="Soft-delete a farmer (sets is_active=False)",
)
def deactivate_farmer(farmer_id: int, db: Session = Depends(get_db)):
    farmer = _get_or_404(farmer_id, db)
    farmer.is_active = False
    db.commit()
    return MessageResponse(message=f"Farmer {farmer_id} deactivated.")
