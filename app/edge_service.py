import platform
import os
from datetime import datetime, timezone

import psutil
from fastapi import FastAPI

from .models import ExecuteRequest

app = FastAPI(title="NOVIX Edge Service", version="0.1.0")
NODE_ID = os.getenv("NODE_ID", "edge-local")


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "edge", "node_id": NODE_ID}


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
def execute(request: ExecuteRequest) -> dict:
    return {
        "status": "accepted",
        "service": "edge",
        "node_id": NODE_ID,
        "task": request.task,
        "payload": request.payload,
        "executed_at": datetime.now(timezone.utc).isoformat(),
        "message": "Execution is a placeholder in the prototype.",
    }
