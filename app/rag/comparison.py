"""Phone comparison utilities.

Produces structured, side-by-side comparisons of two phones using both the
denormalized numeric columns and the full spec sheet, so comparisons are
grounded in real database records.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.database.crud import get_spec_value
from app.database.models import Phone
from app.logging_setup import get_logger

logger = get_logger(__name__)

# (display label, model attribute or (category, key))
_HEADLINE_FIELDS: list[tuple[str, str]] = [
    ("Chipset", "chipset"),
    ("OS", "os"),
    ("Battery", "battery_capacity_mah"),
    ("Display size", "display_size_inches"),
    ("Main camera", "main_camera_mp"),
    ("RAM", "ram_gb"),
    ("Weight", "weight_g"),
    ("Price", "price"),
]


def _value(phone: Phone, attr: str, session: Session) -> str:
    raw = getattr(phone, attr, None)
    if attr == "battery_capacity_mah" and raw:
        return f"{raw} mAh"
    if attr == "display_size_inches" and raw:
        return f"{raw} inches"
    if attr == "main_camera_mp" and raw:
        return f"{raw} MP"
    if attr == "ram_gb" and raw:
        return f"{raw} GB"
    if attr == "weight_g" and raw:
        return f"{raw} g"
    return str(raw) if raw else "Not available"


def build_comparison_table(
    session: Session, a: Phone, b: Phone
) -> list[dict[str, str]]:
    """Return a list of rows: each row maps a feature to both phones' values."""
    rows: list[dict[str, str]] = []
    for label, attr in _HEADLINE_FIELDS:
        rows.append(
            {
                "feature": label,
                a.name: _value(a, attr, session),
                b.name: _value(b, attr, session),
            }
        )
    return rows


def build_comparison_text(session: Session, a: Phone, b: Phone) -> str:
    """Render the comparison as a readable text block for the chatbot/agents."""
    lines: list[str] = [f"Comparison: {a.name} vs {b.name}", ""]
    width = max(len(a.name), len(b.name), 14) + 2
    header = f"{'Feature'.ljust(width)}| {a.name} | {b.name}"
    lines.append(header)
    lines.append("-" * len(header))
    for row in build_comparison_table(session, a, b):
        lines.append(
            f"{row['feature'].ljust(width)}| {row[a.name]} | {row[b.name]}"
        )

    # Attach a few extra spec values that matter for reviews/decision-making.
    for cat, key, label in (
        ("Battery", "Charging", "Charging"),
        ("Display", "Type", "Display type"),
        ("Main Camera", "Video", "Main camera video"),
        ("Comms", "NFC", "NFC"),
        ("Comms", "WLAN", "Wi-Fi"),
    ):
        va = get_spec_value(session, a, cat, key)
        vb = get_spec_value(session, b, cat, key)
        if va or vb:
            lines.append(
                f"{label.ljust(width)}| {va or 'Not available'} | {vb or 'Not available'}"
            )

    return "\n".join(lines)
