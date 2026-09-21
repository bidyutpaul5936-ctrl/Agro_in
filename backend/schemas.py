"""
schemas.py – Pydantic v2 request/response schemas.

Naming convention
-----------------
  <Model>Base   – shared fields (used by both Create and Read)
  <Model>Create – fields accepted on POST (input)
  <Model>Read   – fields returned to the client (output, includes id / timestamps)
  <Model>Update – optional fields for PATCH requests
"""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


# ── Shared config ──────────────────────────────────────────────────────────

class _OrmBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ══════════════════════════════════════════════════════════════════════════
#  FARMER PROFILE
# ══════════════════════════════════════════════════════════════════════════

class FarmerProfileBase(_OrmBase):
    name:           str   = Field(..., max_length=120, examples=["Ramesh Patil"])
    phone:          str   = Field(..., max_length=20,  examples=["+919876543210"])
    location:       str   = Field(..., max_length=255, examples=["Shirdi, Ahmednagar, Maharashtra"])
    assigned_field: Optional[str] = Field(None, max_length=255, examples=["Field A – 1.2 acres near Mula river"])
    field_lat:      Optional[float] = Field(None, ge=-90, le=90, examples=[19.7665])
    field_lon:      Optional[float] = Field(None, ge=-180, le=180, examples=[74.4824])


class FarmerProfileCreate(FarmerProfileBase):
    pass


class FarmerProfileUpdate(_OrmBase):
    name:           Optional[str] = None
    phone:          Optional[str] = None
    location:       Optional[str] = None
    assigned_field: Optional[str] = None
    field_lat:      Optional[float] = None
    field_lon:      Optional[float] = None
    is_active:      Optional[bool] = None


class FarmerProfileRead(FarmerProfileBase):
    id:         int
    is_active:  bool
    created_at: datetime
    updated_at: Optional[datetime] = None


# ══════════════════════════════════════════════════════════════════════════
#  ROVER DEVICE
# ══════════════════════════════════════════════════════════════════════════

class RoverDeviceCreate(_OrmBase):
    """Admin-only: register a new rover device."""
    device_id:     str            = Field(..., max_length=64,  examples=["ROVER-MH-001"])
    api_key:       str            = Field(..., min_length=32,  examples=["<generated 32+ char secret>"])
    assigned_area: Optional[str]  = Field(None, max_length=255, examples=["Ahmednagar district, Block B"])


class RoverDeviceRead(_OrmBase):
    id:            int
    device_id:     str
    assigned_area: Optional[str]
    is_active:     bool
    last_seen_at:  Optional[datetime]
    created_at:    datetime


class RoverDeviceKeyResponse(_OrmBase):
    """Returned once after registration – the caller must save the raw key."""
    device_id:   str
    raw_api_key: str
    message:     str = "Store this key securely. It cannot be retrieved again."


# ══════════════════════════════════════════════════════════════════════════
#  SOIL READING
# ══════════════════════════════════════════════════════════════════════════

class SoilReadingCreate(_OrmBase):
    """
    Payload a rover sends to the ingestion endpoint.
    All measurement fields are optional so partial packets are accepted.
    """
    # Nutrients
    nitrogen:           Optional[float] = Field(None, ge=0,   description="N (kg/ha)")
    phosphorus:         Optional[float] = Field(None, ge=0,   description="P (kg/ha)")
    potassium:          Optional[float] = Field(None, ge=0,   description="K (kg/ha)")
    ph:                 Optional[float] = Field(None, ge=0, le=14, description="Soil pH")
    ec:                 Optional[float] = Field(None, ge=0,   description="EC (dS/m)")
    # Physical
    moisture:           Optional[float] = Field(None, ge=0, le=100, description="Volumetric water content (%)")
    co2_activity_score: Optional[float] = Field(None, ge=0,   description="CO₂ respiration score")
    bulk_density:       Optional[float] = Field(None, ge=0,   description="Bulk density (g/cm³)")
    # GPS
    gps_lat:            Optional[float] = Field(None, ge=-90,  le=90)
    gps_lon:            Optional[float] = Field(None, ge=-180, le=180)
    # Association
    farmer_id:          Optional[int]   = Field(None, description="Farmer this reading belongs to")
    timestamp:          Optional[datetime] = Field(None, description="ISO-8601; defaults to server time if omitted")


class RoverSoilReadingPayload(_OrmBase):
    """
    Payload for POST /rover/soil-reading.
    Accepts sensor metrics + GPS. Can accept rover_device_id and api_key in body or headers.
    """
    nitrogen:           Optional[float] = Field(None, ge=0)
    phosphorus:         Optional[float] = Field(None, ge=0)
    potassium:          Optional[float] = Field(None, ge=0)
    ph:                 Optional[float] = Field(None, ge=0, le=14)
    ec:                 Optional[float] = Field(None, ge=0)
    moisture:           Optional[float] = Field(None, ge=0, le=100)
    co2_activity_score: Optional[float] = Field(None, ge=0)
    bulk_density:       Optional[float] = Field(None, ge=0)
    gps_lat:            float           = Field(..., ge=-90, le=90, description="Rover GPS latitude")
    gps_lon:            float           = Field(..., ge=-180, le=180, description="Rover GPS longitude")
    rover_device_id:    Optional[str]   = Field(None, description="Rover device ID (or pass via X-Device-ID header)")
    api_key:            Optional[str]   = Field(None, description="Rover API key (or pass via X-API-Key header)")
    timestamp:          Optional[datetime] = None



