"""Seedy Backend — Modelos Pydantic para el Índice de Mérito Genético (IM)."""

from datetime import datetime
from enum import Enum
from typing import Dict, Optional

from pydantic import BaseModel, Field, model_validator


class SelectionCategory(str, Enum):
    REPRODUCTOR = "reproductor"    # IM >= 0.85
    PRODUCCION = "produccion"      # IM 0.60-0.84
    DESCARTE = "descarte"          # IM < 0.60


class MeritWeights(BaseModel):
    """Pesos configurables del IM. Deben sumar 1.0."""
    peso: float = Field(0.35, ge=0, le=1)
    conformacion: float = Field(0.25, ge=0, le=1)
    conversion: float = Field(0.15, ge=0, le=1)
    viabilidad: float = Field(0.15, ge=0, le=1)
    docilidad: float = Field(0.10, ge=0, le=1)

    @model_validator(mode="after")
    def validate_sum(self):
        total = self.peso + self.conformacion + self.conversion + self.viabilidad + self.docilidad
        if abs(total - 1.0) > 0.01:
            raise ValueError(f"Los pesos deben sumar 1.0, suman {total:.3f}")
        return self


class MeritInput(BaseModel):
    """Datos de entrada para calcular el IM de un ave."""
    bird_id: str
    gallinero: Optional[str] = None
    age_weeks: int = Field(ge=0)
    weight_grams: float = Field(ge=0)
    target_weight_grams: Optional[float] = Field(None, ge=0, description="Si None, se calcula por Gompertz")
    conformacion_score: float = Field(ge=1, le=5, description="1=pobre, 5=excelente")
    conversion_ratio: Optional[float] = Field(None, ge=0, description="kg pienso / kg peso ganado")
    max_conversion: float = Field(4.5, ge=0.1, description="Máximo teórico de conversión heritage")
    has_antibiotics: bool = False
    has_chronic_lameness: bool = False
    has_transient_lameness: bool = False
    has_deformity: bool = False
    docilidad_score: float = Field(ge=1, le=5, description="1=agresivo, 5=ultra dócil")
    sibling_tasting_bonus: float = Field(0.0, ge=0, le=0.5, description="Bonus por cata de hermano capón")


class MeritResult(BaseModel):
    """Resultado del cálculo del IM."""
    bird_id: str
    im_score: float = Field(ge=0, le=1)
    category: SelectionCategory
    components: Dict[str, float]
    weighted_components: Dict[str, float]
    weights_used: MeritWeights
    calculated_at: datetime
    age_weeks: int
    recommendation: str


class MeritRankingResponse(BaseModel):
    """Ranking completo con estadísticas."""
    total_aves: int
    reproductores: Dict
    produccion: Dict
    descarte: Dict
    stats: Dict
    weights_used: Dict
