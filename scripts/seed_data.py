"""Load the shipped dataset (data/samsung_phones.json) into the database.

Lets the project run without re-scraping GSMArena.

Usage:
    python -m scripts.seed_data
"""
from __future__ import annotations

import json
from pathlib import Path

from app.database.connection import get_session
from app.database.crud import upsert_phone
from app.logging_setup import get_logger

logger = get_logger(__name__)

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
JSON_PATH = DATA_DIR / "samsung_phones.json"


def main() -> None:
    if not JSON_PATH.exists():
        logger.error("Dataset not found at %s. Run scripts/scrape_data.py first.", JSON_PATH)
        raise SystemExit(1)

    with JSON_PATH.open("r", encoding="utf-8") as fh:
        phones = json.load(fh)

    session = get_session()
    for data in phones:
        try:
            upsert_phone(session, data)
        except Exception as exc:
            logger.exception("Failed to seed %s: %s", data.get("name"), exc)
            session.rollback()
    session.close()
    logger.info("Seeded %d phones from dataset.", len(phones))


if __name__ == "__main__":
    main()
