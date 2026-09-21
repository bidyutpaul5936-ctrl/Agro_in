"""
base.py – Abstract Base Class and unified contract for plant disease diagnosis engines.
"""

from abc import ABC, abstractmethod
from typing import List, Optional
from pydantic import BaseModel, Field


class CropDiagnosisResult(BaseModel):
    """
    Standardized, provider-agnostic plant diagnosis output schema.
    Guarantees that replacing Gemini with a fine-tuned local model
    never changes the API response contract.
    """
    crop: str = Field(..., description="Name of the detected crop (e.g. Tomato, Cotton, Wheat, Rice)")
    disease_name: str = Field(..., description="Pathology name, or 'Healthy' if no disease detected")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence score between 0.0 and 1.0")
    pathogen_type: str = Field("Fungal", description="Fungal / Bacterial / Viral / Pest / Nutrient Deficiency / None")
    risk_level: str = Field("High Risk", description="High Risk / Moderate Risk / Low Risk / None")
    treatment: str = Field(..., description="Actionable farmer treatment guidance")
    urgent_steps: List[str] = Field(default_factory=list, description="Immediate actions for the farmer")
    preventive_measures: List[str] = Field(default_factory=list, description="Long-term cultural and crop health practices")


class BaseDiagnosisEngine(ABC):
    """
    Abstract interface for disease diagnosis engines.
    Both cloud providers (Gemini) and locally-hosted fine-tuned vision models
    must implement this interface.
    """

    @abstractmethod
    async def diagnose(
        self,
        image_bytes: bytes,
        mime_type: str = "image/jpeg",
        crop_hint: Optional[str] = None,
        filename_hint: Optional[str] = None,
        filename: Optional[str] = None,
        **kwargs,
    ) -> CropDiagnosisResult:
        """Run disease pathology diagnosis on the supplied image bytes."""
        pass

