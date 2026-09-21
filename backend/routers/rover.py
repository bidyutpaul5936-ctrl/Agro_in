"""
routers/rover.py – Rover device management + data ingestion endpoints.

Ingestion endpoints (POST /rover/ingest/*)
------------------------------------------
All require a registered rover to present:
    X-Device-ID  →  device_id column
    X-API-Key    →  verified against bcrypt api_key_hash

Management endpoints (POST /rover/devices, GET /rover/devices/*)
----------------------------------------------------------------
In a real deployment these would be protected by an admin auth layer;
here they are left open for ease of initial development / testing.
"""

import json
import os
import secrets
import uuid
from typing import Annotated, List, Optional

import aiofiles
from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, Query, UploadFile, status
from sqlalchemy.orm import Session

from backend.auth import authenticate_rover_device, hash_api_key, require_rover
from backend.config import settings
from backend.database import get_db
from backend.diagnosis_engine import get_diagnosis_engine
from backend.geo import find_nearest_farmer_field
from backend.models import Diagnosis, DiagnosisSource, FarmerProfile, RoverDevice, SoilReading
from backend.notifications import send_farmer_notification, send_kvk_review_alert
from backend.schemas import (
    DiagnosisCreate,
    DiagnosisRead,
    MessageResponse,
    PlantPhotoRoverResponse,
    RoverDeviceCreate,
    RoverDeviceKeyResponse,
    RoverDeviceRead,
    RoverSoilReadingPayload,
    SoilReadingCreate,
    SoilReadingRead,
    SoilReadingWithMatchResponse,
)

router = APIRouter(prefix="/rover", tags=["Rover"])



# ═══════════════════════════════════════════════════════════════════════════
#  DEVICE MANAGEMENT  (admin-only in production)
# ═══════════════════════════════════════════════════════════════════════════

@router.post(
    "/devices",
    response_model=RoverDeviceKeyResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new rover device (admin)",
    description=(
        "Creates a rover device record. The caller may supply an ``api_key``; "
        "if omitted a cryptographically random 48-char key is generated. "
        "**The raw key is returned once and never stored.** "
        "Save it immediately."
    ),
)
def register_rover_device(payload: RoverDeviceCreate, db: Session = Depends(get_db)):
    # Guard duplicate device_id
    if db.query(RoverDevice).filter(RoverDevice.device_id == payload.device_id).first():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Device '{payload.device_id}' is already registered.",
        )

    raw_key = payload.api_key or secrets.token_urlsafe(48)
    device  = RoverDevice(
        device_id     = payload.device_id,
        api_key_hash  = hash_api_key(raw_key),
        assigned_area = payload.assigned_area,
    )
    db.add(device)
    db.commit()
    db.refresh(device)

    return RoverDeviceKeyResponse(
        device_id   = device.device_id,
        raw_api_key = raw_key,
    )


@router.get(
    "/devices",
    response_model=List[RoverDeviceRead],
    summary="List all rover devices (admin)",
)
def list_rover_devices(
    skip:  int = Query(0,  ge=0),
    limit: int = Query(20, ge=1, le=200),
    db: Session = Depends(get_db),
):
    return db.query(RoverDevice).order_by(RoverDevice.id).offset(skip).limit(limit).all()


@router.get(
    "/devices/{device_id}",
    response_model=RoverDeviceRead,
    summary="Get a rover device by device_id string (admin)",
)
def get_rover_device(device_id: str, db: Session = Depends(get_db)):
    device = db.query(RoverDevice).filter(RoverDevice.device_id == device_id).first()
    if not device:
        raise HTTPException(status_code=404, detail=f"Device '{device_id}' not found.")
    return device


@router.patch(
    "/devices/{device_id}/deactivate",
    response_model=MessageResponse,
    summary="Deactivate a rover device (admin)",
)
def deactivate_rover_device(device_id: str, db: Session = Depends(get_db)):
    device = db.query(RoverDevice).filter(RoverDevice.device_id == device_id).first()
    if not device:
        raise HTTPException(status_code=404, detail=f"Device '{device_id}' not found.")
    device.is_active = False
    db.commit()
    return MessageResponse(message=f"Device '{device_id}' deactivated.")


