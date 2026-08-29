# 👨‍💻 Nexus Developer Guide

This guide explains the internal architecture and implementation details of Nexus.

Unlike the README, which focuses on getting started, this guide is intended for contributors and developers who want to understand how Nexus works internally.

---


## System Overview
Nexus is a capability-driven orchestration platform responsible for coordinating distributed AI agents.

Rather than embedding business logic inside the orchestrator, Nexus dynamically discovers remote A2A-compatible agents through Agent Cards, selects the appropriate capability for a user request, delegates execution, and tracks the workflow lifecycle from start to completion.


## 📂 Project Structure & File Mappings

### Entry Point

| File           | Responsibility                                                                                                                                               |
| -------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| **main.py** | FastAPI app initialization, observability setup, router registration, lifespan management, and WebSocket service initialization |

### Core Configuration

| File                       | Responsibility                                                                    |
| -------------------------- | --------------------------------------------------------------------------------- |
| **core/config.py**         | Centralized app configuration (`APP_NAME`, `DEFAULT_USER`), environment variables |
| **core/runner_factory.py** | Factory function to instantiate `Runner` with root agent                          |

### Root Agent & Agent Framework

| File                                   | Responsibility                                                                                               |
| -------------------------------------- | ------------------------------------------------------------------------------------------------------------ |
| **agents/agent.py**                    | **Nexus** root agent definition, Azure OpenAI/LiteLLM integration, agent instructions, sub-agent management |
| **agents/remote_agent_connections.py** | Remote agent connection utilities for A2A protocol communication                                             |
| **agents/hitl_handler.py**             | Optional Human-in-the-Loop (HITL) handler for agent decision points                                          |

### API Routers

| File                            | Responsibility                                                                |
| ------------------------------- | ----------------------------------------------------------------------------- |
| **routers/agent_registry.py**   | Agent registration endpoints (`POST /agents/add`, `GET /agents/active`, etc.) |
| **routers/run_agent_router.py** | REST endpoint for synchronous agent execution (`POST /run/`)                  |
| **routers/file_router.py**      | File management endpoints (upload, download, artifact serving)                |
| **routers/upload_router.py**    | Multi-file upload handling with session integration                           |
| **routers/dashboard_router.py** | Admin dashboard endpoints for monitoring active workflows and agents etc.     |
| **routers/histoy_router.py**    | Endpoints for chat-history                                                    |

### Real-Time Communication (WebSocket)

| File                               | Responsibility                                                      |
| ---------------------------------- | ------------------------------------------------------------------- |
| **websocket/websocket_handler.py** | Main WebSocket connection handler, message routing, session binding |
| **websocket/ws_emitter.py**        | Emits WebSocket events (status, errors, tool progress, artifacts)   |
| **websocket/event_processor.py**   | Processes incoming WebSocket events, delegates to services          |
| **wesocket/event_normalizer.py**   | Normalizes event payloads for consistent structure and logging      |

### Business Logic Services

| File                                    | Responsibility                                                                                                                                             |
| --------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **services/workflow_service.py**        | **Workflow Lifecycle**: creates `OrchestrationSession` per user prompt, tracks status (active/completed/failed), computes workflow completion              |
| **services/agent_execution_service.py** | **Invocation Tracking**: creates `AgentInvocation` rows per sub-agent call, manages step order, tracks input/output payloads, started/completed timestamps |
| **services/agent_loader.py**            | Loads active and healthy agents from registry, injects into Nexus                                                                                         |
| **services/agent_sync_service.py**      | Background sync loop for agent status/health updates                                                                                                       |
| **services/artifact_service.py**        | Manages generated artifacts (files) from agent execution                                                                                                   |
| **services/file_service.py**            | **Signed URL generation**, HMAC validation, TTL management, artifact access control                                                                        |
| **services/invocation_context.py**      | Invocation context holder (invocation_id, agent_name, agent_session_idk etc)                                                                               |
| **services/chat_history_service.py**    | Optional chat history persistence and retrieval for user sessions                                                                                          |

### a2a runtime plugin

