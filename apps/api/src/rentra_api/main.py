from contextlib import asynccontextmanager
from typing import AsyncGenerator
from fastapi import FastAPI

from rentra_api.config import get_settings


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Startup and shutdown lifecycle handler.
    
    Validates required settings on startup; fails if any are missing.
    """
    get_settings()
    yield


app = FastAPI(
    title="Rentra API",
    version="0.1.0",
    lifespan=lifespan,
)


@app.get("/health", tags=["health"])
def health() -> dict[str, str]:
    """Liveness probe."""
    return {"status": "ok"}


@app.get("/health/ready", tags=["health"])
def health_ready() -> dict[str, str]:
    """Readiness probe.
    
    Will execute `SELECT 1` as `rentra_api` once database connectivity is configured.
    """
    return {"status": "ok"}
