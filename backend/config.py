"""
config.py – Application settings loaded from environment variables or a .env file.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Database ──────────────────────────────────────────────────────────
    DATABASE_URL: str = "sqlite:///./agro_in.db"
    SQL_ECHO: bool = False                 # set True for verbose SQL logging

    # ── API ───────────────────────────────────────────────────────────────
    APP_TITLE: str = "AgroIn API"
    APP_VERSION: str = "0.1.0"
    APP_DESCRIPTION: str = (
        "Backend for the AgroIn agri-advisory platform. "
        "Rover devices push soil readings and diagnoses; "
        "farmers view results and manage seed listings."
    )
    DEBUG: bool = False

    # ── Upload storage ────────────────────────────────────────────────────
    UPLOAD_DIR: str = "uploads"            # relative to where uvicorn is run

    # ── Disease Diagnosis Backend (Gemini / Local Fine-Tuned Model) ────────
    DIAGNOSIS_BACKEND: str = "gemini"      # "gemini" or "local"
    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-2.5-flash"
    LOCAL_MODEL_ENDPOINT: str = "http://localhost:8080/v1/diagnose"
    KVK_CONFIDENCE_THRESHOLD: float = 0.70  # Diagnoses below 0.70 are flagged for KVK review


settings = Settings()
