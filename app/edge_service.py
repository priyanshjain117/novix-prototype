import asyncio
import json
import logging
import platform
import os
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

import psutil
from fastapi import FastAPI, HTTPException
from pydantic import ValidationError

from .edge_llm_service import (
    EdgeLLMError,
    EdgeLLMOutput,
    EdgeLLMPermanentError,
    edge_llm_mode,
    edge_llm_timeout_seconds,
    generate_response,
)
from .models import ExecuteRequest

app = FastAPI(title="NOVIX Edge Service", version="0.1.0")
logger = logging.getLogger("novix.edge")
NODE_ID = os.getenv("NODE_ID", "edge-local")
MAX_RETRIES = 2


def _structured_log(level: int, event: str, **fields: Any) -> None:
    logger.log(level, json.dumps({"event": event, **fields}, sort_keys=True))


def _extract_query(request: ExecuteRequest) -> str:
    payload = request.payload or {}
    query = payload.get("query") or payload.get("text") or request.task
    if not isinstance(query, str) or not query.strip():
        raise ValueError("a non-empty query is required")
    query = query.strip()
    if len(query) > 12000:
        raise ValueError("query exceeds the 12000 character limit")
    return query


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "edge", "node_id": NODE_ID, "llm_mode": edge_llm_mode()}


@app.get("/resources")
def resources() -> dict:
    memory = psutil.virtual_memory()
    return {
        "service": "edge",
        "node_id": NODE_ID,
        "hostname": platform.node(),
        "cpu_percent": psutil.cpu_percent(interval=0.1),
        "memory": {
            "total_bytes": memory.total,
            "available_bytes": memory.available,
            "used_bytes": memory.used,
            "percent": memory.percent,
        },
    }


@app.post("/execute")
async def execute(request: ExecuteRequest) -> dict:
    request_id = str(uuid4())
    try:
        query = _extract_query(request)
    except ValueError as exc:
        _structured_log(logging.WARNING, "input_validation_failed", request_id=request_id, node_id=NODE_ID)
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    _structured_log(
        logging.INFO,
        "edge_request_received",
        request_id=request_id,
        node_id=NODE_ID,
        mode=edge_llm_mode(),
        max_retries=MAX_RETRIES,
    )

    last_error = "unknown error"
    for retry_number in range(MAX_RETRIES + 1):
        attempt = retry_number + 1
        try:
            _structured_log(
                logging.INFO,
                "edge_llm_attempt_started",
                request_id=request_id,
                node_id=NODE_ID,
                attempt=attempt,
            )
            raw_output = await asyncio.wait_for(
                generate_response(query), timeout=edge_llm_timeout_seconds()
            )
            validated_output = EdgeLLMOutput.model_validate(raw_output)
            _structured_log(
                logging.INFO,
                "edge_llm_output_validated",
                request_id=request_id,
                node_id=NODE_ID,
                attempt=attempt,
                mode=validated_output.mode,
            )
            return {
                "status": "completed",
                "service": "edge",
                "node_id": NODE_ID,
                "task": request.task,
                "payload": request.payload,
                "result": validated_output.model_dump(),
                "attempts": attempt,
                "executed_at": datetime.now(timezone.utc).isoformat(),
            }
        except EdgeLLMPermanentError as exc:
            last_error = type(exc).__name__
            _structured_log(
                logging.WARNING,
                "edge_llm_attempt_failed",
                request_id=request_id,
                node_id=NODE_ID,
                attempt=attempt,
                error=last_error,
                will_retry=False,
            )
            break
        except (EdgeLLMError, TimeoutError, asyncio.TimeoutError, ValidationError) as exc:
            last_error = type(exc).__name__
            will_retry = retry_number < MAX_RETRIES
            _structured_log(
                logging.WARNING,
                "edge_llm_attempt_failed",
                request_id=request_id,
                node_id=NODE_ID,
                attempt=attempt,
                error=last_error,
                will_retry=will_retry,
            )
            if not will_retry:
                break

    _structured_log(
        logging.ERROR,
        "edge_request_failed",
        request_id=request_id,
        node_id=NODE_ID,
        attempts=attempt,
        error=last_error,
    )
    raise HTTPException(
        status_code=502,
        detail={
            "error": "edge execution failed",
            "request_id": request_id,
            "node_id": NODE_ID,
            "attempts": attempt,
            "last_error": last_error,
        },
    )
