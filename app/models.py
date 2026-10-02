from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


class ExecuteRequest(BaseModel):
    """Minimal payload accepted by edge and master execution endpoints."""

    task: str = Field(..., min_length=1, description="Task name or command to execute")
    payload: Optional[Dict[str, Any]] = Field(
        default=None, description="Optional task input"
    )


class QueryRequest(BaseModel):
    """Minimal payload accepted by the router."""

    task: str = Field(..., min_length=1, description="Task to route")
    payload: Optional[Dict[str, Any]] = None