class SoilReadingRead(_OrmBase):
    id:                 int
    nitrogen:           Optional[float]
    phosphorus:         Optional[float]
    potassium:          Optional[float]
    ph:                 Optional[float]
    ec:                 Optional[float]
    moisture:           Optional[float]
    co2_activity_score: Optional[float]
    bulk_density:       Optional[float]
    gps_lat:            Optional[float]
    gps_lon:            Optional[float]
    timestamp:          datetime
    farmer_id:          Optional[int]
    rover_device_id:    Optional[int]


class SoilReadingWithMatchResponse(SoilReadingRead):
    farmer_name:            Optional[str]   = None
    assigned_field:         Optional[str]   = None
    matched_distance_meters: Optional[float] = None
    notification_status:    Optional[str]   = None


# ══════════════════════════════════════════════════════════════════════════
#  DIAGNOSIS
# ══════════════════════════════════════════════════════════════════════════

class DiagnosisCreate(_OrmBase):
    crop:         str   = Field(..., max_length=100, examples=["Tomato"])
    disease_name: str   = Field(..., max_length=200, examples=["Late Blight"])
    confidence:   float = Field(..., ge=0.0, le=1.0, examples=[0.82])
    treatment:    Optional[str]  = Field(None, examples=["Apply Mancozeb 2g/L; remove affected leaves"])
    image_path:   Optional[str]  = Field(None, max_length=500)
    gps_lat:      Optional[float] = Field(None, ge=-90,  le=90)
    gps_lon:      Optional[float] = Field(None, ge=-180, le=180)
    farmer_id:    Optional[int]  = None
    timestamp:    Optional[datetime] = None


class DiagnosisRead(_OrmBase):
    id:                int
    crop:              str
    disease_name:      str
    confidence:        float
    treatment:         Optional[str]
    image_path:        Optional[str]
    source:            str
    gps_lat:           Optional[float]
    gps_lon:           Optional[float]
    farmer_id:         Optional[int]
    rover_device_id:   Optional[int]
    timestamp:         datetime
    needs_kvk_review:  bool = False
    kvk_review_status: Optional[str] = "not_required"
    notification_sent: bool = False


class PlantPhotoRoverResponse(_OrmBase):
    diagnosis_id:        int
    crop:                str
    disease_name:        str
    confidence:          float
    treatment:           Optional[str]
    urgent_steps:        List[str] = []
    pathogen_type:       Optional[str] = None
    risk_level:          Optional[str] = None
    image_path:          Optional[str]
    source:              str
    farmer_id:           Optional[int]
    farmer_name:         Optional[str] = None
    rover_device_id:     Optional[int]
    needs_kvk_review:    bool
    kvk_review_status:   str
    notification_status: str
    message:             str



# ══════════════════════════════════════════════════════════════════════════
#  SEED LISTING
# ══════════════════════════════════════════════════════════════════════════

class SeedListingBase(_OrmBase):
    crop_name:       str            = Field(..., max_length=100, examples=["Tomato"])
    variety:         Optional[str]  = Field(None, max_length=100, examples=["Arka Vikas"])
    quantity_kg:     Optional[float] = Field(None, ge=0)
    price_per_kg:    Optional[float] = Field(None, ge=0, description="0 or null for free/swap")
    listing_type:    str            = Field("sell", examples=["sell", "swap", "free"])
    location:        Optional[str]  = Field(None, max_length=255)
    germination_pct: Optional[float] = Field(None, ge=0, le=100)
    description:     Optional[str]  = None

    @field_validator("listing_type")
    @classmethod
    def validate_listing_type(cls, v: str) -> str:
        allowed = {"sell", "swap", "free"}
        if v not in allowed:
            raise ValueError(f"listing_type must be one of {allowed}")
        return v


class SeedListingCreate(SeedListingBase):
    farmer_id: int


class SeedListingUpdate(_OrmBase):
    quantity_kg:     Optional[float] = None
    price_per_kg:    Optional[float] = None
    listing_type:    Optional[str]   = None
    location:        Optional[str]   = None
    germination_pct: Optional[float] = None
    description:     Optional[str]   = None
    is_active:       Optional[bool]  = None


class SeedListingRead(SeedListingBase):
    id:         int
    farmer_id:  int
    is_active:  bool
    created_at: datetime
    updated_at: Optional[datetime] = None


# ══════════════════════════════════════════════════════════════════════════
#  GENERIC RESPONSES
# ══════════════════════════════════════════════════════════════════════════

class MessageResponse(BaseModel):
    message: str


class PaginatedResponse(BaseModel):
    total:  int
    skip:   int
    limit:  int
    items:  list


# ══════════════════════════════════════════════════════════════════════════
#  FARMER DASHBOARD
# ══════════════════════════════════════════════════════════════════════════

class SoilNutrientIndicator(_OrmBase):
    param:   str = ""
    name:    str
    val:     str
    unit:    str
    status:  str   # "good", "warning", "bad"
    badge:   str
    advice:  str


class CropRecommendationItem(_OrmBase):
    rank:         int
    crop_key:     str
    crop_name:    str
    icon:         str
    category:     str
    score_pct:    float
    suitability:  str
    badge_class:  str
    reason:       str


class FarmerDashboardResponse(_OrmBase):
    farmer:               FarmerProfileRead
    latest_soil_reading:  Optional[SoilReadingRead] = None
    soil_indicators:      List[SoilNutrientIndicator] = []
    crop_recommendations: List[CropRecommendationItem] = []
    past_diagnoses:       List[DiagnosisRead] = []
    total_diagnoses:      int = 0
    total_soil_readings:  int = 0

