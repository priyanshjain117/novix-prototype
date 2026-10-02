# NOVIX Project Iteration Log

This document records the implementation approach used for each NOVIX project update. It is intentionally separate from the user-facing README and should be updated whenever a new feature or architectural iteration is implemented.

## Ongoing update policy

For every future implementation prompt, append a new iteration entry after the code change. Each entry must state:

- The requested scope and resulting behavior.
- Algorithms, rules, protocols, and implementation techniques used.
- Components and files changed.
- Validation performed, including known limitations or blocked checks.

Documentation-only prompts may update this log without incrementing the product feature iteration count.

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

## Iteration 6 — Master AI layer

### Scope

Added the final AI execution layer to the existing master service without adding a new service or changing the router/edge architecture.

### Algorithms and techniques

- Ordered master pipeline: input validation → maximum retry count of two retries → per-attempt timeout → LLM call → Pydantic output validation.
- Deterministic `LLM_MODE=mock` response for offline demos.
- Environment-configured `LLM_MODE=real` HTTP call to an OpenAI-compatible chat-completions endpoint.
- API credentials supplied only through environment variables and excluded from logs.
- Structured JSON logs containing request IDs, attempt numbers, modes, and failure types without logging prompt contents or secrets.
- Lightweight edge behavior remains the existing mock execution path.

### Components

- `app/master_service.py`
- `app/llm_service.py`
- `docker-compose.yml`
- `.env.example`
- `README.md`

### Validation

- Mock mode is the Compose default and requires no API key.
- Real mode validates the API key configuration, provider response shape, and non-empty output.
- Compose build/start verification is performed as part of this iteration.

## Iteration 7 — Real edge and routed execution

### Scope

Completed end-to-end execution for local, distributed, and master routes. Edge nodes now call local Ollama in real mode. Mock mode remains explicit and offline.

### Algorithms and techniques

- Edge `/execute` validates query input and calls Ollama `/api/chat` with `stream: false`.
- Router filters nodes by reported LLM availability and ranks edges by CPU/RAM load.
- Local and master routes now dispatch execution and return the actual result.
- Distributed subtasks execute concurrently and aggregate ordered answers.
- Edge execution failure falls back to master when master is available.
- Real mode raises errors. It never substitutes mock output.

### Components

- `app/llm_service.py`
- `app/edge_service.py`
- `app/master_service.py`
- `app/router_service.py`
- `docker-compose.yml`
- `.env.example`
- `dashboard/app.js`
- `README.md`

### Validation

- Python compilation passed.
- Docker Compose configuration passed.
- Runtime mock execution, routing, fallback, and LLM failure checks are blocked because host lacks Python dependencies.
- Docker startup is blocked because Docker is unavailable in this environment.
- Live Ollama and live OpenAI-compatible inference require external runtimes and credentials.

## Iteration 8 — Ollama-backed edge execution

### Scope

Replaced the edge `/execute` placeholder (which only echoed the task back) with
genuine task execution, with an opt-in Ollama backend alongside the existing
deterministic mock mode. Router and master services were not modified.
Independent edge nodes may run independent models — this iteration does not
implement distributed inference of a single model across edges.

### Algorithms and techniques

- Mirrored the master's existing pipeline shape on the edge: input validation
  → bounded retries → per-attempt timeout → LLM call → Pydantic output
  validation (`app/edge_llm_service.py`, `app/edge_service.py`).
- `EDGE_LLM_MODE=mock` (default, unchanged offline behavior, deterministic,
  no model required) vs. `EDGE_LLM_MODE=ollama` (HTTP call to a configured
  Ollama `/api/chat` endpoint via `httpx.AsyncClient` with an explicit
  timeout).
- Error classification into retryable vs. permanent failures:
  `EdgeLLMError` (connection errors, timeouts, 5xx — retried up to
  `MAX_RETRIES=2` times, matching the master's constant) and
  `EdgeLLMPermanentError` (bad `EDGE_LLM_MODE`/`OLLAMA_URL` config, HTTP 404
  for a model not pulled on the Ollama host, other 4xx, malformed/empty
  response — never retried).
- `/execute` response contract change: `status` now reports `"completed"` on
  success (was `"accepted"`); the placeholder `"message"` field was removed;
  new `result` (the generated answer plus `mode`/`model`) and `attempts`
  fields were added. `task`, `service`, `node_id`, `payload`, `executed_at`
  are unchanged. On exhausted retries, returns HTTP 502 with
  `{"error","request_id","node_id","attempts","last_error"}`, mirroring the
  master's failure contract.
- Router (`app/router_service.py`) required no changes: `_execute_subtask`
  already treats the edge response as an opaque dict and only inspects HTTP
  status, so the contract change above is compatible by construction.
- `/health` now also reports `llm_mode`; `/resources` is unchanged.
- Docker Compose: added an `ollama` service gated behind the `ollama` Compose
  profile (`docker compose --profile ollama up`) so the default
  `docker compose up --build` flow is unaffected and still works offline.
  Edge services gained `EDGE_LLM_MODE`/`OLLAMA_URL`/`OLLAMA_MODEL`/
  `OLLAMA_TIMEOUT_SECONDS` environment variables, all defaulting to mock-mode
  values. No automatic model pull is performed — the model must be pulled
  manually (`docker compose exec ollama ollama pull <model>`) before
  `EDGE_LLM_MODE=ollama` can serve real responses; this is documented in the
  README, not automated.
- Tests use `respx` to mock all outbound HTTP calls (no live Ollama/network
  required), and FastAPI's `TestClient` for route-level tests.

### Components

- `app/edge_llm_service.py` (new)
- `app/edge_service.py`
- `.env.example`
- `docker-compose.yml`
- `README.md`
- `requirements.txt` (test-only: `pytest`, `pytest-asyncio`, `respx`)
- `pytest.ini` (new)
- `tests/test_edge_llm_service.py` (new)
- `tests/test_edge_service.py` (new)
- `tests/test_router_edge_compatibility.py` (new)

### Validation

- `python -m pytest` run locally: **17 passed, 0 failed** — covers mock-mode
  execution, successful Ollama responses, Ollama timeouts, Ollama
  unavailability (connection refused), Ollama 5xx, missing-model (404),
  malformed Ollama responses, invalid `EDGE_LLM_MODE`, retry-then-succeed,
  permanent-error-no-retry, retries-exhausted, `/health` and `/resources`
  regressions, oversized-query rejection, and two router-compatibility tests
  asserting `app/router_service.py`'s `_execute_subtask` still wraps the new
  edge response shape correctly on both success and failure.
- Not verified: behavior against a real, running Ollama instance (no network
  access to pull a model in this environment) and GPU/VRAM-aware scheduling
  (not implemented — edge resource reporting remains CPU/RAM only, as it was
  before this iteration).

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
