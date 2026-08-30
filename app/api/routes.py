"""API routes for the Samsung Phone Query and Review System."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.agents.crew import run_review_workflow
from app.config import settings
from app.database.connection import get_db
from app.database.crud import (
    count_phones,
    get_specifications,
    list_phones,
    resolve_phone,
)
from app.database.models import Phone
from app.logging_setup import get_logger
from app.rag.chatbot import Chatbot, build_chatbot
from app.schemas.schemas import (
    ChatRequest,
    ChatResponse,
    HealthResponse,
    PhoneDetail,
    PhoneSummary,
    QueryRequest,
    QueryResponse,
    ReviewRequest,
    ReviewResponse,
)

logger = get_logger(__name__)

router = APIRouter()

# A module-level chatbot, lazily created (embeddings load once).
_chatbot: Chatbot | None = None


def _get_chatbot() -> Chatbot:
    global _chatbot
    if _chatbot is None:
        _chatbot = build_chatbot(get_db)
    return _chatbot


def _phone_to_summary(p: Phone) -> PhoneSummary:
    return PhoneSummary(
        id=p.id,
        name=p.name,
        slug=p.slug,
        chipset=p.chipset,
        price=p.price,
        battery_capacity_mah=p.battery_capacity_mah,
        display_size_inches=p.display_size_inches,
        main_camera_mp=p.main_camera_mp,
        ram_gb=p.ram_gb,
        weight_g=p.weight_g,
    )


def _phone_to_detail(p: Phone, db: Session) -> PhoneDetail:
    specs = [
        {"category": s.category, "key": s.key, "value": s.value}
        for s in get_specifications(db, p)
    ]
    return PhoneDetail(
        id=p.id,
        name=p.name,
        slug=p.slug,
        brand=p.brand,
        announced=p.announced,
        released=p.released,
        price=p.price,
        chipset=p.chipset,
        os=p.os,
        battery_capacity_mah=p.battery_capacity_mah,
        display_size_inches=p.display_size_inches,
        main_camera_mp=p.main_camera_mp,
        ram_gb=p.ram_gb,
        weight_g=p.weight_g,
        specifications=specs,
    )


@router.get("/", tags=["meta"])
def root() -> dict:
    return {
        "service": "Samsung Phone Query and Review System",
        "docs": "/docs",
        "health": "/health",
    }


@router.get("/health", response_model=HealthResponse, tags=["meta"])
def health(db: Session = Depends(get_db)) -> HealthResponse:
    """Liveness check that also verifies the database."""
    try:
        n = count_phones(db)
        db_status = "ok"
    except Exception as exc:  # pragma: no cover - depends on DB availability
        logger.exception("Health check DB failure: %s", exc)
        db_status = "error"
        n = None
    return HealthResponse(
        status="ok",
        database=db_status,
        phones_in_db=n,
        llm_provider=settings.llm_provider,
    )


@router.get("/phones", response_model=list[PhoneSummary], tags=["phones"])
def get_phones(db: Session = Depends(get_db)) -> list[PhoneSummary]:
    """List all phones in the database (summary fields)."""
    phones = list_phones(db)
    logger.info("Listed %d phones", len(phones))
    return [_phone_to_summary(p) for p in phones]


@router.get("/phones/{phone_name}", response_model=PhoneDetail, tags=["phones"])
def get_phone(phone_name: str, db: Session = Depends(get_db)) -> PhoneDetail:
    """Return a single phone's full specification sheet by (fuzzy) name."""
    phone = resolve_phone(db, phone_name)
    if phone is None:
        raise HTTPException(status_code=404, detail=f"Phone not found: {phone_name}")
    return _phone_to_detail(phone, db)


@router.post("/query", response_model=QueryResponse, tags=["query"])
def query(req: QueryRequest, db: Session = Depends(get_db)) -> QueryResponse:
    """Answer a free-text question about Samsung phones (structured retrieval)."""
    if not req.query.strip():
        raise HTTPException(status_code=400, detail="Query must not be empty.")
    chatbot = _get_chatbot()
    result = chatbot.answer(req.query)
    return QueryResponse(query=req.query, answer=result.answer)


@router.post("/chat", response_model=ChatResponse, tags=["query"])
def chat(req: ChatRequest, db: Session = Depends(get_db)) -> ChatResponse:
    """RAG chatbot: retrieve relevant phone data, then answer."""
    if not req.message.strip():
        raise HTTPException(status_code=400, detail="Message must not be empty.")
    chatbot = _get_chatbot()
    result = chatbot.answer(req.message)
    return ChatResponse(
        query=req.message,
        intent=result.intent,
        sources=result.sources,
        answer=result.answer,
    )


@router.post("/review", response_model=ReviewResponse, tags=["review"])
def review(req: ReviewRequest, db: Session = Depends(get_db)) -> ReviewResponse:
    """Generate a product review via the multi-agent workflow."""
    if not req.phone_name.strip():
        raise HTTPException(status_code=400, detail="phone_name must not be empty.")
    result = run_review_workflow(db, req.phone_name)
    if result is None:
        raise HTTPException(
            status_code=404, detail=f"Phone not found: {req.phone_name}"
        )
    return ReviewResponse(
        phone_name=result.phone_name,
        review=result.review,
        specs_used=result.specs_used,
        saved=result.saved,
    )