| File                                        | Responsibility                                                                          |
| ------------------------------------------- | --------------------------------------------------------------------------------------- |
| **services/a2a_runtime/adapter.py**         | A2A runtime adapter for JSON-RPC calls to remote agents                                 |
| **services/a2a_runtime/client_manager.py**  | Manages active A2A connections, handles retries, timeouts, and health checks            |
| **services/a2a_runtime/response_parser.py** | Parses streaming responses from remote agents, normalizes events for WebSocket emission |
| **services/a2a_runtime/models.py**          | Defines Pydantic models for A2A messages, agent cards, and invocation payloads          |

### State Management

| File                             | Responsibility                                                                               |
| -------------------------------- | -------------------------------------------------------------------------------------------- |
| **state/models.py**              | Pydantic models for session state, workflow state, and invocation state                      |
| **state/state_manager.py**       | Manages in-memory state for active workflows, agent invocations, and session context         |
| **state/orchestration_state.py** | Tracks the state of each orchestration workflow, including step order, status, and artifacts |

### Session Management

| File                           | Responsibility                                                                                                                      |
| ------------------------------ | ----------------------------------------------------------------------------------------------------------------------------------- |
| **session/session_manager.py** | **Dual-mode session mgmt**: ADK persistent sessions (conversation memory) + in-memory active session mirror for WebSocket workflows |

### Database & ORM

| File                    | Responsibility                                                                                                                                      |
| ----------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------- |
| **database/engine.py**  | SQLAlchemy async engine setup                                                                                                                       |
| **database/session.py** | Async session factory (`AsyncSessionLocal`)                                                                                                         |
| **database/models.py**  | **ORM Models**: `AgentRegistry`, `OrchestrationSession`, `AgentInvocation`,`Artifact`,`ChatHistory`,`Dependencies` etc with relationships & indexes |

### Agent Registry (Management)

| File                                 | Responsibility                                                                                                               |
| ------------------------------------ | ---------------------------------------------------------------------------------------------------------------------------- |
| **agent_registry/health_monitor.py** | **Health Check Loop**: async task that periodically calls `GET /health` on each registered agent, updates `is_healthy` in DB |

### Infrastructure & Utilities

| File                              | Responsibility                                                       |
| --------------------------------- | -------------------------------------------------------------------- |
| **infrastructure/a2a_factory.py** | A2A (Agent-to-Agent) protocol factory for remote agent communication |
| **utils/agent_card_extractor.py** | Extracts agent capabilities from agent cards                         |

### Database Migrations

