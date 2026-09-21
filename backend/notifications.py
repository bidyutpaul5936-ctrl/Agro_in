"""
notifications.py – Notification dispatching stub (WhatsApp / SMS) for AgroIn.

Handles notifying farmers when soil or diagnosis reports are ready,
as well as escalating low-confidence diagnoses to Krishi Vigyan Kendra (KVK) experts.
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from backend.models import Diagnosis, FarmerProfile

logger = logging.getLogger("agro_in.notifications")


def send_farmer_notification(
    farmer: FarmerProfile,
    report_type: str,
    summary: str,
    reference_id: int,
    channel: str = "whatsapp",
) -> Dict[str, Any]:
    """
    Stub to send a WhatsApp or SMS notification to a farmer when a new report is ready.

    In production, this integrates with WhatsApp Business API (e.g. Twilio / Gupshup / Infobip)
    or localized SMS gateways (NIC / CDAC for agri-advisories).
    """
    timestamp = datetime.now(timezone.utc).isoformat()
    phone = farmer.phone
    name = farmer.name

    if report_type == "soil":
        message = (
            f"Namaste {name}! Your field's Soil Health Report #{reference_id} is ready. "
            f"{summary} View your detailed NPK and moisture levels in AgroIn."
        )
    elif report_type == "diagnosis":
        message = (
            f"Namaste {name}! Your Crop Diagnosis Report #{reference_id} is ready. "
            f"{summary} Follow recommended treatment steps in the AgroIn app."
        )
    else:
        message = f"Namaste {name}! A new agri-advisory report #{reference_id} is ready."

    # Format realistic notification log
    logger.info(
        f"\n{'='*60}\n"
        f" [NOTIFICATION STUB - {channel.upper()}]\n"
        f" To: {name} ({phone})\n"
        f" Time: {timestamp}\n"
        f" Message: {message}\n"
        f"{'='*60}"
    )

    return {
        "status": "delivered_stub",
        "channel": channel,
        "recipient_phone": phone,
        "recipient_name": name,
        "report_type": report_type,
        "reference_id": reference_id,
        "message": message,
        "timestamp": timestamp,
    }


def send_kvk_review_alert(
    diagnosis: Diagnosis,
    farmer: Optional[FarmerProfile] = None,
    kvk_center: str = "KVK Ahmednagar / Nashik Regional Centre",
) -> Dict[str, Any]:
    """
    Stub to alert Krishi Vigyan Kendra (KVK) agricultural scientists when an AI diagnosis
    confidence score falls below the threshold (< 0.70).
    """
    timestamp = datetime.now(timezone.utc).isoformat()
    farmer_info = f"{farmer.name} ({farmer.phone}, {farmer.location})" if farmer else "Unassigned / Rover GPS Sector"

    alert_message = (
        f"[KVK REVIEW QUEUE] Low confidence diagnosis (#{diagnosis.id}) detected. "
        f"Crop: {diagnosis.crop}, Suspected: {diagnosis.disease_name}, "
        f"Confidence: {diagnosis.confidence * 100:.1f}%. "
        f"Farmer: {farmer_info}. Image: {diagnosis.image_path}. "
        f"Awaiting scientist manual verification before notifying farmer."
    )

    logger.warning(
        f"\n{'#'*60}\n"
        f" [KVK SCIENTIST ALERT - {kvk_center}]\n"
        f" Time: {timestamp}\n"
        f" {alert_message}\n"
        f"{'#'*60}"
    )

    return {
        "status": "queued_for_kvk_review",
        "diagnosis_id": diagnosis.id,
        "crop": diagnosis.crop,
        "disease_name": diagnosis.disease_name,
        "confidence": diagnosis.confidence,
        "kvk_center": kvk_center,
        "timestamp": timestamp,
    }
