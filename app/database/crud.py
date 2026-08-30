"""CRUD + retrieval helpers on top of the ORM models.

Includes :func:`resolve_phone`, a tolerant resolver that maps user text like
``"s23"``, ``"Galaxy S22"`` or ``"z flip5"`` onto the correct database record —
this is what lets the API and chatbot understand short/fuzzy phone names.
"""
from __future__ import annotations

import re
from typing import Any

from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.database.models import Phone, Review, Specification
from app.logging_setup import get_logger

logger = get_logger(__name__)

_BRAND_WORDS = {"samsung", "galaxy", "5g", "phone"}


def normalize_name(text: str) -> str:
    """Lowercase, drop brand words, and collapse to token-safe text."""
    text = text.lower()
    text = re.sub(r"\b(?:samsung|galaxy|5g)\b", " ", text)
    text = re.sub(r"[^a-z0-9+ ]", " ", text)
    return " ".join(text.split())


def _tokens(text: str) -> set[str]:
    return set(normalize_name(text).split())


# --------------------------------------------------------------------------- #
# Phone upsert / retrieval
# --------------------------------------------------------------------------- #
def upsert_phone(session: Session, data: dict[str, Any]) -> Phone:
    """Insert a scraped phone or update it if the slug already exists.

    Duplicate protection is by unique ``slug`` (GSMArena slug is stable).
    """
    slug = data["slug"]
    phone = session.query(Phone).filter(Phone.slug == slug).first()
    if phone is None:
        phone = Phone(slug=slug)
        session.add(phone)
        logger.info("Inserting new phone: %s", data["name"])
    else:
        logger.info("Updating existing phone: %s", slug)

    for field in (
        "name", "brand", "image_url", "url", "announced", "released",
        "price", "chipset", "os", "price_usd", "battery_capacity_mah",
        "display_size_inches", "main_camera_mp", "ram_gb", "weight_g",
    ):
        if field in data:
            setattr(phone, field, data[field])

    # Flush so a newly-inserted phone gets its id before specs reference it.
    session.flush()

    # Replace the spec sheet (specs are authoritative per scrape).
    session.query(Specification).filter(Specification.phone_id == phone.id).delete()
    for spec in data.get("specs", []):
        session.add(
            Specification(
                phone_id=phone.id,
                category=spec["category"],
                key=spec["key"],
                value=spec["value"],
            )
        )
    session.commit()
    session.refresh(phone)
    return phone


def list_phones(session: Session) -> list[Phone]:
    """Return all phones ordered by name."""
    return session.query(Phone).order_by(Phone.name).all()


def get_phone_by_id(session: Session, phone_id: int) -> Phone | None:
    return session.query(Phone).filter(Phone.id == phone_id).first()


def get_phone_by_slug(session: Session, slug: str) -> Phone | None:
    return session.query(Phone).filter(Phone.slug == slug).first()


def resolve_phone(session: Session, query: str) -> Phone | None:
    """Map a fuzzy user query to the best-matching phone, or None.

    Prefers exact name/slug matches, then the phone whose normalized tokens
    contain every query token with the fewest extra tokens (so ``"s21"`` picks
    the base S21 rather than the Ultra/FE variants, and ``"s21 ultra"`` picks
    the Ultra).
    """
    q = normalize_name(query)
    if not q:
        return None
    q_tokens = set(q.split())

    exact_name = None
    candidates: list[tuple[int, int, Phone]] = []

    for phone in session.query(Phone).all():
        p_name = normalize_name(phone.name)
        p_slug = normalize_name(phone.slug)
        if q == p_name or q == p_slug:
            exact_name = phone
            break
        p_tokens = _tokens(phone.name) | _tokens(phone.slug)
        if q_tokens.issubset(p_tokens):
            extra = len(p_tokens - q_tokens)
            candidates.append((extra, phone.id, phone))

    if exact_name is not None:
        return exact_name
    if not candidates:
        return None
    candidates.sort(key=lambda t: (t[0], t[1]))
    return candidates[0][2]


def search_phones(session: Session, query: str, limit: int = 10) -> list[Phone]:
    """Return phones whose name/slug contain the query tokens (substring)."""
    q = normalize_name(query)
    if not q:
        return []
    matches = []
    for phone in session.query(Phone).all():
        haystack = normalize_name(phone.name) + " " + normalize_name(phone.slug)
        if q in haystack:
            matches.append(phone)
    return matches[:limit]


# --------------------------------------------------------------------------- #
# Spec helpers
# --------------------------------------------------------------------------- #
def get_specifications(session: Session, phone: Phone) -> list[Specification]:
    return (
        session.query(Specification)
        .filter(Specification.phone_id == phone.id)
        .order_by(Specification.id)
        .all()
    )


def get_spec_value(
    session: Session, phone: Phone, category: str, key: str
) -> str | None:
    """Return a single spec value by category + key (case-insensitive), or None."""
    spec = (
        session.query(Specification)
        .filter(
            Specification.phone_id == phone.id,
            Specification.category.ilike(category),
            Specification.key.ilike(key),
        )
        .first()
    )
    return spec.value if spec else None


def top_phones_by(
    session: Session, column: str, limit: int = 3
) -> list[Phone]:
    """Return phones ordered descending by a numeric column (NULLs last)."""
    allowed = {
        "battery_capacity_mah",
        "display_size_inches",
        "main_camera_mp",
        "ram_gb",
        "weight_g",
        "price_usd",
    }
    if column not in allowed:
        raise ValueError(f"column {column!r} not sortable")
    col = getattr(Phone, column)
    return (
        session.query(Phone)
        .order_by(desc(col), Phone.name)
        .limit(limit)
        .all()
    )


# --------------------------------------------------------------------------- #
# Reviews
# --------------------------------------------------------------------------- #
def save_review(session: Session, phone: Phone, content: str) -> Review:
    review = Review(phone_id=phone.id, content=content)
    session.add(review)
    session.commit()
    session.refresh(review)
    return review


def get_latest_review(session: Session, phone: Phone) -> Review | None:
    return (
        session.query(Review)
        .filter(Review.phone_id == phone.id)
        .order_by(Review.created_at.desc())
        .first()
    )


def count_phones(session: Session) -> int:
    return session.query(Phone).count()
