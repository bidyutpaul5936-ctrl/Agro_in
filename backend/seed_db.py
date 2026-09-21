"""
seed_db.py – One-time script to insert sample data for development.

Run from the project root (Agro_in/):
    python -m backend.seed_db
"""

import secrets
import sys
import os

# ── Make sure the project root is on the path ──────────────────────────────
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

# Ensure UTF-8 output on Windows consoles
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from backend.auth import hash_api_key
from backend.database import Base, SessionLocal, engine
from backend.models import (
    Diagnosis, DiagnosisSource, FarmerProfile, RoverDevice,
    SeedListing, ListingType, SoilReading,
)


def seed():
    print("Creating tables ...")
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    try:
        # ── Farmers ────────────────────────────────────────────────────────
        if db.query(FarmerProfile).count() == 0:
            farmers = [
                FarmerProfile(
                    name="Ramesh Patil",
                    phone="+919876543210",
                    location="Shirdi, Ahmednagar, MH",
                    assigned_field="Field A - 1.2 acres (Shirdi East)",
                    field_lat=19.7665,
                    field_lon=74.4824,
                ),
                FarmerProfile(
                    name="Priya Deshmukh",
                    phone="+919765432109",
                    location="Kopargaon, Ahmednagar, MH",
                    assigned_field="Field B - 2.0 acres (Godavari Canal)",
                    field_lat=19.8875,
                    field_lon=74.4785,
                ),
                FarmerProfile(
                    name="Kavita Shinde",
                    phone="+919654321098",
                    location="Nashik, MH",
                    assigned_field="Field C - 0.8 acres (Dindori Road)",
                    field_lat=19.9975,
                    field_lon=73.7898,
                ),
            ]
            db.add_all(farmers)
            db.flush()
            print(f"  [+] Inserted {len(farmers)} farmers.")
        else:
            # Update existing farmers with field coordinates if not yet set
            f_ramesh = db.query(FarmerProfile).filter(FarmerProfile.phone == "+919876543210").first()
            if f_ramesh and f_ramesh.field_lat is None:
                f_ramesh.field_lat, f_ramesh.field_lon = 19.7665, 74.4824
            f_priya = db.query(FarmerProfile).filter(FarmerProfile.phone == "+919765432109").first()
            if f_priya and f_priya.field_lat is None:
                f_priya.field_lat, f_priya.field_lon = 19.8875, 74.4785
            f_kavita = db.query(FarmerProfile).filter(FarmerProfile.phone == "+919654321098").first()
            if f_kavita and f_kavita.field_lat is None:
                f_kavita.field_lat, f_kavita.field_lon = 19.9975, 73.7898
            db.commit()
            print("  [-] Farmers already exist, coordinates updated.")

        # ── Rover devices ──────────────────────────────────────────────────
        raw_keys: dict[str, str] = {}
        if db.query(RoverDevice).count() == 0:
            devices_data = [
                ("ROVER-MH-001", "Ahmednagar West Block"),
                ("ROVER-MH-002", "Nashik Valley Zone"),
            ]
            for device_id, area in devices_data:
                raw_key = secrets.token_urlsafe(48)
                raw_keys[device_id] = raw_key
                db.add(RoverDevice(
                    device_id     = device_id,
                    api_key_hash  = hash_api_key(raw_key),
                    assigned_area = area,
                ))
            db.flush()
            print(f"  [+] Inserted {len(devices_data)} rover devices.")
            print()
            print("  +---------------------------------------------------------+")
            print("  |  SAVE THESE KEYS - they will NOT be shown again!        |")
            print("  +---------------------------------------------------------+")
            for did, key in raw_keys.items():
                print(f"  |  {did:20s}  ->  {key}  |")
            print("  +---------------------------------------------------------+")
            print()
        else:
            print("  – Rover devices already exist, skipping.")

        # ── Soil readings ──────────────────────────────────────────────────
        if db.query(SoilReading).count() == 0:
            rover = db.query(RoverDevice).first()
            farmer = db.query(FarmerProfile).first()
            readings = [
                SoilReading(nitrogen=120, phosphorus=28, potassium=165, ph=6.8, ec=0.4,
                            moisture=42, co2_activity_score=3.2, bulk_density=1.25,
                            gps_lat=19.7665, gps_lon=74.4824,
                            farmer_id=farmer.id if farmer else None,
                            rover_device_id=rover.id if rover else None),
                SoilReading(nitrogen=180, phosphorus=35, potassium=200, ph=7.1, ec=0.5,
                            moisture=55, co2_activity_score=4.1, bulk_density=1.18,
                            gps_lat=19.7700, gps_lon=74.4900,
                            farmer_id=farmer.id if farmer else None,
                            rover_device_id=rover.id if rover else None),
            ]
            db.add_all(readings)
            db.flush()
            print(f"  [+] Inserted {len(readings)} soil readings.")
        else:
            print("  [-] Soil readings already exist, skipping.")

        # ── Diagnoses ──────────────────────────────────────────────────────
        if db.query(Diagnosis).count() == 0:
            rover  = db.query(RoverDevice).first()
            farmer = db.query(FarmerProfile).first()
            db.add(Diagnosis(
                crop="Tomato", disease_name="Late Blight", confidence=0.82,
                treatment="Apply Mancozeb 2g/L. Remove affected leaves. Avoid overhead watering.",
                source=DiagnosisSource.ROVER,
                farmer_id=farmer.id if farmer else None,
                rover_device_id=rover.id if rover else None,
            ))
            db.flush()
            print("  [+] Inserted 1 sample diagnosis.")
        else:
            print("  [-] Diagnoses already exist, skipping.")

        # ── Seed listings ──────────────────────────────────────────────────
        if db.query(SeedListing).count() == 0:
            farmers_all = db.query(FarmerProfile).all()
            listings = [
                SeedListing(farmer_id=farmers_all[0].id, crop_name="Tomato",  variety="Arka Vikas",
                            quantity_kg=10, price_per_kg=180, listing_type=ListingType.SELL,
                            location="Shirdi, MH", germination_pct=92),
                SeedListing(farmer_id=farmers_all[1].id, crop_name="Wheat",   variety="HD-2967",
                            quantity_kg=25, listing_type=ListingType.SWAP,
                            location="Kopargaon, MH", germination_pct=88,
                            description="Exchange for onion or soybean seeds."),
                SeedListing(farmer_id=farmers_all[2].id, crop_name="Onion",   variety="Nasik Red",
                            quantity_kg=5, price_per_kg=0, listing_type=ListingType.FREE,
                            location="Nashik, MH", germination_pct=79,
                            description="Self-collect only."),
            ]
            db.add_all(listings)
            db.flush()
            print(f"  [+] Inserted {len(listings)} seed listings.")
        else:
            print("  [-] Seed listings already exist, skipping.")

        db.commit()
        print("\nSeed complete successfully.")

    except Exception as exc:
        db.rollback()
        print(f"\n[!] Seed failed: {exc}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    seed()
