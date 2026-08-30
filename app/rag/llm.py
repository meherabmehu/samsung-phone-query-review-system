"""LLM provider abstraction.

The system is built so it works out of the box with **no external API key**:
``GroundedLLM`` composes answers strictly from the retrieved context (never
inventing facts). If a provider is configured in ``.env`` (``LLM_PROVIDER``),
:func:`get_llm` returns the corresponding client instead:

- ``fallback``     -> GroundedLLM (default, offline)
- ``huggingface``  -> Hugging Face Inference API (open-source models)
- ``openai``       -> any OpenAI-compatible endpoint (OpenAI, Groq, vLLM...)
- ``ollama``       -> a local Ollama server

Every provider exposes the same ``complete(prompt) -> str`` interface and
raises :class:`LLMError` on failure so callers can degrade gracefully.
"""
from __future__ import annotations

from abc import ABC, abstractmethod

import requests

from app.config import settings
from app.logging_setup import get_logger

logger = get_logger(__name__)


class LLMError(RuntimeError):
    """Raised when an LLM provider cannot produce a response."""


class BaseLLM(ABC):
    name: str = "base"

    @abstractmethod
    def complete(self, prompt: str) -> str:
        """Return a generated response for the given prompt."""


class GroundedLLM(BaseLLM):
    """Offline generator that answers strictly from a grounded prompt.

    The caller (chatbot) is responsible for embedding the retrieved facts and
    the actual question into the prompt; this class simply renders a
    deterministic, grounded response. It is deliberately conservative: when
    the prompt carries no facts it says so instead of hallucinating.
    """

    name = "fallback"

    def complete(self, prompt: str) -> str:
        # The chatbot always includes a marker line when context is present.
        has_context = "<FACTS>" in prompt
        if not has_context:
            return (
                "I couldn't find any information about that in the database. "
                "Please try rephrasing your question or naming a specific phone."
            )
        return prompt


class HuggingFaceLLM(BaseLLM):
    name = "huggingface"

    def __init__(self, api_key: str, api_url: str):
        if not api_key:
            raise LLMError("HUGGINGFACE_API_KEY is not set")
        self.api_key = api_key
        self.api_url = api_url

    def complete(self, prompt: str) -> str:
        headers = {"Authorization": f"Bearer {self.api_key}"}
        payload = {
            "inputs": prompt,
            "parameters": {"max_new_tokens": 400, "temperature": 0.3},
        }
        try:
            resp = requests.post(self.api_url, headers=headers, json=payload, timeout=60)
            resp.raise_for_status()
            data = resp.json()
            if isinstance(data, list) and data:
                return data[0].get("generated_text", "")
            return str(data)
        except requests.RequestException as exc:
            raise LLMError(f"Hugging Face request failed: {exc}") from exc


class OpenAILLM(BaseLLM):
    name = "openai"

    def __init__(self, api_key: str, base_url: str, model: str):
        if not api_key:
            raise LLMError("OPENAI_API_KEY is not set")
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model

    def complete(self, prompt: str) -> str:
        url = f"{self.base_url}/chat/completions"
        headers = {"Authorization": f"Bearer {self.api_key}"}
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.3,
        }
        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=60)
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"]
        except (requests.RequestException, KeyError, IndexError) as exc:
            raise LLMError(f"OpenAI-compatible request failed: {exc}") from exc


class OllamaLLM(BaseLLM):
    name = "ollama"

    def __init__(self, base_url: str, model: str):
        self.base_url = base_url.rstrip("/")
        self.model = model

    def complete(self, prompt: str) -> str:
        url = f"{self.base_url}/api/generate"
        payload = {"model": self.model, "prompt": prompt, "stream": False}
        try:
            resp = requests.post(url, json=payload, timeout=120)
            resp.raise_for_status()
            return resp.json().get("response", "")
        except requests.RequestException as exc:
            raise LLMError(f"Ollama request failed: {exc}") from exc


_llm: BaseLLM | None = None


def get_llm() -> BaseLLM:
    """Return a cached LLM instance based on ``LLM_PROVIDER``."""
    global _llm
    if _llm is not None:
        return _llm

    provider = settings.llm_provider.strip().lower()
    logger.info("Configuring LLM provider: %s", provider)

    if provider == "huggingface":
        _llm = HuggingFaceLLM(settings.huggingface_api_key, settings.huggingface_api_url)
    elif provider == "openai":
        _llm = OpenAILLM(
            settings.openai_api_key, settings.openai_base_url, settings.openai_model
        )
    elif provider == "ollama":
        _llm = OllamaLLM(settings.ollama_base_url, settings.ollama_model)
    else:
        # Default: grounded, offline, deterministic. Always works.
        logger.info("Using grounded fallback generator (no external LLM required)")
        _llm = GroundedLLM()

    return _llm
