"""Seedy Backend — Configuración central desde variables de entorno."""

from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # Together.ai
    together_api_key: str = ""
    together_model_id: str = "karaokedurrif/Qwen2.5-7B-Instruct-seedy-v4"
    together_base_url: str = "https://api.together.xyz/v1"

    # Ollama (fallback)
    ollama_base_url: str = "http://ollama:11434"
    ollama_model: str = "seedy:q8"
    ollama_embed_model: str = "mxbai-embed-large"

    # Qdrant
    qdrant_host: str = "qdrant"
    qdrant_port: int = 6333

    # RAG
    rag_chunk_size: int = 1500
    rag_chunk_overlap: int = 300
    rag_top_k: int = 8
    rag_bm25_weight: float = 0.7
    rag_relevance_threshold: float = 0.25
    rag_rerank_top_n: int = 3

    # Backend
    backend_host: str = "0.0.0.0"
    backend_port: int = 8000
    log_level: str = "info"

    # Paths
    knowledge_dir: str = "/app/knowledge"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


@lru_cache
def get_settings() -> Settings:
    return Settings()
