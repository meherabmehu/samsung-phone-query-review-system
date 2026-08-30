"""Tests for RAG retrieval, comparison and the chatbot."""
from __future__ import annotations

from app.rag.comparison import build_comparison_text
from app.rag.retriever import Retriever


def test_retriever_has_chunks(retriever):
    assert len(retriever.chunks) > 0
    assert retriever.vectors.shape[0] == len(retriever.chunks)


def test_retriever_returns_relevant_phone(retriever):
    hits = retriever.search_phones("battery of galaxy s23", k=3)
    assert hits, "expected hits"
    # Top hit should be one of the S23 variants.
    top_name = hits[0][1]
    assert "S23" in top_name


def test_retriever_phone_filter(retriever, seeded):
    hits = retriever.search("camera", k=5, phone_ids=[seeded["s23"].id])
    assert all(h.phone_id == seeded["s23"].id for h, _s in hits)


def test_retriever_empty_query(retriever):
    assert retriever.search("   ", k=3) == []


def test_chatbot_specification(chatbot):
    r = chatbot.answer("What are the camera specs of the Samsung Galaxy S23?")
    assert r.intent == "specification"
    assert "Samsung Galaxy S23" in r.sources
    assert "50.0 MP" in r.answer or "50 MP" in r.answer


def test_chatbot_ranking_battery(chatbot):
    r = chatbot.answer("Which Samsung phone has the best battery life?")
    assert r.intent == "ranking"
    assert "Samsung Galaxy S23 Ultra" in r.answer


def test_chatbot_comparison(chatbot):
    r = chatbot.answer("Compare Galaxy S23 and S22")
    assert r.intent == "comparison"
    assert "Samsung Galaxy S23" in r.sources
    assert "Samsung Galaxy S22 5G" in r.sources


def test_chatbot_unknown_phone(chatbot):
    r = chatbot.answer("Tell me about the Nokia 3310")
    # Should not hallucinate; gracefully says nothing found.
    assert r.intent in ("open", "unknown")


def test_chatbot_empty_query(chatbot):
    r = chatbot.answer("")
    assert r.intent == "empty"


def test_comparison_text_builds(seeded, session):
    text = build_comparison_text(session, seeded["s23"], seeded["s22"])
    assert "Samsung Galaxy S23" in text
    assert "Samsung Galaxy S22 5G" in text
    assert "Chipset" in text
