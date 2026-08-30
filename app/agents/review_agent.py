"""Product Review Agent.

Consumes a structured :class:`SpecificationReport` produced by the
Specification Retrieval Agent and writes a detailed, honest product review:
display, cameras, performance, battery, strengths, weaknesses and an overall
assessment. Every claim is backed by the retrieved specs — the agent never
invents figures.

When an LLM is configured it is used to polish the prose; otherwise a
deterministic, grounded review is assembled directly from the specs.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.agents.specification_agent import SpecificationReport
from app.logging_setup import get_logger
from app.rag.llm import GroundedLLM, LLMError, get_llm

logger = get_logger(__name__)


@dataclass
class ReviewResult:
    phone_name: str
    review: str


def _val(report: SpecificationReport, category: str, key: str) -> str:
    return report.get(category, key) or "Not available"


def _extract_sections(report: SpecificationReport) -> dict[str, str]:
    """Pull the raw spec facts the review needs, into named sections."""
    num = report.numeric
    battery = f"{num['battery_capacity_mah']} mAh" if num.get("battery_capacity_mah") else "Not available"
    display_size = f"{num['display_size_inches']} inches" if num.get("display_size_inches") else "Not available"
    camera_mp = f"{num['main_camera_mp']} MP" if num.get("main_camera_mp") else "Not available"
    ram = f"{num['ram_gb']} GB" if num.get("ram_gb") else "Not available"

    return {
        "display": (
            f"Type: {_val(report, 'Display', 'Type')}\n"
            f"Size: {_val(report, 'Display', 'Size')}\n"
            f"Resolution: {_val(report, 'Display', 'Resolution')}\n"
            f"Protection: {_val(report, 'Display', 'Protection')}"
        ),
        "camera": (
            f"Main camera: {_val(report, 'Main Camera', 'Triple') or _val(report, 'Main Camera', 'Quad') or _val(report, 'Main Camera', 'Single') or _val(report, 'Main Camera', 'Dual') or camera_mp}\n"
            f"Features: {_val(report, 'Main Camera', 'Features')}\n"
            f"Video: {_val(report, 'Main Camera', 'Video')}\n"
            f"Selfie camera: {_val(report, 'Selfie camera', 'Single')}\n"
            f"Selfie video: {_val(report, 'Selfie camera', 'Video')}"
        ),
        "performance": (
            f"Chipset: {_val(report, 'Platform', 'Chipset')}\n"
            f"CPU: {_val(report, 'Platform', 'CPU')}\n"
            f"GPU: {_val(report, 'Platform', 'GPU')}\n"
            f"OS: {_val(report, 'Platform', 'OS')}\n"
            f"RAM: {ram}\n"
            f"Internal storage: {_val(report, 'Memory', 'Internal')}"
        ),
        "battery": (
            f"Type: {_val(report, 'Battery', 'Type')}\n"
            f"Charging: {_val(report, 'Battery', 'Charging')}"
        ),
        "design": (
            f"Dimensions: {_val(report, 'Body', 'Dimensions')}\n"
            f"Weight: {_val(report, 'Body', 'Weight')}\n"
            f"Build: {_val(report, 'Body', 'Build')}\n"
            f"Colors: {_val(report, 'Misc', 'Colors')}"
        ),
        "price": _val(report, "Misc", "Price"),
    }


class ReviewAgent:
    """Generates a grounded product review from a specification report."""

    name = "review_agent"

    def __init__(self, llm=None):
        self.llm = llm or get_llm()

    def run(self, report: SpecificationReport) -> ReviewResult:
        sections = _extract_sections(report)

        if isinstance(self.llm, GroundedLLM):
            review = self._compose_review(report.phone_name, sections)
        else:
            prompt = self._build_prompt(report.phone_name, sections)
            try:
                review = self.llm.complete(prompt)
            except LLMError as exc:
                logger.warning("LLM failed in ReviewAgent (%s); using grounded review", exc)
                review = self._compose_review(report.phone_name, sections)

        logger.info("ReviewAgent generated review for %s", report.phone_name)
        return ReviewResult(phone_name=report.phone_name, review=review)

    # ------------------------------------------------------------------ #
    @staticmethod
    def _build_prompt(phone_name: str, sections: dict[str, str]) -> str:
        return (
            "You are a tech product reviewer. Write a detailed, honest review of the "
            f"phone {phone_name} using ONLY the specifications below. Do not invent "
            "numbers or features that are not listed. Cover, in order: display, "
            "cameras, performance, battery and charging, design, price and value, "
            "strengths, weaknesses, and an overall assessment.\n\n"
            "<SPECIFICATIONS>\n"
            f"Display:\n{sections['display']}\n\n"
            f"Cameras:\n{sections['camera']}\n\n"
            f"Performance:\n{sections['performance']}\n\n"
            f"Battery:\n{sections['battery']}\n\n"
            f"Design:\n{sections['design']}\n\n"
            f"Price: {sections['price']}\n"
            "</SPECIFICATIONS>\n\n"
            "Review:"
        )

    @staticmethod
    def _compose_review(phone_name: str, sections: dict[str, str]) -> str:
        """Deterministic, grounded review assembled from the specs."""
        lines: list[str] = []
        lines.append(f"# Review: {phone_name}")
        lines.append("")

        lines.append("## Display")
        lines.append(sections["display"])
        lines.append("")

        lines.append("## Cameras")
        lines.append(sections["camera"])
        lines.append("")

        lines.append("## Performance")
        lines.append(sections["performance"])
        lines.append("")

        lines.append("## Battery & Charging")
        lines.append(sections["battery"])
        lines.append("")

        lines.append("## Design")
        lines.append(sections["design"])
        lines.append("")

        lines.append("## Price & Value")
        lines.append(sections["price"])
        lines.append("")

        lines.append("## Overall Assessment")
        lines.append(
            f"Based on the retrieved specifications, the {phone_name} ships with the "
            "hardware listed above. Please refer to each section for the exact figures "
            "(display, cameras, chipset, battery and charging) as published by the "
            "manufacturer. This review is generated strictly from the scraped "
            "database records and does not add subjective claims beyond them."
        )
        return "\n".join(lines)
