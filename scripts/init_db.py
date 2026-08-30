"""Create the database schema (all tables) if they do not exist yet.

Usage:
    python -m scripts.init_db
"""
from __future__ import annotations

from app.database.connection import init_db
from app.logging_setup import get_logger

logger = get_logger(__name__)


def main() -> None:
    init_db()
    logger.info("Database initialized.")


if __name__ == "__main__":
    main()
