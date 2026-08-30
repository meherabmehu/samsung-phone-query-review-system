"""Tests for the multi-agent workflow (specification + review agents)."""
from __future__ import annotations

from app.agents.crew import ReviewCrew
from app.agents.review_agent import ReviewAgent
from app.agents.specification_agent import SpecificationAgent
from app.database.crud import get_latest_review
from app.rag.llm import GroundedLLM


def test_specification_agent(seeded, session):
    report = SpecificationAgent(session).run("s23")
    assert report is not None
    assert report.phone_name == "Samsung Galaxy S23"
    assert len(report.specs) >= 1
    assert report.numeric["battery_capacity_mah"] == 3900
    assert report.get("Platform", "Chipset") == "Snapdragon 8 Gen 2"


def test_specification_agent_unknown(session):
    assert SpecificationAgent(session).run("nokia 3310") is None


def test_review_agent_uses_specs(seeded, session):
    report = SpecificationAgent(session).run("s23")
    result = ReviewAgent(llm=GroundedLLM()).run(report)
    assert result.phone_name == "Samsung Galaxy S23"
    assert "Display" in result.review
    assert "Snapdragon 8 Gen 2" in result.review
    assert "3900 mAh" in result.review


def test_review_workflow_persists(seeded, session):
    result = ReviewCrew(session, llm=GroundedLLM()).review_phone("Samsung Galaxy S22 5G")
    assert result is not None
    assert result.saved is True
    assert result.specs_used >= 1
    # Review was persisted to the DB.
    from app.database.crud import resolve_phone

    phone = resolve_phone(session, "s22")
    stored = get_latest_review(session, phone)
    assert stored is not None
    assert "Display" in stored.content


def test_review_workflow_unknown_phone(seeded, session):
    assert ReviewCrew(session, llm=GroundedLLM()).review_phone("Nokia 3310") is None
