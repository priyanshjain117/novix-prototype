import httpx
import respx

from app.router_service import _execute_subtask


@respx.mock
async def test_router_wraps_successful_edge_execute_response():
    respx.post("http://edge-01-test:8000/execute").mock(
        return_value=httpx.Response(
            200,
            json={
                "status": "completed",
                "service": "edge",
                "node_id": "edge-01",
                "task": "query-subtask-01",
                "payload": {"query": "hello", "query_id": "q1"},
                "result": {"answer": "hi", "mode": "mock", "model": "novix-edge-mock"},
                "attempts": 1,
                "executed_at": "2026-01-01T00:00:00+00:00",
            },
        )
    )

    async with httpx.AsyncClient(timeout=1.5) as client:
        result = await _execute_subtask(
            client,
            {"node": "edge-01", "url": "http://edge-01-test:8000"},
            "01",
            "hello",
            "q1",
        )

    assert result["status"] == "completed"
    assert result["node"] == "edge-01"
    assert result["result"]["result"]["answer"] == "hi"


@respx.mock
async def test_router_marks_subtask_failed_on_edge_error_response():
    respx.post("http://edge-02-test:8000/execute").mock(
        return_value=httpx.Response(
            502,
            json={
                "detail": {
                    "error": "edge execution failed",
                    "attempts": 3,
                    "last_error": "EdgeLLMError",
                }
            },
        )
    )

    async with httpx.AsyncClient(timeout=1.5) as client:
        result = await _execute_subtask(
            client,
            {"node": "edge-02", "url": "http://edge-02-test:8000"},
            "02",
            "world",
            "q1",
        )

    assert result["status"] == "failed"
    assert result["error"] == "HTTPStatusError"
