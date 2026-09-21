"""
test_backend.py - Integration and unit tests for AgroIn FastAPI backend using standard unittest.
"""

import os
import sys
import io
import unittest
from fastapi.testclient import TestClient

# Ensure root directory is on PYTHONPATH
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from backend.main import app
from backend.database import SessionLocal
from backend.models import RoverDevice, FarmerProfile
from backend.auth import hash_api_key

TEST_DEVICE_ID = "ROVER-TEST-999"
TEST_RAW_KEY = "super_secret_test_key_1234567890"


class TestAgroInBackend(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)
        db = SessionLocal()
        try:
            device = db.query(RoverDevice).filter(RoverDevice.device_id == TEST_DEVICE_ID).first()
            if not device:
                device = RoverDevice(
                    device_id=TEST_DEVICE_ID,
                    api_key_hash=hash_api_key(TEST_RAW_KEY),
                    assigned_area="Test Sector 42",
                )
                db.add(device)
                db.commit()
                db.refresh(device)
            cls.device = device

            farmer = db.query(FarmerProfile).first()
            if not farmer:
                farmer = FarmerProfile(
                    name="Test Farmer",
                    phone="+919999999999",
                    location="Pune, MH",
                    assigned_field="Plot 1",
                )
                db.add(farmer)
                db.commit()
                db.refresh(farmer)
            cls.farmer = farmer
        finally:
            db.close()

    def test_01_health(self):
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ok")

    def test_02_get_farmers(self):
        response = self.client.get("/api/v1/farmers/")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIsInstance(data, list)
        self.assertGreaterEqual(len(data), 1)

    def test_03_rover_auth_missing_headers(self):
        response = self.client.post("/api/v1/rover/ingest/soil", json={
            "nitrogen": 110, "phosphorus": 25, "potassium": 140, "ph": 6.5
        })
        self.assertEqual(response.status_code, 401)

    def test_04_rover_auth_invalid_credentials(self):
        headers = {
            "X-Device-ID": TEST_DEVICE_ID,
            "X-API-Key": "wrong_key_xyz",
        }
        response = self.client.post("/api/v1/rover/ingest/soil", json={
            "nitrogen": 110, "phosphorus": 25, "potassium": 140, "ph": 6.5
        }, headers=headers)
        self.assertEqual(response.status_code, 401)

    def test_05_rover_ingest_soil_success(self):
        headers = {
            "X-Device-ID": TEST_DEVICE_ID,
            "X-API-Key": TEST_RAW_KEY,
        }
        payload = {
            "nitrogen": 135.5,
            "phosphorus": 30.2,
            "potassium": 180.0,
            "ph": 6.9,
            "ec": 0.45,
            "moisture": 48.0,
            "co2_activity_score": 3.8,
            "bulk_density": 1.22,
            "gps_lat": 19.8001,
            "gps_lon": 74.5002,
            "farmer_id": self.farmer.id,
        }
        response = self.client.post("/api/v1/rover/ingest/soil", json=payload, headers=headers)
        self.assertEqual(response.status_code, 201)
        res_data = response.json()
        self.assertEqual(res_data["nitrogen"], 135.5)
        self.assertEqual(res_data["ph"], 6.9)
        self.assertEqual(res_data["rover_device_id"], self.device.id)

    def test_06_rover_ingest_diagnosis_success(self):
        headers = {
            "X-Device-ID": TEST_DEVICE_ID,
            "X-API-Key": TEST_RAW_KEY,
        }
        payload = {
            "crop": "Cotton",
            "disease_name": "Leaf Curl Virus",
            "confidence": 0.91,
            "treatment": "Spray systemic insecticide for whitefly vector control. Destroy infected plants.",
            "farmer_id": self.farmer.id,
        }
        response = self.client.post("/api/v1/rover/ingest/diagnosis", json=payload, headers=headers)
        self.assertEqual(response.status_code, 201)
        res_data = response.json()
        self.assertEqual(res_data["crop"], "Cotton")
        self.assertEqual(res_data["source"], "rover")
        self.assertEqual(res_data["rover_device_id"], self.device.id)

    def test_07_manual_diagnosis_upload(self):
        fake_image_file = io.BytesIO(b"\xff\xd8\xff\xe0\x00\x10JFIFfakeimagecontent")
        response = self.client.post(
            "/api/v1/diagnoses/manual",
            data={
                "farmer_id": str(self.farmer.id),
                "crop": "Wheat",
                "disease_name": "Rust",
                "confidence": "0.85",
                "treatment": "Apply Propiconazole 25 EC",
            },
            files={
                "image": ("leaf.jpg", fake_image_file, "image/jpeg")
            }
        )
        self.assertEqual(response.status_code, 201)
        res_data = response.json()
        self.assertEqual(res_data["crop"], "Wheat")
        self.assertEqual(res_data["source"], "manual_upload")
        self.assertIsNotNone(res_data["image_path"])

    def test_08_seed_listings(self):
        response = self.client.get("/api/v1/seeds/")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIsInstance(data, list)
        self.assertGreaterEqual(len(data), 1)

    def test_09_rover_soil_reading_gps_nearest_match(self):
        # Shirdi coordinates close to Ramesh Patil (19.7665, 74.4824)
        headers = {
            "X-Device-ID": TEST_DEVICE_ID,
            "X-API-Key": TEST_RAW_KEY,
        }
        payload = {
            "nitrogen": 142.0,
            "phosphorus": 29.0,
            "potassium": 195.0,
            "ph": 6.7,
            "moisture": 52.0,
            "gps_lat": 19.7668,
            "gps_lon": 74.4826,
        }
        # Test both direct route /rover/soil-reading and /api/v1/rover/soil-reading
        response = self.client.post("/rover/soil-reading", json=payload, headers=headers)
        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertEqual(data["farmer_name"], "Ramesh Patil")
        self.assertIsNotNone(data["matched_distance_meters"])
        self.assertLess(data["matched_distance_meters"], 100.0)  # within 100 meters
        self.assertEqual(data["notification_status"], "delivered_stub")

    def test_10_rover_soil_reading_unauthorized(self):
        payload = {
            "ph": 7.0,
            "gps_lat": 19.7668,
            "gps_lon": 74.4826,
            "rover_device_id": TEST_DEVICE_ID,
            "api_key": "wrong_key_12345",
        }
        response = self.client.post("/rover/soil-reading", json=payload)
        self.assertEqual(response.status_code, 401)

    def test_11_rover_plant_photo_high_confidence(self):
        fake_photo = io.BytesIO(b"\xff\xd8\xff\xe0\x00\x10JFIFhealthy_leaf_photo_data")
        headers = {
            "X-Device-ID": TEST_DEVICE_ID,
            "X-API-Key": TEST_RAW_KEY,
        }
        response = self.client.post(
            "/rover/plant-photo",
            data={
                "crop_hint": "Tomato",
                "gps_lat": "19.7665",
                "gps_lon": "74.4824",
            },
            files={
                "image": ("tomato_leaf.jpg", fake_photo, "image/jpeg"),
            },
            headers=headers,
        )
        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertEqual(data["crop"], "Tomato")
        self.assertGreaterEqual(data["confidence"], 0.70)
        self.assertFalse(data["needs_kvk_review"])
        self.assertEqual(data["notification_status"], "notified_farmer")
        self.assertIn("Mancozeb", data["treatment"])
        self.assertGreaterEqual(len(data["urgent_steps"]), 1)

    def test_12_rover_plant_photo_low_confidence_kvk_triage(self):
        # low_conf in filename triggers fallback low-confidence (<0.70) simulation
        fake_photo = io.BytesIO(b"\xff\xd8\xff\xe0\x00\x10JFIFblurry_leaf_photo")
        headers = {
            "X-Device-ID": TEST_DEVICE_ID,
            "X-API-Key": TEST_RAW_KEY,
        }
        response = self.client.post(
            "/rover/plant-photo",
            data={
                "gps_lat": "19.7665",
                "gps_lon": "74.4824",
            },
            files={
                "image": ("low_conf_ambiguous.jpg", fake_photo, "image/jpeg"),
            },
            headers=headers,
        )
        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertLess(data["confidence"], 0.70)
        self.assertTrue(data["needs_kvk_review"])
        self.assertEqual(data["kvk_review_status"], "pending")
        self.assertEqual(data["notification_status"], "held_for_kvk_review")

    def test_13_manual_upload_fallback_endpoint(self):
        fake_photo = io.BytesIO(b"\xff\xd8\xff\xe0\x00\x10JFIFmanual_fallback_leaf")
        response = self.client.post(
            "/manual-upload",
            data={
                "farmer_id": str(self.farmer.id),
                "crop": "Cotton",
            },
            files={
                "image": ("cotton_sample.jpg", fake_photo, "image/jpeg"),
            },
        )
        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertEqual(data["crop"], "Cotton")
        self.assertEqual(data["source"], "manual_upload")
        self.assertIsNotNone(data["disease_name"])
        self.assertIsNotNone(data["treatment"])

    def test_14_crop_recommender_ml(self):
        from backend.crop_recommender import predict_ranked_crops
        # Simulate rice/cotton friendly high NPK & moisture
        recommendations = predict_ranked_crops(
            n=90.0, p=42.0, k=43.0, ph=6.5, moisture=75.0, temperature=26.0, humidity=80.0, rainfall=220.0
        )
        self.assertEqual(len(recommendations), 5)
        for i, rec in enumerate(recommendations, 1):
            self.assertEqual(rec["rank"], i)
            self.assertIn("crop", rec)
            self.assertGreaterEqual(rec["confidence_pct"], 0.0)
            self.assertLessEqual(rec["confidence_pct"], 100.0)
            self.assertIn(rec["suitability_badge"], ["Highly Recommended", "Suitable", "Moderate Match"])
            self.assertTrue(len(rec["reasoning"]) > 10)

    def test_15_soil_indicators_evaluation(self):
        from backend.crop_recommender import evaluate_soil_health
        from backend.models import SoilReading
        reading = SoilReading(
            farmer_id=self.farmer.id,
            nitrogen=145.0, # Good
            phosphorus=25.0,  # Good
            potassium=80.0,  # Low / Warning
            ph=6.8,  # Good
            moisture=45.0, # Good
            ec=1.1,  # Moderate Salinity / Warning
        )
        indicators = evaluate_soil_health(reading)
        param_map = {ind["param"]: ind for ind in indicators}
        self.assertIn("n", param_map)
        self.assertIn("p", param_map)
        self.assertIn("k", param_map)
        self.assertIn("ph", param_map)
        self.assertIn("moisture", param_map)
        self.assertIn("ec", param_map)

        # Check structure
        n_ind = param_map["n"]
        self.assertEqual(n_ind["status"], "good")
        self.assertEqual(n_ind["badge"], "Optimal")

        k_ind = param_map["k"]
        self.assertEqual(k_ind["status"], "warning")
        self.assertEqual(k_ind["badge"], "Low")

    def test_16_dashboard_json(self):
        # 1. Via query param ?format=json
        res1 = self.client.get(f"/dashboard/{self.farmer.id}?format=json")
        self.assertEqual(res1.status_code, 200)
        data = res1.json()
        self.assertIn("farmer", data)
        self.assertEqual(data["farmer"]["id"], self.farmer.id)
        self.assertIn("crop_recommendations", data)
        self.assertEqual(len(data["crop_recommendations"]), 5)
        self.assertIn("soil_indicators", data)
        self.assertIn("past_diagnoses", data)

        # 2. Via api/v1 prefix
        res2 = self.client.get(f"/api/v1/dashboard/{self.farmer.id}", headers={"Accept": "application/json"})
        self.assertEqual(res2.status_code, 200)
        self.assertEqual(res2.json()["farmer"]["name"], self.farmer.name)

    def test_17_dashboard_html(self):
        res = self.client.get(f"/dashboard/{self.farmer.id}", headers={"Accept": "text/html"})
        self.assertEqual(res.status_code, 200)
        self.assertIn("text/html", res.headers.get("content-type", ""))
        html = res.text
        self.assertIn(self.farmer.name, html)
        self.assertIn("AgroIn Advisory", html)
        self.assertIn("Ranked Crop Recommendations", html)
        self.assertIn("Latest Soil Health Analysis", html)
        self.assertIn("Crop Disease Diagnosis History", html)

    def test_18_pluggable_diagnosis_architecture(self):
        import asyncio
        from backend.diagnosis_engine import get_diagnosis_engine, BaseDiagnosisEngine, LocalModelDiagnosisEngine, GeminiDiagnosisEngine

        engine = get_diagnosis_engine()
        self.assertIsInstance(engine, BaseDiagnosisEngine)

        # Test local model engine graceful fallback
        local_eng = LocalModelDiagnosisEngine(local_url="http://127.0.0.1:99999/predict")
        res = asyncio.run(local_eng.diagnose(b"dummy_image_data", crop_hint="Cotton", filename="sample.jpg"))
        self.assertEqual(res.crop, "Cotton")
        self.assertIsNotNone(res.disease_name)
        self.assertGreater(len(res.treatment), 0)


if __name__ == "__main__":
    unittest.main()


