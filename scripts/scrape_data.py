"""Scrape Samsung phones from GSMArena and store them in the database.

Also exports the scraped data to ``data/samsung_phones.json`` so the project
can be run without scraping again.

Usage:
    # Scrape the curated default set of 15 phones:
    python -m scripts.scrape_data

    # Scrape specific slugs:
    python -m scripts.scrape_data --slugs samsung_galaxy_s23-12082.php

    # Discover + scrape the first N phones from the brand listing:
    python -m scripts.scrape_data --discover --limit 15
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.config import settings
from app.database.connection import get_session
from app.database.crud import upsert_phone
from app.logging_setup import get_logger
from app.scraper.gsmarena_scraper import DEFAULT_MODELS, discover_samsung_phones, scrape_phones

logger = get_logger(__name__)

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
JSON_PATH = DATA_DIR / "samsung_phones.json"


def export_json(parsed_phones: list[dict]) -> None:
    DATA_DIR.mkdir(exist_ok=True)
    with JSON_PATH.open("w", encoding="utf-8") as fh:
        json.dump(parsed_phones, fh, indent=2, ensure_ascii=False)
    logger.info("Exported %d phones to %s", len(parsed_phones), JSON_PATH)


def main() -> None:
    parser = argparse.ArgumentParser(description="Scrape Samsung phones from GSMArena")
    parser.add_argument("--slugs", nargs="*", help="specific slugs/URLs to scrape")
    parser.add_argument("--discover", action="store_true", help="discover from the brand listing")
    parser.add_argument("--limit", type=int, default=None, help="max phones to scrape")
    parser.add_argument("--delay", type=float, default=settings.scrape_delay, help="delay between requests")
    args = parser.parse_args()

    if args.slugs:
        parsed_phones = scrape_phones(args.slugs, limit=args.limit, delay=args.delay)
    elif args.discover:
        discovered = discover_samsung_phones()
        if args.limit:
            discovered = discovered[: args.limit]
        parsed_phones = scrape_phones(
            [p["slug"] for p in discovered], delay=args.delay
        )
    else:
        parsed_phones = scrape_phones(DEFAULT_MODELS, limit=args.limit, delay=args.delay)

    if not parsed_phones:
        logger.error("No phones scraped. Check network access and try again.")
        return

    session = get_session()
    for parsed in parsed_phones:
        try:
            upsert_phone(session, parsed)
        except Exception as exc:  # keep one bad record from aborting the batch
            logger.exception("Failed to store %s: %s", parsed.get("name"), exc)
            session.rollback()
    session.close()

    export_json(parsed_phones)
    logger.info("Done. %d phones stored and exported.", len(parsed_phones))


if __name__ == "__main__":
    main()
