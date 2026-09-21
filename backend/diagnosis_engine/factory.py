"""
factory.py – Diagnosis engine factory.

Instantiates and returns the configured diagnosis provider based on settings.
"""

from backend.config import settings
from backend.diagnosis_engine.base import BaseDiagnosisEngine
from backend.diagnosis_engine.gemini_engine import GeminiDiagnosisEngine
from backend.diagnosis_engine.local_engine import LocalModelDiagnosisEngine

_cached_engine: BaseDiagnosisEngine | None = None


def get_diagnosis_engine() -> BaseDiagnosisEngine:
    """
    Return the active diagnosis engine (Gemini or Local model) based on configuration.
    Allows seamlessly switching engines without modifying any route or client code.
    """
    backend_choice = getattr(settings, "DIAGNOSIS_BACKEND", "gemini").lower()
    if backend_choice == "local":
        return LocalModelDiagnosisEngine()
    return GeminiDiagnosisEngine()
