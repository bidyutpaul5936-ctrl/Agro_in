"""
routers/soil.py – Read / query soil readings.

Write (ingest) access is rover-only and lives in routers/rover.py.
These endpoints expose data to the farmer-facing frontend or an admin dashboard.
"""

from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models import SoilReading
from backend.schemas import SoilReadingRead

router = APIRouter(prefix="/soil", tags=["Soil Readings"])


@router.get(
    "/",
    response_model=List[SoilReadingRead],
    summary="List soil readings (paginated, filterable)",
)
def list_soil_readings(
    skip:            int            = Query(0,   ge=0),
    limit:           int            = Query(20,  ge=1, le=200),
    farmer_id:       Optional[int]  = Query(None, description="Filter by farmer"),
    rover_device_id: Optional[int]  = Query(None, description="Filter by rover"),
    db: Session = Depends(get_db),
):
    q = db.query(SoilReading)
    if farmer_id is not None:
        q = q.filter(SoilReading.farmer_id == farmer_id)
    if rover_device_id is not None:
        q = q.filter(SoilReading.rover_device_id == rover_device_id)
    return q.order_by(SoilReading.timestamp.desc()).offset(skip).limit(limit).all()


@router.get(
    "/{reading_id}",
    response_model=SoilReadingRead,
    summary="Get a single soil reading by ID",
)
def get_soil_reading(reading_id: int, db: Session = Depends(get_db)):
    from fastapi import HTTPException
    reading = db.get(SoilReading, reading_id)
    if not reading:
        raise HTTPException(status_code=404, detail=f"Soil reading {reading_id} not found.")
    return reading


@router.get(
    "/farmer/{farmer_id}/latest",
    response_model=SoilReadingRead,
    summary="Get the most recent soil reading for a farmer",
)
def latest_for_farmer(farmer_id: int, db: Session = Depends(get_db)):
    from fastapi import HTTPException
    reading = (
        db.query(SoilReading)
        .filter(SoilReading.farmer_id == farmer_id)
        .order_by(SoilReading.timestamp.desc())
        .first()
    )
    if not reading:
        raise HTTPException(status_code=404, detail=f"No readings found for farmer {farmer_id}.")
    return reading
