# AgroIn Agri-Advisory System — Full Walkthrough

## What was built

A complete farmer-facing agri-advisory web system with a FastAPI + SQLite backend,
designed for rover-pushed data over patchy connectivity.

---

## Feature Summary

### 1. Wireframes / Frontend ([wireframes.html](file:///c:/Users/AYUSH/OneDrive/Desktop/agro_in/Agro_in/wireframes.html))
Low-bandwidth, full-screen HTML/CSS UI with:
- Home / Landing page with "Diagnose my crop" and "View soil report" actions
- Photo upload page with drag-and-drop + mobile camera capture
- Diagnosis result page (crop, disease, confidence, treatment steps)
- Soil report dashboard with NPK/pH/moisture color indicators
- Seed exchange listing page
- Fully responsive across mobile, tablet, and desktop (max 1280px, CSS grid layout)
- System fonts, large tap targets, simple Hindi-friendly language

---

### 2. FastAPI Backend ([backend/](file:///c:/Users/AYUSH/OneDrive/Desktop/agro_in/Agro_in/backend/))

#### Database Models ([models.py](file:///c:/Users/AYUSH/OneDrive/Desktop/agro_in/Agro_in/backend/models.py))
| Table | Key fields |
|---|---|
| `farmer_profiles` | name, phone, location, assigned_field, field_lat/lon |
| `rover_devices` | device_id, api_key_hash (bcrypt), assigned_area |
| `soil_readings` | N, P, K, pH, EC, moisture, CO₂, GPS, farmer_id, rover_id |
| `diagnoses` | crop, disease_name, confidence, treatment, image_path, source, KVK status |
| `seed_listings` | crop_name, variety, quantity_kg, price_per_kg, listing_type |

#### Authentication ([auth.py](file:///c:/Users/AYUSH/OneDrive/Desktop/agro_in/Agro_in/backend/auth.py))
- Rover-only auth: `X-Device-ID` + `X-API-Key` headers required on all ingest endpoints
- Bcrypt hash verification; raw keys never stored

#### Rover Ingest Endpoints ([routers/rover.py](file:///c:/Users/AYUSH/OneDrive/Desktop/agro_in/Agro_in/backend/routers/rover.py))
- `POST /rover/soil-reading` — accepts sensor values + GPS, nearest-farmer geo-match, WhatsApp/SMS stub notification
- `POST /rover/plant-photo` — image + rover ID → Gemini/local diagnosis → confidence < 0.70 → KVK review queue; > 0.70 → farmer notified
- `POST /manual-upload` — farmer-initiated fallback reusing same diagnosis logic

#### Farmer Dashboard ([routers/dashboard.py](file:///c:/Users/AYUSH/OneDrive/Desktop/agro_in/Agro_in/backend/routers/dashboard.py))
- `GET /dashboard/{farmer_id}` — dual format:
  - **Browser** (`Accept: text/html`): full responsive HTML dashboard
  - **API client** (`?format=json` or `Accept: application/json`): `FarmerDashboardResponse` JSON
- Also mounted at `/api/v1/dashboard/{farmer_id}`
- Shows: farmer profile, latest soil reading, color-coded nutrient indicators, ranked crop recommendations, past diagnoses with KVK status

---

### 3. Pluggable Diagnosis Engine ([diagnosis_engine/](file:///c:/Users/AYUSH/OneDrive/Desktop/agro_in/Agro_in/backend/diagnosis_engine/))

Fully decoupled from routers — swap Gemini ↔ local model with one config change:

```
DIAGNOSIS_BACKEND=gemini    # use Google Gemini (default)
DIAGNOSIS_BACKEND=local     # use locally-hosted fine-tuned model
```

| File | Purpose |
|---|---|
| `base.py` | `BaseDiagnosisEngine` ABC + `CropDiagnosisResult` Pydantic schema |
| `gemini_engine.py` | Google Gemini multimodal API with structured JSON output |
| `local_engine.py` | HTTP POST to local inference server; graceful rulebook fallback |
| `factory.py` | `get_diagnosis_engine()` reads `settings.DIAGNOSIS_BACKEND` |

Both engines implement `async diagnose(image_bytes, crop_hint, ...)` → `CropDiagnosisResult`.
Zero breaking changes to rover or farmer API contracts when switching backends.

---

### 4. ML Crop Recommender ([crop_recommender.py](file:///c:/Users/AYUSH/OneDrive/Desktop/agro_in/Agro_in/backend/crop_recommender.py))

