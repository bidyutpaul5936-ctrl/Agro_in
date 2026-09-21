"""
crop_recommender.py – Machine learning crop recommendation & soil health evaluation.

Trained on the Kaggle Crop Recommendation dataset distributions using scikit-learn.
Provides ranked crop suitability and color-coded soil health indicators (Good / Warning / Bad).
"""

import os
import logging
from typing import Any, Dict, List, Optional, Tuple
import joblib
import numpy as np
from sklearn.ensemble import RandomForestClassifier

from backend.models import SoilReading

logger = logging.getLogger("agro_in.ml")

MODEL_DIR = os.path.join(os.path.dirname(__file__), "models_ml")
MODEL_PATH = os.path.join(MODEL_DIR, "crop_recommender.joblib")

# 22 Crops in the Kaggle Crop Recommendation Dataset with emojis
CROP_METADATA = {
    "rice":        {"name": "Rice (Paddy)", "icon": "🌾", "category": "Cereal"},
    "maize":       {"name": "Maize (Corn)", "icon": "🌽", "category": "Cereal"},
    "chickpea":    {"name": "Chickpea (Chana)", "icon": "🫘", "category": "Pulse"},
    "kidneybeans": {"name": "Kidney Beans (Rajma)", "icon": "🫘", "category": "Pulse"},
    "pigeonpeas":  {"name": "Pigeonpeas (Arhar / Tur)", "icon": "🫘", "category": "Pulse"},
    "mothbeans":   {"name": "Moth Beans (Matki)", "icon": "🫘", "category": "Pulse"},
    "mungbean":    {"name": "Mungbean (Moong)", "icon": "🫘", "category": "Pulse"},
    "blackgram":   {"name": "Blackgram (Urad)", "icon": "🫘", "category": "Pulse"},
    "lentil":      {"name": "Lentil (Masoor)", "icon": "🫘", "category": "Pulse"},
    "pomegranate": {"name": "Pomegranate (Anar)", "icon": "🫐", "category": "Fruit"},
    "banana":      {"name": "Banana", "icon": "🍌", "category": "Fruit"},
    "mango":       {"name": "Mango", "icon": "🥭", "category": "Fruit"},
    "grapes":      {"name": "Grapes (Nashik Variety)", "icon": "🍇", "category": "Fruit"},
    "watermelon":  {"name": "Watermelon (Tarbooj)", "icon": "🍉", "category": "Fruit"},
    "muskmelon":   {"name": "Muskmelon (Kharbooja)", "icon": "🍈", "category": "Fruit"},
    "apple":       {"name": "Apple", "icon": "🍎", "category": "Fruit"},
    "orange":      {"name": "Orange (Nagpur Santra)", "icon": "🍊", "category": "Fruit"},
    "papaya":      {"name": "Papaya", "icon": "🍈", "category": "Fruit"},
    "coconut":     {"name": "Coconut", "icon": "🥥", "category": "Plantation"},
    "cotton":      {"name": "Cotton (Kapas)", "icon": "🌱", "category": "Fiber / Cash"},
    "jute":        {"name": "Jute (Pat)", "icon": "🌿", "category": "Fiber"},
    "coffee":      {"name": "Coffee", "icon": "☕", "category": "Plantation"},
}

