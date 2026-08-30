"""Shared pytest fixtures.

Tests run against an isolated in-memory/temp SQLite database (no PostgreSQL or
network required) seeded with a few representative Samsung phones. Retrieval
uses the lightweight hash embedder so the suite is fast and deterministic.
"""
from __future__ import annotations

import pytest

from app.database import connection
from app.database.connection import get_session, reset_db, reset_engine
from app.rag.embeddings import HashEmbedder
from app.rag.retriever import Retriever

# Use SQLite for tests — override whatever the environment points at.
TEST_DB_URL = "sqlite:///./data/test_samsung.db"


@pytest.fixture(scope="session", autouse=True)
def _isolated_db():
    reset_engine()
    reset_db(TEST_DB_URL)
    yield
    connection.reset_engine()


@pytest.fixture()
def session(_isolated_db):
    s = get_session()
    yield s
    s.close()


@pytest.fixture()
def seeded(session):
    """Seed a few phones with representative specs and return them."""
    from app.database.crud import upsert_phone

    def phone(name, slug, battery, display, camera, ram, weight, chipset="Chipset X", price="$ 500.00", price_usd=500.0):
        return {
            "name": name,
            "slug": slug,
            "brand": "Samsung",
            "image_url": None,
            "url": f"https://www.gsmarena.com/{slug}",
            "announced": "2023, January 01",
            "released": "Available. Released 2023, February 01",
            "price": price,
            "price_usd": price_usd,
            "chipset": chipset,
            "os": "Android 13",
            "battery_capacity_mah": battery,
            "display_size_inches": display,
            "main_camera_mp": camera,
            "ram_gb": ram,
            "weight_g": weight,
            "specs": [
                {"category": "Display", "key": "Size", "value": f"{display} inches"},
                {"category": "Display", "key": "Type", "value": "Dynamic AMOLED 2X"},
                {"category": "Battery", "key": "Type", "value": f"Li-Ion {battery} mAh"},
                {"category": "Battery", "key": "Charging", "value": "25W wired"},
                {"category": "Main Camera", "key": "Triple", "value": f"{camera} MP, f/1.8, wide"},
                {"category": "Main Camera", "key": "Video", "value": "8K@24fps, 4K@60fps"},
                {"category": "Platform", "key": "Chipset", "value": chipset},
                {"category": "Platform", "key": "OS", "value": "Android 13"},
                {"category": "Memory", "key": "Internal", "value": f"256GB {ram}GB RAM"},
                {"category": "Misc", "key": "Price", "value": price},
            ],
        }

    a = upsert_phone(session, phone("Samsung Galaxy S23", "samsung_galaxy_s23-12082.php", 3900, 6.1, 50.0, 8.0, 168, chipset="Snapdragon 8 Gen 2", price_usd=799.0))
    b = upsert_phone(session, phone("Samsung Galaxy S22 5G", "samsung_galaxy_s22_5g-11253.php", 3700, 6.1, 50.0, 8.0, 167, chipset="Snapdragon 8 Gen 1", price_usd=699.0))
    c = upsert_phone(session, phone("Samsung Galaxy S23 Ultra", "samsung_galaxy_s23_ultra-12024.php", 5000, 6.8, 200.0, 12.0, 234, chipset="Snapdragon 8 Gen 2", price_usd=1199.0))
    return {"s23": a, "s22": b, "s23_ultra": c}


@pytest.fixture()
def retriever(seeded, session):
    from app.database.crud import list_phones

    return Retriever.from_phones(list_phones(session), embedder=HashEmbedder())


@pytest.fixture()
def chatbot(seeded, session, retriever):
    from app.rag.chatbot import Chatbot
    from app.rag.llm import GroundedLLM

    return Chatbot(get_session, llm=GroundedLLM(), retriever=retriever)


@pytest.fixture()
def client(seeded, retriever):
    """FastAPI TestClient wired to the seeded DB and hash retriever."""
    from fastapi.testclient import TestClient

    from app.main import app
    import app.api.routes as routes

    routes._chatbot = None  # reset so it builds with our retriever
    routes._chatbot = __import__("app.rag.chatbot", fromlist=["Chatbot"]).Chatbot(
        get_session,
        llm=__import__("app.rag.llm", fromlist=["GroundedLLM"]).GroundedLLM(),
        retriever=retriever,
    )
    with TestClient(app) as c:
        yield c
    routes._chatbot = None
