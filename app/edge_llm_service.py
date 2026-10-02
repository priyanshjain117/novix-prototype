import os
from typing import Any, Dict

import httpx
from pydantic import BaseModel, Field


class EdgeLLMError(Exception):
    """Raised when an edge LLM call cannot produce a usable response."""


class EdgeLLMPermanentError(EdgeLLMError):
    """Raised for failures that will not be fixed by retrying (bad config,
    malformed response, or a model that is not available on the endpoint)."""


class EdgeLLMOutput(BaseModel):
    answer: str = Field(..., min_length=1, max_length=12000)
    mode: str
    model: str


def edge_llm_mode() -> str:
    return os.getenv("EDGE_LLM_MODE", "mock").strip().lower()


def edge_llm_timeout_seconds() -> float:
    return float(os.getenv("OLLAMA_TIMEOUT_SECONDS", "15"))


def edge_llm_model() -> str:
    return os.getenv("OLLAMA_MODEL", "llama3.2")


def _ollama_base_url() -> str:
    return os.getenv("OLLAMA_URL", "http://localhost:11434").strip().rstrip("/")


async def generate_response(query: str) -> Dict[str, Any]:
    """Generate a response using deterministic mock mode or a real Ollama call."""

    mode = edge_llm_mode()
    if mode == "mock":
        return {
            "answer": f"Mock edge response for: {query}",
            "mode": "mock",
            "model": "novix-edge-mock",
        }

    if mode != "ollama":
        raise EdgeLLMPermanentError("EDGE_LLM_MODE must be either 'mock' or 'ollama'")

    base_url = _ollama_base_url()
    model = edge_llm_model()
    if not base_url:
        raise EdgeLLMPermanentError("OLLAMA_URL must not be empty when EDGE_LLM_MODE=ollama")

    try:
        async with httpx.AsyncClient(timeout=edge_llm_timeout_seconds()) as client:
            response = await client.post(
                f"{base_url}/api/chat",
                json={
                    "model": model,
                    "stream": False,
                    "messages": [{"role": "user", "content": query}],
                },
            )
    except httpx.TimeoutException as exc:
        raise EdgeLLMError(f"Ollama request timed out: {type(exc).__name__}") from exc
    except httpx.ConnectError as exc:
        raise EdgeLLMError(f"Ollama endpoint unreachable: {type(exc).__name__}") from exc
    except httpx.HTTPError as exc:
        raise EdgeLLMError(f"Ollama request failed: {type(exc).__name__}") from exc

    if response.status_code == 404:
        raise EdgeLLMPermanentError(
            f"model '{model}' is not available on the Ollama endpoint; "
            f"pull it first with `ollama pull {model}`"
        )
    if response.status_code >= 500:
        raise EdgeLLMError(f"Ollama server error: HTTP {response.status_code}")
    if response.status_code >= 400:
        raise EdgeLLMPermanentError(f"Ollama rejected the request: HTTP {response.status_code}")

    try:
        body = response.json()
        answer = body["message"]["content"]
    except (ValueError, KeyError, TypeError) as exc:
        raise EdgeLLMPermanentError(f"Ollama response was malformed: {type(exc).__name__}") from exc

    if not isinstance(answer, str) or not answer.strip():
        raise EdgeLLMPermanentError("Ollama returned an empty answer")

    return {"answer": answer.strip(), "mode": "ollama", "model": model}
