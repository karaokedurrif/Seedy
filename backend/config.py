"""Seedy Backend — Configuración central desde variables de entorno."""

from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # Together.ai
    together_api_key: str = ""
    together_model_id: str = "Qwen/Qwen3-235B-A22B-Instruct-2507-tput"  # Principal: rápido + capaz
    together_classifier_model: str = "Qwen/Qwen2.5-7B-Instruct-Turbo"  # Barato para clasificar
    together_critic_model: str = "Qwen/Qwen3-235B-A22B-Instruct-2507-tput"  # Critic inteligente
    together_report_model: str = "deepseek-ai/DeepSeek-R1-0528"  # Brain: máximo razonamiento
    together_vision_model: str = "Qwen/Qwen2.5-VL-72B-Instruct"
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
    rag_top_k: int = 15
    rag_bm25_weight: float = 1.0
    rag_relevance_threshold: float = 0.25
    rag_rerank_top_n: int = 8

    # Behavior analysis
    behavior_default_window: str = "24h"
    behavior_min_window: str = "1h"
    behavior_min_history_windows: int = 3
    behavior_displacement_threshold: int = 50  # pixels → ~0.071 norm (P5 inter-bird dist)
    behavior_chase_min_frames: int = 4  # calibrado: 4 frames consecutivos para filtrar FP
    behavior_isolation_percentile: float = 0.1
    behavior_nest_anomaly_hours: str = "6,20"  # comma-separated
    behavior_baseline_path: str = "data/behavior_baselines/"
    behavior_event_store_path: str = "data/behavior_events/"
    behavior_snapshot_interval_sec: int = 60
    behavior_retention_days: int = 14  # El ML entrena con 14 días, no recortar antes
    behavior_feeder_ratio_high: float = 1.3

    # Capture Manager (dual-stream)
    capture_min_interval: int = 10        # Mín segundos entre capturas 4K
    capture_scheduled_interval: int = 300  # Captura periódica fallback (5 min)
    capture_sub_frame_skip: int = 2        # Procesar 1 de cada N sub-frames

    # Crop Curator
    curation_min_conf_yolo: float = 0.65
    curation_min_conf_gemini: float = 0.80
    curation_min_crop_size: int = 128
    curation_min_sharpness: float = 40.0
    curation_max_per_class_day: int = 50

    # Behavior ML
    behavior_ml_train_interval: int = 21600  # 6 horas en segundos
    behavior_ml_min_events: int = 100
    behavior_ml_models_path: str = "data/ml_models/"

    behavior_feeder_ratio_low: float = 0.7
    behavior_heat_threshold: float = 35.0
    behavior_cold_threshold: float = 5.0
    behavior_heat_feeder_override: float = 0.5
    behavior_cold_feeder_override: float = 1.5
    behavior_aggressiveness_multiplier: float = 1.5
    behavior_subordination_isolation_multiplier: float = 1.4
    behavior_stress_activity_multiplier: float = 2.0
    behavior_dominance_min_signals: int = 3

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
