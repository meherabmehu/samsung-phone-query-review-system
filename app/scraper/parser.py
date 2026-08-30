"""Parsing helpers that turn a raw GSMArena phone page into structured data.

The module is deliberately split from the network code so it can be tested on
saved HTML without touching the internet.

The core output is a dict::

    {
        "name": str, "slug": str, "url": str, "image_url": str,
        "announced": str, "released": str, "price": str,
        "price_usd": float | None,
        "chipset": str | None, "os": str | None,
        "battery_capacity_mah": int | None,
        "display_size_inches": float | None,
        "main_camera_mp": float | None,
        "ram_gb": float | None,
        "weight_g": int | None,
        "specs": [{"category": str, "key": str, "value": str}, ...],
    }
"""
from __future__ import annotations

import re
from typing import Any

from bs4 import BeautifulSoup, Tag

# Fields that, when missing, should still be represented as "Not available"
# rather than dropped entirely (keeps output predictable for downstream code).
NOT_AVAILABLE = "Not available"


def _clean(text: str) -> str:
    """Collapse whitespace and replace non-breaking spaces."""
    return re.sub(r"\s+", " ", text.replace("\xa0", " ")).strip()


def extract_battery_mah(text: str) -> int | None:
    """Return battery capacity in mAh from a spec string, else None."""
    m = re.search(r"(\d{3,5})\s*mAh", text, flags=re.IGNORECASE)
    return int(m.group(1)) if m else None


def extract_display_size_inches(text: str) -> float | None:
    """Return the display diagonal in inches, else None."""
    m = re.search(r"(\d+(?:\.\d+)?)\s*inches", text, flags=re.IGNORECASE)
    return float(m.group(1)) if m else None


def extract_main_camera_mp(text: str) -> float | None:
    """Return the main (rear) camera resolution in megapixels, else None.

    Uses the first ``NN MP`` occurrence, which on GSMArena is the primary
    wide camera.
    """
    m = re.search(r"(\d+(?:\.\d+)?)\s*MP", text, flags=re.IGNORECASE)
    return float(m.group(1)) if m else None


def extract_ram_gb(text: str) -> float | None:
    """Return the largest RAM option in GB from an 'Internal' spec string."""
    matches = re.findall(r"(\d+(?:\.\d+)?)\s*GB\s*RAM", text, flags=re.IGNORECASE)
    if not matches:
        return None
    return max(float(x) for x in matches)


def extract_weight_g(text: str) -> int | None:
    """Return weight in grams, else None."""
    m = re.search(r"(\d+)\s*g\b", text, flags=re.IGNORECASE)
    return int(m.group(1)) if m else None


def extract_price_usd(text: str) -> float | None:
    """Return the first USD price as a float, else None."""
    m = re.search(r"\$\s*([\d,]+(?:\.\d+)?)", text)
    if not m:
        return None
    return float(m.group(1).replace(",", ""))


def _extract_spec_tables(soup: BeautifulSoup) -> list[dict[str, str]]:
    """Walk ``#specs-list`` and return a flat list of category/key/value dicts.

    Rows without a label (GSMArena continuation rows) are appended to the
    previous key so multi-line values are preserved.
    """
    specs: list[dict[str, str]] = []
    tables = soup.select("#specs-list table")
    for table in tables:
        th = table.find("th")
        category = _clean(th.get_text(" ", strip=True)) if th else "Other"
        current_key: str | None = None
        lines: list[str] = []

        def flush() -> None:
            if current_key and lines:
                specs.append(
                    {
                        "category": category,
                        "key": current_key,
                        "value": " | ".join(lines),
                    }
                )

        for tr in table.select("tr"):
            ttl = tr.select_one(".ttl")
            nfo = tr.select_one(".nfo")
            label = _clean(ttl.get_text(" ", strip=True)) if ttl else ""
            value = _clean(nfo.get_text(" ", strip=True)) if nfo else ""
            if label:
                flush()
                current_key = label
                lines = [value] if value else []
            elif value and current_key:
                lines.append(value)
        flush()

    return specs


def _get(specs: list[dict[str, str]], category: str, key: str) -> str | None:
    """Look up a single spec value by exact category + key (case-insensitive)."""
    for s in specs:
        if s["category"].lower() == category.lower() and s["key"].lower() == key.lower():
            return s["value"]
    return None


def parse_phone_page(html: str, slug: str = "", url: str = "") -> dict[str, Any]:
    """Parse a GSMArena phone detail page into a structured dict.

    Missing fields become ``None`` (or "Not available" for the raw text
    columns that the chatbot displays directly). Nothing is fabricated.
    """
    soup = BeautifulSoup(html, "lxml")

    title_el = soup.select_one("h1.specs-phone-name-title")
    name = _clean(title_el.get_text(" ", strip=True)) if title_el else (slug or "Unknown")

    img_el = soup.select_one(".specs-photo-main img")
    image_url = img_el.get("src") if img_el else None

    specs = _extract_spec_tables(soup)

    announced = _get(specs, "Launch", "Announced")
    released = _get(specs, "Launch", "Status")
    price = _get(specs, "Misc", "Price")
    chipset = _get(specs, "Platform", "Chipset")
    os = _get(specs, "Platform", "OS")

    display_size_raw = _get(specs, "Display", "Size")
    battery_raw = _get(specs, "Battery", "Type")
    camera_raw = _get(specs, "Main Camera", "Triple") or _get(
        specs, "Main Camera", "Quad"
    ) or _get(specs, "Main Camera", "Single") or _get(
        specs, "Main Camera", "Dual"
    )
    internal_raw = _get(specs, "Memory", "Internal")
    weight_raw = _get(specs, "Body", "Weight")

    return {
        "name": name,
        "slug": slug,
        "url": url,
        "image_url": image_url,
        "announced": announced or NOT_AVAILABLE,
        "released": released or NOT_AVAILABLE,
        "price": price or NOT_AVAILABLE,
        "price_usd": extract_price_usd(price) if price else None,
        "chipset": chipset,
        "os": os,
        "battery_capacity_mah": extract_battery_mah(battery_raw)
        if battery_raw
        else None,
        "display_size_inches": extract_display_size_inches(display_size_raw)
        if display_size_raw
        else None,
        "main_camera_mp": extract_main_camera_mp(camera_raw) if camera_raw else None,
        "ram_gb": extract_ram_gb(internal_raw) if internal_raw else None,
        "weight_g": extract_weight_g(weight_raw) if weight_raw else None,
        "specs": specs,
    }


def spec_sheet_to_text(parsed: dict[str, Any]) -> str:
    """Render a parsed phone into a human-readable text block (for RAG)."""
    lines: list[str] = [f"Phone: {parsed['name']}"]
    for label, key in (
        ("Announced", "announced"),
        ("Released", "released"),
        ("Price", "price"),
    ):
        val = parsed.get(key)
        if val and val != NOT_AVAILABLE:
            lines.append(f"{label}: {val}")
    current_cat: str | None = None
    for s in parsed["specs"]:
        if s["category"] != current_cat:
            lines.append(f"\n{s['category']}:")
            current_cat = s["category"]
        lines.append(f"  {s['key']}: {s['value']}")
    return "\n".join(lines)
