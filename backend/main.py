"""SCL-Governor -- FastAPI application entry point.

This is the main module for the LLM-Supervised Control Loop Governor.  It
wires up middleware, routers, lifecycle hooks, and exposes the ASGI app
object that uvicorn serves.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncGenerator

import redis.asyncio as aioredis
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse

from config import get_settings
from core.shared import init_governor, get_governor
from routes.config_routes import reload_yaml_configs
from routes.governor import router as governor_router
from routes.telemetry import router as telemetry_router
from routes.decisions import router as decisions_router
from routes.config_routes import router as config_router
from routes.simulation import router as simulation_router
from routes.websocket import router as ws_router, manager as ws_manager
from routes.connections import router as connections_router
from utils.logger import get_logger

log = get_logger(__name__)

# -- Redis connection (module-level so it can be shared) -------------------
_redis: aioredis.Redis | None = None


async def get_redis() -> aioredis.Redis:
    """Return the shared async Redis connection."""
    if _redis is None:
        raise RuntimeError("Redis has not been initialised yet")
    return _redis


# -- Lifespan --------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan: startup and shutdown logic."""
    global _redis  # noqa: PLW0603
    settings = get_settings()

    # -- Startup ---------------------------------------------------------------
    log.info(
        "startup",
        app=settings.APP_NAME,
        version=settings.APP_VERSION,
        debug=settings.DEBUG,
    )

    # Initialise the governor singleton and wire the WebSocket manager
    governor = init_governor()
    governor._ws_manager = ws_manager
    log.info("governor_singleton_initialized")

    # Attempt Redis connection (non-fatal if Redis is unavailable during dev)
    try:
        _redis = aioredis.from_url(
            settings.REDIS_URL,
            encoding="utf-8",
            decode_responses=True,
        )
        await _redis.ping()
        log.info("redis_connected", url=settings.REDIS_URL)
    except Exception as exc:
        log.warning("redis_unavailable", error=str(exc))
        _redis = None

    # Load YAML configuration files
    reload_yaml_configs()

    log.info("startup_complete")

    yield  # Application is running

    # -- Shutdown --------------------------------------------------------------
    # Stop the control loop if it's running
    governor = get_governor()
    if governor.is_running:
        governor.stop()
        log.info("governor_stopped_on_shutdown")

    # Close connectors
    try:
        await governor.prometheus.close()
    except Exception:
        pass
    try:
        await governor.notifications.close()
    except Exception:
        pass

    if _redis is not None:
        await _redis.aclose()
        log.info("redis_disconnected")

    log.info("shutdown_complete")


# -- Application factory ---------------------------------------------------

settings = get_settings()

app = FastAPI(
    title="SCL-Governor API",
    description=(
        "LLM-Supervised Control Loop Governor -- replaces static Kubernetes "
        "autoscalers with an AI-driven feedback loop: "
        "Observe -> Predict -> Simulate -> Decide -> Actuate -> Learn"
    ),
    version=settings.APP_VERSION,
    lifespan=lifespan,
)

# -- CORS ------------------------------------------------------------------

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -- Routers ---------------------------------------------------------------

app.include_router(governor_router, prefix="/api/v1")
app.include_router(telemetry_router, prefix="/api/v1")
app.include_router(decisions_router, prefix="/api/v1")
app.include_router(config_router, prefix="/api/v1")
app.include_router(simulation_router, prefix="/api/v1")
app.include_router(ws_router, prefix="/api/v1")
app.include_router(connections_router, prefix="/api/v1")

# -- Top-level endpoints ---------------------------------------------------


@app.get("/", include_in_schema=False)
async def root() -> RedirectResponse:
    """Redirect the root URL to the interactive API docs."""
    return RedirectResponse(url="/docs")


@app.get("/health")
async def health() -> dict[str, str]:
    """Liveness / readiness probe."""
    return {
        "status": "healthy",
        "version": settings.APP_VERSION,
    }