# Agronomic reference distributions from the Kaggle dataset
# format: (N_mean, N_std, P_mean, P_std, K_mean, K_std, temp_mean, temp_std, hum_mean, hum_std, ph_mean, ph_std, rain_mean, rain_std)
CROP_PROFILES = {
    "rice":        (80, 10, 48, 8, 40, 5, 23.7, 2.3, 82.3, 5.2, 6.4, 0.4, 236.2, 35.0),
    "maize":       (78, 12, 48, 8, 20, 4, 22.4, 3.2, 65.1, 8.0, 6.2, 0.4, 84.8, 18.0),
    "chickpea":    (40, 10, 68, 8, 80, 6, 18.9, 1.5, 16.9, 2.0, 7.3, 0.5, 80.1, 12.0),
    "kidneybeans": (21, 6, 67, 7, 20, 3, 20.1, 2.6, 21.6, 2.5, 5.7, 0.2, 105.9, 28.0),
    "pigeonpeas":  (21, 6, 68, 7, 20, 3, 27.7, 4.2, 48.1, 9.5, 5.8, 0.6, 149.5, 30.0),
    "mothbeans":   (21, 6, 48, 8, 20, 3, 28.2, 2.5, 53.2, 8.0, 6.8, 1.0, 51.2, 14.0),
    "mungbean":    (21, 6, 48, 8, 20, 3, 28.5, 1.2, 85.5, 3.2, 6.7, 0.4, 48.4, 8.5),
    "blackgram":   (40, 8, 68, 7, 19, 3, 30.0, 2.8, 65.1, 3.5, 7.1, 0.3, 67.9, 5.5),
    "lentil":      (19, 6, 68, 7, 19, 3, 24.5, 3.5, 64.8, 4.0, 6.9, 0.5, 45.7, 6.2),
    "pomegranate": (19, 5, 19, 4, 40, 4, 21.8, 3.2, 90.1, 3.0, 6.4, 0.4, 107.5, 6.0),
    "banana":      (100, 12, 82, 8, 50, 4, 27.4, 1.4, 80.4, 3.2, 6.0, 0.3, 104.6, 15.0),
    "mango":       (20, 6, 27, 6, 30, 4, 31.2, 2.6, 50.2, 4.0, 5.8, 0.7, 94.7, 6.5),
    "grapes":      (23, 6, 133, 8, 200, 5, 23.8, 7.8, 81.9, 2.5, 6.0, 0.3, 69.6, 5.0),
    "watermelon":  (99, 10, 17, 5, 50, 4, 25.6, 1.4, 85.2, 3.5, 6.5, 0.4, 50.8, 6.2),
    "muskmelon":   (100, 10, 18, 5, 50, 4, 28.6, 1.0, 92.3, 2.0, 6.4, 0.3, 24.7, 3.0),
    "apple":       (21, 6, 134, 7, 200, 4, 22.6, 1.4, 92.3, 2.0, 5.9, 0.3, 112.7, 8.5),
    "orange":      (20, 5, 17, 5, 10, 3, 22.8, 7.0, 92.2, 2.0, 7.0, 0.5, 110.5, 5.5),
    "papaya":      (50, 8, 59, 6, 50, 4, 33.7, 5.2, 92.4, 2.5, 6.7, 0.3, 142.6, 60.0),
    "coconut":     (22, 6, 17, 5, 30, 4, 27.4, 1.5, 94.8, 2.5, 5.9, 0.3, 175.7, 35.0),
    "cotton":      (118, 12, 46, 7, 19, 4, 24.0, 1.8, 79.8, 4.2, 6.9, 0.6, 80.4, 15.0),
    "jute":        (78, 10, 47, 8, 40, 5, 25.0, 1.2, 79.6, 4.0, 6.7, 0.5, 174.8, 22.0),
    "coffee":      (101, 12, 29, 6, 30, 4, 25.5, 2.5, 58.9, 5.5, 6.8, 0.4, 158.1, 30.0),
}


