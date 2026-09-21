"""
dashboard.py – Farmer history dashboard endpoint and interactive web page.

Features:
  - Farmer profile & field details
  - Latest soil reading with color-coded nutrient indicators (Green / Amber / Red)
  - Ranked crop recommendations from the Kaggle dataset ML model
  - Past disease diagnoses with photo thumbnails, treatments, and KVK status
  - Dual format: returns HTML page for browser requests, or JSON for API clients.
"""

from typing import Optional
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from backend.crop_recommender import evaluate_soil_health, predict_ranked_crops
from backend.database import get_db
from backend.models import Diagnosis, FarmerProfile, SoilReading
from backend.schemas import (
    CropRecommendationItem,
    DiagnosisRead,
    FarmerDashboardResponse,
    FarmerProfileRead,
    SoilNutrientIndicator,
    SoilReadingRead,
)

router = APIRouter(tags=["Dashboard"])


def _render_dashboard_html(data: dict) -> str:
    """Generate responsive, low-bandwidth HTML dashboard matching AgroIn design system."""
    farmer = data["farmer"]
    soil = data["latest_soil_reading"]
    indicators = data["soil_indicators"]
    recommendations = data["crop_recommendations"]
    diagnoses = data["past_diagnoses"]

    # Nutrient indicators HTML
    indicators_html = ""
    for ind in indicators:
        badge_cls = "pill-good" if ind["status"] == "good" else ("pill-warn" if ind["status"] == "warning" else "pill-bad")
        status_color = "var(--green-dark)" if ind["status"] == "good" else ("#b25e00" if ind["status"] == "warning" else "var(--red)")
        border_color = "#4cb86a" if ind["status"] == "good" else ("#e8a000" if ind["status"] == "warning" else "#c0392b")

        indicators_html += f"""
        <div class="soil-card" style="border-left: 5px solid {border_color};">
          <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
            <span style="font-size: 0.85rem; font-weight: 700; color: var(--text-primary);">{ind['name']}</span>
            <span class="pill {badge_cls}">{ind['badge']}</span>
          </div>
          <div style="display: flex; align-items: baseline; gap: 6px; margin-bottom: 4px;">
            <span style="font-size: 1.6rem; font-weight: 800; color: {status_color};">{ind['val']}</span>
            <span style="font-size: 0.78rem; color: var(--text-muted);">{ind['unit']}</span>
          </div>
          <p style="font-size: 0.78rem; color: var(--text-muted); margin: 0;">💡 {ind['advice']}</p>
        </div>
        """

    # Crop recommendations HTML
    recs_html = ""
    for rec in recommendations:
        badge_cls = rec["badge_class"]
        recs_html += f"""
        <div class="rec-card">
          <div class="rec-rank-badge">#{rec['rank']}</div>
          <div class="rec-icon">{rec['icon']}</div>
          <div style="flex: 1;">
            <div style="display: flex; justify-content: space-between; align-items: center; gap: 8px;">
              <span class="rec-name">{rec['crop_name']}</span>
              <span class="pill {badge_cls}">{rec['suitability']}</span>
            </div>
            <div style="display: flex; align-items: center; gap: 8px; margin: 4px 0;">
              <div class="bar-track" style="flex: 1; height: 8px; background: #e0e0e0; border-radius: 4px; overflow: hidden;">
                <div style="width: {rec['score_pct']}%; height: 100%; background: var(--green-mid); border-radius: 4px;"></div>
              </div>
              <span style="font-size: 0.8rem; font-weight: 700; color: var(--green-dark);">{rec['score_pct']}% Match</span>
            </div>
            <p style="font-size: 0.78rem; color: var(--text-muted); margin: 0;">{rec['reason']}</p>
          </div>
        </div>
        """

    # Past diagnoses HTML
    diagnoses_html = ""
    if diagnoses:
        for diag in diagnoses:
            kvk_badge = ""
            if getattr(diag, "needs_kvk_review", False):
                kvk_badge = '<span class="pill pill-warn" style="margin-left: 6px;">🔬 KVK Review Pending</span>'
            elif getattr(diag, "kvk_review_status", "") == "reviewed":
                kvk_badge = '<span class="pill pill-good" style="margin-left: 6px;">✓ KVK Verified</span>'

            img_html = ""
            if diag.image_path:
                img_html = f'<div class="diag-img"><img src="/uploads/{diag.image_path}" alt="{diag.crop}" onerror="this.onerror=null;this.parentElement.innerHTML=\'🌿\';"/></div>'
            else:
                img_html = '<div class="diag-img-placeholder">🌿</div>'

            treat_text = diag.treatment or "Treatment instructions pending agronomist review."
            conf_pct = int(diag.confidence * 100)

            diagnoses_html += f"""
            <div class="diag-card">
              {img_html}
              <div style="flex: 1; min-width: 0;">
                <div style="display: flex; justify-content: space-between; align-items: flex-start; flex-wrap: wrap; gap: 6px;">
                  <div>
                    <span style="font-size: 0.78rem; text-transform: uppercase; color: var(--text-muted); font-weight: 700;">{diag.crop}</span>
                    <h3 style="font-size: 1.05rem; font-weight: 800; color: var(--green-dark); margin: 2px 0;">{diag.disease_name}</h3>
                  </div>
                  <div style="display: flex; gap: 4px; align-items: center;">
                    <span class="pill pill-good">{conf_pct}% Confidence</span>
                    {kvk_badge}
                  </div>
                </div>
                <div style="margin-top: 8px; background: var(--bg); padding: 10px; border-radius: var(--radius-sm); border: 1px solid var(--border);">
                  <strong style="font-size: 0.8rem; color: var(--green-dark);">💊 Recommended Action:</strong>
                  <p style="font-size: 0.82rem; color: var(--text-primary); margin: 4px 0 0;">{treat_text}</p>
                </div>
                <div style="display: flex; justify-content: space-between; align-items: center; margin-top: 8px; font-size: 0.75rem; color: var(--text-muted);">
                  <span>Source: {diag.source}</span>
                  <span>Recorded: {diag.timestamp.strftime('%d %b %Y, %I:%M %p')}</span>
                </div>
              </div>
            </div>
            """
    else:
        diagnoses_html = """
        <div class="card" style="text-align: center; padding: 28px 16px;">
          <span style="font-size: 2.2rem;">🌱</span>
          <h4 style="margin: 8px 0 4px; color: var(--green-dark);">No Disease Diagnoses Yet</h4>
          <p style="font-size: 0.82rem; color: var(--text-muted);">Your crops are currently healthy or no leaf scans have been uploaded.</p>
        </div>
        """

    soil_header_info = ""
    if soil:
        gps_text = f"GPS: {soil.gps_lat:.4f}, {soil.gps_lon:.4f}" if (soil.gps_lat and soil.gps_lon) else "Field Centroid"
        soil_header_info = f"Latest Rover Scan: {soil.timestamp.strftime('%d %b %Y, %I:%M %p')} • {gps_text}"
    else:
        soil_header_info = "No rover soil telemetry recorded yet."

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>{farmer.name} – AgroIn Farmer Dashboard</title>
  <meta name="description" content="AgroIn Farmer History Dashboard: Soil telemetry, disease diagnoses, and ML crop recommendations." />
  <style>
    :root {{
      --green-dark:   #1a5c2a;
      --green-mid:    #2d8a45;
      --green-light:  #4cb86a;
      --green-pale:   #d4edda;
      --amber:        #e8a000;
      --amber-pale:   #fff3cd;
      --red:          #c0392b;
      --red-pale:     #fde8e6;
      --sky:          #1976d2;
      --sky-pale:     #e3f2fd;
      --text-primary: #1a1a1a;
      --text-muted:   #555555;
      --border:       #c8d5c9;
      --bg:           #f4f7f4;
      --card:         #ffffff;
      --radius:       12px;
      --radius-sm:    8px;
      --shadow:       0 2px 10px rgba(0,0,0,0.08);
      --tap-min:      48px;
    }}
    *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
      background: #e8ede8;
      color: var(--text-primary);
      line-height: 1.5;
    }}
    a {{ color: inherit; text-decoration: none; }}
    .app-shell {{
      width: 100%;
      max-width: 1280px;
      margin: 0 auto;
      background: var(--bg);
      min-height: 100vh;
      padding-bottom: 60px;
    }}
    .dashboard-header {{
      background: linear-gradient(135deg, var(--green-dark) 0%, var(--green-mid) 100%);
      color: #fff;
      padding: 24px 20px;
      position: sticky;
      top: 0;
      z-index: 100;
      box-shadow: 0 4px 12px rgba(0,0,0,0.15);
    }}
    .dashboard-topbar {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 12px;
    }}
    .back-btn {{
      background: rgba(255,255,255,0.2);
      border: none;
      color: #fff;
      padding: 6px 14px;
      border-radius: 20px;
      font-size: 0.85rem;
      font-weight: 700;
      cursor: pointer;
    }}
    .profile-hero {{
      display: flex;
      align-items: center;
      gap: 16px;
      flex-wrap: wrap;
    }}
    .profile-avatar {{
      width: 58px; height: 58px;
      border-radius: 50%;
      background: rgba(255,255,255,0.2);
      display: flex; align-items: center; justify-content: center;
      font-size: 1.8rem;
    }}
    .profile-title {{ font-size: 1.4rem; font-weight: 800; }}
    .profile-sub {{ font-size: 0.85rem; opacity: 0.9; margin-top: 2px; }}
    .dashboard-grid {{
      padding: 16px;
      display: grid;
      grid-template-columns: 1fr;
      gap: 16px;
    }}
    @media (min-width: 900px) {{
      .dashboard-grid {{
        grid-template-columns: 1.2fr 1fr;
        padding: 24px;
        gap: 24px;
      }}
      .full-span {{ grid-column: span 2; }}
    }}
    .card {{
      background: var(--card);
      border-radius: var(--radius);
      box-shadow: var(--shadow);
      padding: 18px;
      border: 1px solid var(--border);
    }}
    .card-header {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 12px;
      padding-bottom: 10px;
      border-bottom: 1px solid var(--border);
    }}
    .card-title {{
      font-size: 1.05rem;
      font-weight: 700;
      color: var(--green-dark);
      display: flex;
      align-items: center;
      gap: 8px;
    }}
    .pill {{
      display: inline-flex; align-items: center; gap: 4px;
      padding: 4px 10px; border-radius: 16px;
      font-size: 0.75rem; font-weight: 700;
    }}
    .pill-good  {{ background: var(--green-pale); color: var(--green-dark); }}
    .pill-warn  {{ background: var(--amber-pale); color: #7a5000; }}
    .pill-bad   {{ background: var(--red-pale);   color: var(--red); }}
    .soil-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
      gap: 12px;
    }}
    .soil-card {{
      background: var(--bg);
      border-radius: var(--radius-sm);
      padding: 12px;
      border: 1px solid var(--border);
    }}
    .rec-card {{
      background: var(--bg);
      border: 1px solid var(--border);
      border-radius: var(--radius-sm);
      padding: 12px;
      margin-bottom: 10px;
      display: flex;
      align-items: center;
      gap: 12px;
    }}
    .rec-rank-badge {{
      background: var(--green-dark);
      color: #fff;
      font-size: 0.75rem;
      font-weight: 800;
      padding: 2px 8px;
      border-radius: 6px;
    }}
    .rec-icon {{ font-size: 1.8rem; flex-shrink: 0; }}
    .rec-name {{ font-size: 0.95rem; font-weight: 700; color: var(--green-dark); }}
    .diag-card {{
      background: var(--card);
      border: 1px solid var(--border);
      border-radius: var(--radius);
      padding: 14px;
      margin-bottom: 12px;
      display: flex;
      gap: 14px;
      align-items: flex-start;
      flex-wrap: wrap;
    }}
    .diag-img {{
      width: 90px; height: 90px;
      border-radius: var(--radius-sm);
      overflow: hidden;
      background: #eee;
      flex-shrink: 0;
    }}
    .diag-img img {{ width: 100%; height: 100%; object-fit: cover; }}
    .diag-img-placeholder {{
      width: 90px; height: 90px;
      border-radius: var(--radius-sm);
      background: var(--green-pale);
      color: var(--green-dark);
      display: flex; align-items: center; justify-content: center;
      font-size: 2.2rem; flex-shrink: 0;
    }}
    .quick-bar {{
      display: flex;
      gap: 8px;
      overflow-x: auto;
      margin-top: 14px;
    }}
    .quick-chip {{
      background: rgba(255,255,255,0.25);
      color: #fff;
      padding: 6px 12px;
      border-radius: 20px;
      font-size: 0.75rem;
      font-weight: 600;
      white-space: nowrap;
    }}
  </style>
