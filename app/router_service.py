import asyncio
import json
import logging
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles

from .models import QueryRequest

app = FastAPI(title="NOVIX Router Service", version="0.1.0")
logger = logging.getLogger("novix.router")

DASHBOARD_DIR = Path(__file__).resolve().parent.parent / "dashboard"
app.mount("/dashboard", StaticFiles(directory=DASHBOARD_DIR, html=True), name="dashboard")

RESOURCE_TIMEOUT_SECONDS = float(os.getenv("RESOURCE_TIMEOUT_SECONDS", "1.5"))
EDGE_URLS = [
    url.strip().rstrip("/")
    for url in os.getenv(
        "EDGE_URLS", "http://localhost:8001,http://localhost:8002"
    ).split(",")
    if url.strip()
]
MASTER_URL = os.getenv("MASTER_URL", "http://localhost:8002").rstrip("/")

# These rules are intentionally transparent and easy to replace with a model later.
HIGH_COMPLEXITY_TERMS = {
    "architecture",
    "architect",
    "debug",
    "debugging",
    "design",
    "optimize",
    "optimization",
    "research",
    "strategy",
    "tradeoff",
    "multi-step",
}
MEDIUM_COMPLEXITY_TERMS = {
    "analyze",
    "analysis",
    "compare",
    "explain",
    "extract",
    "plan",
    "summarize",
    "transform",
}
PARALLEL_TERMS = {
    "batch",
    "compare",
    "each",
    "multiple",
    "parallel",
    "separately",
}


def _structured_log(level: int, event: str, **fields: Any) -> None:
    logger.log(level, json.dumps({"event": event, **fields}, sort_keys=True))


def _contains_term(query: str, terms: set[str]) -> bool:
    return any(re.search(rf"\b{re.escape(term)}\b", query) for term in terms)


def classify_query(query: str) -> tuple[str, bool, str]:
    """Classify a query using deterministic length and keyword rules."""

    normalized = query.lower().strip()
    parallelizable = _contains_term(normalized, PARALLEL_TERMS) or bool(
        re.search(r"\b(and|versus|vs)\b", normalized)
    )

    if len(normalized) > 240 or _contains_term(normalized, HIGH_COMPLEXITY_TERMS):
        return "high", parallelizable, "high-complexity keyword or long query"
    if len(normalized) > 80 or _contains_term(normalized, MEDIUM_COMPLEXITY_TERMS):
        return "medium", parallelizable, "medium-complexity keyword or query length"
    return "low", parallelizable, "short query without complexity keywords"


async def _probe_resource(
    client: httpx.AsyncClient, node: str, url: str
) -> Dict[str, Any]:
    try:
        response = await client.get(f"{url}/resources")
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, dict):
            raise ValueError("resource response must be a JSON object")
        return {"node": node, "url": url, "available": True, "resources": data}
    except (httpx.HTTPError, ValueError) as exc:
        _structured_log(
            logging.WARNING,
            "resource_probe_failed",
            node=node,
            url=url,
            error=type(exc).__name__,
            detail=str(exc),
        )
        return {
            "node": node,
            "url": url,
            "available": False,
            "error": type(exc).__name__,
        }


def _load_score(resource: Dict[str, Any]) -> float:
    """Lower is less loaded; use both CPU and memory where available."""

    cpu = float(resource.get("cpu_percent", 100.0))
    memory = resource.get("memory", {})
    memory_percent = float(memory.get("percent", 100.0))
    return (cpu + memory_percent) / 2