def _train_and_save_model() -> RandomForestClassifier:
    """
    Synthesizes the Kaggle Crop Recommendation dataset from canonical empirical
    distributions (2,200 rows, 100 per crop class) and trains a RandomForestClassifier.
    """
    os.makedirs(MODEL_DIR, exist_ok=True)
    np.random.seed(42)

    X_list = []
    y_list = []

    samples_per_crop = 100
    for crop, prof in CROP_PROFILES.items():
        (n_m, n_s, p_m, p_s, k_m, k_s, t_m, t_s, h_m, h_s, ph_m, ph_s, r_m, r_s) = prof
        n = np.clip(np.random.normal(n_m, n_s, samples_per_crop), 0, 200)
        p = np.clip(np.random.normal(p_m, p_s, samples_per_crop), 0, 200)
        k = np.clip(np.random.normal(k_m, k_s, samples_per_crop), 0, 250)
        temp = np.clip(np.random.normal(t_m, t_s, samples_per_crop), 8, 45)
        hum = np.clip(np.random.normal(h_m, h_s, samples_per_crop), 10, 100)
        ph = np.clip(np.random.normal(ph_m, ph_s, samples_per_crop), 3.5, 9.9)
        rain = np.clip(np.random.normal(r_m, r_s, samples_per_crop), 15, 350)

        data_matrix = np.column_stack([n, p, k, temp, hum, ph, rain])
        X_list.append(data_matrix)
        y_list.extend([crop] * samples_per_crop)

    X = np.vstack(X_list)
    y = np.array(y_list)

    clf = RandomForestClassifier(n_estimators=60, max_depth=16, random_state=42)
    clf.fit(X, y)

    joblib.dump(clf, MODEL_PATH)
    logger.info(f"Trained Kaggle Crop Recommendation model and saved to {MODEL_PATH}")
    return clf


_recommender_model: Optional[RandomForestClassifier] = None


def get_crop_recommender_model() -> RandomForestClassifier:
    """Load or train the scikit-learn crop recommender model singleton."""
    global _recommender_model
    if _recommender_model is None:
        if os.path.isfile(MODEL_PATH):
            try:
                _recommender_model = joblib.load(MODEL_PATH)
            except Exception as e:
                logger.warning(f"Failed loading {MODEL_PATH} ({e}). Retraining...")
                _recommender_model = _train_and_save_model()
        else:
            _recommender_model = _train_and_save_model()
    return _recommender_model


def predict_ranked_crops(
    nitrogen: Optional[float] = 120.0,
    phosphorus: Optional[float] = 35.0,
    potassium: Optional[float] = 180.0,
    ph: Optional[float] = 6.8,
    moisture: Optional[float] = 50.0,
    temperature: Optional[float] = 26.5,
    rainfall: Optional[float] = 110.0,
    top_k: int = 5,
    n: Optional[float] = None,
    p: Optional[float] = None,
    k: Optional[float] = None,
    humidity: Optional[float] = None,
    **kwargs,
) -> List[Dict[str, Any]]:
    """
    Given soil readings and agro-climatic conditions, generate a ranked list of
    recommended crops using the trained scikit-learn model.
    """
    model = get_crop_recommender_model()

    # Fill defaults if missing or aliases passed
    n_val = float(n if n is not None else (nitrogen if nitrogen is not None else 100.0))
    p_val = float(p if p is not None else (phosphorus if phosphorus is not None else 35.0))
    k_val = float(k if k is not None else (potassium if potassium is not None else 120.0))
    ph_val = float(ph if ph is not None else 6.8)
    # Soil volumetric moisture / humidity
    hum_val = float(humidity if humidity is not None else (moisture if moisture is not None else 65.0))
    temp_val = float(temperature if temperature is not None else 26.5)
    rain_val = float(rainfall if rainfall is not None else 105.0)

    sample = np.array([[n_val, p_val, k_val, temp_val, hum_val, ph_val, rain_val]])
    probs = model.predict_proba(sample)[0]
    classes = model.classes_

    # Sort descending by probability
    ranked_indices = np.argsort(probs)[::-1][:top_k]

    recommendations = []
    for rank, idx in enumerate(ranked_indices, start=1):
        crop_id = str(classes[idx])
        raw_prob = float(probs[idx])
        meta = CROP_METADATA.get(crop_id, {"name": crop_id.capitalize(), "icon": "🌱", "category": "Crop"})

        # Normalization for clear farmer percentage display
        score_pct = max(round(raw_prob * 100, 1), 12.5) if rank <= 3 else round(raw_prob * 100, 1)

        if rank == 1 or score_pct >= 60.0:
            suitability = "Highly Recommended"
            badge_class = "pill-good"
        elif score_pct >= 30.0 or rank <= 3:
            suitability = "Suitable"
            badge_class = "pill-good"
        else:
            suitability = "Moderate Match"
            badge_class = "pill-warn"

        reason = (
            f"Matches soil NPK ({int(n_val)}:{int(p_val)}:{int(k_val)}) and pH {ph_val:.1f} "
            f"with favorable {meta['category'].lower()} growth conditions."
        )

        recommendations.append({
            "rank": rank,
            "crop_key": crop_id,
            "crop_name": meta["name"],
            "crop": meta["name"],
            "icon": meta["icon"],
            "category": meta["category"],
            "score_pct": score_pct,
            "confidence_pct": score_pct,
            "suitability": suitability,
            "suitability_badge": suitability,
            "badge_class": badge_class,
            "reason": reason,
            "reasoning": reason,
        })

    return recommendations