</head>
<body>

<div class="app-shell">
  <!-- Header -->
  <header class="dashboard-header">
    <div class="dashboard-topbar">
      <a href="/" class="back-btn">← Home &amp; Wireframes</a>
      <span style="font-size: 0.8rem; font-weight: 700; letter-spacing: 0.05em; text-transform: uppercase; opacity: 0.85;">AgroIn Advisory</span>
    </div>
    <div class="profile-hero">
      <div class="profile-avatar">👨‍🌾</div>
      <div>
        <h1 class="profile-title">{farmer.name}</h1>
        <p class="profile-sub">📍 {farmer.location} • 🌾 {farmer.assigned_field or 'Field Sector A'} • 📞 {farmer.phone}</p>
      </div>
    </div>
    <div class="quick-bar">
      <span class="quick-chip">🌱 {data['total_soil_readings']} Soil Scans</span>
      <span class="quick-chip">🔬 {data['total_diagnoses']} Crop Diagnoses</span>
      <span class="quick-chip">🤖 ML Recommender Active</span>
    </div>
  </header>

  <main class="dashboard-grid">
    <!-- Soil Telemetry & Indicators -->
    <section class="card">
      <div class="card-header">
        <div>
          <h2 class="card-title">🧪 Latest Soil Health Analysis</h2>
          <p style="font-size: 0.75rem; color: var(--text-muted); margin-top: 2px;">{soil_header_info}</p>
        </div>
        <span class="pill pill-good">Rover Telemetry</span>
      </div>
      <div class="soil-grid">
        {indicators_html}
      </div>
    </section>

    <!-- ML Crop Recommendations -->
    <section class="card">
      <div class="card-header">
        <div>
          <h2 class="card-title">🌾 Ranked Crop Recommendations</h2>
          <p style="font-size: 0.75rem; color: var(--text-muted); margin-top: 2px;">Predicted by Scikit-Learn Model (Kaggle Dataset)</p>
        </div>
        <span class="pill pill-good">ML Match</span>
      </div>
      <div>
        {recs_html}
      </div>
    </section>

    <!-- Past Crop Diagnoses -->
    <section class="card full-span">
      <div class="card-header">
        <div>
          <h2 class="card-title">🔬 Crop Disease Diagnosis History</h2>
          <p style="font-size: 0.75rem; color: var(--text-muted); margin-top: 2px;">AI Pathologist results with KVK Expert Escalation</p>
        </div>
        <span class="pill pill-good">{data['total_diagnoses']} Recorded</span>
      </div>
      <div>
        {diagnoses_html}
      </div>
    </section>
  </main>
