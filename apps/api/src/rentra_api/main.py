from contextlib import asynccontextmanager
from typing import AsyncGenerator
from fastapi import FastAPI, HTTPException, status
import psycopg

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
    
    Connects as rentra_api via DATABASE_URL and executes `SELECT 1`.
    """
    settings = get_settings()
    try:
        with psycopg.connect(settings.DATABASE_URL) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
                row = cur.fetchone()
                if not row or row[0] != 1:
                    raise HTTPException(
                        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                        detail="Database query returned unexpected result",
                    )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Database connection failed: {exc}",
        ) from exc
    return {"status": "ok"}