# ═══════════════════════════════════════════════════════════════════════════
#  DATA INGESTION  (rover-authenticated)
# ═══════════════════════════════════════════════════════════════════════════

@router.post(
    "/ingest/soil",
    response_model=SoilReadingRead,
    status_code=status.HTTP_201_CREATED,
    summary="[ROVER] Push a soil reading",
    description=(
        "Authenticated rovers send one soil measurement packet. "
        "All measurement fields are optional so a device can omit "
        "sensors it does not carry. ``farmer_id`` links the reading "
        "to the farmer whose field the rover is currently working."
    ),
)
def ingest_soil(
    payload: SoilReadingCreate,
    rover:   RoverDevice = Depends(require_rover),
    db:      Session     = Depends(get_db),
):
    # Validate farmer_id if provided
    if payload.farmer_id:
        farmer = db.get(FarmerProfile, payload.farmer_id)
        if not farmer:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Farmer {payload.farmer_id} not found.",
            )

    data = payload.model_dump(exclude={"farmer_id", "timestamp"})
    reading = SoilReading(
        **data,
        farmer_id       = payload.farmer_id,
        rover_device_id = rover.id,
        timestamp       = payload.timestamp,          # None → model default (_now)
        raw_payload     = json.dumps(payload.model_dump(), default=str),
    )
    db.add(reading)
    db.commit()
    db.refresh(reading)
    return reading


@router.post(
    "/ingest/diagnosis",
    response_model=DiagnosisRead,
    status_code=status.HTTP_201_CREATED,
    summary="[ROVER] Push a crop disease diagnosis",
    description=(
        "Rover submits an AI-generated diagnosis. ``confidence`` must be "
        "in [0.0, 1.0]. ``image_path`` is the path where the rover "
        "uploaded the associated image (can be set after the fact)."
    ),
)
def ingest_diagnosis(
    payload: DiagnosisCreate,
    rover:   RoverDevice = Depends(require_rover),
    db:      Session     = Depends(get_db),
):
    if payload.farmer_id:
        if not db.get(FarmerProfile, payload.farmer_id):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Farmer {payload.farmer_id} not found.",
            )

    data = payload.model_dump(exclude={"timestamp"})
    diagnosis = Diagnosis(
        **data,
        source          = DiagnosisSource.ROVER,
        rover_device_id = rover.id,
        timestamp       = payload.timestamp,
    )
    db.add(diagnosis)
    db.commit()
    db.refresh(diagnosis)
    return diagnosis


# ── Convenience: latest readings per rover ─────────────────────────────────

@router.get(
    "/ingest/soil/latest",
    response_model=List[SoilReadingRead],
    summary="[ROVER] Get the N most recent soil readings pushed by this rover",
)
def latest_soil_readings(
    n:     int          = Query(10, ge=1, le=100),
    rover: RoverDevice  = Depends(require_rover),
    db:    Session      = Depends(get_db),
):
    return (
        db.query(SoilReading)
        .filter(SoilReading.rover_device_id == rover.id)
        .order_by(SoilReading.timestamp.desc())
        .limit(n)
        .all()
    )


# ═══════════════════════════════════════════════════════════════════════════
#  NEW ROVER ENDPOINTS (GPS MATCHING, GEMINI PATHOLOGY, KVK TRIAGE)
# ═══════════════════════════════════════════════════════════════════════════

