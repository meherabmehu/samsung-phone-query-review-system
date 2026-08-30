"""Specification Retrieval Agent.

Understands which phone information is needed, resolves the target phone(s)
against the database, and returns a structured, factual specification payload
for the next agent in the pipeline.

Output is a ``SpecificationReport`` dataclass that the Review Agent consumes,
so the two agents communicate through a typed contract rather than free text.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session

from app.database.crud import get_spec_value, resolve_phone
from app.database.models import Phone
from app.logging_setup import get_logger

logger = get_logger(__name__)


@dataclass
class SpecificationReport:
    phone_name: str
    slug: str
    specs: list[dict[str, str]] = field(default_factory=list)
    numeric: dict[str, Any] = field(default_factory=dict)

    def get(self, category: str, key: str) -> str | None:
        for s in self.specs:
            if s["category"].lower() == category.lower() and s["key"].lower() == key.lower():
                return s["value"]
        return None

    def as_text(self) -> str:
        lines = [f"Specification report for {self.phone_name}", ""]
        by_cat: dict[str, list[str]] = {}
        for s in self.specs:
            by_cat.setdefault(s["category"], []).append(f"  {s['key']}: {s['value']}")
        for cat in by_cat:
            lines.append(cat + ":")
            lines.extend(by_cat[cat])
        return "\n".join(lines)


class SpecificationAgent:
    """Retrieves structured, factual specifications for a phone."""

    name = "specification_agent"

    def __init__(self, session: Session):
        self.session = session

    def run(self, phone_query: str) -> SpecificationReport | None:
        """Resolve the phone and return its full structured spec report."""
        phone = resolve_phone(self.session, phone_query)
        if phone is None:
            logger.warning("SpecificationAgent could not resolve phone: %r", phone_query)
            return None
        return self._build_report(phone)

    def run_on_phone(self, phone: Phone) -> SpecificationReport:
        return self._build_report(phone)

    def _build_report(self, phone: Phone) -> SpecificationReport:
        specs = [
            {"category": s.category, "key": s.key, "value": s.value}
            for s in phone.specifications
        ]
        numeric = {
            "battery_capacity_mah": phone.battery_capacity_mah,
            "display_size_inches": phone.display_size_inches,
            "main_camera_mp": phone.main_camera_mp,
            "ram_gb": phone.ram_gb,
            "weight_g": phone.weight_g,
            "price_usd": phone.price_usd,
        }
        report = SpecificationReport(
            phone_name=phone.name,
            slug=phone.slug,
            specs=specs,
            numeric=numeric,
        )
        logger.info(
            "SpecificationAgent retrieved %d specs for %s", len(specs), phone.name
        )
        return report
