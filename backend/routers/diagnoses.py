"""
routers/diagnoses.py – Read diagnoses + manual-upload endpoint.

Rover-pushed diagnoses arrive via routers/rover.py.
Manual uploads (farmer uses mobile app) are accepted here.
"""

import os
import uuid
from typing import List, Optional

import aiofiles
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from sqlalchemy.orm import Session

from backend.config import settings
from backend.database import get_db
from backend.diagnosis_engine import get_diagnosis_engine
from backend.geo import find_nearest_farmer_field
from backend.models import Diagnosis, DiagnosisSource, FarmerProfile
from backend.notifications import send_farmer_notification, send_kvk_review_alert
from backend.schemas import DiagnosisCreate, DiagnosisRead

router = APIRouter(prefix="/diagnoses", tags=["Diagnoses"])

# Allowed image MIME types for manual uploads
_ALLOWED_MIME = {"image/jpeg", "image/png", "image/webp", "image/heic"}
_MAX_SIZE_MB  = 10


# ── Helpers ─────────────────────────────────────────────────────────────────

def _ensure_upload_dir() -> str:
    path = os.path.join(settings.UPLOAD_DIR, "diagnoses")
    os.makedirs(path, exist_ok=True)
    return path


# ── Routes ───────────────────────────────────────────────────────────────────

@router.get(
    "/",
    response_model=List[DiagnosisRead],
    summary="List diagnoses (paginated, filterable)",
)
def list_diagnoses(
    skip:      int           = Query(0,   ge=0),
    limit:     int           = Query(20,  ge=1, le=200),
    farmer_id: Optional[int] = Query(None),
    source:    Optional[str] = Query(None, description="'rover' or 'manual_upload'"),
    db: Session = Depends(get_db),
):
    q = db.query(Diagnosis)
    if farmer_id is not None:
        q = q.filter(Diagnosis.farmer_id == farmer_id)
    if source is not None:
        try:
            src = DiagnosisSource(source)
        except ValueError:
            raise HTTPException(status_code=422, detail="source must be 'rover' or 'manual_upload'")
        q = q.filter(Diagnosis.source == src)
    return q.order_by(Diagnosis.timestamp.desc()).offset(skip).limit(limit).all()


@router.get(
    "/{diagnosis_id}",
    response_model=DiagnosisRead,
    summary="Get a single diagnosis by ID",
)
def get_diagnosis(diagnosis_id: int, db: Session = Depends(get_db)):
    diag = db.get(Diagnosis, diagnosis_id)
    if not diag:
        raise HTTPException(status_code=404, detail=f"Diagnosis {diagnosis_id} not found.")
    return diag


@router.post(
    "/manual-upload",
    response_model=DiagnosisRead,
    status_code=status.HTTP_201_CREATED,
    summary="Farmer manually uploads a plant photo for diagnosis (fallback)",
    description=(
        "Farmer-initiated fallback: accepts a plant photo, runs Gemini disease diagnosis, "
        "stores the result, flags for KVK review if confidence < 0.70, and notifies farmer."
    ),
)
@router.post(
    "/manual",
    response_model=DiagnosisRead,
    status_code=status.HTTP_201_CREATED,
    include_in_schema=False,
)
async def manual_upload_diagnosis(
    image:        UploadFile = File(..., description="Plant photo (JPEG/PNG/WEBP/HEIC, max 10 MB)"),
    farmer_id:    Optional[int]   = Form(None),
    crop:         Optional[str]   = Form(None),
    disease_name: Optional[str]   = Form(None),
    confidence:   Optional[float] = Form(None),
    treatment:    Optional[str]   = Form(None),
    gps_lat:      Optional[float] = Form(None),
    gps_lon:      Optional[float] = Form(None),
    db:           Session         = Depends(get_db),
):
    # Validate image MIME
    if image.content_type and image.content_type not in _ALLOWED_MIME:
        raise HTTPException(
            status_code=415,
            detail=f"Unsupported image type '{image.content_type}'. Allowed: {_ALLOWED_MIME}",
        )

    # Read and size-check
    content = await image.read()
    if len(content) > _MAX_SIZE_MB * 1024 * 1024:
        raise HTTPException(status_code=413, detail=f"Image exceeds {_MAX_SIZE_MB} MB limit.")

    # Save to disk
    ext       = (image.filename or "img.jpg").rsplit(".", 1)[-1].lower()
    filename  = f"manual_{uuid.uuid4().hex[:8]}.{ext}"
    save_dir  = _ensure_upload_dir()
    rel_path  = os.path.join("diagnoses", filename)
    full_path = os.path.join(save_dir, filename)

    async with aiofiles.open(full_path, "wb") as f:
        await f.write(content)

    # Match farmer
    farmer = None
    if farmer_id:
        farmer = db.get(FarmerProfile, farmer_id)
        if not farmer:
            raise HTTPException(status_code=422, detail=f"Farmer {farmer_id} not found.")
    elif gps_lat is not None and gps_lon is not None:
        farmer, _ = find_nearest_farmer_field(db, gps_lat, gps_lon)

    # If explicit disease and confidence were provided (e.g. from tests or pre-labeled upload)
    if crop and disease_name and confidence is not None:
        diag_crop = crop
        diag_disease = disease_name
        diag_conf = float(confidence)
        diag_treat = treatment
        raw_ai = None
    else:
        # Re-use pluggable plant disease diagnosis engine
        engine = get_diagnosis_engine()
        ai_result = await engine.diagnose(
            image_bytes=content,
            mime_type=image.content_type or "image/jpeg",
            crop_hint=crop,
            filename_hint=image.filename,
        )
        diag_crop = ai_result.crop
        diag_disease = ai_result.disease_name
        diag_conf = ai_result.confidence
        diag_treat = ai_result.treatment
        raw_ai = ai_result.model_dump_json()

    # KVK triage: confidence < 0.70
    needs_kvk = diag_conf < settings.KVK_CONFIDENCE_THRESHOLD
    kvk_status = "pending" if needs_kvk else "not_required"

    diag = Diagnosis(
        farmer_id         = farmer.id if farmer else None,
        crop              = diag_crop,
        disease_name      = diag_disease,
        confidence        = diag_conf,
        treatment         = diag_treat,
        gps_lat           = gps_lat,
        gps_lon           = gps_lon,
        image_path        = rel_path,
        source            = DiagnosisSource.MANUAL_UPLOAD,
        needs_kvk_review  = needs_kvk,
        kvk_review_status = kvk_status,
        raw_ai_response   = raw_ai,
        notification_sent = False,
    )
    db.add(diag)
    db.commit()
    db.refresh(diag)

    if needs_kvk:
        send_kvk_review_alert(diag, farmer)
    else:
        if farmer:
            send_farmer_notification(
                farmer=farmer,
                report_type="diagnosis",
                summary=f"Detected: {diag_crop} - {diag_disease} (Confidence: {diag_conf*100:.0f}%).",
                reference_id=diag.id,
            )
            diag.notification_sent = True
            db.commit()

    return diag

