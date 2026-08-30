"""FastAPI application — Samsung Phone Query and Review System.

Exposes endpoints for health checks, phone lookups, free-form queries, RAG
chat and multi-agent review generation. All responses come from the real
database / RAG / agent pipeline.
"""
from __future__ import annotations

from fastapi import FastAPI

from app.api.routes import router
from app.logging_setup import get_logger

logger = get_logger(__name__)

app = FastAPI(
    title="Samsung Phone Query and Review System",
    description=(
        "Query Samsung smartphone specifications, compare models, chat with a "
        "RAG-based assistant, and generate multi-agent product reviews — all "
        "backed by scraped GSMArena data stored in PostgreSQL."
    ),
    version="1.0.0",
)

app.include_router(router)


@app.on_event("startup")
def _on_startup() -> None:
    logger.info("FastAPI application started")
