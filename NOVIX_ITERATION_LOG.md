# NOVIX Project Iteration Log

This document records the implementation approach used for each NOVIX project update. It is intentionally separate from the user-facing README and should be updated whenever a new feature or architectural iteration is implemented.

## Iteration 1 — Minimal service backend

### Scope

Created the initial NOVIX backend with router, edge, and master FastAPI services.

### Algorithms and techniques

- REST API design using FastAPI route handlers.
- Shared Pydantic request models for consistent request validation.
- Placeholder execution responses to keep the prototype deterministic and dependency-light.
- Host resource sampling on edge nodes using `psutil` CPU and virtual-memory metrics.

### Components

- `app/router_service.py`
- `app/edge_service.py`
- `app/master_service.py`
- `app/models.py`

## Iteration 2 — Docker Compose deployment

### Scope

Containerized the existing services without changing their boundaries or introducing distributed infrastructure.

### Algorithms and techniques

- Single reusable Python image definition with service-specific Uvicorn commands.
- Docker Compose service discovery through DNS names.
- Shared user-defined network: `novix-network`.
- One reusable edge image with environment-based `NODE_ID` values for `edge-01` and `edge-02`.
- Container health checks and dependency ordering with `depends_on` conditions.

### Components

- `Dockerfile`
- `docker-compose.yml`
- `.dockerignore`

## Iteration 3 — Intelligent query routing

### Scope

Replaced the router placeholder with deterministic, resource-aware routing.

### Algorithms and techniques

- Rule-based query classification using explicit keywords and query length:
  - `low`: short queries without complexity keywords.
  - `medium`: analysis-oriented keywords or longer queries.
  - `high`: high-complexity keywords or very long queries.
- Parallelizability detection using keywords such as `compare`, `multiple`, `parallel`, and conjunctions.
- Live node discovery by probing each node’s `/resources` endpoint before routing.
- Least-loaded edge selection using the mean of reported CPU and RAM percentages.
- Deterministic fallback routing when an edge or master is unavailable.
- Bounded network calls using `httpx` timeouts.
- Structured JSON event logs for received queries, failed probes, routing decisions, and failures.

### Components

- `app/router_service.py`
- `app/models.py`
- `requirements.txt` (`httpx`)

## Iteration 4 — Distributed execution

### Scope

Added concurrent execution for medium-complexity parallelizable queries.

### Algorithms and techniques

- Deterministic query decomposition using separators such as `and`, `also`, `then`, `versus`, and `vs`.
- Word-midpoint splitting as the deterministic fallback when no separator exists.
- Concurrent subtask dispatch with `asyncio.gather` and `httpx.AsyncClient`.
- Stable subtask IDs and ordered result collection.
- Deterministic aggregation that preserves each completed edge response and reports `completed` or `partial` status.
- Per-subtask failure capture so one failed edge does not hide the other result.

### Response structure

Distributed responses include:

- `routing_decision`
- `nodes_used`
- `subtask_results`
- `final_result`

## Iteration 5 — Presentation dashboard

### Scope

Added a simple browser dashboard served by the router service.

### Algorithms and techniques

- Static HTML/CSS/JavaScript without a frontend framework.
- Same-origin requests to the router’s `/query` endpoint.
- Direct browser polling of host-exposed node `/resources` endpoints.
- Periodic telemetry refresh every five seconds.
- Conditional pipeline rendering for standard and distributed execution flows.
- Deterministic rendering of routing metadata, subtask status, and final JSON responses.

### Components

- `dashboard/index.html`
- `dashboard/styles.css`
- `dashboard/app.js`
- Router static mount at `/dashboard/`

## Future iteration template

Append a new section using this format for each future implementation prompt:

```markdown
## Iteration N — Short feature name

### Scope

What changed and why.

### Algorithms and techniques

- Algorithm, rule, protocol, or design technique used.
- Concurrency, failure handling, validation, or UI technique used.

### Components

- Files or services changed.

### Validation

- Tests, smoke checks, or manual verification performed.
```
