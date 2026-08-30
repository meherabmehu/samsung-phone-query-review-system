"""Tests for the FastAPI endpoints (using the seeded test DB)."""
from __future__ import annotations


def test_root(client):
    resp = client.get("/")
    assert resp.status_code == 200
    # The root path now serves the web UI (HTML), not JSON.
    assert "Samsung Phone Query" in resp.text


def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["database"] == "ok"
    assert body["phones_in_db"] == 3


def test_list_phones(client):
    resp = client.get("/phones")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 3
    assert all("name" in p and "battery_capacity_mah" in p for p in data)


def test_get_phone_detail(client):
    resp = client.get("/phones/s23")
    assert resp.status_code == 200
    body = resp.json()
    assert body["name"] == "Samsung Galaxy S23"
    assert body["battery_capacity_mah"] == 3900
    assert len(body["specifications"]) >= 1


def test_get_phone_not_found(client):
    resp = client.get("/phones/iphone-99")
    assert resp.status_code == 404


def test_query_endpoint(client):
    resp = client.post("/query", json={"query": "screen size of galaxy s22"})
    assert resp.status_code == 200
    assert "Samsung Galaxy S22 5G" in resp.json()["answer"] or "6.1" in resp.json()["answer"]


def test_chat_endpoint(client):
    resp = client.post("/chat", json={"message": "best battery life?"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["intent"] == "ranking"
    assert "Samsung Galaxy S23 Ultra" in body["answer"]


def test_chat_validation_empty(client):
    resp = client.post("/chat", json={"message": ""})
    assert resp.status_code in (400, 422)


def test_query_validation_empty(client):
    resp = client.post("/query", json={"query": "   "})
    assert resp.status_code in (400, 422)


def test_review_endpoint(client):
    resp = client.post("/review", json={"phone_name": "Galaxy S23"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["phone_name"] == "Samsung Galaxy S23"
    assert body["saved"] is True
    assert "Display" in body["review"] or "Display" in body["review"].lower()


def test_review_not_found(client):
    resp = client.post("/review", json={"phone_name": "Nokia 3310"})
    assert resp.status_code == 404


def test_openapi_schema(client):
    resp = client.get("/openapi.json")
    assert resp.status_code == 200
    paths = resp.json()["paths"]
    for expected in ["/health", "/phones", "/phones/{phone_name}", "/query", "/chat", "/review"]:
        assert expected in paths