- Synthesizes Kaggle Crop Recommendation dataset (2,200 rows, 22 crop classes)
- Trains `RandomForestClassifier` on first run → saves to `backend/models_ml/crop_recommender.joblib`
- `predict_ranked_crops(n, p, k, ph, moisture, temperature, rainfall)` → top-5 ranked crops with suitability badges and agronomic reasoning
- `evaluate_soil_health(reading)` → per-parameter indicators:
  - ✅ **Good** (green `#16a34a`)
  - ⚠️ **Warning** (amber `#e8a000`)
  - 🔴 **Bad** (red `#dc2626`)

---

## Test Results

All **18 / 18 tests pass** in 11.35s:

| # | Test | Status |
|---|---|---|
| 01 | Health check | ✅ |
| 02 | Get farmers list | ✅ |
| 03 | Rover auth: missing headers | ✅ |
| 04 | Rover auth: invalid credentials | ✅ |
| 05 | Rover soil ingest (success) | ✅ |
| 06 | Rover diagnosis ingest | ✅ |
| 07 | Manual diagnosis upload | ✅ |
| 08 | Seed listings | ✅ |
| 09 | Rover soil reading GPS nearest match | ✅ |
| 10 | Rover soil reading unauthorized | ✅ |
| 11 | Rover plant photo — high confidence | ✅ |
| 12 | Rover plant photo — low confidence → KVK triage | ✅ |
| 13 | Manual upload fallback endpoint | ✅ |
| 14 | ML crop recommender (5 ranked crops) | ✅ |
| 15 | Soil indicators evaluation (good/warning/bad) | ✅ |
| 16 | Dashboard JSON endpoint | ✅ |
| 17 | Dashboard HTML endpoint | ✅ |
| 18 | Pluggable diagnosis architecture | ✅ |

---

## Running Locally

```powershell
# Start the backend
python -m uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
```

| URL | Description |
|---|---|
| `http://localhost:8000/` | API root / docs redirect |
| `http://localhost:8000/docs` | FastAPI Swagger UI |
| `http://localhost:8000/dashboard/1` | Farmer 1 dashboard (HTML) |
| `http://localhost:8000/dashboard/1?format=json` | Farmer 1 dashboard (JSON) |
| `http://localhost:8000/api/v1/dashboard/1` | Dashboard via versioned prefix |
| `file:///c:/Users/AYUSH/OneDrive/Desktop/agro_in/Agro_in/wireframes.html` | Frontend wireframes |

---

## Config ([backend/config.py](file:///c:/Users/AYUSH/OneDrive/Desktop/agro_in/Agro_in/backend/config.py))

| Variable | Default | Notes |
|---|---|---|
| `DIAGNOSIS_BACKEND` | `gemini` | `gemini` or `local` |
| `GEMINI_API_KEY` | _(empty)_ | Set for live Gemini calls |
| `GEMINI_MODEL` | `gemini-1.5-flash` | |
| `LOCAL_MODEL_ENDPOINT` | `http://localhost:8080/v1/diagnose` | For local model |
| `KVK_CONFIDENCE_THRESHOLD` | `0.70` | Below → KVK review queue |

---

## Architecture Diagram

```
Rover ──[HTTPS + device_id/api_key]──▶ POST /rover/soil-reading
                                       POST /rover/plant-photo
                                              │
                                    ┌─────────▼─────────┐
                                    │  Rover Router      │
                                    │  - Auth middleware  │
                                    │  - GPS geo-match   │
                                    │  - Diagnosis engine│
                                    └────────┬───────────┘
                                             │
                          ┌──────────────────▼──────────────────┐
                          │     Pluggable Diagnosis Engine        │
                          │  ┌───────────────┐ ┌──────────────┐ │
                          │  │ GeminiEngine  │ │ LocalEngine  │ │
                          │  │ (cloud API)   │ │ (fine-tuned) │ │
                          │  └───────────────┘ └──────────────┘ │
                          │  factory.py → DIAGNOSIS_BACKEND env  │
                          └──────────────────┬───────────────────┘
                                             │
                                     SQLite Database
                                             │
Farmer ──[Browser]──▶ GET /dashboard/{id} ──┘
                          │
                   ┌──────▼──────────────────────────┐
                   │  HTML Dashboard                   │
                   │  - Soil indicators (🟢🟡🔴)       │
                   │  - ML crop recommendations        │
                   │  - Diagnosis history + KVK status │
                   └──────────────────────────────────┘
```
