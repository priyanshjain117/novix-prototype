# NOVIX Prototype Backend

Minimal Python + FastAPI services for the NOVIX prototype. The services are intentionally independent and use in-memory placeholder behavior.

## Services

- Router: `POST /query` — returns a placeholder routing decision.
- Edge: `GET /health`, `GET /resources`, `POST /execute` — reports host CPU and memory using `psutil`.
- Master: `GET /health`, `GET /resources`, `POST /execute` — exposes coordination status and placeholder execution.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Run

Run each service in a separate terminal from the project root:

```bash
uvicorn app.router_service:app --reload --port 8000
uvicorn app.edge_service:app --reload --port 8001
uvicorn app.master_service:app --reload --port 8002
```

Interactive API documentation is available at `/docs` for each service.

## Run with Docker Compose

Docker Compose starts the router, two edge nodes, and the master on the shared `novix-network` network:

```bash
docker compose up --build
```

Container-to-container addresses are:

- Router: `http://router:8000`
- Edge nodes: `http://edge-01:8000`, `http://edge-02:8000`
- Master: `http://master:8000`

From the host, the services are available on ports `8000` (router), `8001` (edge-01), `8002` (edge-02), and `8003` (master).

## Example requests

```bash
curl http://localhost:8001/health
curl http://localhost:8001/resources

curl -X POST http://localhost:8000/query \
  -H 'Content-Type: application/json' \
  -d '{"task":"summarize","payload":{"text":"hello"}}'

curl -X POST http://localhost:8001/execute \
  -H 'Content-Type: application/json' \
  -d '{"task":"summarize","payload":{"text":"hello"}}'
```

No Docker, Kubernetes, Redis, Kafka, Celery, or cloud deployment configuration is included.
