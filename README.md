
# 🧠 Agentic AI Orchestrator

> **Capability‑driven, dynamic, multi‑agent orchestration with real‑time streaming, A2A, and workflow observability.**

[![Framework: FastAPI](https://img.shields.io/badge/Framework-FastAPI-009688.svg)](https://fastapi.tiangolo.com/)
[![Transport: WebSocket](https://img.shields.io/badge/Transport-WebSocket-1f6feb.svg)](https://developer.mozilla.org/docs/Web/API/WebSockets_API)
[![DB: PostgreSQL](https://img.shields.io/badge/DB-PostgreSQL-336791.svg)](https://www.postgresql.org/)
[![LLM: Azure OpenAI](https://img.shields.io/badge/LLM-Azure%20OpenAI-0078D4.svg)](https://learn.microsoft.com/azure/ai-services/openai/)
[![Protocol: A2A](https://img.shields.io/badge/Protocol-A2A-6f42c1.svg)](#)
[![Agent Framework: Google ADK](https://img.shields.io/badge/Framework-Google%20ADK-EA4335.svg)](#)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

---

## 📌 Overview

This project implements a **Generic Multi‑Agent Orchestrator** that dynamically connects to remote agents, routes user requests, and tracks execution with robust observability.

**Tech Stack**
- **FastAPI** (orchestration API & WebSocket streaming)
- **WebSocket** (real‑time status, tool execution, file events, errors)
- **Google ADK (Agent Development Kit)** (agent orchestration framework & patterns)
- **A2A protocol** (Agent‑to‑Agent communication via JSON‑RPC, `/.well-known/agent-card.json`)
- **PostgreSQL** (agent registry, workflow tracking, invocation history)
- **Azure OpenAI via LiteLLM** (LLM backbone in root agent "Cortex")
- **SQLAlchemy + Alembic** (ORM & database migrations)

---

## 🏗️ High‑Level Architecture

```
Frontend (WebSocket)
        ↓
FastAPI Orchestrator
        ↓
Root Agent (Cortex)
        ↓
Remote Agents (via A2A protocol)
        ↓
PostgreSQL (Tracking & Registry)
```

> See [`architecture.puml`](architecture.puml) for the PlantUML diagram.

---

## ⚙️ Core Components

### 1) WebSocket Layer
- Real‑time streaming of:
  - Agent status updates
  - Tool execution states
  - File generation events
  - Error states
- Maintains **stateful session** per user (`session_id`)
- Supports **file artifact forwarding**
- Compatible with **A2A** remote agents

### 2) Root Agent (Cortex)
- Central orchestration brain:
  - Understand user intent
  - Select appropriate sub‑agents
  - Forward artifacts **without reading them**
  - Handle multi‑step execution
  - Provide structured status updates
- Uses **Azure OpenAI via LiteLLM**
- Uses **RemoteServerManager** for dynamic A2A connections

### 3) Dynamic Agent Registry
- Agents **not hardcoded**
- Endpoints:
  - `POST /agents/add`
  - `GET /agents/active`
  - `DELETE /agents/{name}` (optional)
- **AgentRegistry** table fields:
  - `name, host, port, auth_token, is_active, is_healthy, created_at, last_health_check`
- **Health Monitor**:
  - Background async loop calling `/health`
  - Writes `is_healthy` to DB
- Cortex only receives **active + healthy** agents.

### 4) A2A Protocol Integration
- Each remote agent exposes: `/.well-known/agent-card.json`
  - `name, description, skills, input_modes, output_modes, tags, streaming`
- Orchestrator:
  - Validates agent existence
  - Connects dynamically
  - Supports **streaming JSON‑RPC transport**

### 5) File Handling System
- Multi‑file upload
- **Signed URL** generation with **exp + HMAC**
- Secure access control
- **Automatic forwarding** of file artifacts to agents
- Flow: `Upload → Signed URL → Stored in session → Forwarded as file_data`

---

## 📂 Project Structure & File Mappings

### Entry Point
| File | Responsibility |
|------|---|
| **main_v2.py** | FastAPI app initialization, middleware setup (CORS), router registration, lifespan management (startup/shutdown), WebSocket endpoint, service initialization |

### Core Configuration
| File | Responsibility |
|------|---|
| **core/config.py** | Centralized app configuration (`APP_NAME`, `DEFAULT_USER`), environment variables |
| **core/runner_factory.py** | Factory function to instantiate `Runner` with root agent |

### Root Agent & Agent Framework
| File | Responsibility |
|------|---|
| **agents/agent.py** | **Cortex** root agent definition, Azure OpenAI/LiteLLM integration, agent instructions, sub-agent management |
| **agents/remote_agent_connections.py** | Remote agent connection utilities for A2A protocol communication |

### API Routers
| File | Responsibility |
|------|---|
| **routers/agent_registry.py** | Agent registration endpoints (`POST /agents/add`, `GET /agents/active`, etc.) |
| **routers/run_agent_router.py** | REST endpoint for synchronous agent execution (`POST /run/`) |
| **routers/file_router.py** | File management endpoints (upload, download, artifact serving) |
| **routers/upload_router.py** | Multi-file upload handling with session integration |

### Real-Time Communication (WebSocket)
| File | Responsibility |
|------|---|
| **websocket/websocket_handler.py** | Main WebSocket connection handler, message routing, session binding |
| **websocket/ws_emitter.py** | Emits WebSocket events (status, errors, tool progress, artifacts) |
| **websocket/event_processor.py** | Processes incoming WebSocket events, delegates to services |

### Business Logic Services
| File | Responsibility |
|------|---|
| **services/workflow_service.py** | **Workflow Lifecycle**: creates `OrchestrationSession` per user prompt, tracks status (active/completed/failed), computes workflow completion |
| **services/agent_execution_service.py** | **Invocation Tracking**: creates `AgentInvocation` rows per sub-agent call, manages step order, tracks input/output payloads, started/completed timestamps |
| **services/agent_loader.py** | Loads active and healthy agents from registry, injects into Cortex |
| **services/agent_sync_service.py** | Background sync loop for agent status/health updates |
| **services/artifact_service.py** | Manages generated artifacts (files) from agent execution |
| **services/file_service.py** | **Signed URL generation**, HMAC validation, TTL management, artifact access control |
| **services/invocation_context.py** | Invocation context holder (invocation_id, agent_name, agent_session_id) |

### Session Management
| File | Responsibility |
|------|---|
| **session/session_manager.py** | **Dual-mode session mgmt**: ADK persistent sessions (conversation memory) + in-memory active session mirror for WebSocket workflows |

### Database & ORM
| File | Responsibility |
|------|---|
| **database/engine.py** | SQLAlchemy async engine setup |
| **database/session.py** | Async session factory (`AsyncSessionLocal`) |
| **database/models.py** | **ORM Models**: `AgentRegistry`, `OrchestrationSession`, `AgentInvocation` with relationships & indexes |

### Agent Registry (Management)
| File | Responsibility |
|------|---|
| **agent_registry/health_monitor.py** | **Health Check Loop**: async task that periodically calls `GET /health` on each registered agent, updates `is_healthy` in DB |

### Infrastructure & Utilities
| File | Responsibility |
|------|---|
| **infrastructure/a2a_factory.py** | A2A (Agent-to-Agent) protocol factory for remote agent communication |
| **utils/agent_card_extractor.py** | Extracts agent capabilities from agent cards |

### Database Migrations
| File | Responsibility |
|------|---|
| **alembic.ini** | Alembic configuration file |
| **migrations/env.py** | Alembic migration environment setup |
| **migrations/script.py.mako** | Alembic migration template |
| **migrations/versions/** | Versioned migration files (one per schema change) |

### Configuration & Dependencies
| File | Responsibility |
|------|---|
| **.env** | Environment variables (see [Configuration](#-configuration)) |
| **pyproject.toml** | Project metadata, dependencies (FastAPI, SQLAlchemy, Google ADK, LiteLLM, etc.) |
| **main.py** | Alternative entry point (legacy) |

### Testing & Development Tools
| File | Responsibility |
|------|---|
| **tools/** | Development utilities and testing scripts (not part of production runtime) |
| **cli_testing.py** | CLI testing utilities |
| **sample_testing.py** | Sample testing scripts |

### Legacy/Unused Files
| File | Responsibility |
|------|---|
| **agents/remote_agent_connections_v2.py** | Testing version (not used in production) |
| **utils/file_manager.py** | File management utilities (not currently used) |
| **websocket/a2a_utils.py** | A2A protocol utilities (not currently used) |
| **database/create_tables.py** | Alternative table creation script (migrations preferred) |
| **agent_registry/** (other files) | Alternative agent registry implementation (not used in main_v2.py) |

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
   → creates AgentInvocation row (Cortex, step_order=1, status=working)
   ↓
5. Runner.run_async(new_message=Content(text=prompt))
   → calls Cortex agent with message
   ↓
6. Cortex Decision:
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
   - Types: status, invocation_started, tool_progress, artifact, invocation_completed
   ↓
9. WorkflowService.complete_workflow() 
   → marks OrchestrationSession as completed
   ↓
10. Session Preserved for next prompt (ADK session_id keeps context)
```

---

## 🧱 Execution Tracking (Three-Layer Model)

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
  - Workflow A: `step_order: 1→Cortex, 2→classification_bot, 3→scoring_agent`
  - Workflow B: `step_order: 1→Cortex, 2→different_agent`

**AgentRegistry (Capability & Health)**
- Persistent agent metadata
- Table: `agents`
- Fields:
  - `id (PK), name (UNIQUE), host, port, is_active, is_healthy, agent_card (JSON), created_at, last_health_check`
- Maintained by:
  - Health Monitor background loop (checks `/health` every N seconds)
  - Agent Registry API (add/remove agents)
  - Only **active + healthy** agents injected into Cortex decision context

---

## 🧠 Session Separation Model

| Layer                      | Purpose                                      | Managed By |
|----------------------------|----------------------------------------------|---|
| WebSocket `session_id`     | Transport connection (per client session)    | SessionManager (in-memory) |
| ADK `session_id`           | Conversation memory (ADK persistent session) | DatabaseSessionService (Google ADK) |
| Workflow UUID              | Execution tracking per request               | OrchestrationSession (DB) |
| ADK `agent_session_id`     | Per-agent message history                    | Runner (ADK framework) |

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

### Future‑Ready Tables (Planned)
- `agent_dependencies` (DAG execution ordering)
- `agent_events` (streaming trace logging)
- `artifacts` (generated file persistence)
- `workflow_events` (workflow-level event log)

**Timestamps**: All use `TIMESTAMP WITH TIME ZONE` (UTC‑safe).

> **Migration Management**: Use **Alembic** (`alembic upgrade head`, `alembic downgrade -1`)

---

## 🔁 Complete Execution Flow (Step-by-Step)

### User Request → Agent Response

```
1. Frontend sends WebSocket message:
   {
     "prompt": "Classify and score this document",
     "files": [{ "name": "doc.pdf", "signed_url": "..." }]
   }

2. WebSocketHandler.handle() receives message
   → EventProcessor processes the message
   → Delegates to WorkflowService

3. WorkflowService.start_workflow(user_id)
   → Creates: OrchestrationSession {
       session_id=UUID,
       user_id=user_id,
       status='active',
       created_at=NOW()
     }
   → Returns workflow object

4. AgentExecutionService.start_root_invocation(workflow.id, session_id, prompt)
   → Creates: AgentInvocation {
       orchestration_session_id=workflow.id,
       agent_name='Cortex',
       step_order=1,
       status='working',
       input_payload={'prompt': prompt},
       started_at=NOW()
     }

5. Runner.run_async(user_id, session_id, Content(text=prompt))
   → SessionManager ensures ADK session exists
   → AgentLoader.load_active_agents() queries DB for healthy agents
   → Injects agents into Cortex.sub_agents list
   → Cortex LLM processes intent and selects sub-agents

6. Cortex Decision & Routing:
   - Analyzes prompt: "Route to classification_bot, then scoring_agent"
   - For each selected sub-agent:
     → AgentExecutionService.start_invocation() creates AgentInvocation
     → Remote agent connection (A2A protocol) via infrastructure/a2a_factory.py
     → JSON-RPC call to agent's HTTP endpoint
     → Streaming response handling

7. Sub-agent Execution:
   ✓ AgentInvocation created: {
       agent_name='classification_bot',
       step_order=2,
       status='working'
     }
   ✓ A2A call: POST http://agent-host:port/ with JSON-RPC payload
   ✓ Agent processes request and streams back results
   ✓ AgentInvocation updated: { status='completed', output_payload=result }

8. Real-time Event Streaming:
   → WSEmitter sends WebSocket events to frontend:
     { "type": "invocation_started", "agent": "classification_bot", "step": 2 }
     { "type": "tool_progress", "detail": "extract_text" }
     { "type": "artifact", "signed_url": "https://..." }
     { "type": "invocation_completed", "status": "completed" }

9. Workflow Completion:
   → WorkflowService.complete_workflow(workflow_id)
   → Updates: OrchestrationSession {
       status='completed',
       completed_at=NOW()
     }

10. Final Response:
    → Frontend receives: {
        "type": "workflow_completed",
        "workflow_id": "...",
        "final_response": "Classification complete..."
      }

11. Session Persistence:
    → ADK session maintains conversation context for next prompt
    → WebSocket session_id tracks transport connection
    → Workflow UUID provides execution isolation
```

---

## 📈 Execution Flow Sequence Diagram

```plantuml
@startuml ExecutionFlowSequence
!pragma teoz true

title Agentic Orchestrator — Execution Flow Sequence

actor "Frontend\n(Web Client)" as FE
participant "WebSocketHandler" as WS
participant "EventProcessor" as EP
participant "WorkflowService" as WF
participant "AgentExecutionService" as AES
participant "SessionManager" as SM
participant "AgentLoader" as AL
participant "Cortex Agent" as CORTEX
participant "A2A Factory" as A2A
participant "Remote Agent" as AGENT
participant "WSEmitter" as EMITTER
database "PostgreSQL" as DB

== Initial Setup ==
FE -> WS: WebSocket connect (/ws/{session_id})
WS -> SM: ensure_session(user_id, session_id)
SM -> DB: create/get ADK session

== User Request Processing ==
FE -> WS: send message {"prompt": "...", "files": [...]}
WS -> EP: process_event(message)
EP -> WF: start_workflow(user_id)
WF -> DB: INSERT orchestration_sessions
WF --> EP: return workflow

EP -> AES: start_root_invocation(workflow, session_id, prompt)
AES -> DB: INSERT agent_invocations (Cortex, step=1)
AES --> EP: return invocation

EP -> SM: get_session(user_id, session_id)
SM -> DB: get ADK session
SM --> EP: return session

== Agent Orchestration ==
EP -> SM: create_runner(session_service)
SM --> EP: return Runner

EP -> AL: load_active_agents()
AL -> DB: SELECT agents WHERE is_active=true AND is_healthy=true
DB --> AL: return healthy agents
AL --> EP: return agent list

EP -> CORTEX: run_async(user_msg)
CORTEX -> CORTEX: LLM processes intent
CORTEX -> A2A: get_client_for_agent(agent_name)
A2A -> AGENT: A2A JSON-RPC call
AGENT -> A2A: streaming response

== Sub-agent Execution ==
CORTEX -> AES: start_invocation(workflow, agent_name, step=2)
AES -> DB: INSERT agent_invocations (sub-agent)
AES --> CORTEX: return invocation

CORTEX -> A2A: call_remote_agent(prompt, files)
A2A -> AGENT: HTTP POST / with JSON-RPC
AGENT -> A2A: process & respond
A2A --> CORTEX: streaming results

== Result Processing ==
CORTEX -> AES: update_invocation_status(completed, output)
AES -> DB: UPDATE agent_invocations SET status='completed'

CORTEX -> EMITTER: emit_events(invocation_completed, artifacts)
EMITTER -> FE: WebSocket events

== Workflow Completion ==
CORTEX -> WF: complete_workflow(workflow_id)
WF -> DB: UPDATE orchestration_sessions SET status='completed'
WF --> CORTEX: workflow done

EMITTER -> FE: workflow_completed event

== Session Preservation ==
note over SM, DB
ADK session persists conversation context
for next user prompt
end note

@enduml
```

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

| Event Type | Payload | Purpose |
|---|---|---|
| `status` | `{ stage, message }` | Status update (e.g., "Selecting best agent") |
| `invocation_started` | `{ agent, step, workflow_id }` | Sub-agent invocation started |
| `tool_progress` | `{ agent, detail }` | Tool execution progress (e.g., "extract_text") |
| `artifact` | `{ name, signed_url }` | Artifact generated (file) |
| `invocation_completed` | `{ agent, step, status }` | Sub-agent completed |
| `workflow_completed` | `{ workflow_id, final_response }` | Entire workflow done |
| `error` | `{ scope, message, agent? }` | Error occurred |

---

## ✅ What’s Done

- [x] Dynamic agent registration  
- [x] Health monitoring  
- [x] WebSocket streaming  
- [x] A2A protocol integration  
- [x] File artifact forwarding  
- [x] Signed URL security  
- [x] Workflow tracking (minimal invocation)  
- [x] Step order tracking  
- [x] Failure capture  
- [x] Timezone‑safe DB schema  

---

## 🛠️ Roadmap

- Deterministic pipelines (DAG-based execution)
- Dependency graph tracking & validation
- Capability‑driven dynamic orchestration (matching skills to tasks)
- Artifact persistence (long-term storage of generated files)
- Event‑level streaming trace logging (detailed audit trail)
- Retry mechanisms with exponential backoff
- Workflow replay capability (rerun from saved state)
- Cost tracking (per-agent, per-workflow)
- Agent timeout handling & graceful degradation
- Parallel agent execution (spawn multiple agents concurrently)

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
- **No direct file reads** by Cortex (opaque artifact forwarding)
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
- **PostgreSQL** 13+ (Docker recommended)
- **pip/poetry** for package management
- **.env** file with configuration

### Quick Start (with Docker Postgres)

```bash
# 1. Create Python virtual environment
python -m venv .venv
source .venv/bin/activate        # Linux/Mac
# or: .venv\Scripts\activate.ps1  # Windows PowerShell

# 2. Install dependencies
pip install -U pip
pip install -e .                 # Install from pyproject.toml

# 3. Start PostgreSQL (Docker)
docker run -d --name pg_orchestrator \
  -e POSTGRES_PASSWORD=password \
  -e POSTGRES_DB=orchestrator \
  -p 5432:5432 \
  postgres:15

# 4. Create .env
cp .env.example .env
# Edit .env with your Azure OpenAI credentials

# 5. Apply migrations
alembic upgrade head

# 6. Run dev server with auto-reload
uvicorn main_v2:app --reload --port 8080
```

### Access Points

| Endpoint | Purpose |
|----------|---------|
| `http://localhost:8080/docs` | **Swagger UI** (interactive API docs) |
| `http://localhost:8080/redoc` | ReDoc (alternative API docs) |
| `ws://localhost:8080/ws/{session_id}` | WebSocket endpoint |
| `GET http://localhost:8080/agents/active` | List active agents |
| `POST http://localhost:8080/run/` | Sync agent execution |

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
    { "name": "report.pdf", "signed_url": "https://...&exp=...", "content_type": "application/pdf" }
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
- **Cortex forwards artifacts as opaque references** (never reads file content directly)
- **Step order is per-workflow** and resets on each new workflow UUID
- **Health monitor updates `is_healthy`** in background; only healthy agents injected into Cortex
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
- **Invalid agent**: Skip from Cortex sub_agents list during health check
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
| Term | Meaning |
|------|---------|
| **Cortex** | Root agent (LLM-powered orchestrator) |
| **OrchestrationSession** | Workflow UUID (execution scope) |
| **AgentInvocation** | Sub-agent invocation (step in workflow) |
| **A2A** | Agent-to-Agent protocol (JSON-RPC over HTTP/HTTPS) |
| **Signed URL** | HMAC-validated artifact reference (time-limited) |
| **health_monitor** | Background loop checking agent `/health` |
| **step_order** | Sequential counter per workflow (1, 2, 3...) |

### Common Commands

```bash
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
uvicorn main_v2:app --reload --port 8080

# Production server (Gunicorn + Uvicorn workers)
gunicorn main_v2:app --worker-class uvicorn.workers.UvicornWorker --workers 4 --bind 0.0.0.0:8080
```

---

## 🚢 Deployment

### Docker

**Dockerfile**
```dockerfile
FROM python:3.12-slim

WORKDIR /app
COPY pyproject.toml .
RUN pip install -U pip && pip install .

COPY . .

EXPOSE 8080
CMD ["uvicorn", "main_v2:app", "--host", "0.0.0.0", "--port", "8080"]
```

**docker-compose.yaml**
```yaml
version: '3.9'
services:
  postgres:
    image: postgres:15
    environment:
      POSTGRES_DB: orchestrator
      POSTGRES_PASSWORD: password
    volumes:
      - pg_data:/var/lib/postgresql/data
    ports:
      - "5432:5432"

  orchestrator:
    build: .
    ports:
      - "8080:8080"
    environment:
      DATABASE_URL: postgresql+psycopg2://postgres:password@postgres:5432/orchestrator
      AZURE_API_KEY: ${AZURE_API_KEY}
      AZURE_API_BASE: ${AZURE_API_BASE}
      DEPLOYMENT_NAME: ${DEPLOYMENT_NAME}
    depends_on:
      - postgres
    volumes:
      - ./uploads:/app/uploads

volumes:
  pg_data:
```

Run:
```bash
docker-compose up -d
docker-compose exec orchestrator alembic upgrade head
```

### Kubernetes (Helm)

```bash
# Create namespace
kubectl create namespace orchestrator

# Deploy with Helm (create values.yaml)
helm install orchestrator ./helm/orchestrator -n orchestrator -f values.yaml

# Check deployment
kubectl get pods -n orchestrator
kubectl logs -n orchestrator deployment/orchestrator
```

### Production Checklist
- [ ] Database credentials in Vault/KeyVault
- [ ] Connection pooling configured (pgbouncer)
- [ ] HTTPS/TLS enabled for all endpoints
- [ ] Rate limiting at reverse proxy (Nginx)
- [ ] Monitoring enabled (metrics, logs, traces)
- [ ] Backups automated (daily DB snapshots)
- [ ] Load balancer configured (sticky sessions for WebSocket)
- [ ] Health checks exposed (`/health`)
- [ ] Error logging centralized (ELK, Datadog)

---

## 🤝 Contributing

### Development Workflow

1. **Clone & Setup**
   ```bash
   git clone https://github.com/adityait019/orchestrator
   cd orchestrator
   python -m venv .venv && source .venv/bin/activate
   pip install -e ".[dev]"
   ```

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
- **Maintainer**: adityait019
- **Contributors**: Welcome! See [CONTRIBUTING.md](CONTRIBUTING.md)

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

## 🧭 PlantUML Architecture Diagram

> Save or edit `architecture.puml`. To render locally, use the PlantUML jar or VS Code PlantUML extension. Online renderer example: https://www.plantuml.com/plantuml/

```plantuml
@startuml AgenticOrchestratorArchitecture
!pragma teoz true

title Agentic AI Orchestrator — High-Level Architecture

skinparam backgroundColor #FFFFFF
skinparam shadowing false
skinparam componentStyle rectangle
skinparam ArrowColor #444444
skinparam ArrowThickness 1
skinparam defaultTextAlignment left
skinparam wrapWidth 200
skinparam maxMessageSize 200

rectangle "Frontend\n(Web Client)" as FE #E6F7FF

node "FastAPI Orchestrator\n(main_v2.py)" as API #E8F5E9 {
  component "WebSocket Handler\n(websocket_handler.py)" as WS
  component "API Routers\n(agent_registry, run_agent, file, upload)" as ROUTERS
  component "Root Agent: Cortex\n(agents/agent.py)" as CORTEX
  component "Services Layer\n(workflow, execution, loader, etc.)" as SERVICES
  component "Session Manager\n(session_manager.py)" as SM
  component "File Service\n(file_service.py)" as FILES
}

database "PostgreSQL" as PG #F8F1FF {
  component "Agent Registry\n(agents table)" as AGENTS_DB
  component "Workflow Sessions\n(orchestration_sessions)" as WORKFLOW_DB
  component "Execution Tracking\n(agent_invocations)" as INVOCATION_DB
}

folder "Remote Agents\n(A2A / JSON-RPC)" as REMOTE_AGENTS #FFF8E1 {
  component "classification_bot" as AG1
  component "scoring_agent" as AG2
  component "… more agents" as AGN
}

collections "Infrastructure\n(a2a_factory.py, health_monitor.py)" as INFRA #FFF3E0

' Main user flow
FE -down-> WS : WebSocket\n(user prompts, files)
WS -down-> ROUTERS : route requests
ROUTERS -down-> SERVICES : business logic
SERVICES -down-> CORTEX : agent orchestration
CORTEX -right-> SM : session management

' Agent discovery and execution
CORTEX -down-> INFRA : load active agents\n(A2A factory)
INFRA -down-> AGENTS_DB : query healthy agents
INFRA -right-> REMOTE_AGENTS : A2A JSON-RPC calls
REMOTE_AGENTS -left-> INFRA : streaming responses

' Data persistence
SERVICES -down-> WORKFLOW_DB : create/update sessions
SERVICES -down-> INVOCATION_DB : track executions
SM -down-> PG : ADK session persistence

' File handling
FE -up-> ROUTERS : file uploads
ROUTERS -down-> FILES : generate signed URLs
FILES -down-> FE : signed URLs\n(file artifacts)
CORTEX -right-> REMOTE_AGENTS : forward file_data\n(opaque refs)

' Health monitoring
INFRA -down-> REMOTE_AGENTS : GET /health\n(agent discovery)
INFRA -down-> AGENTS_DB : update is_healthy

' Event streaming back to frontend
SERVICES -up-> WS : status events\n(invocation updates)
WS -up-> FE : WebSocket streaming\n(real-time updates)

note right of PG
Database Tables:
• agents (registry + health)
• orchestration_sessions (workflows)
• agent_invocations (steps)
All with UTC timestamps
end note

note bottom of CORTEX
Cortex Responsibilities:
• Intent understanding (LLM)
• Agent selection & routing
• Multi-step orchestration
• Status streaming
• Artifact forwarding (no read)
end note

note bottom of SERVICES
Service Layer:
• WorkflowService: session lifecycle
• AgentExecutionService: invocation tracking
• AgentLoader: dynamic agent loading
• FileService: signed URL generation
• ArtifactService: file management
end note

@enduml
```
