"""
geo.py – Geospatial calculations and nearest-field matching.

Uses the Haversine formula to compute great-circle distance between coordinates
on the Earth's surface.
"""

import math
from typing import Optional, Tuple
from sqlalchemy.orm import Session

from backend.models import FarmerProfile

# Mean radius of Earth in meters
EARTH_RADIUS_METERS = 6371000.0


def haversine_distance_meters(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Compute great-circle distance between two GPS coordinates in meters.
    """
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = (
        math.sin(delta_phi / 2.0) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2.0) ** 2
    )
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return EARTH_RADIUS_METERS * c


def find_nearest_farmer_field(
    db: Session,
    lat: float,
    lon: float,
) -> Tuple[Optional[FarmerProfile], Optional[float]]:
    """
    Given a rover GPS latitude and longitude, find the nearest active farmer whose field
    coordinates are registered.

    Returns:
        (nearest_farmer, distance_meters) or (None, None) if no active farmers exist.
    """
    active_farmers = db.query(FarmerProfile).filter(FarmerProfile.is_active == True).all()
    if not active_farmers:
        return None, None

    # Filter farmers with registered GPS coordinates
    farmers_with_coords = [
        f for f in active_farmers if f.field_lat is not None and f.field_lon is not None
    ]

    if not farmers_with_coords:
        # Fallback to the first active farmer if no farmers have explicit coordinates yet
        return active_farmers[0], None

    nearest_farmer = None
    min_dist = float("inf")

    for farmer in farmers_with_coords:
        dist = haversine_distance_meters(lat, lon, farmer.field_lat, farmer.field_lon)
        if dist < min_dist:
            min_dist = dist
            nearest_farmer = farmer

    return nearest_farmer, min_dist
