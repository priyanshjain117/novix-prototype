import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from pydantic import ValidationError

from .llm_service import (
    LLMError,
    LLMOutput,
    generate_response,
    llm_mode,
    llm_timeout_seconds,
)
from .models import ExecuteRequest

app = FastAPI(title="NOVIX Master Service", version="0.1.0")
logger = logging.getLogger("novix.master")
MAX_RETRIES = 2


def _structured_log(level: int, event: str, **fields: Any) -> None:
    logger.log(level, json.dumps({"event": event, **fields}, sort_keys=True))


def _extract_query(request: ExecuteRequest) -> str:
    payload: Dict[str, Any] = request.payload or {}
    query = payload.get("query") or payload.get("text") or request.task
    if not isinstance(query, str) or not query.strip():
        raise ValueError("a non-empty query is required")
    query = query.strip()
    if len(query) > 12000:
        raise ValueError("query exceeds the 12000 character limit")
    return query


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "master", "llm_mode": llm_mode()}


@app.get("/resources")
def resources() -> dict:
    return {
        "service": "master",
        "role": "coordination",
        "capacity": {"status": "available"},
        "llm_mode": llm_mode(),
    }


@app.post("/execute")
async def execute(request: ExecuteRequest) -> dict:
    request_id = str(uuid4())
    try:
        query = _extract_query(request)
    except ValueError as exc:
        _structured_log(logging.WARNING, "input_validation_failed", request_id=request_id)
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    _structured_log(
        logging.INFO,
        "master_request_received",
        request_id=request_id,
        mode=llm_mode(),
        max_retries=MAX_RETRIES,
    )

    last_error = "unknown error"
    for retry_number in range(MAX_RETRIES + 1):
        attempt = retry_number + 1
        try:
            _structured_log(
                logging.INFO,
                "llm_attempt_started",
                request_id=request_id,
                attempt=attempt,
            )
            raw_output = await asyncio.wait_for(
                generate_response(query), timeout=llm_timeout_seconds()
            )
            validated_output = LLMOutput.model_validate(raw_output)
            _structured_log(
                logging.INFO,
                "llm_output_validated",
                request_id=request_id,
                attempt=attempt,
                mode=validated_output.mode,
            )
            return {
                "status": "completed",
                "service": "master",
                "request_id": request_id,
                "task": request.task,
                "llm": {
                    "mode": validated_output.mode,
                    "model": validated_output.model,
                    "attempts": attempt,
                },
                "result": validated_output.model_dump(),
                "executed_at": datetime.now(timezone.utc).isoformat(),
            }
        except (LLMError, TimeoutError, asyncio.TimeoutError, ValidationError) as exc:
            last_error = type(exc).__name__
            _structured_log(
                logging.WARNING,
                "llm_attempt_failed",
                request_id=request_id,
                attempt=attempt,
                error=last_error,
                will_retry=retry_number < MAX_RETRIES,
            )

    _structured_log(
        logging.ERROR,
        "master_request_failed",
        request_id=request_id,
        attempts=MAX_RETRIES + 1,
        error=last_error,
    )
    raise HTTPException(
        status_code=502,
        detail={
            "error": "master LLM execution failed",
            "request_id": request_id,
            "attempts": MAX_RETRIES + 1,
            "last_error": last_error,
        },
    )
