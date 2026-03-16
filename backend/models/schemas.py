"""Seedy Backend — Pydantic schemas para API."""

from pydantic import BaseModel, Field


class Message(BaseModel):
    """Mensaje de conversación (historial multi-turno)."""
    role: str = Field(..., description="system, user o assistant")
    content: str


class ChatRequest(BaseModel):
    """Petición al endpoint /chat o /chat/stream."""
    query: str = Field(..., min_length=1, max_length=4000, description="Pregunta del usuario")
    farm_id: str | None = Field(None, description="ID de la explotación (para filtrar contexto IoT)")
    barn_id: str | None = Field(None, description="ID de la nave (para Digital Twin)")
    history: list[Message] = Field(default_factory=list, description="Mensajes previos para multi-turno")


class Source(BaseModel):
    """Fuente RAG usada en la respuesta."""
    file: str
    collection: str
    chunk_index: int
    score: float
    text: str = Field("", description="Fragmento del chunk usado")


class ChatResponse(BaseModel):
    """Respuesta del endpoint /chat."""
    answer: str
    category: str = Field(
        ...,
        description="Categoría: RAG, IOT, TWIN, NUTRITION, GENETICS, NORMATIVA, AVICULTURA, GENERAL",
    )
    sources: list[Source] = []
    model_used: str = Field(..., description="Modelo que generó la respuesta (together/ollama)")


class HealthResponse(BaseModel):
    status: str = "ok"
    ollama: bool = False
    qdrant: bool = False
    together: bool = False


# ─── Vision Schemas ───────────────────────────────────


class BoundingBox(BaseModel):
    """Bounding box normalizada [0-1]."""
    x1: float
    y1: float
    x2: float
    y2: float


class Detection(BaseModel):
    """Una detección individual."""
    class_name: str
    confidence: float
    bbox: BoundingBox
    track_id: int | None = None


class VisionEvent(BaseModel):
    """Evento de detección enviado desde Jetson/cámara."""
    camera_id: str = Field(..., description="ID de la cámara (e.g. cam_nave1)")
    farm_id: str = Field(..., description="ID de la explotación")
    barn_id: str | None = Field(None, description="ID de la nave")
    timestamp: str = Field(..., description="ISO 8601 timestamp")
    frame_number: int = 0
    detections: list[Detection] = []
    inference_ms: float = 0.0
    model_name: str = ""


class VisionEventResponse(BaseModel):
    """Respuesta al recibir un evento de visión."""
    status: str = "ok"
    event_id: str
    alerts_triggered: int = 0


class WeightEvent(BaseModel):
    """Evento de estimación de peso."""
    camera_id: str
    farm_id: str
    barn_id: str | None = None
    timestamp: str
    track_id: int
    species: str
    estimated_weight_kg: float
    confidence: float
    calibrated: bool = False


class BehaviourAlert(BaseModel):
    """Alerta de comportamiento anómalo."""
    camera_id: str
    farm_id: str
    barn_id: str | None = None
    timestamp: str
    track_id: int = Field(..., description="-1 para eventos grupales")
    species: str
    behaviour: str = Field(
        ...,
        description="fighting, stereotypy, abnormal_grouping, prolonged_resting, running",
    )
    confidence: float
    duration_seconds: float
    severity: str = Field(..., description="info, warning, alert")


class VisionStats(BaseModel):
    """Estadísticas agregadas de visión."""
    camera_id: str
    period_start: str
    period_end: str
    total_detections: int = 0
    species_counts: dict[str, int] = {}
    avg_confidence: float = 0.0
    alerts_count: int = 0
    avg_weight_kg: dict[str, float] = {}
    behaviour_distribution: dict[str, int] = {}


# ─── Genetics Schemas ────────────────────────────────


class PredictF1Request(BaseModel):
    """Petición de predicción F1."""
    sire_breed: str = Field(..., description="ID raza padre (e.g. 'orpington', 'duroc')")
    dam_breed: str = Field(..., description="ID raza madre")
    species: str = Field(..., description="chicken, pig, cattle")


class PredictGenerationsRequest(BaseModel):
    """Petición de simulación multi-generación."""
    sire_breed: str
    dam_breed: str
    species: str
    n_generations: int = Field(5, ge=1, le=10)
    strategy: str = Field(
        "f1_inter_se",
        description="f1_inter_se, backcross_sire, backcross_dam, rotational",
    )


class OptimalMatingRequest(BaseModel):
    """Petición de cruces óptimos."""
    species: str
    target_traits: list[str] = Field(
        default_factory=list,
        description="Rasgos objetivo (vacío = todos los predeterminados)",
    )
    top_n: int = Field(5, ge=1, le=20)


class BLUPRequest(BaseModel):
    """Petición de cálculo BLUP."""
    species: str
    trait: str = Field(..., description="Nombre del rasgo a evaluar")
    heritability: float = Field(..., ge=0.01, le=0.99)
    pedigree: list[dict] = Field(
        ...,
        description="Lista de {id, sire, dam, sex, breed, generation}",
    )
    phenotypes: dict[str, float] = Field(
        ...,
        description="{animal_id: valor_fenotipo}",
    )
    top_n: int = Field(10, ge=1, le=100)


class SelectionIndexRequest(BaseModel):
    """Petición de índice de selección."""
    species: str
    traits: dict[str, float] = Field(
        ...,
        description="{trait_name: valor}",
    )
    weights: dict[str, float] | None = Field(
        None,
        description="Pesos custom. Si None, usa los por defecto de la especie.",
    )


# ─── Bird Tracking Schemas (IA Vision) ───────────────


class BirdRecord(BaseModel):
    """Registro individual de un ave identificada por IA Vision."""
    bird_id: str = Field(..., description="ID único: PAL-2026-XXXX")
    breed: str = Field(..., description="Raza identificada (e.g. Bresse, Sussex, Marans)")
    color: str = Field("", description="Color/variedad del plumaje (blanco, silver, negro cobrizo...)")
    sex: str = Field("unknown", description="male, female, unknown")
    gallinero: str = Field(..., description="gallinero_durrif_1 o gallinero_durrif_2")
    first_seen: str = Field(..., description="ISO 8601 timestamp primera detección")
    last_seen: str = Field(..., description="ISO 8601 timestamp última detección")
    ia_vision_number: int = Field(..., description="Número secuencial IA Vision dentro de raza+color")
    ai_vision_id: str = Field("", description="ID compacto: sussexbl1, maransnc2...")
    confidence: float = Field(0.0, description="Confianza media de la identificación")
    photo_path: str | None = Field(None, description="Ruta a la mejor foto capturada")
    photo_b64: str | None = Field(None, description="Miniatura base64 para dashboard")
    notes: str = ""


class BirdRegisterRequest(BaseModel):
    """Petición para registrar un ave desde la pipeline de visión."""
    breed: str
    color: str = ""
    sex: str = "unknown"
    gallinero: str
    confidence: float = 0.0
    photo_b64: str | None = None


class BirdUpdateRequest(BaseModel):
    """Actualización parcial de un ave."""
    breed: str | None = None
    color: str | None = None
    sex: str | None = None
    gallinero: str | None = None
    confidence: float | None = None
    photo_b64: str | None = None
    notes: str | None = None
