"""Document preparation + semantic retrieval for the RAG pipeline.

Each phone is turned into a set of text chunks (one overview chunk plus one
chunk per spec category). Chunks carry metadata pointing back to the source
phone so answers can always be grounded in real database records.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from app.database.models import Phone
from app.logging_setup import get_logger
from app.rag.embeddings import BaseEmbedder, get_embedder
from app.scraper.parser import spec_sheet_to_text

logger = get_logger(__name__)


@dataclass
class Chunk:
    """A single retrievable text unit + its provenance metadata."""

    text: str
    phone_id: int
    phone_name: str
    category: str = "Overview"
    key: str = ""
    value: str = ""


def _phone_to_chunks(phone: Phone) -> list[Chunk]:
    """Build chunks for one phone: an overview + one chunk per spec category."""
    chunks: list[Chunk] = []

    # Overview chunk: identity + the key headline fields.
    overview_lines = [f"{phone.name}", f"Brand: {phone.brand or 'Samsung'}"]
    if phone.chipset:
        overview_lines.append(f"Chipset: {phone.chipset}")
    if phone.os:
        overview_lines.append(f"OS: {phone.os}")
    if phone.price and phone.price != "Not available":
        overview_lines.append(f"Price: {phone.price}")
    if phone.battery_capacity_mah:
        overview_lines.append(f"Battery: {phone.battery_capacity_mah} mAh")
    if phone.display_size_inches:
        overview_lines.append(f"Display: {phone.display_size_inches} inches")
    if phone.main_camera_mp:
        overview_lines.append(f"Main camera: {phone.main_camera_mp} MP")
    if phone.ram_gb:
        overview_lines.append(f"RAM: {phone.ram_gb} GB")
    chunks.append(
        Chunk(
            text="\n".join(overview_lines),
            phone_id=phone.id,
            phone_name=phone.name,
            category="Overview",
        )
    )

    # Per-category chunks for granular retrieval (battery, camera, display...).
    by_category: dict[str, list[str]] = {}
    for spec in phone.specifications:
        by_category.setdefault(spec.category, []).append(
            f"{spec.key}: {spec.value}"
        )
    for category, lines in by_category.items():
        chunks.append(
            Chunk(
                text=f"{phone.name} — {category}\n" + "\n".join(lines),
                phone_id=phone.id,
                phone_name=phone.name,
                category=category,
                key="",
                value="",
            )
        )
    return chunks


class Retriever:
    """In-memory semantic retriever over phone chunks (cosine similarity)."""

    def __init__(self, chunks: list[Chunk], embedder: BaseEmbedder | None = None):
        self.chunks = chunks
        self.embedder = embedder or get_embedder()
        self.vectors = self.embedder.encode([c.text for c in chunks]) if chunks else np.zeros((0, 1), dtype=np.float32)

    @classmethod
    def from_phones(cls, phones: list[Phone], embedder: BaseEmbedder | None = None) -> "Retriever":
        chunks: list[Chunk] = []
        for phone in phones:
            chunks.extend(_phone_to_chunks(phone))
        return cls(chunks, embedder=embedder)

    def search(self, query: str, k: int = 5) -> list[tuple[Chunk, float]]:
        """Return the top-k chunks with their cosine-similarity scores."""
        if not self.chunks or not query.strip():
            return []
        q = self.embedder.encode([query])[0]
        scores = self.vectors @ q  # vectors are unit-normalized
        top_idx = np.argsort(-scores)[:k]
        return [(self.chunks[i], float(scores[i])) for i in top_idx]

    def search_phones(self, query: str, k: int = 3) -> list[tuple[int, str, float]]:
        """Return the top-k *phones* relevant to a query (aggregated scores).

        Returns a list of (phone_id, phone_name, best_score).
        """
        hits = self.search(query, k=k * 10)
        best: dict[int, tuple[str, float]] = {}
        for chunk, score in hits:
            cur = best.get(chunk.phone_id)
            if cur is None or score > cur[1]:
                best[chunk.phone_id] = (chunk.phone_name, score)
        ordered = sorted(best.items(), key=lambda kv: -kv[1][1])[:k]
        return [(pid, name, score) for pid, (name, score) in ordered]


def phone_to_full_text(phone: Phone) -> str:
    """Render the complete spec sheet of a phone as one text block."""
    parsed: dict[str, Any] = {
        "name": phone.name,
        "announced": phone.announced or "",
        "released": phone.released or "",
        "price": phone.price or "",
        "specs": [
            {"category": s.category, "key": s.key, "value": s.value}
            for s in phone.specifications
        ],
    }
    return spec_sheet_to_text(parsed)
