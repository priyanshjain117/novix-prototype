import os
from typing import Any, Dict

import httpx
from pydantic import BaseModel, Field


class LLMError(Exception):
    """Raised when an LLM call cannot produce a usable response."""


class LLMOutput(BaseModel):
    answer: str = Field(..., min_length=1, max_length=12000)
    mode: str
    model: str


def llm_mode() -> str:
    return os.getenv("LLM_MODE", "mock").strip().lower()


def llm_timeout_seconds() -> float:
    return float(os.getenv("LLM_TIMEOUT_SECONDS", "8"))


def llm_model() -> str:
    return os.getenv("LLM_MODEL", "gpt-4o-mini")


async def generate_response(query: str) -> Dict[str, Any]:
    """Generate a response using deterministic mock mode or an HTTP LLM."""

    mode = llm_mode()
    model = llm_model()
    if mode == "mock":
        return {
            "answer": f"Mock master response for: {query}",
            "mode": "mock",
            "model": "novix-mock",
        }

    if mode != "real":
        raise LLMError("LLM_MODE must be either 'mock' or 'real'")

    api_key = os.getenv("LLM_API_KEY", "").strip()
    api_url = os.getenv(
        "LLM_API_URL", "https://api.openai.com/v1/chat/completions"
    ).strip()
    if not api_key:
        raise LLMError("LLM_API_KEY is required when LLM_MODE=real")
    if not api_url:
        raise LLMError("LLM_API_URL must not be empty when LLM_MODE=real")

    try:
        async with httpx.AsyncClient(timeout=llm_timeout_seconds()) as client:
            response = await client.post(
                api_url,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model,
                    "temperature": 0,
                    "messages": [
                        {
                            "role": "system",
                            "content": "Answer the user's request clearly and concisely.",
                        },
                        {"role": "user", "content": query},
                    ],
                },
            )
            response.raise_for_status()
            body = response.json()
            answer = body["choices"][0]["message"]["content"]
            if not isinstance(answer, str):
                raise ValueError("LLM answer must be a string")
            return {"answer": answer.strip(), "mode": "real", "model": model}
    except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError) as exc:
        raise LLMError(f"LLM request failed: {type(exc).__name__}") from exc
