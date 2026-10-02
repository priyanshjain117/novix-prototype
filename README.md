# NOVIX Prototype Backend

Minimal Python + FastAPI services for the NOVIX prototype. The services are intentionally independent and use in-memory placeholder behavior.

Implementation algorithms and techniques for each project iteration are tracked in [NOVIX_ITERATION_LOG.md](NOVIX_ITERATION_LOG.md).

## Services

- Router: `POST /query` — classifies queries and routes them using live node resources.
- Edge: `GET /health`, `GET /resources`, `POST /execute` — reports host CPU and memory using `psutil`.
- Master: `GET /health`, `GET /resources`, `POST /execute` — exposes coordination status and placeholder execution.

The router uses deterministic keyword and query-length rules (no LLM) to classify requests as `low`, `medium`, or `high`. Low-complexity requests go to the least-loaded available edge, medium parallelizable requests use both edges when available, and high or non-parallelizable requests go to master. Every routing decision probes `/resources` first and reports unavailable nodes or degraded fallbacks.

For a medium parallelizable query, the router splits the request into two deterministic subtasks, sends them concurrently to `edge-01` and `edge-02`, and returns `routing_decision`, `nodes_used`, `subtask_results`, and `final_result`.

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

The presentation dashboard is served by the router at [http://localhost:8000/dashboard/](http://localhost:8000/dashboard/). It polls edge/master resources and sends queries to the router API.

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
  -d '{"query":"summarize this short text"}'

curl -X POST http://localhost:8001/execute \
  -H 'Content-Type: application/json' \
  -d '{"task":"summarize","payload":{"text":"hello"}}'
```

No Kubernetes, Redis, Kafka, Celery, or cloud deployment configuration is included.
