"""
routers/seeds.py – Seed exchange listing CRUD.

Any farmer can create, update, or deactivate their own listings.
All listings are publicly readable (no auth required to browse).
"""

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models import FarmerProfile, SeedListing
from backend.schemas import (
    MessageResponse,
    SeedListingCreate,
    SeedListingRead,
    SeedListingUpdate,
)

router = APIRouter(prefix="/seeds", tags=["Seed Exchange"])


# ── Helpers ─────────────────────────────────────────────────────────────────

def _get_or_404(listing_id: int, db: Session) -> SeedListing:
    listing = db.get(SeedListing, listing_id)
    if not listing:
        raise HTTPException(status_code=404, detail=f"Listing {listing_id} not found.")
    return listing


# ── Routes ───────────────────────────────────────────────────────────────────

@router.post(
    "/",
    response_model=SeedListingRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a seed listing",
)
def create_listing(payload: SeedListingCreate, db: Session = Depends(get_db)):
    # Validate farmer
    if not db.get(FarmerProfile, payload.farmer_id):
        raise HTTPException(status_code=422, detail=f"Farmer {payload.farmer_id} not found.")

    listing = SeedListing(**payload.model_dump())
    db.add(listing)
    db.commit()
    db.refresh(listing)
    return listing


@router.get(
    "/",
    response_model=List[SeedListingRead],
    summary="Browse all active seed listings",
)
def list_listings(
    skip:         int            = Query(0,  ge=0),
    limit:        int            = Query(20, ge=1, le=200),
    crop_name:    Optional[str]  = Query(None, description="Filter by crop name (partial, case-insensitive)"),
    listing_type: Optional[str]  = Query(None, description="sell | swap | free"),
    farmer_id:    Optional[int]  = Query(None),
    active_only:  bool           = Query(True),
    db: Session = Depends(get_db),
):
    q = db.query(SeedListing)
    if active_only:
        q = q.filter(SeedListing.is_active.is_(True))
    if crop_name:
        q = q.filter(SeedListing.crop_name.ilike(f"%{crop_name}%"))
    if listing_type:
        q = q.filter(SeedListing.listing_type == listing_type)
    if farmer_id is not None:
        q = q.filter(SeedListing.farmer_id == farmer_id)
    return q.order_by(SeedListing.created_at.desc()).offset(skip).limit(limit).all()


@router.get(
    "/{listing_id}",
    response_model=SeedListingRead,
    summary="Get a single seed listing",
)
def get_listing(listing_id: int, db: Session = Depends(get_db)):
    return _get_or_404(listing_id, db)


@router.patch(
    "/{listing_id}",
    response_model=SeedListingRead,
    summary="Update a seed listing",
)
def update_listing(
    listing_id: int,
    payload:    SeedListingUpdate,
    db: Session = Depends(get_db),
):
    listing = _get_or_404(listing_id, db)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(listing, field, value)
    db.commit()
    db.refresh(listing)
    return listing


@router.delete(
    "/{listing_id}",
    response_model=MessageResponse,
    summary="Deactivate (soft-delete) a seed listing",
)
def deactivate_listing(listing_id: int, db: Session = Depends(get_db)):
    listing = _get_or_404(listing_id, db)
    listing.is_active = False
    db.commit()
    return MessageResponse(message=f"Listing {listing_id} deactivated.")
