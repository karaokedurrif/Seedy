"""
Seedy Backend — API principal FastAPI.

Sistema de IA para NeoFarm: clasificación → RAG → rerank → LLM.
Incluye scheduler de actualización diaria (circuito B offline).
"""

import asyncio
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from config import get_settings
from routers import chat, health, vision, genetics, openai_compat, ingest, birds
from routers import vision_identify
from routers import ovosfera_bridge
from routers import survey
from services import embeddings, rag
from services import gemini_vision
from services.reranker import warmup as reranker_warmup
from services.daily_update import run_daily_update

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

    # Precargar reranker (evita timeout de 150s en primera petición)
    try:
        reranker_warmup()
    except Exception as e:
        logger.warning(f"Reranker warmup falló: {e}. Se cargará con la primera query.")

    # Programar actualización diaria (circuito B offline)
    daily_task = asyncio.create_task(_daily_update_loop())
    app.state.daily_task = daily_task  # Mantener referencia

    logger.info("🌱 Seedy Backend listo")
    yield

    # Cleanup
    daily_task.cancel()
    await embeddings.close()
    await gemini_vision.close()
    rag.close()
    logger.info("🌱 Seedy Backend detenido")


async def _daily_update_loop():
    """Loop que ejecuta actualización diaria cada 24h."""
    # Esperar 5 min tras arranque para no cargar al inicio
    await asyncio.sleep(300)
    while True:
        try:
            logger.info("📡 Ejecutando actualización diaria de conocimientos...")
            count = await run_daily_update()
            logger.info(f"📡 Actualización diaria completa: {count} nuevos chunks")
        except Exception as e:
            logger.error(f"Error en actualización diaria: {e}")
        # Esperar 24h hasta la siguiente
        await asyncio.sleep(86400)


app = FastAPI(
    title="Seedy Backend",
    description="API de IA para NeoFarm — clasificación, RAG, rerank y LLM",
    version="0.1.0",
    lifespan=lifespan,
)

# API Key auth middleware
_settings = get_settings()
_valid_keys = {k.strip() for k in _settings.api_keys.split(",") if k.strip()}


class APIKeyMiddleware(BaseHTTPMiddleware):
    """Valida Bearer token contra API_KEYS configuradas.
    Peticiones desde la red interna Docker (172.x) se permiten sin auth.
    """

    OPEN_PATHS = {"/", "/docs", "/openapi.json", "/redoc", "/health", "/v1/models"}
    OPEN_PREFIXES = ("/ovosfera/", "/dashboard/", "/survey/")

    async def dispatch(self, request: Request, call_next):
        if not _valid_keys:
            return await call_next(request)
        path = request.url.path
        if path in self.OPEN_PATHS or request.method == "OPTIONS":
            return await call_next(request)
        if any(path.startswith(p) for p in self.OPEN_PREFIXES):
            return await call_next(request)
        # Allow internal Docker network (Open WebUI, etc.)
        client_ip = request.client.host if request.client else ""
        if client_ip.startswith("172.") or client_ip == "127.0.0.1":
            return await call_next(request)
        auth = request.headers.get("authorization", "")
        if auth.startswith("Bearer "):
            token = auth[7:]
            if token in _valid_keys:
                return await call_next(request)
            logger.warning(f"API key rechazada: {token[:20]}... (path={request.url.path}, ip={client_ip})")
        else:
            logger.warning(f"Sin Authorization header (path={request.url.path}, ip={client_ip})")
        return JSONResponse(status_code=401, content={"error": "Invalid API key"})


app.add_middleware(APIKeyMiddleware)

# CORS — orígenes permitidos (configurable via env CORS_ORIGINS)
_default_origins = [
    "https://seedy.neofarm.io",
    "https://seedy-api.neofarm.io",
    "https://seedy-grafana.neofarm.io",
    "https://hub.ovosfera.com",
    "http://localhost:3000",
    "http://10.10.10.1:3000",
    "http://localhost:8000",
]
_cors_env = os.environ.get("CORS_ORIGINS", "")
cors_origins = [o.strip() for o in _cors_env.split(",") if o.strip()] if _cors_env else _default_origins

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(chat.router)
app.include_router(health.router)
app.include_router(vision.router)
app.include_router(genetics.router)
app.include_router(openai_compat.router)
app.include_router(ingest.router)
app.include_router(birds.router)
app.include_router(vision_identify.router)
app.include_router(ovosfera_bridge.router)
app.include_router(survey.router)

# ── Dashboard gallineros (HTML estático) ──
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import pathlib

_DASHBOARD_DIR = pathlib.Path("/app/dashboard")
if _DASHBOARD_DIR.exists():
    app.mount("/dashboard", StaticFiles(directory=str(_DASHBOARD_DIR), html=True), name="dashboard")


@app.get("/")
async def root():
    return {"service": "Seedy Backend", "version": "0.1.0", "docs": "/docs"}
