import os

from fastapi import FastAPI

from .models import QueryRequest

app = FastAPI(title="NOVIX Router Service", version="0.1.0")

EDGE_URLS = [
    url.strip()
    for url in os.getenv(
        "EDGE_URLS", "http://localhost:8001,http://localhost:8002"
    ).split(",")
    if url.strip()
]
MASTER_URL = os.getenv("MASTER_URL", "http://localhost:8002")


@app.post("/query")
def query(request: QueryRequest) -> dict:
    return {
        "task": request.task,
        "decision": "edge",
        "target": EDGE_URLS[0],
        "available_edges": EDGE_URLS,
        "master": MASTER_URL,
        "reason": "Placeholder routing decision.",
    }