</div>

</body>
</html>
"""
    return html_content


@router.get(
    "/dashboard/{farmer_id}",
    response_model=FarmerDashboardResponse,
    summary="Get farmer advisory history, soil health indicators, and ML crop recommendations",
    description=(
        "Returns the farmer's advisory dashboard. If requested via a browser (HTML), "
        "renders an interactive, low-bandwidth web page with color-coded nutrient indicators. "
        "If requested with `Accept: application/json` or `?format=json`, returns JSON."
    ),
)
def get_farmer_dashboard(
    farmer_id: int,
    format: Optional[str] = Query(None, description="Set 'json' for raw JSON payload"),
    accept: Optional[str] = Header(None, alias="Accept"),
    db: Session = Depends(get_db),
):
    farmer = db.get(FarmerProfile, farmer_id)
    if not farmer:
        raise HTTPException(status_code=404, detail=f"Farmer {farmer_id} not found.")

    # Latest soil reading
    latest_soil = (
        db.query(SoilReading)
        .filter(SoilReading.farmer_id == farmer_id)
        .order_by(SoilReading.timestamp.desc())
        .first()
    )

    # Color-coded soil nutrient indicators (Green / Amber / Red)
    indicators = evaluate_soil_health(latest_soil)

    # ML Crop Recommendations from Kaggle-trained model
    n_val = latest_soil.nitrogen if latest_soil else 120.0
    p_val = latest_soil.phosphorus if latest_soil else 35.0
    k_val = latest_soil.potassium if latest_soil else 180.0
    ph_val = latest_soil.ph if latest_soil else 6.8
    m_val = latest_soil.moisture if latest_soil else 50.0

    crop_recs = predict_ranked_crops(
        nitrogen=n_val,
        phosphorus=p_val,
        potassium=k_val,
        ph=ph_val,
        moisture=m_val,
        top_k=5,
    )

    # Past diagnoses
    past_diagnoses = (
        db.query(Diagnosis)
        .filter(Diagnosis.farmer_id == farmer_id)
        .order_by(Diagnosis.timestamp.desc())
        .all()
    )

    total_soil = db.query(SoilReading).filter(SoilReading.farmer_id == farmer_id).count()
    total_diag = len(past_diagnoses)

    payload = {
        "farmer": FarmerProfileRead.model_validate(farmer),
        "latest_soil_reading": SoilReadingRead.model_validate(latest_soil) if latest_soil else None,
        "soil_indicators": [SoilNutrientIndicator(**ind) for ind in indicators],
        "crop_recommendations": [CropRecommendationItem(**rec) for rec in crop_recs],
        "past_diagnoses": [DiagnosisRead.model_validate(d) for d in past_diagnoses],
        "total_diagnoses": total_diag,
        "total_soil_readings": total_soil,
    }

    # If client explicitly asked for JSON
    wants_json = (format and format.lower() == "json") or (accept and "application/json" in accept and "text/html" not in accept)
    if wants_json:
        return FarmerDashboardResponse(**payload)

    # Otherwise return styled HTML page
    html_page = _render_dashboard_html({
        "farmer": farmer,
        "latest_soil_reading": latest_soil,
        "soil_indicators": indicators,
        "crop_recommendations": crop_recs,
        "past_diagnoses": past_diagnoses,
        "total_diagnoses": total_diag,
        "total_soil_readings": total_soil,
    })
    return HTMLResponse(content=html_page, status_code=200)
