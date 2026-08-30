"""Central logging configuration.

Every module gets a logger through :func:`get_logger` so scraping, database,
retrieval, chatbot, agent and API activity is consistently logged.

Secrets (API keys, passwords, tokens) are never logged anywhere in this
project.
"""
from __future__ import annotations

import logging
import sys

_CONFIGURED = False


def _configure_root_logger() -> None:
    global _CONFIGURED
    if _CONFIGURED:
        return
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        logging.Formatter(
            fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(handler)
    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    """Return a logger for the given module name."""
    _configure_root_logger()
    return logging.getLogger(name)