def decompose_query(query: str) -> List[str]:
    """Split a query into two stable subtasks for the two edge nodes."""

    parts = [
        part.strip(" ,;:.\t")
        for part in re.split(r"\s+(?:and|also|then|versus|vs)\s+|[.;]\s*", query)
        if part.strip(" ,;:.\t")
    ]
    if len(parts) >= 2:
        midpoint = (len(parts) + 1) // 2
        return [" and ".join(parts[:midpoint]), " and ".join(parts[midpoint:])]

    words = query.split()
    midpoint = max(1, len(words) // 2)
    return [" ".join(words[:midpoint]), " ".join(words[midpoint:]) or query]


async def _execute_subtask(
    client: httpx.AsyncClient,
    node: Dict[str, Any],
    subtask_id: str,
    subtask: str,
    query_id: str,
) -> Dict[str, Any]:
    try:
        response = await client.post(
            f"{node['url']}/execute",
            json={
                "task": f"query-subtask-{subtask_id}",
                "payload": {"query": subtask, "query_id": query_id},
            },
        )
        response.raise_for_status()
        result = response.json()
        if not isinstance(result, dict):
            raise ValueError("execution response must be a JSON object")
        return {
            "subtask_id": subtask_id,
            "node": node["node"],
            "subtask": subtask,
            "status": "completed",
            "result": result,
        }
    except (httpx.HTTPError, ValueError) as exc:
        _structured_log(
            logging.WARNING,
            "subtask_execution_failed",
            query_id=query_id,
            subtask_id=subtask_id,
            node=node["node"],
            error=type(exc).__name__,
            detail=str(exc),
        )
        return {
            "subtask_id": subtask_id,
            "node": node["node"],
            "subtask": subtask,
            "status": "failed",
            "error": type(exc).__name__,
        }


def aggregate_subtask_results(
    query: str, subtask_results: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """Create a deterministic aggregate without interpreting the results."""

    completed = [
        result for result in subtask_results if result["status"] == "completed"
    ]
    return {
        "status": "completed" if len(completed) == len(subtask_results) else "partial",
        "query": query,
        "completed_count": len(completed),
        "total_count": len(subtask_results),
        "results_in_subtask_order": [
            result.get("result") for result in subtask_results if result["status"] == "completed"
        ],
    }


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "router"}


@app.post("/query")
async def query(request: QueryRequest) -> dict:
    query_id = str(uuid4())
    query_text = request.query.strip()
    if not query_text:
        raise HTTPException(status_code=422, detail="query must not be blank")

    complexity, parallelizable, classification_reason = classify_query(query_text)
    _structured_log(
        logging.INFO,
        "query_received",
        query_id=query_id,
        complexity=complexity,
        parallelizable=parallelizable,
    )

    async with httpx.AsyncClient(timeout=RESOURCE_TIMEOUT_SECONDS) as client:
        edge_results, master_result = await asyncio.gather(
            asyncio.gather(
                *[
                    _probe_resource(client, f"edge-{index + 1:02d}", url)
                    for index, url in enumerate(EDGE_URLS)
                ]
            ),
            _probe_resource(client, "master", MASTER_URL),
        )

    available_edges = [node for node in edge_results if node["available"]]
    master_available = master_result["available"]
    unavailable_nodes = [
        node["node"] for node in [*edge_results, master_result] if not node["available"]
    ]
    selected: List[Dict[str, Any]] = []
    decision: Optional[str] = None
    fallback: Optional[str] = None
    reason = classification_reason

    if complexity == "low" and available_edges:
        selected = [
            min(
                available_edges,
                key=lambda node: _load_score(node["resources"]),
            )
        ]
        decision = "edge"
        reason = "selected the least-loaded available edge"
    elif complexity == "medium" and parallelizable and available_edges:
        selected = available_edges
        decision = "parallel-edge" if len(selected) > 1 else "edge"
        if len(selected) == 1:
            fallback = "parallel request degraded to one available edge"
            reason = fallback
        else:
            reason = "selected all available edges for parallel execution"
    elif master_available:
        selected = [master_result]
        decision = "master"
        if complexity == "low" or (complexity == "medium" and parallelizable):
            fallback = "no suitable edge capacity was available"
            reason = fallback
        else:
            reason = "high-complexity or non-parallelizable query"

    if not selected:
        _structured_log(
            logging.ERROR,
            "routing_failed",
            query_id=query_id,
            complexity=complexity,
            unavailable_nodes=unavailable_nodes,
        )
        raise HTTPException(
            status_code=503,
            detail={
                "error": "no available execution nodes",
                "unavailable_nodes": unavailable_nodes,
            },
        )

    targets = [node["url"] for node in selected]
    selected_nodes = [node["node"] for node in selected]
    _structured_log(
        logging.INFO,
        "query_routed",
        query_id=query_id,
        complexity=complexity,
        parallelizable=parallelizable,
        decision=decision,
        selected_nodes=selected_nodes,
        unavailable_nodes=unavailable_nodes,
        fallback=fallback,
    )

    if decision == "parallel-edge" and len(selected) == 2:
        subtasks = decompose_query(query_text)
        async with httpx.AsyncClient(timeout=RESOURCE_TIMEOUT_SECONDS) as client:
            subtask_results = list(
                await asyncio.gather(
                    *[
                        _execute_subtask(
                            client,
                            node,
                            f"{index + 1:02d}",
                            subtask,
                            query_id,
                        )
                        for index, (node, subtask) in enumerate(zip(selected, subtasks))
                    ]
                )
            )
        final_result = aggregate_subtask_results(query_text, subtask_results)
        _structured_log(
            logging.INFO,
            "distributed_query_completed",
            query_id=query_id,
            nodes_used=selected_nodes,
            completed_count=final_result["completed_count"],
            total_count=final_result["total_count"],
        )
        return {
            "query_id": query_id,
            "routing_decision": decision,
            "complexity": complexity,
            "parallelizable": parallelizable,
            "nodes_used": selected_nodes,
            "subtask_results": subtask_results,
            "final_result": final_result,
            "unavailable_nodes": unavailable_nodes,
        }

    return {
        "query_id": query_id,
        "complexity": complexity,
        "parallelizable": parallelizable,
        "decision": decision,
        "targets": targets,
        "selected_nodes": selected_nodes,
        "unavailable_nodes": unavailable_nodes,
        "fallback": fallback,
        "reason": reason,
    }
