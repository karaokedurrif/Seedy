"""Seedy Backend — Pydantic schemas para API."""

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    """Petición al endpoint /chat."""
    query: str = Field(..., min_length=1, max_length=4000, description="Pregunta del usuario")
    farm_id: str | None = Field(None, description="ID de la explotación (para filtrar contexto IoT)")
    barn_id: str | None = Field(None, description="ID de la nave (para Digital Twin)")


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
    category: str = Field(..., description="Categoría detectada: RAG, IOT, TWIN, NUTRITION, GENETICS, GENERAL")
    sources: list[Source] = []
    model_used: str = Field(..., description="Modelo que generó la respuesta (together/ollama)")


class HealthResponse(BaseModel):
    status: str = "ok"
    ollama: bool = False
    qdrant: bool = False
    together: bool = False
