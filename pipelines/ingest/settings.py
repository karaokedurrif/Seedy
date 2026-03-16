"""Pipeline de autoingesta — Configuración."""

from pydantic_settings import BaseSettings
from functools import lru_cache
from pathlib import Path


class PipelineSettings(BaseSettings):
    # Qdrant
    qdrant_url: str = "http://qdrant:6333"

    # Ollama (embeddings)
    ollama_url: str = "http://ollama:11434"
    embed_model: str = "mxbai-embed-large"

    # Paths — defaults relativos al proyecto (funcionan local y en Docker con env override)
    sources_file: str = str(Path(__file__).parent / "sources.yaml")
    data_dir: str = str(Path(__file__).parent.parent.parent / "data")
    briefs_dir: str = str(Path(__file__).parent.parent.parent / "briefs")
    db_path: str = str(Path(__file__).parent.parent.parent / "data" / "ingest_state.db")

    # Chunking (mismos defaults que backend)
    chunk_size: int = 800
    chunk_overlap: int = 150

    # Scoring
    score_threshold: int = 50       # >= indexar
    quarantine_threshold: int = 35  # 35-49 cuarentena

    # Fetch
    fetch_timeout: int = 30
    max_retries: int = 3
    user_agent: str = "SeedyBot/1.0 (NeoFarm autoingesta)"

    # Batch
    embed_batch_size: int = 10

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}


@lru_cache
def get_settings() -> PipelineSettings:
    return PipelineSettings()