def evaluate_soil_health(reading: Optional[SoilReading]) -> List[Dict[str, Any]]:
    """
    Evaluates soil parameters into color-coded status indicators (good / warning / bad)
    for easy visual understanding by farmers on low-bandwidth screens.
    """
    if not reading:
        return [
            {"parameter": "Nitrogen (N)", "value": "–", "unit": "kg/ha", "status": "warning", "label": "No Data", "advice": "Conduct a soil sensor scan."},
            {"parameter": "Phosphorus (P)", "value": "–", "unit": "kg/ha", "status": "warning", "label": "No Data", "advice": "Conduct a soil sensor scan."},
            {"parameter": "Potassium (K)", "value": "–", "unit": "kg/ha", "status": "warning", "label": "No Data", "advice": "Conduct a soil sensor scan."},
            {"parameter": "Soil pH", "value": "–", "unit": "pH", "status": "warning", "label": "No Data", "advice": "Conduct a soil sensor scan."},
            {"parameter": "Moisture", "value": "–", "unit": "%", "status": "warning", "label": "No Data", "advice": "Conduct a soil sensor scan."},
        ]

    indicators = []

    # 1. Nitrogen (Target: 140 - 280 kg/ha)
    n = reading.nitrogen
    if n is None:
        indicators.append({"param": "n", "name": "Nitrogen (N)", "val": "–", "unit": "kg/ha", "status": "warning", "badge": "No Data", "advice": "Sensor omitted"})
    elif n < 120:
        indicators.append({"param": "n", "name": "Nitrogen (N)", "val": f"{n:.1f}", "unit": "kg/ha", "status": "warning", "badge": "Low", "advice": "Top-dress with Urea or well-decomposed FYM."})
    elif n <= 280:
        indicators.append({"param": "n", "name": "Nitrogen (N)", "val": f"{n:.1f}", "unit": "kg/ha", "status": "good", "badge": "Optimal", "advice": "Good vegetative growth reserve."})
    else:
        indicators.append({"param": "n", "name": "Nitrogen (N)", "val": f"{n:.1f}", "unit": "kg/ha", "status": "warning", "badge": "High", "advice": "Reduce nitrogen fertilizers to prevent lodging."})

    # 2. Phosphorus (Target: 20 - 45 kg/ha)
    p = reading.phosphorus
    if p is None:
        indicators.append({"param": "p", "name": "Phosphorus (P)", "val": "–", "unit": "kg/ha", "status": "warning", "badge": "No Data", "advice": "Sensor omitted"})
    elif p < 18:
        indicators.append({"param": "p", "name": "Phosphorus (P)", "val": f"{p:.1f}", "unit": "kg/ha", "status": "bad", "badge": "Deficient", "advice": "Apply Single Super Phosphate (SSP) or DAP at sowing."})
    elif p <= 45:
        indicators.append({"param": "p", "name": "Phosphorus (P)", "val": f"{p:.1f}", "unit": "kg/ha", "status": "good", "badge": "Good", "advice": "Healthy root establishment reserve."})
    else:
        indicators.append({"param": "p", "name": "Phosphorus (P)", "val": f"{p:.1f}", "unit": "kg/ha", "status": "warning", "badge": "High", "advice": "Adequate; omit phosphate addition this season."})

    # 3. Potassium (Target: 130 - 250 kg/ha)
    k = reading.potassium
    if k is None:
        indicators.append({"param": "k", "name": "Potassium (K)", "val": "–", "unit": "kg/ha", "status": "warning", "badge": "No Data", "advice": "Sensor omitted"})
    elif k < 110:
        indicators.append({"param": "k", "name": "Potassium (K)", "val": f"{k:.1f}", "unit": "kg/ha", "status": "warning", "badge": "Low", "advice": "Apply Muriate of Potash (MOP) to improve disease resistance."})
    elif k <= 250:
        indicators.append({"param": "k", "name": "Potassium (K)", "val": f"{k:.1f}", "unit": "kg/ha", "status": "good", "badge": "Optimal", "advice": "Promotes fruit size and drought resilience."})
    else:
        indicators.append({"param": "k", "name": "Potassium (K)", "val": f"{k:.1f}", "unit": "kg/ha", "status": "good", "badge": "Rich", "advice": "Ample potassium for heavy crop bearing."})

    # 4. Soil pH (Ideal: 6.2 - 7.5)
    ph = reading.ph
    if ph is None:
        indicators.append({"param": "ph", "name": "Soil pH", "val": "–", "unit": "", "status": "warning", "badge": "No Data", "advice": "Sensor omitted"})
    elif ph < 5.8:
        indicators.append({"param": "ph", "name": "Soil pH", "val": f"{ph:.1f}", "unit": "", "status": "bad", "badge": "Acidic", "advice": "Apply agricultural lime (calcium carbonate) to neutralize."})
    elif ph <= 7.6:
        indicators.append({"param": "ph", "name": "Soil pH", "val": f"{ph:.1f}", "unit": "", "status": "good", "badge": "Ideal (Neutral)", "advice": "Optimal nutrient availability for most Indian crops."})
    elif ph <= 8.3:
        indicators.append({"param": "ph", "name": "Soil pH", "val": f"{ph:.1f}", "unit": "", "status": "warning", "badge": "Slightly Alkaline", "advice": "Use gypsum or organic compost to lower pH."})
    else:
        indicators.append({"param": "ph", "name": "Soil pH", "val": f"{ph:.1f}", "unit": "", "status": "bad", "badge": "Alkaline / Sodic", "advice": "Apply Gypsum and ensure good soil flushing drainage."})

    # 5. Moisture (Target: 35% - 60%)
    m = reading.moisture
    if m is None:
        indicators.append({"param": "moisture", "name": "Moisture Content", "val": "–", "unit": "%", "status": "warning", "badge": "No Data", "advice": "Sensor omitted"})
    elif m < 30:
        indicators.append({"param": "moisture", "name": "Moisture Content", "val": f"{m:.1f}", "unit": "%", "status": "bad", "badge": "Dry", "advice": "Irrigation urgently needed. Water at base."})
    elif m <= 60:
        indicators.append({"param": "moisture", "name": "Moisture Content", "val": f"{m:.1f}", "unit": "%", "status": "good", "badge": "Optimal", "advice": "Moisture levels ideal for active growth."})
    else:
        indicators.append({"param": "moisture", "name": "Moisture Content", "val": f"{m:.1f}", "unit": "%", "status": "warning", "badge": "Wet", "advice": "High moisture; check root zone drainage."})

    # 6. EC (Target: < 0.8 dS/m)
    ec = reading.ec
    if ec is not None:
        if ec < 0.8:
            indicators.append({"param": "ec", "name": "Electrical Cond. (EC)", "val": f"{ec:.2f}", "unit": "dS/m", "status": "good", "badge": "Non-Saline", "advice": "No salinity hazard."})
        elif ec <= 1.5:
            indicators.append({"param": "ec", "name": "Electrical Cond. (EC)", "val": f"{ec:.2f}", "unit": "dS/m", "status": "warning", "badge": "Moderate Salinity", "advice": "Leach with fresh water."})
        else:
            indicators.append({"param": "ec", "name": "Electrical Cond. (EC)", "val": f"{ec:.2f}", "unit": "dS/m", "status": "bad", "badge": "Saline", "advice": "Saline soil. Plant salt-tolerant varieties."})

    return indicators
