"""
Seedy Backend — API principal FastAPI.

Sistema de IA para NeoFarm: clasificación → RAG → rerank → LLM.
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import get_settings
from routers import chat, health
from services import embeddings, rag

# Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup y shutdown del backend."""
    logger.info("🌱 Seedy Backend iniciando...")

    # Inicializar colecciones Qdrant
    try:
        embed_dim = await embeddings.get_embedding_dimension()
        await rag.ensure_collections(embed_dim=embed_dim)
        logger.info(f"Qdrant listo (embed_dim={embed_dim})")
    except Exception as e:
        logger.warning(f"No se pudo inicializar Qdrant: {e}. Se reintentará al recibir queries.")

    logger.info("🌱 Seedy Backend listo")
    yield

    # Cleanup
    await embeddings.close()
    rag.close()
    logger.info("🌱 Seedy Backend detenido")


app = FastAPI(
    title="Seedy Backend",
    description="API de IA para NeoFarm — clasificación, RAG, rerank y LLM",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS — permitir Open WebUI y hub.vacasdata.com
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Restringir en producción
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(chat.router)
app.include_router(health.router)


@app.get("/")
async def root():
    return {"service": "Seedy Backend", "version": "0.1.0", "docs": "/docs"}