@router.post(
    "/soil-reading",
    response_model=SoilReadingWithMatchResponse,
    status_code=status.HTTP_201_CREATED,
    summary="[ROVER] Ingest soil reading with GPS & match nearest farmer's field",
    description=(
        "Accepts sensor values + GPS + rover_device_id. "
        "Validates the rover's api_key, stores the reading, matches it to the nearest "
        "farmer's field based on GPS coordinates, and triggers an alert notification to the farmer."
    ),
)
def rover_soil_reading(
    payload: RoverSoilReadingPayload,
    x_device_id: Annotated[Optional[str], Header(alias="X-Device-ID")] = None,
    x_api_key:   Annotated[Optional[str], Header(alias="X-API-Key")]   = None,
    db: Session = Depends(get_db),
):
    device_id = x_device_id or payload.rover_device_id
    api_key = x_api_key or payload.api_key
    rover = authenticate_rover_device(device_id, api_key, db)

    # Match nearest farmer field using GPS coordinates
    nearest_farmer, distance_m = find_nearest_farmer_field(db, payload.gps_lat, payload.gps_lon)

    data = payload.model_dump(exclude={"rover_device_id", "api_key", "timestamp"})
    reading = SoilReading(
        **data,
        farmer_id=nearest_farmer.id if nearest_farmer else None,
        rover_device_id=rover.id,
        timestamp=payload.timestamp,
        raw_payload=json.dumps(payload.model_dump(), default=str),
    )
    db.add(reading)
    db.commit()
    db.refresh(reading)

    notif_res = None
    if nearest_farmer:
        summary_text = f"pH: {payload.ph or 'N/A'}, Moisture: {payload.moisture or 'N/A'}%."
        if payload.nitrogen is not None or payload.phosphorus is not None or payload.potassium is not None:
            summary_text += f" NPK: {payload.nitrogen or 0}-{payload.phosphorus or 0}-{payload.potassium or 0}."
        notif_res = send_farmer_notification(
            farmer=nearest_farmer,
            report_type="soil",
            summary=summary_text,
            reference_id=reading.id,
        )

    return SoilReadingWithMatchResponse(
        id=reading.id,
        nitrogen=reading.nitrogen,
        phosphorus=reading.phosphorus,
        potassium=reading.potassium,
        ph=reading.ph,
        ec=reading.ec,
        moisture=reading.moisture,
        co2_activity_score=reading.co2_activity_score,
        bulk_density=reading.bulk_density,
        gps_lat=reading.gps_lat,
        gps_lon=reading.gps_lon,
        timestamp=reading.timestamp,
        farmer_id=reading.farmer_id,
        rover_device_id=reading.rover_device_id,
        farmer_name=nearest_farmer.name if nearest_farmer else None,
        assigned_field=nearest_farmer.assigned_field if nearest_farmer else None,
        matched_distance_meters=round(distance_m, 1) if distance_m is not None else None,
        notification_status="delivered_stub" if notif_res else "no_farmer_matched",
    )


