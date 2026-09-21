"""
models.py – SQLAlchemy ORM models.

Tables
------
farmer_profiles   – farmer identity and field assignment
rover_devices     – registered devices allowed to push data
soil_readings     – sensor readings pushed by a rover
diagnoses         – crop disease diagnoses (rover or manual upload)
seed_listings     – farmer-to-farmer seed exchange board
"""

import secrets
from datetime import datetime, timezone
from enum import Enum as PyEnum

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from backend.database import Base


# ── Helpers ────────────────────────────────────────────────────────────────

def _now() -> datetime:
    return datetime.now(timezone.utc)


# ── Enums ──────────────────────────────────────────────────────────────────

class DiagnosisSource(str, PyEnum):
    ROVER = "rover"
    MANUAL_UPLOAD = "manual_upload"


class ListingType(str, PyEnum):
    SELL = "sell"
    SWAP = "swap"
    FREE = "free"


# ── Models ─────────────────────────────────────────────────────────────────

class FarmerProfile(Base):
    """Represents a registered farmer and their primary field."""

    __tablename__ = "farmer_profiles"

    id             = Column(Integer, primary_key=True, index=True)
    name           = Column(String(120), nullable=False)
    phone          = Column(String(20), nullable=False, unique=True, index=True)
    location       = Column(String(255), nullable=False)   # village / taluka / district
    assigned_field = Column(String(255), nullable=True)    # human-readable field description
    field_lat      = Column(Float, nullable=True, comment="Field centroid latitude for geo-matching")
    field_lon      = Column(Float, nullable=True, comment="Field centroid longitude for geo-matching")
    is_active      = Column(Boolean, default=True, nullable=False)
    created_at     = Column(DateTime(timezone=True), default=_now, nullable=False)
    updated_at     = Column(DateTime(timezone=True), default=_now, onupdate=_now)

    # Relationships
    soil_readings = relationship("SoilReading", back_populates="farmer", lazy="dynamic")
    diagnoses     = relationship("Diagnosis",   back_populates="farmer", lazy="dynamic")
    seed_listings = relationship("SeedListing", back_populates="farmer", lazy="dynamic")

    def __repr__(self) -> str:
        return f"<FarmerProfile id={self.id} name={self.name!r}>"


class RoverDevice(Base):
    """
    A physical rover unit that is authorised to push data.

    Authentication: the device sends its ``device_id`` and ``api_key``
    in every request header. The stored ``api_key_hash`` is a bcrypt hash
    of the plain-text key; the plain-text is NEVER stored.
    """

    __tablename__ = "rover_devices"
    __table_args__ = (UniqueConstraint("device_id", name="uq_rover_device_id"),)

    id            = Column(Integer, primary_key=True, index=True)
    device_id     = Column(String(64),  nullable=False, unique=True, index=True)
    api_key_hash  = Column(String(256), nullable=False)   # bcrypt hash of the raw key
    assigned_area = Column(String(255), nullable=True)    # geographic area served
    is_active     = Column(Boolean, default=True, nullable=False)
    last_seen_at  = Column(DateTime(timezone=True), nullable=True)
    created_at    = Column(DateTime(timezone=True), default=_now, nullable=False)

    # Relationships
    soil_readings = relationship("SoilReading", back_populates="rover", lazy="dynamic")

    def __repr__(self) -> str:
        return f"<RoverDevice device_id={self.device_id!r} active={self.is_active}>"


