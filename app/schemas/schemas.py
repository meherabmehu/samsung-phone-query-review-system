"""Pydantic schemas for API request/response bodies."""
from __future__ import annotations

from pydantic import BaseModel, Field


# --- Requests ------------------------------------------------------------- #
class QueryRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=1000, description="Free-text question about Samsung phones.")


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=1000, description="Chat message for the RAG chatbot.")


class ReviewRequest(BaseModel):
    phone_name: str = Field(..., min_length=1, max_length=200, description="Name of the phone to review (e.g. 'Galaxy S23').")


# --- Responses ------------------------------------------------------------ #
class HealthResponse(BaseModel):
    status: str
    database: str
    phones_in_db: int | None = None
    llm_provider: str | None = None


class PhoneSummary(BaseModel):
    id: int
    name: str
    slug: str
    chipset: str | None = None
    price: str | None = None
    battery_capacity_mah: int | None = None
    display_size_inches: float | None = None
    main_camera_mp: float | None = None
    ram_gb: float | None = None
    weight_g: int | None = None


class PhoneDetail(BaseModel):
    id: int
    name: str
    slug: str
    brand: str | None = None
    announced: str | None = None
    released: str | None = None
    price: str | None = None
    chipset: str | None = None
    os: str | None = None
    battery_capacity_mah: int | None = None
    display_size_inches: float | None = None
    main_camera_mp: float | None = None
    ram_gb: float | None = None
    weight_g: int | None = None
    specifications: list[dict[str, str]] = []


class ChatResponse(BaseModel):
    query: str
    intent: str
    sources: list[str] = []
    answer: str


class QueryResponse(BaseModel):
    query: str
    answer: str


class ReviewResponse(BaseModel):
    phone_name: str
    review: str
    specs_used: int | None = None
    saved: bool | None = None
