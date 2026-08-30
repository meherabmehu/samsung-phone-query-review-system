"""Multi-agent orchestration.

Wires the two specialised agents into a single review workflow:

    User query
        │
        ▼
    Specification Retrieval Agent  ──►  resolves the phone, reads the database
        │
        ▼
    Structured SpecificationReport
        │
        ▼
    Product Review Agent  ──►  consumes the specs, writes the review
        │
        ▼
    Final review (persisted to the database)

The agents communicate through a typed contract (:class:`SpecificationReport`),
so each stage genuinely does its own job rather than being a renamed function.
"""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.agents.review_agent import ReviewAgent, ReviewResult
from app.agents.specification_agent import SpecificationAgent
from app.database.crud import resolve_phone, save_review
from app.database.models import Phone
from app.logging_setup import get_logger
from app.rag.llm import BaseLLM, get_llm

logger = get_logger(__name__)


@dataclass
class ReviewWorkflowResult:
    phone_name: str
    review: str
    specs_used: int
    saved: bool = False


class ReviewCrew:
    """Coordinates the specification + review agents to produce a review."""

    def __init__(self, session: Session, llm: BaseLLM | None = None):
        self.session = session
        self.spec_agent = SpecificationAgent(session)
        self.review_agent = ReviewAgent(llm=llm or get_llm())

    def review_phone(self, phone_query: str) -> ReviewWorkflowResult | None:
        """Run the full workflow for a phone named/described by ``phone_query``."""
        phone = resolve_phone(self.session, phone_query)
        if phone is None:
            logger.warning("ReviewCrew could not resolve phone: %r", phone_query)
            return None

        # 1) Specification agent fetches structured data from the DB.
        report = self.spec_agent.run_on_phone(phone)

        # 2) Review agent consumes the report and writes the review.
        result: ReviewResult = self.review_agent.run(report)

        # 3) Persist the review so it is available to the API / chatbot.
        save_review(self.session, phone, result.review)

        logger.info(
            "ReviewCrew completed review for %s (%d specs used)",
            result.phone_name,
            len(report.specs),
        )
        return ReviewWorkflowResult(
            phone_name=result.phone_name,
            review=result.review,
            specs_used=len(report.specs),
            saved=True,
        )


def run_review_workflow(session: Session, phone_query: str) -> ReviewWorkflowResult | None:
    """Convenience entry point for the API layer."""
    return ReviewCrew(session).review_phone(phone_query)
