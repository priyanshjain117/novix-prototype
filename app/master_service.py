from datetime import datetime, timezone

from fastapi import FastAPI

from .models import ExecuteRequest

app = FastAPI(title="NOVIX Master Service", version="0.1.0")


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "master"}


@app.get("/resources")
def resources() -> dict:
    return {
        "service": "master",
        "role": "coordination",
        "capacity": {"status": "available"},
    }


@app.post("/execute")
def execute(request: ExecuteRequest) -> dict:
    return {
        "status": "accepted",
        "service": "master",
        "task": request.task,
        "payload": request.payload,
        "executed_at": datetime.now(timezone.utc).isoformat(),
        "message": "Execution is a placeholder in the prototype.",
    }
