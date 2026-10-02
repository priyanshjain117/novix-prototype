import httpx
import respx
from fastapi.testclient import TestClient

from app.edge_service import app

client = TestClient(app)


def test_health_still_works(monkeypatch):
    monkeypatch.setenv("EDGE_LLM_MODE", "mock")
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["service"] == "edge"
    assert body["llm_mode"] == "mock"


def test_resources_still_works():
    response = client.get("/resources")
    assert response.status_code == 200
    body = response.json()
    assert body["service"] == "edge"
    assert "cpu_percent" in body
    assert "percent" in body["memory"]


def test_execute_mock_mode_returns_completed_result(monkeypatch):
    monkeypatch.setenv("EDGE_LLM_MODE", "mock")
    response = client.post(
        "/execute",
        json={"task": "query-subtask-01", "payload": {"query": "hello"}},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "completed"
    assert body["service"] == "edge"
    assert body["attempts"] == 1
    assert body["result"]["mode"] == "mock"
    assert "hello" in body["result"]["answer"]


def test_execute_rejects_oversized_query(monkeypatch):
    monkeypatch.setenv("EDGE_LLM_MODE", "mock")
    response = client.post(
        "/execute",
        json={"task": "query-subtask-01", "payload": {"query": "x" * 12001}},
    )
    assert response.status_code == 422


@respx.mock
def test_execute_ollama_retries_then_succeeds(monkeypatch):
    monkeypatch.setenv("EDGE_LLM_MODE", "ollama")
    monkeypatch.setenv("OLLAMA_URL", "http://ollama-test:11434")
    monkeypatch.setenv("OLLAMA_MODEL", "test-model")
    route = respx.post("http://ollama-test:11434/api/chat").mock(
        side_effect=[
            httpx.ConnectError("connection refused"),
            httpx.Response(200, json={"message": {"content": "answer after retry"}}),
        ]
    )

    response = client.post(
        "/execute",
        json={"task": "query-subtask-01", "payload": {"query": "hello"}},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["attempts"] == 2
    assert body["result"]["answer"] == "answer after retry"
    assert route.call_count == 2


@respx.mock
def test_execute_permanent_error_does_not_retry(monkeypatch):
    monkeypatch.setenv("EDGE_LLM_MODE", "ollama")
    monkeypatch.setenv("OLLAMA_URL", "http://ollama-test:11434")
    monkeypatch.setenv("OLLAMA_MODEL", "missing-model")
    route = respx.post("http://ollama-test:11434/api/chat").mock(
        return_value=httpx.Response(404)
    )

    response = client.post(
        "/execute",
        json={"task": "query-subtask-01", "payload": {"query": "hello"}},
    )

    assert response.status_code == 502
    body = response.json()
    assert body["detail"]["attempts"] == 1
    assert body["detail"]["last_error"] == "EdgeLLMPermanentError"
    assert route.call_count == 1


@respx.mock
def test_execute_unavailable_ollama_exhausts_retries(monkeypatch):
    monkeypatch.setenv("EDGE_LLM_MODE", "ollama")
    monkeypatch.setenv("OLLAMA_URL", "http://ollama-test:11434")
    route = respx.post("http://ollama-test:11434/api/chat").mock(
        side_effect=httpx.ConnectError("connection refused")
    )

    response = client.post(
        "/execute",
        json={"task": "query-subtask-01", "payload": {"query": "hello"}},
    )

    assert response.status_code == 502
    body = response.json()
    assert body["detail"]["attempts"] == 3
    assert route.call_count == 3
