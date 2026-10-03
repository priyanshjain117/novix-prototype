<div align="center">

# 🧠 NOVIX Prototype Backend

[![Typing SVG](https://readme-typing-svg.demolab.com/?font=Fira+Code&size=20&pause=1000&color=6C5CE7&center=true&vCenter=true&width=600&lines=Route+queries+across+edge+LLMs...;Mock+mode+by+default%2C+no+API+key...;Ollama+and+OpenAI-compatible+ready!)](https://git.io/typing-svg)

**Distributed query routing across local edge LLMs and a master OpenAI-compatible LLM.**

![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB?style=for-the-badge&logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-async-009688?style=for-the-badge&logo=fastapi&logoColor=white)
![Docker Compose](https://img.shields.io/badge/Docker-Compose-2496ED?style=for-the-badge&logo=docker&logoColor=white)
![Ollama](https://img.shields.io/badge/Ollama-compatible-000000?style=for-the-badge&logo=ollama&logoColor=white)
![pytest](https://img.shields.io/badge/tested%20with-pytest-0A9EDC?style=for-the-badge&logo=pytest&logoColor=white)

</div>

Implementation algorithms and techniques for each project iteration are tracked in [NOVIX_ITERATION_LOG.md](NOVIX_ITERATION_LOG.md).

## 📑 Contents

- [🧩 Services](#-services)
- [🏗️ Architecture](#️-architecture)
- [🔀 Routing logic](#-routing-logic)
- [⚙️ Execution flow](#️-execution-flow)
- [🔄 Developer workflow](#-developer-workflow)
- [🎛️ LLM mode state machine](#️-llm-mode-state-machine)
- [🚀 Setup](#-setup)
- [▶️ Run](#️-run)
- [✅ Tests](#-tests)
- [🐳 Run with Docker Compose](#-run-with-docker-compose)
- [📡 Example requests](#-example-requests)
- [📋 Validation status](#-validation-status)

## 🧩 Services

| Service | Endpoints | Role |
| --- | --- | --- |
| 🔀 **Router** | `POST /query` | Classifies queries and routes them using live node resources. |
| 🖥️ **Edge** | `GET /health`, `GET /resources`, `POST /execute` | Reports host CPU/memory via `psutil`. Executes through `EDGE_LLM_MODE`: `mock` (default, deterministic, no model needed) or `ollama` (calls a configured Ollama endpoint). |
| 🧠 **Master** | `GET /health`, `GET /resources`, `POST /execute` | Validates and executes queries through the final AI layer. |

## 🏗️ Architecture

```mermaid
flowchart LR
    U["🧑 Client"] -->|"POST /query"| R["🔀 Router\n:8000"]

    R -->|"low"| E1["🖥️ Edge-01\n:8001"]
    R -->|"medium (split)"| E1
    R -->|"medium (split)"| E2["🖥️ Edge-02\n:8002"]
    R -->|"high / fallback"| M["🧠 Master\n:8003"]

    E1 -.->|"mock"| E1m[["deterministic\nstring"]]
    E1 -->|"ollama"| O["🦙 Ollama\n/api/chat"]
    E2 -->|"ollama"| O
    M -->|"real"| A["☁️ OpenAI-compatible\nchat-completions API"]
    M -.->|"mock"| Mm[["deterministic\nstring"]]

    style R fill:#6C5CE7,color:#fff,stroke:#4834d4
    style E1 fill:#00B894,color:#fff,stroke:#019868
    style E2 fill:#00B894,color:#fff,stroke:#019868
    style M fill:#0984E3,color:#fff,stroke:#065a9e
    style O fill:#2D3436,color:#fff,stroke:#000
    style A fill:#E17055,color:#fff,stroke:#b2502f
    style U fill:#FDCB6E,color:#000,stroke:#b8960b
```

## 🔀 Routing logic

The router uses deterministic keyword and query-length rules (no extra routing model) to classify requests as `low`, `medium`, or `high`:

| Class | Behavior |
| --- | --- |
| 🟢 **Low** | Executes on the least-loaded edge. |
| 🟡 **Medium** (parallelizable) | Splits into two deterministic subtasks, sent concurrently to two available edges; returns real LLM outputs plus an ordered aggregate. |
| 🔴 **High** (or indivisible) | Executes on master. |

Resource probes include CPU, RAM, and LLM availability. If an edge execution fails, the router retries the query on master when available.

```mermaid
sequenceDiagram
    participant C as 🧑 Client
    participant R as 🔀 Router
    participant E as 🖥️ Edge
    participant Mst as 🧠 Master

    C->>R: POST /query
    R->>R: classify (low / medium / high)
    alt low
        R->>E: dispatch subtask
        E-->>R: result
    else medium (parallel)
        R->>E: subtask A
        R->>E: subtask B
        E-->>R: result A
        E-->>R: result B
        R->>R: aggregate (ordered)
    else high / edge failed
        R->>Mst: dispatch query
        Mst-->>R: result
    end
    R-->>C: response
```

## ⚙️ Execution flow

**Master** — input validation → up to two retries → per-attempt timeout → LLM call → output validation.

- `LLM_MODE=mock` — deterministic, no API key required.
- `LLM_MODE=real` — calls the configured OpenAI-compatible chat-completions endpoint.

**Edge** — the same shape: input validation → up to two retries → per-attempt timeout → LLM call → output validation.

- `EDGE_LLM_MODE=mock` (default) — deterministic, no HTTP call, returns a fixed `f"Mock edge response for: {query}"` string.
- `EDGE_LLM_MODE=ollama` — calls `OLLAMA_URL`'s `/api/chat` endpoint. Permanent failures (bad config, missing model, malformed response) are not retried; connection errors, timeouts, and 5xx responses are retried up to twice.

```mermaid
flowchart TD
    A["📥 input validation"] --> B{"valid?"}
    B -- no --> X["❌ HTTP 422"]
    B -- yes --> C["⏱️ per-attempt timeout"]
    C --> D["🤖 LLM call"]
    D --> E{"success?"}
    E -- yes --> F["✅ output validation"]
    F --> G["📤 200 result"]
    E -- "permanent error" --> X2["❌ HTTP 502 (no retry)"]
    E -- "transient error" --> H{"retries left?"}
    H -- yes --> C
    H -- no --> X2

    style A fill:#0984E3,color:#fff
    style C fill:#FDCB6E,color:#000
    style D fill:#6C5CE7,color:#fff
    style F fill:#00B894,color:#fff
    style G fill:#00B894,color:#fff
    style X fill:#D63031,color:#fff
    style X2 fill:#D63031,color:#fff
```

Each edge independently selects mock or Ollama execution, so subtasks sent to different edges may be answered by different, independently running models — this is not single-model distributed inference. Real mode never falls back to mock output.

## 🔄 Developer workflow

```mermaid
flowchart LR
    A["✏️ Code change"] --> B["🧪 python -m pytest"]
    B --> C{"pass?"}
    C -- no --> A
    C -- yes --> D["🐍 py_compile sanity"]
    D --> E["🐳 docker compose up --build"]
    E --> F["🔎 curl /health + /resources"]
    F --> G["📨 POST /query smoke test"]
    G --> H["📝 update NOVIX_ITERATION_LOG.md"]
    H --> I["✅ commit"]

    style A fill:#FDCB6E,color:#000
    style B fill:#0984E3,color:#fff
    style D fill:#0984E3,color:#fff
    style E fill:#2496ED,color:#fff
    style F fill:#6C5CE7,color:#fff
    style G fill:#6C5CE7,color:#fff
    style H fill:#00B894,color:#fff
    style I fill:#00B894,color:#fff
```

## 🎛️ LLM mode state machine

Each service (master, edge) resolves its execution mode independently from its own env var (`LLM_MODE` for master, `EDGE_LLM_MODE` for edge):

```mermaid
stateDiagram-v2
    [*] --> Mock
    Mock --> Mock: default, deterministic\nno API key / model needed
    Mock --> Real: LLM_MODE=real /\nEDGE_LLM_MODE=ollama
    Real --> Real: success
    Real --> Retry: transient error\n(timeout, connection, 5xx)
    Retry --> Real: attempt < max
    Retry --> Failed: retries exhausted
    Real --> Failed: permanent error\n(bad config, 404 model, malformed)
    Failed --> [*]: HTTP 502
    Real --> [*]: HTTP 200
    Mock --> [*]: HTTP 200

    note right of Real
        never falls back
        to mock output
    end note
```

## 🚀 Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Copy `.env.example` to `.env` for local configuration. The default mock mode works without credentials:

```bash
cp .env.example .env
```

## ▶️ Run

Run each service in a separate terminal from the project root:

```bash
uvicorn app.router_service:app --reload --port 8000
uvicorn app.edge_service:app --reload --port 8001
uvicorn app.edge_service:app --reload --port 8002
uvicorn app.master_service:app --reload --port 8003
```

Interactive API documentation is available at `/docs` for each service.

The presentation dashboard is served by the router at [http://localhost:8000/dashboard/](http://localhost:8000/dashboard/). It polls edge/master resources and sends queries to the router API.

## ✅ Tests

```bash
python -m pytest
```

Tests mock all outbound HTTP calls (via `respx`), so they do not require a live model or network access.

## 🐳 Run with Docker Compose

Docker Compose starts the router, two edge nodes, and the master on the shared `novix-network` network:

```bash
docker compose up --build
```

Compose reads `.env` automatically. Mock mode runs fully offline.

### ☁️ Real mode (master)

For master to call a real OpenAI-compatible endpoint:

```bash
cp .env.example .env
# Set LLM_MODE=real and LLM_API_KEY in .env.
docker compose up --build
```

### 🦙 Ollama mode (edges)

The `ollama` service is opt-in via a Compose profile, so the default `docker compose up --build` flow is unchanged and keeps working offline.

```bash
docker compose --profile ollama up -d ollama
docker compose exec ollama ollama pull llama3.2
```

> ⚠️ The model is **not** downloaded automatically — the `ollama pull` step above is required before the edges can serve real responses.

Then set in `.env`:

```bash
EDGE_LLM_MODE=ollama
OLLAMA_MODEL=llama3.2
```

and restart the edge containers:

```bash
docker compose up -d edge-01 edge-02
```

### 🔌 Container addresses

| From | Router | Edge nodes | Master |
| --- | --- | --- | --- |
| Container-to-container | `http://router:8000` | `http://edge-01:8000`, `http://edge-02:8000` | `http://master:8000` |
| From host | `:8000` | `:8001`, `:8002` | `:8003` |

## 📡 Example requests

```bash
curl http://localhost:8001/health
curl http://localhost:8001/resources

curl -X POST http://localhost:8000/query \
  -H 'Content-Type: application/json' \
  -d '{"query":"summarize this short text"}'

curl -X POST http://localhost:8001/execute \
  -H 'Content-Type: application/json' \
  -d '{"task":"summarize","payload":{"text":"hello"}}'

curl -X POST http://localhost:8003/execute \
  -H 'Content-Type: application/json' \
  -d '{"task":"answer","payload":{"query":"Explain the NOVIX routing flow."}}'
```

🚫 No Kubernetes, Redis, Kafka, Celery, or cloud deployment configuration is included.

## 📋 Validation status

Python compilation and Compose configuration pass locally. Runtime mock execution, routing, fallback, LLM failure, Docker startup, Ollama inference, and OpenAI-compatible inference remain unverified without dependencies, Docker, runtimes, or credentials.
