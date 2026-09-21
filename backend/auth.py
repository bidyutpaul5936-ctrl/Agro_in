"""
auth.py – Rover device authentication.

How it works
------------
Every request to a rover-only ingestion endpoint must carry two headers:

    X-Device-ID:  <device_id registered in rover_devices table>
    X-API-Key:    <plain-text API key issued at registration>

The dependency ``require_rover`` looks up the device by ``device_id``,
verifies the bcrypt hash, checks ``is_active``, then stamps ``last_seen_at``
and returns the ``RoverDevice`` ORM object.

Raising HTTP 401 for any auth failure prevents timing-based device
enumeration (we always verify the hash even when the device is unknown,
using a dummy hash compare).

Admin operations (registering / deactivating devices) are intentionally
left to direct database access or a separate admin CLI for now.
"""

from datetime import datetime, timezone
from typing import Annotated
import bcrypt
from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models import RoverDevice

# ── Bcrypt hashing helpers ──────────────────────────────────────────────────

def hash_api_key(plain_key: str) -> str:
    """Return the bcrypt hash of a plain-text API key."""
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(plain_key.encode("utf-8"), salt).decode("utf-8")


def verify_api_key(plain_key: str, hashed_key: str) -> bool:
    """Return True if ``plain_key`` matches the stored bcrypt hash."""
    try:
        return bcrypt.checkpw(plain_key.encode("utf-8"), hashed_key.encode("utf-8"))
    except Exception:
        return False


# A constant-time dummy hash used when a device_id is not found,
# so the response time is indistinguishable from a found-but-wrong-key case.
_DUMMY_HASH = hash_api_key("__dummy_key_for_timing_safety__")


def authenticate_rover_device(
    device_id: str | None,
    api_key: str | None,
    db: Session,
) -> RoverDevice:
    """
    Validates rover credentials (device_id + plain-text api_key) against bcrypt hash.
    Raises HTTPException 401 on missing/invalid, 403 on deactivated.
    """
    _UNAUTH = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or missing rover credentials.",
        headers={"WWW-Authenticate": "X-Device-ID / X-API-Key"},
    )

    if not device_id or not api_key:
        raise _UNAUTH

    rover: RoverDevice | None = (
        db.query(RoverDevice)
        .filter(RoverDevice.device_id == device_id)
        .first()
    )

    # Constant-time dummy hash prevents timing attacks
    stored_hash = rover.api_key_hash if rover else _DUMMY_HASH
    key_valid = verify_api_key(api_key, stored_hash)

    if not rover or not key_valid:
        raise _UNAUTH

    if not rover.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Rover device is deactivated. Contact the admin.",
        )

    # Stamp last_seen
    rover.last_seen_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(rover)

    return rover


# ── FastAPI dependency ──────────────────────────────────────────────────────

async def require_rover(
    x_device_id: Annotated[str | None, Header(alias="X-Device-ID")] = None,
    x_api_key:   Annotated[str | None, Header(alias="X-API-Key")]   = None,
    db: Session = Depends(get_db),
) -> RoverDevice:
    """
    FastAPI dependency that authenticates a rover device via headers.
    """
    return authenticate_rover_device(x_device_id, x_api_key, db)

