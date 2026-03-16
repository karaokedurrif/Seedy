"""Seedy Backend — Configuración central desde variables de entorno."""

from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # Together.ai
    together_api_key: str = ""
    together_model_id: str = "Qwen/Qwen2.5-7B-Instruct-Turbo"
    together_classifier_model: str = "Qwen/Qwen2.5-7B-Instruct-Turbo"
    together_critic_model: str = "meta-llama/Llama-3.3-70B-Instruct-Turbo"
    together_base_url: str = "https://api.together.xyz/v1"

    # Ollama (principal — modelo fine-tuned local)
    ollama_base_url: str = "http://ollama:11434"
    ollama_model: str = "seedy:v16"
    ollama_embed_model: str = "mxbai-embed-large"

    # Qdrant
    qdrant_host: str = "qdrant"
    qdrant_port: int = 6333

    # Gemini (visión)
    gemini_api_key: str = ""

    # SearXNG (búsqueda web)
    searxng_url: str = "http://searxng:8080"

    # crawl4ai (URL fetcher)
    crawl4ai_url: str = "http://crawl4ai:11235"

    # RAG
    rag_chunk_size: int = 800
    rag_chunk_overlap: int = 150
    rag_top_k: int = 20
    rag_bm25_weight: float = 1.0
    rag_relevance_threshold: float = 0.25
    rag_rerank_top_n: int = 8

    # Backend
    backend_host: str = "0.0.0.0"
    backend_port: int = 8000
    log_level: str = "info"

    # API keys (comma-separated) — if empty, no auth required
    api_keys: str = ""

    # Paths
    knowledge_dir: str = "/app/knowledge"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}


@lru_cache
def get_settings() -> Settings:
    return Settings()
