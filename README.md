
# 🧠 Agentic AI Orchestrator

> **Capability‑driven, dynamic, multi‑agent orchestration with real‑time streaming, A2A, and workflow observability.**

[![Framework: FastAPI](https://img.shields.io/badge/Framework-FastAPI-009688.svg)](https://fastapi.tiangolo.com/)
[![Transport: WebSocket](https://img.shields.io/badge/Transport-WebSocket-1f6feb.svg)](https://developer.mozilla.org/docs/Web/API/WebSockets_API)
[![DB: PostgreSQL](https://img.shields.io/badge/DB-PostgreSQL-336791.svg)](https://www.postgresql.org/)
[![LLM: Azure OpenAI](https://img.shields.io/badge/LLM-Azure%20OpenAI-0078D4.svg)](https://learn.microsoft.com/azure/ai-services/openai/)
[![Protocol: A2A](https://img.shields.io/badge/Protocol-A2A-6f42c1.svg)](#)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

---

## 📌 Overview

This project implements a **Generic Multi‑Agent Orchestrator** that dynamically connects to remote agents, routes user requests, and tracks execution with robust observability.

**Tech Stack**
- **FastAPI** (orchestration API & WebSocket)
- **WebSocket streaming** (status, tool execution, file events, errors)
- **Google ADK (Agent Development Kit)** (agent orchestration patterns)
- **A2A protocol** (Agent‑to‑Agent communication via JSON‑RPC, `/.well-known/agent-card.json`)
- **PostgreSQL** (agent registry & execution tracking)
- **Azure OpenAI via LiteLLM** (LLM backbone in the root agent “Cortex”)

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

## 🧱 Execution Tracking (Minimal Invocation Layer)

**OrchestrationSession (Workflow)**
- New workflow UUID per user prompt
- Table: `orchestration_sessions`
- Fields:
  - `id, session_id (workflow UUID), user_id, status (active/completed/failed), created_at, completed_at`
- Guarantees:
  - Execution isolation per prompt
  - Clean debugging
  - Future replay

**AgentInvocation (Execution Step)**
- New row per sub‑agent call
- Table: `agent_invocations`
- Fields:
  - `orchestration_session_id, agent_name, step_order, status`
  - `input_payload, output_payload`
  - `started_at, completed_at`
- **Step order** resets per workflow:
  - Workflow A: 1→classification_bot, 2→scoring_agent
  - Workflow B: 1→classification_bot

---

## 🧠 Session Separation Model

| Layer                  | Purpose                     |
|------------------------|-----------------------------|
| WebSocket `session_id` | Transport connection        |
| ADK `session_id`       | Conversation memory         |
| Workflow UUID          | Execution tracking per call |

Benefits:
- Conversation context preserved across prompts
- Workflow tracking isolated **per request**
- No cross‑workflow mixing

---

## 🛢️ Database Schema (Summary)

**Active Tables**
- `agents`
- `orchestration_sessions`
- `agent_invocations`

**Future‑Ready Tables**
- `agent_dependencies` (DAG execution)
- `agent_events` (streaming trace logging)
- `artifacts` (generated file persistence)

**Timestamps**: use `TIMESTAMP WITH TIME ZONE` (UTC‑safe).

> Tip: Manage schema via **Alembic** migrations.

---

## 🔁 Current Execution Flow

1. User sends prompt via **WebSocket**  
2. New **workflow UUID** created  
3. Root agent loads **active & healthy** agents dynamically  
4. **Cortex** selects agent(s)  
5. Create **AgentInvocation** row (`status=working`)  
6. Agent completes → update row (`status=completed`)  
7. Mark workflow **completed**

---

## 📊 Observability

Query execution status quickly:

```sql
SELECT 
  os.session_id AS workflow_id,
  ai.agent_name,
  ai.step_order,
  ai.status
FROM orchestration_sessions os
JOIN agent_invocations ai
  ON os.id = ai.orchestration_session_id
ORDER BY ai.started_at DESC;
```

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

- Deterministic pipelines
- Dependency graph tracking (DAG)
- Capability‑driven dynamic orchestration
- Artifact persistence
- Event‑level streaming trace logging
- Retry mechanisms
- Workflow replay

---

## ⚙️ Configuration

Create a `.env` file:

```dotenv
# Server
APP_ENV=local
APP_PORT=8080
ALLOWED_WS_ORIGINS=http://localhost:3000

# DB
DATABASE_URL=postgresql+psycopg2://user:pass@localhost:5432/orchestrator

# LLM (Azure OpenAI via LiteLLM)
AZURE_OPENAI_API_KEY=your_key
AZURE_OPENAI_ENDPOINT=https://<resource>.openai.azure.com/
AZURE_OPENAI_DEPLOYMENT_NAME=gpt-4o
LITELLM_MODEL=gpt-4o
LITELLM_API_BASE=${AZURE_OPENAI_ENDPOINT}
LITELLM_API_KEY=${AZURE_OPENAI_API_KEY}

# A2A
A2A_SHARED_SECRET=change_me
A2A_HEALTH_INTERVAL_SECONDS=30

# Files
FILE_SIGNING_SECRET=change_me
SIGNED_URL_TTL_SECONDS=600
MAX_UPLOAD_MB=50

# Telemetry
LOG_LEVEL=INFO
```

---

## 🚀 Run Locally

### Prerequisites
- Python 3.10+
- PostgreSQL 13+
- (Optional) Docker/Docker Compose
- `make` (optional)

### Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -r requirements.txt

# Apply DB migrations
alembic upgrade head

# Run dev server
uvicorn app.main:app --reload --port ${APP_PORT:-8080}
```

### Health Check

- Orchestrator: `GET /health`
- Agent(s): each agent exposes `GET /health` and `/.well-known/agent-card.json`

---

## 🔌 API Reference (Essentials)

### WebSocket

- **URL**: `GET /ws?session_id=<uuid>`
- **Inbound message (example)**:
```json
{
  "type": "user_prompt",
  "session_id": "2cde9b9e-...-a41d",
  "message": "Classify this document and score it.",
  "files": [
    { "name": "report.pdf", "signed_url": "https://...&exp=...", "content_type": "application/pdf" }
  ]
}
```

- **Outbound stream events**
```json
{ "type": "status", "stage": "planning", "message": "Selecting best agent..." }
{ "type": "invocation_started", "agent": "classification_bot", "step": 1, "workflow_id": "..." }
{ "type": "tool_progress", "agent": "classification_bot", "detail": "extract_text" }
{ "type": "artifact", "name": "summary.md", "signed_url": "https://..." }
{ "type": "invocation_completed", "agent": "classification_bot", "step": 1, "status": "completed" }
{ "type": "workflow_completed", "workflow_id": "..." }
{ "type": "error", "scope": "agent", "message": "timeout", "agent": "scoring_agent" }
```

### Agent Registry

- `POST /agents/add`
  ```json
  {
    "name": "classification_bot",
    "host": "https://agent.example.com",
    "port": 443,
    "auth_token": "bearer_or_hmac",
    "is_active": true
  }
  ```
- `GET /agents/active`
- `DELETE /agents/{name}` (optional)

---

## 🔐 Security

- **HMAC‑signed URLs** with `exp` for artifact access
- **A2A** calls signed with shared secret or bearer token
- Strict **CORS/WS origins**
- **Principle of least privilege** for DB and storage credentials
- All timestamps stored as **UTC** (`TIMESTAMP WITH TIME ZONE`)

---

## 🧩 Implementation Notes

- **Cortex** forwards artifacts **as opaque references** (never reads file content)
- **Step order** is per‑workflow and resets on each new workflow UUID
- **Health monitor** updates `is_healthy`; only healthy agents are injected into Cortex decision context

---

## 🤝 Contributing

1. Fork and create a feature branch  
2. Add/adjust Alembic migration if schema changes  
3. Add unit/integration tests  
4. Open a PR with a clear description and screenshots/logs where helpful

---

## 📄 License

MIT — see LICENSE.

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

node "FastAPI Orchestrator" as API #E8F5E9 {
  component "WebSocket Gateway\n(session_id: transport)" as WS
  component "Root Agent: Cortex\n(LLM via LiteLLM)" as CORTEX
  component "RemoteServerManager\n(A2A discovery + routing)" as RSM
  component "File Service\n(Signed URLs, HMAC, exp)" as FILES
  collections "Health Monitor\n(async loop)" as HM
}

database "PostgreSQL" as PG #F8F1FF
folder "Remote Agents\n(A2A / JSON-RPC)" as AGENTS #FFF8E1 {
  component "classification_bot" as AG1
  component "scoring_agent" as AG2
  component "… more agents" as AGN
}

FE -down-> WS : WebSocket\n(messages, files)
WS -down-> CORTEX : user prompts\nstatus streaming
CORTEX -right-> RSM : load active+healthy agents
RSM -down-> AG1 : JSON-RPC\nw/ streaming
RSM -down-> AG2
RSM -down-> AGN

CORTEX -down-> PG : write OrchestrationSession\n& AgentInvocations
RSM -down-> PG : read Agents (active, healthy)\nupdate health status

FILES -down-> FE : signed URLs\n(file artifacts)
FE -up-> FILES : file uploads (store/ref only)
CORTEX -right-> AGENTS : forward file_data (opaque refs)

HM -down-> AGENTS : GET /health
HM -down-> PG : update is_healthy

note right of PG
Tables:
- agents
- orchestration_sessions
- agent_invocations
(UTC timestamps)
end note

note bottom of CORTEX
Responsibilities:
- Intent understanding
- Agent selection
- Multi-step orchestration
- Status streaming
- Artifact forwarding (no read)
end note

@enduml
```
