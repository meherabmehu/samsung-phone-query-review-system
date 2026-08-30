"""Application configuration loaded from environment variables / a .env file.

All secrets are read from the environment; nothing is hard-coded here.
"""
from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central settings object.

    Values can be provided either as environment variables or in a `.env`
    file in the project root.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Database ---
    database_url: str = (
        "postgresql+psycopg2://app:app_pass@localhost:5432/samsung_phones"
    )

    # --- RAG / embeddings ---
    embedding_model_name: str = "all-MiniLM-L6-v2"

    # --- LLM provider ---
    llm_provider: str = "fallback"  # fallback | huggingface | openai | ollama
    huggingface_api_key: str = ""
    huggingface_api_url: str = (
        "https://api-inference.huggingface.co/models/mistralai/Mistral-7B-Instruct-v0.2"
    )
    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    openai_model: str = "gpt-4o-mini"
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.1"

    # --- Scraper ---
    scrape_targets: str = "all"
    scrape_delay: float = 1.0


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance (avoids re-reading .env on every call)."""
    return Settings()


settings = get_settings()
