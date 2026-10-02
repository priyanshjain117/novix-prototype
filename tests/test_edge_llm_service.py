import httpx
import pytest
import respx

from app.edge_llm_service import (
    EdgeLLMError,
    EdgeLLMPermanentError,
    generate_response,
)


async def test_mock_mode_returns_deterministic_answer(monkeypatch):
    monkeypatch.setenv("EDGE_LLM_MODE", "mock")
    result = await generate_response("hello world")
    assert result == {
        "answer": "Mock edge response for: hello world",
        "mode": "mock",
        "model": "novix-edge-mock",
    }


@respx.mock
async def test_ollama_success(monkeypatch):
    monkeypatch.setenv("EDGE_LLM_MODE", "ollama")
    monkeypatch.setenv("OLLAMA_URL", "http://ollama-test:11434")
    monkeypatch.setenv("OLLAMA_MODEL", "test-model")
    route = respx.post("http://ollama-test:11434/api/chat").mock(
        return_value=httpx.Response(200, json={"message": {"content": "hi there"}})
    )

    result = await generate_response("hello")

    assert route.called
    assert result == {"answer": "hi there", "mode": "ollama", "model": "test-model"}


@respx.mock
async def test_ollama_timeout_raises_retryable_error(monkeypatch):
    monkeypatch.setenv("EDGE_LLM_MODE", "ollama")
    monkeypatch.setenv("OLLAMA_URL", "http://ollama-test:11434")
    respx.post("http://ollama-test:11434/api/chat").mock(
        side_effect=httpx.ReadTimeout("timed out")
    )

    with pytest.raises(EdgeLLMError) as exc_info:
        await generate_response("hello")

    assert not isinstance(exc_info.value, EdgeLLMPermanentError)


@respx.mock
async def test_ollama_unavailable_raises_retryable_error(monkeypatch):
    monkeypatch.setenv("EDGE_LLM_MODE", "ollama")
    monkeypatch.setenv("OLLAMA_URL", "http://ollama-test:11434")
    respx.post("http://ollama-test:11434/api/chat").mock(
        side_effect=httpx.ConnectError("connection refused")
    )

    with pytest.raises(EdgeLLMError) as exc_info:
        await generate_response("hello")

    assert not isinstance(exc_info.value, EdgeLLMPermanentError)


@respx.mock
async def test_ollama_server_error_is_retryable(monkeypatch):
    monkeypatch.setenv("EDGE_LLM_MODE", "ollama")
    monkeypatch.setenv("OLLAMA_URL", "http://ollama-test:11434")
    respx.post("http://ollama-test:11434/api/chat").mock(return_value=httpx.Response(503))

    with pytest.raises(EdgeLLMError) as exc_info:
        await generate_response("hello")

    assert not isinstance(exc_info.value, EdgeLLMPermanentError)


@respx.mock
async def test_ollama_model_missing_raises_permanent_error(monkeypatch):
    monkeypatch.setenv("EDGE_LLM_MODE", "ollama")
    monkeypatch.setenv("OLLAMA_URL", "http://ollama-test:11434")
    monkeypatch.setenv("OLLAMA_MODEL", "missing-model")
    respx.post("http://ollama-test:11434/api/chat").mock(return_value=httpx.Response(404))

    with pytest.raises(EdgeLLMPermanentError):
        await generate_response("hello")


@respx.mock
async def test_ollama_malformed_response_raises_permanent_error(monkeypatch):
    monkeypatch.setenv("EDGE_LLM_MODE", "ollama")
    monkeypatch.setenv("OLLAMA_URL", "http://ollama-test:11434")
    respx.post("http://ollama-test:11434/api/chat").mock(
        return_value=httpx.Response(200, json={"unexpected": "shape"})
    )

    with pytest.raises(EdgeLLMPermanentError):
        await generate_response("hello")


async def test_invalid_mode_raises_permanent_error(monkeypatch):
    monkeypatch.setenv("EDGE_LLM_MODE", "bogus")

    with pytest.raises(EdgeLLMPermanentError):
        await generate_response("hello")