| File                          | Responsibility                                    |
| ----------------------------- | ------------------------------------------------- |
| **alembic.ini**               | Alembic configuration file                        |
| **migrations/env.py**         | Alembic migration environment setup               |
| **migrations/script.py.mako** | Alembic migration template                        |
| **migrations/versions/**      | Versioned migration files (one per schema change) |

### Configuration & Dependencies

| File               | Responsibility                                                                  |
| ------------------ | ------------------------------------------------------------------------------- |
| **.env**           | Environment variables (see [Configuration](#-configuration))                    |
| **pyproject.toml** | Project metadata, dependencies (FastAPI, SQLAlchemy, Google ADK, LiteLLM, etc.) |
| **observability/setup.py** | OpenTelemetry provider, OTLP/Jaeger export, and optional HTTP/FastAPI instrumentation |
| **observability/tracing.py** | Span helpers and semantic attributes for orchestration and A2A calls |
| **services/context_broker.py** | Builds bounded planner context from active task, plan, and completed node outputs |
| **services/planning_service.py** | Creates dependency-aware plans from the user prompt and registered capabilities |
| **services/plan_execution_service.py** | Executes approved plans and resumes nodes awaiting A2A input |

### Testing & Development Tools

| File                  | Responsibility                                                             |
| --------------------- | -------------------------------------------------------------------------- |
| **tools/**            | Development utilities and testing scripts (not part of production runtime) |
| **cli_testing.py**    | CLI testing utilities                                                      |
| **sample_testing.py** | Sample testing scripts                                                     |

---

## 🔄 Data Flow & Execution Workflow

### Request → Orchestration Workflow

```
1. WebSocket Message (User Prompt)
   ↓
2. WebSocketHandler.handle() receives message
   ↓
3. WorkflowService.start_workflow() → creates OrchestrationSession (UUID)
   ↓
4. AgentExecutionService.start_root_invocation()
   → creates AgentInvocation row (Nexus, step_order=1, status=working)
   ↓
5. Runner.run_async(new_message=Content(text=prompt))
   → calls Nexus agent with message
   ↓
6. Nexus Decision:
   - Receives active+healthy agents dynamically
   - Routes request to 1+ sub-agents via RemoteServerManager (A2A protocol)
   ↓
7. Sub-agent Execution:
   - For each sub-agent: create AgentInvocation row (step_order increments)
   - Send JSON-RPC call via A2A with file_data references
   - Receive streaming response
   ↓
8. Status Updates:
   - EventProcessor → WSEmitter → WebSocket client
   - Types: status, plan, waiting_for_input, invocation_started, tool_progress, artifact, invocation_completed
   ↓
9. WorkflowService.complete_workflow()
   → marks OrchestrationSession as completed
   ↓
10. Session preserved for the next prompt (ADK session_id keeps conversation context)
11. If an A2A agent returns `input-required`, persist `orchestrator.task` and resume later
    with the same `task_id` and `context_id` after a `user_response` message.
```

---

## 🧱 Execution Tracking (Three-Layer Model)

**OrchestrationSession (Workflow)**

- New workflow UUID per user prompt
- Table: `orchestration_sessions`
- Fields:
  - `id (PK), session_id (workflow UUID), user_id, status (active/completed/failed), created_at, completed_at`
- Guarantees:
  - Execution isolation per prompt
  - Clean debugging & observability
  - Future replay capability

**AgentInvocation (Execution Step)**

- New row per sub‑agent call
- Table: `agent_invocations`
- Fields:
  - `id (PK), orchestration_session_id (FK), agent_name, step_order, status, input_payload (JSON), output_payload (JSON), started_at, completed_at`
- **Step order** increments per workflow (resets on new workflow):
  - Workflow A: `step_order: 1→Nexus, 2→classification_bot, 3→scoring_agent`
  - Workflow B: `step_order: 1→Nexus, 2→different_agent`

**AgentRegistry (Capability & Health)**

- Persistent agent metadata
- Table: `agents`
- Fields:
  - `id (PK), name (UNIQUE), host, port, is_active, is_healthy, agent_card (JSON), created_at, last_health_check`
- Maintained by:
  - Health Monitor background loop (checks `/health` every N seconds)
  - Agent Registry API (add/remove agents)
  - Only **active + healthy** agents injected into Nexus decision context

---

## 🧠 Session Separation Model

| Layer                  | Purpose                                      | Managed By                          |
| ---------------------- | -------------------------------------------- | ----------------------------------- |
| WebSocket `session_id` | Transport connection (per client session)    | SessionManager (in-memory)          |
| ADK `session_id`       | Conversation memory (ADK persistent session) | DatabaseSessionService (Google ADK) |
| Workflow UUID          | Execution tracking per request               | OrchestrationSession (DB)           |
| ADK `agent_session_id` | Per-agent message history                    | Runner (ADK framework)              |

**Benefits**:

- ✅ Conversation context preserved across multiple prompts (ADK session)
- ✅ Workflow tracking isolated **per request** (workflow UUID)
- ✅ No cross‑workflow mixing or state leakage
- ✅ Easy debugging: query `orchestration_sessions` + `agent_invocations`
- ✅ Future replay: replay entire workflow from UUID

---

## 🛢️ Database Schema (Comprehensive)

### Active Tables

**agents** (Agent Registry)

```sql
CREATE TABLE agents (
  id SERIAL PRIMARY KEY,
  name VARCHAR(255) UNIQUE NOT NULL,
  host VARCHAR(255) NOT NULL,
  port INTEGER NOT NULL,
  is_active BOOLEAN DEFAULT TRUE,
  is_healthy BOOLEAN DEFAULT FALSE,
  agent_card JSONB NOT NULL,  -- /.well-known/agent-card.json
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  last_health_check TIMESTAMP WITH TIME ZONE
);
```

**orchestration_sessions** (Workflow)

```sql
CREATE TABLE orchestration_sessions (
  id SERIAL PRIMARY KEY,
  session_id VARCHAR(255) UNIQUE INDEX,
  user_id VARCHAR(255) INDEX,
  status VARCHAR(50) DEFAULT 'active',  -- active, completed, failed
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  completed_at TIMESTAMP WITH TIME ZONE
);
```

**agent_invocations** (Execution Steps)

```sql
CREATE TABLE agent_invocations (
  id SERIAL PRIMARY KEY,
  orchestration_session_id INTEGER FK REFERENCES orchestration_sessions(id),
  agent_name VARCHAR(255) NOT NULL,
  step_order INTEGER NOT NULL,  -- 1, 2, 3... per workflow
  status VARCHAR(50) DEFAULT 'working',  -- working, completed, failed
  input_payload JSONB,  -- The input sent to agent
  output_payload JSONB,  -- The output/response
  started_at TIMESTAMP WITH TIME ZONE,
  completed_at TIMESTAMP WITH TIME ZONE
);
```

### Implemented Trace Tables

- `agent_dependencies` (plan/dependency relationships)
- `agent_events` (streaming trace logging)
- `artifacts` (generated file persistence)
- `chat_messages` and ADK session/event tables (conversation memory)

The durable orchestration state also stores the active `task` and `plan` payload for
input-required continuation and plan approval.

**Timestamps**: All use `TIMESTAMP WITH TIME ZONE` (UTC‑safe).

> **Migration Management**: Use **Alembic** (`alembic upgrade head`, `alembic downgrade -1`)

---

## 🔁 Complete Execution Flow (Step-by-Step)

### User Request → Agent Response

```
1. Client sends WebSocket message with prompt and optionally uploaded files
2. WebSocketHandler accepts the development/mock authentication frame. External identity
   validation is intentionally deferred and must be added before production deployment.
3. WorkflowService creates an OrchestrationSession (workflow UUID)
4. AgentExecutionService creates root AgentInvocation for Nexus agent (step_order=1)
5. Runner executes Nexus agent with user's prompt and attaches uploaded files as file_data parts
6. Nexus dynamically loads active and healthy sub-agents from registry
7. Nexus routes prompt to sub-agents:
     - For each sub-agent, AgentExecutionService creates AgentInvocation with incremented step_order
     - JSON-RPC calls are made to remote agents over A2A protocol
     - Streaming responses handled in real-time
8. Artifact Management:
     - When agents produce file artifacts with URLs, EventProcessor fetches them securely
     - ArtifactService stores metadata, ownership (tenant/user/session), and persists files
     - Signed URLs are generated for secure, time-limited access
     - Artifacts are forwarded as opaque file references to other agents or clients
     - WebSocket client is notified with artifact events including download links
9. Status Updates and tool progress streamed to the frontend via WSEmitter
10. WorkflowService marks orchestration workflow completed upon finish
11. ADK sessions keep conversation context for future messages; ContextBroker supplies
    only bounded task context to the planner.
```

---

## 📈 Execution Flow Sequence Diagram

![Screenshot](sequence-diagram\sequence_diagram_upgrade.png)

---

## 📊 Observability & Debugging

### Query Execution Status

```sql
-- Recent workflows
SELECT
  os.id as workflow_id,
  os.session_id,
  os.user_id,
  os.status,
  os.created_at,
  COUNT(ai.id) as invocation_count
FROM orchestration_sessions os
LEFT JOIN agent_invocations ai ON os.id = ai.orchestration_session_id
WHERE os.created_at > NOW() - INTERVAL '1 hour'
GROUP BY os.id
ORDER BY os.created_at DESC;
```

```sql
-- Detailed execution trace
SELECT
  ai.step_order,
  ai.agent_name,
  ai.status,
  ai.started_at,
  ai.completed_at,
  EXTRACT(EPOCH FROM (ai.completed_at - ai.started_at)) as duration_sec,
  ai.input_payload->'prompt' as prompt_excerpt,
  ai.output_payload->'result' as result_excerpt
FROM agent_invocations ai
WHERE ai.orchestration_session_id = :workflow_id
ORDER BY ai.step_order;
```

```sql
-- Agent health status
SELECT
  name,
  is_active,
  is_healthy,
  last_health_check,
  created_at
FROM agents
ORDER BY name;
```

### WebSocket Event Types

| Event Type             | Payload                           | Purpose                                        |
| ---------------------- | --------------------------------- | ---------------------------------------------- |
| `status`               | `{ stage, message }`              | Status update (e.g., "Selecting best agent")   |
| `invocation_started`   | `{ agent, step, workflow_id }`    | Sub-agent invocation started                   |
| `tool_progress`        | `{ agent, detail }`               | Tool execution progress (e.g., "extract_text") |
| `artifact`             | `{ name, signed_url }`            | Artifact generated (file)                      |
| `invocation_completed` | `{ agent, step, status }`         | Sub-agent completed                            |
| `workflow_completed`   | `{ workflow_id, final_response }` | Entire workflow done                           |
| `error`                | `{ scope, message, agent? }`      | Error occurred                                 |

---

## 🔐 Security Best Practices

### A2A Communication

- **Verify agent identity** via `/health` endpoint before trusting
- **Sign all JSON-RPC calls** with shared secret or bearer token
- **Validate agent_card** schema (`/.well-known/agent-card.json`)
- **HTTPS only** for remote agent communication

### File Handling

- **HMAC-signed URLs** with configurable TTL (default: 600 sec)
- **Expiration** timestamp embedded in signature
- **No direct file reads** by Nexus (opaque artifact forwarding)
- **Secure storage** with access logging

### Database & Secrets

- **Least privilege**: App-specific DB user (no superuser)
- **Connection pooling**: Async + pgbouncer for scale
- **Secrets management**: `.env` file (dev only), Vault/Secrets Manager (prod)
- **Audit timestamps**: All UTC, timezone-sensitive

### CORS & Origins

- **Strict origin validation**: only approved WebSocket/HTTP origins
- **No credentials** in logs
- **Rate limiting** recommended at load balancer

---

## 🧪 Testing Strategy

### Unit Tests

- Mock A2A calls for sub-agents
- Test workflow state transitions
- Verify signed URL generation

### Integration Tests

- Spin up test PostgreSQL container
- Register mock agents
- E2E workflow execution
- Health monitor updates

### Example (pytest):

```python
# tests/test_workflow_service.py
@pytest.mark.asyncio
async def test_start_workflow_creates_session():
    service = WorkflowService(mock_db_factory)
    workflow = await service.start_workflow(user_id="user123")
    assert workflow.status == "active"
    assert workflow.session_id is not None
```

---

## 🐛 Troubleshooting

### Agent not appearing in active agents

- ✅ Check `agents` table: `is_active=true AND is_healthy=true`
- ✅ Run health monitor: Check `agent_registry/health_monitor.py`
- ✅ Verify agent URL responds to `GET /health`
- ✅ Check `last_health_check` timestamp (recent = good)

### Workflow stuck in "active" state

- ✅ Check `agent_invocations` for failed sub-agents
- ✅ Review WebSocket connection status
- ✅ Manually update: `UPDATE orchestration_sessions SET status='failed' WHERE id=:id`

### File artifact not forwarded to sub-agent

- ✅ Verify `signed_url` not expired (check TTL in URL)
- ✅ Confirm file exists in `uploads/` folder
- ✅ Check `FileService.generate_signed_url()` logic
- ✅ Review sub-agent logs for 403 Forbidden on artifact fetch

### High latency

- ✅ Profile agent execution times: `EXTRACT(EPOCH FROM (completed_at - started_at))`
- ✅ Check database query performance (indexes on `orchestration_session_id`)
- ✅ Monitor A2A network latency
- ✅ Consider async concurrency limits

---

## ⚙️ Configuration

### Environment Variables (.env)

```dotenv
# ============================================================
# SERVER & APP
# ============================================================
APP_ENV=local                              # local, staging, production
APP_NAME=my_agent_app                      # ADK app identifier
APP_PORT=8080                              # FastAPI port
DEFAULT_USER=default_user                  # Default user for API calls
ALLOWED_WS_ORIGINS=http://localhost:3000   # WebSocket allowed origins (comma-separated)

# ============================================================
# DATABASE (PostgreSQL)
# ============================================================
DATABASE_URL=postgresql+psycopg2://user:pass@localhost:5432/orchestrator
# Format: postgresql+asyncpg://user:pass@host:port/dbname (for async)
# Production: use connection pooling with pgbouncer

# ============================================================
# LLM (Azure OpenAI via LiteLLM)
# ============================================================
DEPLOYMENT_NAME=gpt-4o                     # Azure deployment name
AZURE_API_KEY=your_base64_key              # Azure OpenAI API key
AZURE_API_BASE=https://<resource>.openai.azure.com  # Azure endpoint
AZURE_API_VERSION=2024-02-15               # API version

# Alternative: Direct LiteLLM config
LITELLM_MODEL=azure/gpt-4o
LITELLM_API_BASE=${AZURE_API_BASE}
LITELLM_API_KEY=${AZURE_API_KEY}

# ============================================================
# A2A (Agent-to-Agent Protocol)
# ============================================================
A2A_SHARED_SECRET=change_me_in_prod        # HMAC secret for A2A calls
A2A_HEALTH_INTERVAL_SECONDS=30             # Health check interval
A2A_TIMEOUT_SECONDS=60                     # A2A call timeout
A2A_VERIFY_AGENT_CARD=true                 # Validate agent.card.json schema

# ============================================================
# FILE HANDLING
# ============================================================
FILE_SIGNING_SECRET=change_me_in_prod      # HMAC secret for signed URLs
SIGNED_URL_TTL_SECONDS=600                 # URL validity (10 min)
MAX_UPLOAD_MB=50                           # Max file upload size
UPLOAD_FOLDER=./uploads                    # Local upload directory
PUBLIC_BASE_URL=http://localhost:8000      # Base URL for signed URLs

# ============================================================
# LOGGING & OBSERVABILITY
# ============================================================
LOG_LEVEL=INFO                             # DEBUG, INFO, WARNING, ERROR, CRITICAL
LOG_FORMAT=json                            # json or text
```

### Configuration by Environment

**Local (Development)**

```dotenv
APP_ENV=local
DATABASE_URL=postgresql+psycopg2://postgres:password@localhost:5432/orchestrator_dev
AZURE_API_KEY=test_key_or_real_sandbox
LOG_LEVEL=DEBUG
```

**Staging**

```dotenv
APP_ENV=staging
DATABASE_URL=postgresql+psycopg2://user:pass@staging-db:5432/orchestrator
AZURE_API_KEY=staging_key
A2A_SHARED_SECRET=staging_secret_123
LOG_LEVEL=INFO
```

**Production**

```dotenv
APP_ENV=production
DATABASE_URL=postgresql+asyncpg://user:pass@prod-db:5432/orchestrator
AZURE_API_KEY=prod_key_from_vault
A2A_SHARED_SECRET=prod_secret_from_vault
FILE_SIGNING_SECRET=prod_secret_from_vault
LOG_LEVEL=WARNING
ALLOWED_WS_ORIGINS=https://app.example.com,https://api.example.com
```

---

## 🚀 Run Locally

### Prerequisites

- **Python** 3.12+
- **PostgreSQL** 12+
- **uv** for package management
- **.env** file with configuration

### Quick Start (with Docker Postgres)

```bash
# 1. Create Python virtual environment and do project setup
uv sync

# 4. Create .env
cp .env.example .env
# Edit .env with your Azure OpenAI credentials

# 5. Apply migrations
alembic upgrade head

# 6. Run dev server with auto-reload
uvicorn main:app --reload --port 8000
```

### Access Points

| Endpoint                                  | Purpose                               |
| ----------------------------------------- | ------------------------------------- |
| `http://localhost:8080/docs`              | **Swagger UI** (interactive API docs) |
| `http://localhost:8080/redoc`             | ReDoc (alternative API docs)          |
| `ws://localhost:8080/ws/{session_id}`     | WebSocket endpoint                    |
| `GET http://localhost:8080/agents/active` | List active agents                    |
| `POST http://localhost:8080/run/`         | Sync agent execution                  |

### Health Check

```bash
# Orchestrator health
curl http://localhost:8080/health

# Agent health (sub-agent endpoint)
curl https://agent-host:port/health

# Agent card (agent capabilities)
curl https://agent-host:port/.well-known/agent-card.json
```

---

## 🔌 API Reference (Essential Endpoints)

### WebSocket: `/ws/{session_id}` (Streaming)

**Connect**

```
ws://localhost:8080/ws/my-session-123
```

**Send Message**

```json
{
  "prompt": "Classify and score this document",
  "content": "optional alternative to prompt",
  "files": [
    {
      "name": "report.pdf",
      "signed_url": "https://...&exp=...",
      "content_type": "application/pdf"
    }
  ]
}
```

**Receive Events (streaming)**

```json
{"type": "status", "stage": "planning", "message": "Selecting best agent..."}
{"type": "invocation_started", "agent": "classification_bot", "step": 1, "workflow_id": "abc-123"}
{"type": "tool_progress", "agent": "classification_bot", "detail": "extract_text"}
{"type": "artifact", "name": "summary.md", "signed_url": "https://...", "content_type": "text/markdown"}
{"type": "invocation_completed", "agent": "classification_bot", "step": 1, "status": "completed", "duration_sec": 12.5}
{"type": "workflow_completed", "workflow_id": "abc-123", "final_response": "Classification: Important..."}
{"type": "error", "scope": "agent", "message": "timeout", "agent": "scoring_agent", "recoverable": false}
```

### REST: `/run/` (Sync Execution)

**POST /run/**

```bash
curl -X POST http://localhost:8080/run/ \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "Analyze this CSV file",
    "session_id": "default-session"
  }'
```

**Response**

```json
{
  "response": "Analysis complete: 1000 records processed..."
}
```

### Agent Registry: `/agents/`

**Register Agent**

```bash
POST /agents/add
{
  "name": "classification_bot",
  "host": "https://agent.example.com",
  "port": 443,
  "is_active": true
}
```

**List Active Agents**

```bash
GET /agents/active
```

Response:

```json
{
  "agents": [
    {
      "name": "classification_bot",
      "is_active": true,
      "is_healthy": true,
      "last_health_check": "2024-04-13T10:30:00Z",
      "agent_card": {
        "name": "classification_bot",
        "description": "Classifies documents...",
        "skills": ["classify", "extract_features"],
        "input_modes": ["text", "file"],
        "output_modes": ["json", "text"]
      }
    }
  ]
}
```

**Remove Agent**

```bash
DELETE /agents/{agent_name}
```

### File Management

**Upload File** (multipart/form-data)

```bash
POST /upload/
Content-Type: multipart/form-data

--boundary
Content-Disposition: form-data; name="file"; filename="report.pdf"
Content-Type: application/pdf
<binary file data>
--boundary--
```

Response:

```json
{
  "signed_url": "https://localhost:8000/artifacts/report.pdf?exp=1234567890&sig=abc123",
  "file_id": "doc-uuid-123",
  "expires_in_seconds": 600
}
```

---

## 🧩 Implementation Notes & Design Patterns

### Core Principles

- **Nexus forwards artifacts as opaque references** (never reads file content directly)
- **Step order is per-workflow** and resets on each new workflow UUID
- **Health monitor updates `is_healthy`** in background; only healthy agents injected into Nexus
- **Conversation context preserved** across prompts via ADK session
- **File artifacts are immutable** (signed URLs are one-time references)

### Design Patterns Used

1. **Factory Pattern**: `runner_factory.py` → creates `Runner` instances
2. **Service Pattern**: Separate `*_service.py` for business logic isolation
3. **Repository Pattern**: CRUD ops normalized in `agent_registry/database.py`
4. **Event-Driven**: WebSocket events stream progress asynchronously
5. **Dependency Injection**: Services receive `db_session_factory`, `session_service`

### Error Handling

- **Workflow fails gracefully**: Update `OrchestrationSession` status to `failed`
- **Sub-agent timeout**: Create `AgentInvocation` with status `failed`, emit error event
- **Invalid agent**: Skip from Nexus sub_agents list during health check
- **File expiration**: Signed URL validation + refresh capability

---

## 🔐 Security

### HMAC‑Signed URLs

- **Generation**: `HMAC-SHA256(file_path + exp_timestamp, FILE_SIGNING_SECRET)`
- **Validation**: Verify signature + check expiration before serving
- **Artifact access control**: Only requestor with valid signature can download

### A2A Communication

- **Signing**: JSON-RPC calls include `Authorization: Bearer <token>` or HMAC header
- **Verification**: Sub-agents verify sender token/signature before accepting
- **Encryption**: Use HTTPS for all remote agent communication

### Database & Credentials

- **Least privilege**: App-specific DB user (no superuser)
- **Connection pooling**: Use pgbouncer or AsyncPG for connection reuse
- **Secrets management**: `.env` (dev only) → Vault/KeyVault (prod)
- **Audit timestamps**: All UTC, timezone-sensitive

### WebSocket & CORS

- **Origin validation**: Strict CORS policy via `ALLOWED_WS_ORIGINS`
- **No credentials in logs**: Sanitize API keys, tokens, file paths
- **Rate limiting**: Implement at reverse proxy (Nginx, WAF)

---

## 📚 Quick Reference

### Key Concepts

| Term                     | Meaning                                            |
| ------------------------ | -------------------------------------------------- |
| **Nexus**               | Root agent (LLM-powered orchestrator)              |
| **OrchestrationSession** | Workflow UUID (execution scope)                    |
| **AgentInvocation**      | Sub-agent invocation (step in workflow)            |
| **A2A**                  | Agent-to-Agent protocol (JSON-RPC over HTTP/HTTPS) |
| **Signed URL**           | HMAC-validated artifact reference (time-limited)   |
| **health_monitor**       | Background loop checking agent `/health`           |
| **step_order**           | Sequential counter per workflow (1, 2, 3...)       |

### Common Commands

````bash
# Run tests
pytest tests/ -v

# Format code
black .
isort .

# Type checking
mypy services/ agents/

# Database
alembic current              # Current schema version
alembic history              # Migration history
alembic upgrade head         # Apply pending migrations
alembic downgrade -1         # Rollback last migration

# Development server
uvicorn main:app --reload --port 8000



## 🤝 Contributing

### Development Workflow

1. **Clone & Setup**

   ```bash
   git clone https://github.com/git-repos/orchestrator
   cd orchestrator
   uv sync
   cp .env.example .env

````

2. **Create Feature Branch**

   ```bash
   git checkout -b feature/your-feature
   ```

3. **Make Changes**
   - Update code
   - Add tests
   - If schema changes: `alembic revision --autogenerate -m "describe change"`

4. **Test Locally**

   ```bash
   pytest tests/ -v --cov=services,agents,routers,database
   ```

5. **Commit & Push**

   ```bash
   git add .
   git commit -m "feat: descriptive message"
   git push origin feature/your-feature
   ```

6. **Open PR** on GitHub with:
   - Clear description
   - Screenshots/logs if UI/API changes
   - Test results
   - Migration steps (if applicable)

### Code Standards

- **Style**: Black (line length 100)
- **Imports**: isort
- **Types**: MyPy (strict mode)
- **Docstrings**: Google-style
- **Tests**: pytest with fixtures

---

---

## 📖 Resources & References

### Documentation

- [FastAPI Docs](https://fastapi.tiangolo.com/) - Web framework
- [Google ADK Docs](https://google-cloud.readme.io/) - Agent orchestration framework
- [SQLAlchemy Async](https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html) - ORM
- [Alembic](https://alembic.sqlalchemy.org/) - Database migrations
- [WebSockets API](https://developer.mozilla.org/en-US/docs/Web/API/WebSocket) - Real-time transport
- [PostgreSQL Docs](https://www.postgresql.org/docs/) - Database
- [LiteLLM](https://litellm.vercel.app/) - LLM abstraction layer

### Related Projects

- **a2a-sdk** (Agent-to-Agent protocol SDK)
- **google-adk** (Google Agent Development Kit)
- **litellm** (LLM provider abstraction)

### External References

- [JSON-RPC 2.0 Spec](https://www.jsonrpc.org/specification) - A2A protocol base
- [Agent Card Standard](https://github.com/google-research/agent-card-spec) - Discovery format
- [Well-Known URIs RFC](https://tools.ietf.org/html/rfc8615) - `.well-known/` convention

---

## 📄 License

MIT — see [LICENSE](LICENSE).

---

## 👤 Authors

- **Created**: 2026
- **Maintainer**: Aditya


---

## 💬 Support & Feedback

- **Issues**: GitHub Issues
- **Discussions**: GitHub Discussions
- **Documentation**: See this README + inline comments
- **Examples**: Check `tools/sample_testing.py` for integration examples

---

**Last Updated**: 2026-04-14  
**Current Version**: 0.1.0

---

# OUTPUT on test



## 🚀 Roadmap

Current implementation includes:

- [x] Multi-agent workflow planning
- [x] Planner module and dependency-aware execution
- [x] Durable plan approval and A2A input-required resume
- [x] OpenTelemetry tracing and AgentEvent persistence

Remaining improvements:

- [ ] Parallel execution where dependencies allow it
- [ ] Retry and recovery policies
- [ ] Dynamic workflow replanning
- [ ] Capability-based scheduling
- [ ] Trace/timeline UI and production authentication
