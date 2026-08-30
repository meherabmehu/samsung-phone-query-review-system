"""FastAPI application — Samsung Phone Query and Review System.

Exposes endpoints for health checks, phone lookups, free-form queries, RAG
chat and multi-agent review generation. All responses come from the real
database / RAG / agent pipeline.
"""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.api.routes import router
from app.logging_setup import get_logger

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("FastAPI application started")
    yield
    logger.info("FastAPI application shutting down")


app = FastAPI(
    title="Samsung Phone Query and Review System",
    description=(
        "Query Samsung smartphone specifications, compare models, chat with a "
        "RAG-based assistant, and generate multi-agent product reviews — all "
        "backed by scraped GSMArena data stored in PostgreSQL."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

app.include_router(router)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Return a clean 500 without leaking stack traces to clients."""
    logger.exception("Unhandled error on %s %s: %s", request.method, request.url.path, exc)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error. Please try again later."},
    )
