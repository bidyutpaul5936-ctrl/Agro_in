"""
diagnosis_engine package – Pluggable disease diagnosis architecture for AgroIn.
"""

from backend.diagnosis_engine.base import BaseDiagnosisEngine, CropDiagnosisResult
from backend.diagnosis_engine.factory import get_diagnosis_engine
from backend.diagnosis_engine.gemini_engine import GeminiDiagnosisEngine
from backend.diagnosis_engine.local_engine import LocalModelDiagnosisEngine

__all__ = [
    "BaseDiagnosisEngine",
    "CropDiagnosisResult",
    "GeminiDiagnosisEngine",
    "LocalModelDiagnosisEngine",
    "get_diagnosis_engine",
]