@router.post(
    "/plant-photo",
    response_model=PlantPhotoRoverResponse,
    status_code=status.HTTP_201_CREATED,
    summary="[ROVER] Upload plant photo for Gemini AI disease diagnosis & KVK triage",
    description=(
        "Accepts a plant image + rover_device_id. Validates rover api_key, "
        "runs disease diagnosis via Gemini API with structured JSON schema. "
        "Stores the result. If confidence < 0.70, flags for KVK review instead "
        "of notifying the farmer directly. If confidence >= 0.70, notifies farmer."
    ),
)
async def rover_plant_photo(
    image:           UploadFile = File(..., description="Crop leaf photo"),
    rover_device_id: Optional[str]   = Form(None),
    api_key:         Optional[str]   = Form(None),
    gps_lat:         Optional[float] = Form(None),
    gps_lon:         Optional[float] = Form(None),
    crop_hint:       Optional[str]   = Form(None),
    x_device_id:     Annotated[Optional[str], Header(alias="X-Device-ID")] = None,
    x_api_key:       Annotated[Optional[str], Header(alias="X-API-Key")]   = None,
    db:              Session         = Depends(get_db),
):
    device_id = x_device_id or rover_device_id
    plain_key = x_api_key or api_key
    rover = authenticate_rover_device(device_id, plain_key, db)

    content = await image.read()
    if len(content) > 10 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Image exceeds 10 MB limit.")

    # Save to disk
    save_dir = os.path.join(settings.UPLOAD_DIR, "diagnoses")
    os.makedirs(save_dir, exist_ok=True)
    ext = (image.filename or "photo.jpg").rsplit(".", 1)[-1].lower()
    filename = f"rover_{rover.device_id}_{uuid.uuid4().hex[:8]}.{ext}"
    full_path = os.path.join(save_dir, filename)
    rel_path = os.path.join("diagnoses", filename)

    async with aiofiles.open(full_path, "wb") as f:
        await f.write(content)

    # Call pluggable diagnosis engine (Gemini or Local Fine-Tuned Model)
    engine = get_diagnosis_engine()
    ai_result = await engine.diagnose(
        image_bytes=content,
        mime_type=image.content_type or "image/jpeg",
        crop_hint=crop_hint,
        filename_hint=image.filename,
    )

    # Match nearest farmer if GPS is provided
    nearest_farmer = None
    if gps_lat is not None and gps_lon is not None:
        nearest_farmer, _ = find_nearest_farmer_field(db, gps_lat, gps_lon)

    # Check confidence threshold for KVK triage (< 0.70)
    needs_kvk = ai_result.confidence < settings.KVK_CONFIDENCE_THRESHOLD
    kvk_status = "pending" if needs_kvk else "not_required"

    diagnosis = Diagnosis(
        crop=ai_result.crop,
        disease_name=ai_result.disease_name,
        confidence=ai_result.confidence,
        treatment=ai_result.treatment,
        image_path=rel_path,
        source=DiagnosisSource.ROVER,
        gps_lat=gps_lat,
        gps_lon=gps_lon,
        farmer_id=nearest_farmer.id if nearest_farmer else None,
        rover_device_id=rover.id,
        needs_kvk_review=needs_kvk,
        kvk_review_status=kvk_status,
        raw_ai_response=ai_result.model_dump_json(),
        notification_sent=False,
    )
    db.add(diagnosis)
    db.commit()
    db.refresh(diagnosis)

    if needs_kvk:
        # Escalate to KVK scientist review queue instead of notifying farmer directly
        send_kvk_review_alert(diagnosis, nearest_farmer)
        notification_status = "held_for_kvk_review"
        msg = f"Diagnosis confidence ({ai_result.confidence:.2f}) is below 0.70. Flagged for KVK expert review. Direct farmer notification withheld."
    else:
        # Confidence >= 0.70 -> Notify farmer directly
        if nearest_farmer:
            summary = f"Detected: {ai_result.crop} - {ai_result.disease_name} (Confidence: {ai_result.confidence*100:.0f}%)."
            send_farmer_notification(
                farmer=nearest_farmer,
                report_type="diagnosis",
                summary=summary,
                reference_id=diagnosis.id,
            )
            diagnosis.notification_sent = True
            db.commit()
            notification_status = "notified_farmer"
            msg = f"Farmer {nearest_farmer.name} notified via WhatsApp/SMS."
        else:
            notification_status = "farmer_unassigned"
            msg = "Diagnosis recorded with high confidence. No farmer assigned to this location."

    return PlantPhotoRoverResponse(
        diagnosis_id=diagnosis.id,
        crop=diagnosis.crop,
        disease_name=diagnosis.disease_name,
        confidence=diagnosis.confidence,
        treatment=diagnosis.treatment,
        urgent_steps=ai_result.urgent_steps,
        pathogen_type=ai_result.pathogen_type,
        risk_level=ai_result.risk_level,
        image_path=diagnosis.image_path,
        source="rover",
        farmer_id=diagnosis.farmer_id,
        farmer_name=nearest_farmer.name if nearest_farmer else None,
        rover_device_id=diagnosis.rover_device_id,
        needs_kvk_review=diagnosis.needs_kvk_review,
        kvk_review_status=diagnosis.kvk_review_status,
        notification_status=notification_status,
        message=msg,
    )

