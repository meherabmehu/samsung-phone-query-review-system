"""RAG conversational chatbot for Samsung phone queries.

The chatbot never answers from memory: it resolves the relevant phone(s) from
the database, retrieves the matching spec chunks, and only then composes a
response. For "best battery" / "largest display" style questions it uses the
structured numeric columns directly (an exact ordered query, not a guess).

Intents handled:
- single-phone specification questions
- comparisons between two phones
- "best / highest / largest" ranking questions
- review requests (delegated to the multi-agent pipeline)

A response is always returned with provenance (which phone(s) it used), so the
API layer can surface sources. If the LLM provider fails, the chatbot falls
back to a fully grounded deterministic answer.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session

from app.config import settings
from app.database.crud import (
    get_spec_value,
    resolve_phone,
    search_phones,
    top_phones_by,
)
from app.database.models import Phone
from app.logging_setup import get_logger
from app.rag.llm import BaseLLM, GroundedLLM, LLMError, get_llm
from app.rag.retriever import Retriever, phone_to_full_text

logger = get_logger(__name__)

# Numeric columns and the questions that should be answered with an ordered
# query rather than fuzzy retrieval.
_RANKING_MAP: dict[str, tuple[str, str]] = {
    "battery": ("battery_capacity_mah", "mAh"),
    "battery life": ("battery_capacity_mah", "mAh"),
    "battery capacity": ("battery_capacity_mah", "mAh"),
    "display": ("display_size_inches", "inches"),
    "screen": ("display_size_inches", "inches"),
    "camera": ("main_camera_mp", "MP"),
    "ram": ("ram_gb", "GB"),
}

_SUPERLATIVES = (
    "best", "highest", "largest", "biggest", "most", "top", "maximum", "max",
)


@dataclass
class ChatResponse:
    answer: str
    sources: list[str] = field(default_factory=list)
    intent: str = "unknown"


def _spec_line(session: Session, phone: Phone, category: str, key: str) -> str | None:
    return get_spec_value(session, phone, category, key)


# Keyword -> spec category mapping used to deterministically include the
# right spec section for "camera / battery / display / performance" questions,
# independent of embedding quality.
_CATEGORY_KEYWORDS: dict[str, str] = {
    "camera": "Main Camera",
    "selfie": "Selfie camera",
    "battery": "Battery",
    "charging": "Battery",
    "display": "Display",
    "screen": "Display",
    "processor": "Platform",
    "chipset": "Platform",
    "cpu": "Platform",
    "gpu": "Platform",
    "performance": "Platform",
    "storage": "Memory",
    "memory": "Memory",
    "ram": "Memory",
    "weight": "Body",
    "dimension": "Body",
    "price": "Misc",
    "connectivity": "Comms",
    "wifi": "Comms",
    "bluetooth": "Comms",
}


def _target_categories(query: str) -> list[str]:
    """Return the spec categories explicitly asked about in the query."""
    q = query.lower()
    categories = []
    for keyword, category in _CATEGORY_KEYWORDS.items():
        if keyword in q and category not in categories:
            categories.append(category)
    return categories


def _rank_intent(query: str) -> str | None:
    """Return the ranking column key if the query is a superlative question."""
    q = query.lower()
    if not any(w in q for w in _SUPERLATIVES):
        return None
    for phrase, (col, _unit) in _RANKING_MAP.items():
        if phrase in q:
            return col
    return None


def _find_mentioned_phones(session: Session, query: str) -> list[Phone]:
    """Resolve phone mentions in a query (handles comparisons)."""
    # Try to resolve the whole query and its token windows as phone names.
    found: list[Phone] = []
    seen_ids: set[int] = set()

    # Strategy 1: resolve known phone names via search_phones on name tokens.
    phones = search_phones(session, query, limit=5)
    for p in phones:
        if p.id not in seen_ids:
            seen_ids.add(p.id)
            found.append(p)

    # Strategy 2: also try resolving common short aliases embedded in the text.
    # e.g. "s23" or "s22 ultra" appear as standalone tokens.
    aliases = re.findall(r"\b(?:galaxy\s+)?(?:s\d{2}[a-z+]*|z\s*flip\d?|z\s*fold\d?|a\d{2}|m\d{2})\b", query.lower())
    for alias in aliases:
        p = resolve_phone(session, alias)
        if p and p.id not in seen_ids:
            seen_ids.add(p.id)
            found.append(p)

    return found


def _best_rank_answer(session: Session, query: str, col: str) -> ChatResponse:
    """Answer a superlative question using exact ordered DB queries."""
    unit = _RANKING_MAP[[k for k in _RANKING_MAP if _RANKING_MAP[k][0] == col][0]][1]
    top = top_phones_by(session, col, limit=3)
    if not top:
        return ChatResponse(
            answer="I couldn't find any phones to rank. The database may be empty.",
            intent="ranking",
        )
    leader = top[0]
    value = getattr(leader, col)
    label = _human_column_label(col)
    lines = [f"{leader.name} has the highest {label}: {_fmt(value)} {unit}."]
    if len(top) > 1:
        runners = ", ".join(
            f"{p.name} ({_fmt(getattr(p, col))} {unit})" for p in top[1:]
        )
        lines.append(f"Runners-up: {runners}.")
    return ChatResponse(answer=" ".join(lines), sources=[p.name for p in top], intent="ranking")


def _human_column_label(col: str) -> str:
    return {
        "battery_capacity_mah": "battery capacity",
        "display_size_inches": "display size",
        "main_camera_mp": "main camera resolution",
        "ram_gb": "RAM",
    }.get(col, col)


def _fmt(value: Any) -> str:
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


class Chatbot:
    """Retrieval-augmented chatbot over the phone database."""

    def __init__(
        self,
        session_factory,
        llm: BaseLLM | None = None,
        retriever: Retriever | None = None,
    ):
        self.session_factory = session_factory
        self.llm = llm or get_llm()
        self._retriever = retriever

    def _get_retriever(self, session: Session) -> Retriever:
        if self._retriever is None:
            from app.database.crud import list_phones

            self._retriever = Retriever.from_phones(list_phones(session))
        return self._retriever

    # ------------------------------------------------------------------ #
    def answer(self, query: str) -> ChatResponse:
        """Answer a free-text question about Samsung phones."""
        query = (query or "").strip()
        if not query:
            return ChatResponse(
                answer="Please ask a question about Samsung phones.",
                intent="empty",
            )

        session = self.session_factory()
        try:
            # 1) Superlative / ranking questions -> exact ordered query.
            rank_col = _rank_intent(query)
            if rank_col:
                return _best_rank_answer(session, query, rank_col)

            # 2) Find phones mentioned in the query.
            mentioned = _find_mentioned_phones(session, query)

            if len(mentioned) >= 2:
                return self._compare(session, query, mentioned[:2])

            if len(mentioned) == 1:
                return self._single_phone(session, query, mentioned[0])

            # 3) No specific phone -> retrieve broadly.
            return self._open_answer(session, query)
        finally:
            session.close()

    # ------------------------------------------------------------------ #
    def _single_phone(self, session: Session, query: str, phone: Phone) -> ChatResponse:
        retriever = self._get_retriever(session)
        # Constrain retrieval to the resolved phone so variants (FE/Ultra)
        # do not leak into a single-phone answer.
        hits = retriever.search(f"{phone.name} {query}", k=4, phone_ids=[phone.id])

        # Keep retrieval hits, deduped by category.
        chunks: list = []
        seen_categories: set[str] = set()
        for h, _s in hits:
            if h.category not in seen_categories:
                seen_categories.add(h.category)
                chunks.append(h)

        # Deterministically include the spec categories the user asked about
        # (e.g. "camera" -> Main Camera) so answers stay grounded even when
        # embedding similarity is weak.
        for category in _target_categories(query):
            if category in seen_categories:
                continue
            for chunk in retriever.chunks:
                if chunk.phone_id == phone.id and chunk.category == category:
                    chunks.append(chunk)
                    seen_categories.add(category)
                    break

        if not chunks:
            # Fall back to the full spec sheet if nothing matched.
            facts = phone_to_full_text(phone)
        else:
            facts = "\n".join(f"- {h.text}" for h in chunks)
        grounded = self._compose(
            query=query,
            facts=facts,
            phones=[phone.name],
            instruction=(
                f"Answer the question about {phone.name} using only the facts below. "
                "If a fact is not listed, say it is not available."
            ),
        )
        return ChatResponse(answer=grounded, sources=[phone.name], intent="specification")

    def _compare(self, session: Session, query: str, phones: list[Phone]) -> ChatResponse:
        a, b = phones
        from app.rag.comparison import build_comparison_text

        table = build_comparison_text(session, a, b)

        # Add relevant spec-category detail from retrieval.
        retriever = self._get_retriever(session)
        hits = retriever.search(
            f"{a.name} {b.name} {query}", k=4, phone_ids=[a.id, b.id]
        )
        extra = "\n".join(f"- {h.text[:400]}" for h, _s in hits)

        facts = table + "\n\nAdditional details:\n" + extra

        grounded = self._compose(
            query=query,
            facts=facts,
            phones=[p.name for p in phones],
            instruction=(
                "Compare the two phones using only the facts below. Present a clear, "
                "side-by-side comparison and, where the data supports it, say which is "
                "better in each category. Do not invent numbers."
            ),
        )
        return ChatResponse(
            answer=grounded, sources=[p.name for p in phones], intent="comparison"
        )

    def _open_answer(self, session: Session, query: str) -> ChatResponse:
        retriever = self._get_retriever(session)
        hits = retriever.search(query, k=5)
        if not hits:
            return ChatResponse(
                answer=(
                    "I couldn't find information about that in the database. "
                    "Try naming a specific phone (e.g. Galaxy S23)."
                ),
                intent="unknown",
            )
        facts = "\n".join(f"- {h.text[:500]}" for h, _s in hits)
        phones = sorted({h.phone_name for h, _s in hits})
        grounded = self._compose(
            query=query,
            facts=facts,
            phones=phones,
            instruction=(
                "Answer the question using only the facts below. If the information "
                "is not present, say so rather than guessing."
            ),
        )
        return ChatResponse(answer=grounded, sources=phones, intent="open")

    # ------------------------------------------------------------------ #
    def _compose(
        self, query: str, facts: str, phones: list[str], instruction: str
    ) -> str:
        """Build the grounded answer, using the LLM when available."""
        prompt = (
            f"{instruction}\n\n"
            f"Question: {query}\n\n"
            f"<FACTS>\n{facts}\n</FACTS>\n\n"
            f"Answer (grounded in the facts above):"
        )

        if isinstance(self.llm, GroundedLLM):
            # Deterministic, grounded response — never fabricated.
            header = f"Here is what I found for: {query}\n\n"
            return header + facts.strip()

        try:
            return self.llm.complete(prompt)
        except LLMError as exc:
            logger.warning("LLM failed (%s); returning grounded fallback", exc)
            return f"Here is what I found for: {query}\n\n" + facts.strip()

    def full_specs(self, phone: Phone) -> str:
        """Return the complete spec sheet of a phone (used by /query)."""
        return phone_to_full_text(phone)


# Convenience factory used by the API.
def build_chatbot(session_factory, llm: BaseLLM | None = None) -> Chatbot:
    return Chatbot(session_factory, llm=llm or get_llm())
