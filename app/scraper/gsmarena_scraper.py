"""GSMArena Samsung phone scraper.

Fetches the Samsung brand listing to discover phones and then scrapes each
detail page. The scraper is polite (a configurable delay between requests),
retries transient network errors, skips pages it cannot parse, and never
touches anything behind authentication or CAPTCHAs.
"""
from __future__ import annotations

import time
from typing import Any

import requests
from bs4 import BeautifulSoup

from app.logging_setup import get_logger
from app.scraper.parser import parse_phone_page

logger = get_logger(__name__)

BASE_URL = "https://www.gsmarena.com"
SAMSUNG_BRAND_URL = f"{BASE_URL}/samsung-phones-9.php"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/122.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

# A curated, deterministic set of popular Samsung models used by the default
# scrape script. Slugs are the stable GSMArena identifiers.
DEFAULT_MODELS: list[str] = [
    "samsung_galaxy_s21_5g-10626.php",
    "samsung_galaxy_s21_ultra_5g-10596.php",
    "samsung_galaxy_s22_5g-11253.php",
    "samsung_galaxy_s22_ultra_5g-11251.php",
    "samsung_galaxy_s23-12082.php",
    "samsung_galaxy_s23_ultra-12024.php",
    "samsung_galaxy_s23_fe-12520.php",
    "samsung_galaxy_s24-12773.php",
    "samsung_galaxy_s24_ultra-12771.php",
    "samsung_galaxy_a54-12070.php",
    "samsung_galaxy_a34-12074.php",
    "samsung_galaxy_a15_5g-12638.php",
    "samsung_galaxy_m54-12189.php",
    "samsung_galaxy_z_flip5-12252.php",
    "samsung_galaxy_z_fold5-12418.php",
]

MAX_RETRIES = 3
RETRY_BACKOFF = 2.0


def _get(url: str, session: requests.Session) -> str | None:
    """GET a URL with retries/backoff. Returns HTML text or None on failure."""
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = session.get(url, headers=HEADERS, timeout=30)
            if resp.status_code == 200:
                return resp.text
            logger.warning(
                "HTTP %s for %s (attempt %d/%d)",
                resp.status_code,
                url,
                attempt,
                MAX_RETRIES,
            )
        except requests.RequestException as exc:
            logger.warning("Request error for %s: %s (attempt %d/%d)",
                           url, exc, attempt, MAX_RETRIES)
        if attempt < MAX_RETRIES:
            time.sleep(RETRY_BACKOFF * attempt)
    logger.error("Giving up on %s after %d attempts", url, MAX_RETRIES)
    return None


def discover_samsung_phones(max_pages: int = 30) -> list[dict[str, str]]:
    """Return every Samsung phone listed on the brand pages (name/slug/url)."""
    phones: list[dict[str, str]] = []
    seen: set[str] = set()
    with requests.Session() as session:
        for page in range(1, max_pages + 1):
            url = SAMSUNG_BRAND_URL if page == 1 else (
                f"{BASE_URL}/samsung-phones-f-9-0-p{page}.php"
            )
            html = _get(url, session)
            if html is None:
                break
            soup = BeautifulSoup(html, "lxml")
            items = soup.select(".makers ul li a")
            if not items:
                break
            for a in items:
                slug = (a.get("href") or "").strip()
                name = a.get_text(" ", strip=True).replace("\xa0", " ")
                if slug and slug not in seen:
                    seen.add(slug)
                    phones.append(
                        {"name": name, "slug": slug, "url": f"{BASE_URL}/{slug}"}
                    )
            logger.info("Discovered %d Samsung phones so far (page %d)",
                        len(phones), page)
    logger.info("Discovery complete: %d phones", len(phones))
    return phones


def _slug_to_url(slug: str) -> str:
    """Normalize a slug or full URL into a full GSMArena detail URL."""
    slug = slug.strip()
    if slug.startswith("http"):
        return slug
    if slug.startswith("/"):
        return f"{BASE_URL}{slug}"
    if not slug.endswith(".php"):
        slug += ".php"
    if not slug.startswith("samsung_"):
        slug = f"samsung_{slug}"
    return f"{BASE_URL}/{slug}"


def scrape_phone(slug_or_url: str, session: requests.Session | None = None) -> dict[str, Any] | None:
    """Scrape a single phone detail page. Returns a parsed dict or None."""
    url = _slug_to_url(slug_or_url)
    slug = url.rsplit("/", 1)[-1].replace(".php", "")
    own_session = session is None
    if own_session:
        session = requests.Session()

    html = _get(url, session)
    if html is None:
        return None
    try:
        parsed = parse_phone_page(html, slug=slug, url=url)
    except Exception as exc:  # keep scraping resilient to parse surprises
        logger.exception("Failed to parse %s: %s", url, exc)
        return None

    logger.info("Scraped %s (%d specs)", parsed["name"], len(parsed["specs"]))
    return parsed


def scrape_phones(
    slugs: list[str] | None = None,
    *,
    limit: int | None = None,
    delay: float = 1.0,
) -> list[dict[str, Any]]:
    """Scrape several phones, tolerating individual failures.

    ``slugs`` may contain slugs, partial names or full URLs. If ``None`` the
    phones are discovered from the Samsung brand listing (up to ``limit``).
    """
    if slugs is None:
        discovered = discover_samsung_phones()
        if limit:
            discovered = discovered[:limit]
        slugs = [p["slug"] for p in discovered]

    results: list[dict[str, Any]] = []
    with requests.Session() as session:
        for slug in slugs:
            parsed = scrape_phone(slug, session=session)
            if parsed is not None:
                results.append(parsed)
            time.sleep(delay)
    logger.info("Scraped %d/%d phones successfully", len(results), len(slugs))
    return results