class SoilReading(Base):
    """
    One soil measurement packet pushed by a rover.

    All nutrient/physical columns are nullable so a rover can omit
    sensors it doesn't carry without rejecting the whole packet.
    """

    __tablename__ = "soil_readings"

    id                  = Column(Integer, primary_key=True, index=True)

    # ── Nutrient & chemistry ────────────────────────────────────────────
    nitrogen            = Column(Float, nullable=True,  comment="N  (kg/ha)")
    phosphorus          = Column(Float, nullable=True,  comment="P  (kg/ha)")
    potassium           = Column(Float, nullable=True,  comment="K  (kg/ha)")
    ph                  = Column(Float, nullable=True,  comment="Soil pH (0-14)")
    ec                  = Column(Float, nullable=True,  comment="Electrical Conductivity (dS/m)")

    # ── Physical ────────────────────────────────────────────────────────
    moisture            = Column(Float, nullable=True,  comment="Volumetric water content (%)")
    co2_activity_score  = Column(Float, nullable=True,  comment="Microbial CO₂ respiration (µg CO₂-C/g/day)")
    bulk_density        = Column(Float, nullable=True,  comment="Bulk density (g/cm³)")

    # ── Location ────────────────────────────────────────────────────────
    gps_lat             = Column(Float, nullable=True)
    gps_lon             = Column(Float, nullable=True)

    # ── Metadata ────────────────────────────────────────────────────────
    timestamp           = Column(DateTime(timezone=True), default=_now, nullable=False, index=True)
    raw_payload         = Column(Text, nullable=True,   comment="Original JSON from rover for debugging")

    # ── Foreign keys ────────────────────────────────────────────────────
    farmer_id      = Column(Integer, ForeignKey("farmer_profiles.id", ondelete="SET NULL"), nullable=True,  index=True)
    rover_device_id = Column(Integer, ForeignKey("rover_devices.id",   ondelete="SET NULL"), nullable=True,  index=True)

    # Relationships
    farmer = relationship("FarmerProfile", back_populates="soil_readings")
    rover  = relationship("RoverDevice",   back_populates="soil_readings")

    def __repr__(self) -> str:
        return f"<SoilReading id={self.id} farmer_id={self.farmer_id} ts={self.timestamp}>"


class Diagnosis(Base):
    """
    A crop disease diagnosis, either pushed by a rover or submitted
    manually by a farmer via the mobile app.
    """

    __tablename__ = "diagnoses"

    id           = Column(Integer, primary_key=True, index=True)
    crop         = Column(String(100), nullable=False)
    disease_name = Column(String(200), nullable=False)
    confidence   = Column(Float,       nullable=False,  comment="0.0 – 1.0")
    treatment    = Column(Text,        nullable=True,   comment="Free-text treatment steps")
    image_path   = Column(String(500), nullable=True,   comment="Relative path inside UPLOAD_DIR")
    source       = Column(
        Enum(DiagnosisSource, name="diagnosis_source"),
        nullable=False,
        default=DiagnosisSource.MANUAL_UPLOAD,
    )
    gps_lat      = Column(Float, nullable=True)
    gps_lon      = Column(Float, nullable=True)
    timestamp    = Column(DateTime(timezone=True), default=_now, nullable=False, index=True)

    # ── KVK Review & Notification Status ────────────────────────────────
    needs_kvk_review  = Column(Boolean, default=False, nullable=False, index=True, comment="True if confidence < threshold")
    kvk_review_status = Column(String(50), default="not_required", nullable=True, comment="pending / reviewed / not_required")
    raw_ai_response   = Column(Text, nullable=True, comment="Complete structured JSON from Gemini")
    notification_sent = Column(Boolean, default=False, nullable=False, comment="True if WhatsApp/SMS notification sent to farmer")

    # Foreign keys
    farmer_id       = Column(Integer, ForeignKey("farmer_profiles.id", ondelete="SET NULL"), nullable=True,  index=True)
    rover_device_id = Column(Integer, ForeignKey("rover_devices.id",   ondelete="SET NULL"), nullable=True)

    # Relationships
    farmer = relationship("FarmerProfile", back_populates="diagnoses")

    def __repr__(self) -> str:
        return f"<Diagnosis id={self.id} crop={self.crop!r} disease={self.disease_name!r}>"


class SeedListing(Base):
    """Peer-to-peer seed exchange listing created by a farmer."""

    __tablename__ = "seed_listings"

    id              = Column(Integer, primary_key=True, index=True)
    crop_name       = Column(String(100), nullable=False)
    variety         = Column(String(100), nullable=True)
    quantity_kg     = Column(Float,       nullable=True)
    price_per_kg    = Column(Float,       nullable=True,  comment="0 or null for free/swap")
    listing_type    = Column(
        Enum(ListingType, name="listing_type"),
        nullable=False,
        default=ListingType.SELL,
    )
    location        = Column(String(255), nullable=True)
    germination_pct = Column(Float,       nullable=True,  comment="0-100")
    description     = Column(Text,        nullable=True)
    is_active       = Column(Boolean, default=True, nullable=False)
    created_at      = Column(DateTime(timezone=True), default=_now, nullable=False, index=True)
    updated_at      = Column(DateTime(timezone=True), default=_now, onupdate=_now)

    # Foreign key
    farmer_id = Column(Integer, ForeignKey("farmer_profiles.id", ondelete="CASCADE"), nullable=False, index=True)

    # Relationships
    farmer = relationship("FarmerProfile", back_populates="seed_listings")

    def __repr__(self) -> str:
        return f"<SeedListing id={self.id} crop={self.crop_name!r} type={self.listing_type}>"
