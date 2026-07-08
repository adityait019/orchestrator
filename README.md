# 🧠 Cortex

<div align="center">

### Capability-Driven Multi-Agent Orchestration Platform

*Discover • Route • Orchestrate • Stream • Observe*

[![Framework: FastAPI](https://img.shields.io/badge/Framework-FastAPI-009688.svg)](https://fastapi.tiangolo.com/)
[![Protocol: A2A](https://img.shields.io/badge/Protocol-A2A-6f42c1.svg)](#)
[![Framework: Google ADK](https://img.shields.io/badge/Framework-Google%20ADK-EA4335.svg)](#)
[![Transport: WebSocket](https://img.shields.io/badge/Transport-WebSocket-1f6feb.svg)](https://developer.mozilla.org/docs/Web/API/WebSockets_API)
[![Database: PostgreSQL](https://img.shields.io/badge/Database-PostgreSQL-336791.svg)](https://www.postgresql.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

</div>

---

# 📌 Overview

**Cortex** is a capability-driven orchestration platform that discovers, coordinates, and interacts with distributed AI agents using the **A2A (Agent-to-Agent) protocol**.

Unlike traditional applications that tightly couple business logic to specific agents, Cortex dynamically discovers remote Agent Cards, builds a capability registry, selects the most appropriate agent for a task, and orchestrates the complete execution lifecycle.

The platform acts as an orchestration layer between clients and distributed AI agents while providing workflow tracking, Human-in-the-Loop approvals, real-time streaming, and persistent execution metadata.

---

# 🚀 Why Cortex?

Modern AI systems often require multiple specialized agents.

Instead of hardcoding connections to every agent, Cortex introduces a capability-driven orchestration layer that:

- Dynamically discovers remote A2A-compatible agents
- Selects agents based on advertised capabilities
- Coordinates distributed execution
- Streams execution events in real time
- Tracks workflow state and execution history
- Keeps users in control through Human-in-the-Loop approvals

This allows new agents to be added without modifying the orchestrator itself.

---

# ✨ Features

## Agent Orchestration

- Dynamic A2A Agent Discovery
- Capability-Based Agent Routing
- Human-in-the-Loop (HITL) Approval
- Dynamic Agent Card Loading
- Multi-Agent Delegation
- Execution Coordination

## Workflow Management

- Stateful Workflow Tracking
- Session Management
- Agent Invocation Tracking
- Workflow Persistence
- Artifact Management

## Communication

- REST API
- WebSocket Streaming
- JSON-RPC Communication
- A2A Protocol Integration
- Real-time Status Updates

## Platform

- PostgreSQL Persistence
- Health Monitoring
- Dynamic Capability Registry
- Signed File URLs
- Secure Artifact Forwarding

---

# 🏗 Technology Stack

| Category | Technologies |
|-----------|--------------|
| Backend | FastAPI, Python, AsyncIO |
| AI Framework | Google ADK, LiteLLM, Azure OpenAI |
| Communication | A2A Protocol, JSON-RPC, REST, WebSocket |
| Database | PostgreSQL, SQLAlchemy, Alembic |
| Storage | Scoped File Storage, Signed URLs |
| Architecture | Capability-Driven Multi-Agent Orchestration |

---

# 🏛 System Architecture

<p align="center">

![System Architecture](docs\architecture-diagram\architecture_diagram.png)

</p>

---

# 🔄 Request Lifecycle

```text
                  User Request
                        │
                        ▼
                REST API / WebSocket
                        │
                        ▼
                 API Gateway (FastAPI)
                        │
                        ▼
               Cortex Orchestrator
                        │
          Load Active Agent Capabilities
                        │
                        ▼
              Capability-Based Routing
                        │
                        ▼
          Human-in-the-Loop (Optional)
                        │
                        ▼
             Agent Invocation Layer
                        │
                        ▼
                 Pure A2A Runtime
                        │
                        ▼
              Remote A2A Agents
                        │
                        ▼
          Streaming Events & Artifacts
                        │
                        ▼
           Persist Workflow State
                        │
                        ▼
                 Return Response
```

---

# 🧩 Core Components

| Component | Responsibility |
|------------|----------------|
| **API Gateway** | REST API, WebSocket endpoints, session routing |
| **Cortex Orchestrator** | Capability matching, delegation, workflow coordination |
| **Human-in-the-Loop** | User approval before agent delegation |
| **Dynamic Agent Registry** | Agent discovery, capability loading, health monitoring |
| **Agent Invocation Layer** | Session/context mapping and remote invocation |
| **Pure A2A Runtime** | JSON-RPC communication with remote agents |
| **Core Services** | Workflow, state, artifacts, files and chat history |
| **Persistence Layer** | Workflow state, sessions, registry and artifacts |

---

# 🎯 Design Principles

Cortex is designed around a few architectural principles:

- **Capability-driven routing** instead of hardcoded agent integrations.
- **Protocol abstraction** through an independent A2A runtime.
- **Separation of orchestration and communication layers.**
- **Human approval before delegated execution.**
- **Persistent workflow state for observability.**
- **Extensible architecture for future workflow planning and execution engines.**

---
# 🚀 Quick Start

## Prerequisites

- Python 3.12+
- PostgreSQL
- uv (recommended) or pip
- Azure OpenAI / LiteLLM configuration
- One or more A2A-compatible remote agents

---

## Installation

```bash
# Clone the repository
git clone https://github.com/adityait019/orchestrator.git

cd orchestrator

# Install dependencies
uv sync

# Copy environment variables
cp .env.example .env

# Configure your environment variables

# Run database migrations
alembic upgrade head

# Start Cortex
uvicorn main_v2:app --reload --port 8080
```

---

## Running

Swagger UI

```
http://localhost:8080/docs
```

ReDoc

```
http://localhost:8080/redoc
```

WebSocket

```
ws://localhost:8080/ws/{session_id}
```

---
## OUTPUT ON CLI
```bash
(orchestrator) PS C:\Users\adity\project\orchestrator>  uv run .\cli_testing.py
🔌 Server: connection_established
✅ Authentication successful
🤖 Connected to Orchestrator
🧠 Session ID: 1bc642ce-ce78-4d3a-bcf7-a4d239aa8483
Type /help for commands

You: Hi How are you?

Bot:

🤖 Cortex
Hello! I'm here and ready to assist you. How can I help you today?

----------------------------------------------------------------------
You: /list

📡 Active Agents:
- UICouplingAnalysisAgent (10.73.83.83:10101)
- LegacyApplicationDiscoveryAgent (10.73.83.83:10100)
You: Analyze the following legacy JSP/Java code and identify dependencies.IMPORTANT:Do the analysis first, but DO NOT finalize immediately.After analysis, ask me for confirmation before producing the final summary.When asking, include:- Extracted classes- Detected tables- APIs- Dependency relationshipsThen ask questions like:- "Do you want me to include RAG knowledge?"- "Should I refine the dependency analysis?"- "Proceed to final summary?"Code:public class UserService {    public List<User> getUsers() {        String sql = "SELECT * FROM USERS";        return fetchUsers(sql);    }}public class OrderService {    public void getOrders() {        String sql = "SELECT * FROM ORDERS";    }}fetch("http://order-api/getOrders")

Bot:

🤖 Cortex
I suggest delegating this task to LegacyApplicationDiscoveryAgent. Do you want me to proceed? (yes/no)

----------------------------------------------------------------------
You: yes

Bot:

🚀 Starting agent: LegacyApplicationDiscoveryAgent
🛠️ transfer_to_agent  (agent: LegacyApplicationDiscoveryAgent)
🔄 Switching → LegacyApplicationDiscoveryAgent
✅ transfer_to_agent
{
  "result": null
}
• LegacyApplicationDiscoveryAgent → submitted
🔄 LegacyApplicationDiscoveryAgent → working
🔄 LegacyApplicationDiscoveryAgent → working

🤖 LegacyApplicationDiscoveryAgent
org.enterprise.agent.wrb_02.v2 started processing
🔄 LegacyApplicationDiscoveryAgent → working
🛠️ extract_entities  (agent: LegacyApplicationDiscoveryAgent)
🔄 LegacyApplicationDiscoveryAgent → working
🛠️ extract_entities  (agent: LegacyApplicationDiscoveryAgent)
🔄 LegacyApplicationDiscoveryAgent → working
✅ extract_entities
{
  "classes": [
    "UserService",
    "OrderService"
  ],
  "tables": [
    "ORDERS"
  ],
  "apis": [
    "http://order-api/getOrders"
  ]
}
🔄 LegacyApplicationDiscoveryAgent → working
✅ extract_entities
{
  "classes": [],
  "tables": [],
  "apis": [
    "http://order-api/getOrders"
  ]
}
🔄 LegacyApplicationDiscoveryAgent → working
🛠️ analyze_dependencies  (agent: LegacyApplicationDiscoveryAgent)
🔄 LegacyApplicationDiscoveryAgent → working
✅ analyze_dependencies
UserService depends on DB tables: USERS, ORDERS
OrderService depends on DB tables: USERS, ORDERS
• LegacyApplicationDiscoveryAgent → input-required
{
  "type": "question",
  "content": "Analysis results:\n- Extracted classes: UserService, OrderService\n- Detected tables: USERS, ORDERS\n- APIs: http://order-api/getOrders\n- Dependency relationships: UserService depends on USERS table, OrderService depends on ORDERS table and both mention these tables in SQL statements; API call to http://order-api/getOrders is present.\n\nDo you want me to include RAG knowledge for further context?\nShould I refine the dependency analysis?\nProceed to final summary?",
  "questions": [
    "Include RAG knowledge?",
    "Refine dependency analysis?",
    "Proceed to final summary?"
  ],
  "interaction": "request_input"
}

----------------------------------------------------------------------
You: do not include rag , just give me final summary

Bot:

🚀 Starting agent: LegacyApplicationDiscoveryAgent
🛠️ transfer_to_agent  (agent: LegacyApplicationDiscoveryAgent)
🔄 Switching → LegacyApplicationDiscoveryAgent
✅ transfer_to_agent
{
  "result": null
}
🔄 LegacyApplicationDiscoveryAgent → working
🔄 LegacyApplicationDiscoveryAgent → working

🤖 LegacyApplicationDiscoveryAgent
org.enterprise.agent.wrb_02.v2 started processing
🔄 LegacyApplicationDiscoveryAgent → working
🛠️ summarize_findings  (agent: LegacyApplicationDiscoveryAgent)
🔄 LegacyApplicationDiscoveryAgent → working
✅ summarize_findings

=== Dependency Report ===
UserService depends on the USERS table for fetching user data. OrderService depends on the ORDERS table to retrieve order data. The legacy system
interfaces with an external API at http://order-api/getOrders for order retrieval. These dependencies indicate a clear separation between user and
order data management, with database tables accessed directly by the respective service classes, and orders also accessed via an external API.

=== Supporting Knowledge (RAG) ===


=== Final Insight ===
This legacy system shows tight coupling between business logic and database layers.
Recommended: Introduce service abstraction layer before modernization.

🔄 LegacyApplicationDiscoveryAgent → working
Final summary:
The legacy JSP/Java system consists of two main service classes: UserService and OrderService. UserService directly accesses the USERS database
table to fetch user information, while OrderService accesses the ORDERS table. Additionally, OrderService interacts with an external API at
http://order-api/getOrders to retrieve order data.

This structure reveals a clear division between user and order management with dependencies on respective database tables and external API for
orders. The current architecture shows tight coupling between the business logic and data access layers, indicating the need for introducing a
service abstraction layer to facilitate modernization efforts.
🔄 LegacyApplicationDiscoveryAgent → working

💰 Token Usage
┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━┳━━━━━━━━┳━━━━━━━┓
┃ Agent                           ┃ Input ┃ Output ┃ Total ┃
┡━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━╇━━━━━━━━╇━━━━━━━┩
│ LegacyApplicationDiscoveryAgent │ 2516  │ 247    │ 2763  │
└─────────────────────────────────┴───────┴────────┴───────┘
✅ LegacyApplicationDiscoveryAgent → completed

💰 Token Usage
┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━┳━━━━━━━━┳━━━━━━━┓
┃ Agent                           ┃ Input ┃ Output ┃ Total ┃
┡━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━╇━━━━━━━━╇━━━━━━━┩
│ LegacyApplicationDiscoveryAgent │ 5032  │ 494    │ 5526  │
└─────────────────────────────────┴───────┴────────┴───────┘

----------------------------------------------------------------------
You:


```

# 📂 Project Structure

```
Cortex
│
├── agents/                  # Root agent & HITL
├── routers/                 # REST APIs
├── services/                # Business logic
├── websocket/               # Real-time communication
├── state/                   # Workflow state
├── session/                 # Session management
├── database/                # ORM & persistence
├── infrastructure/          # A2A factories
├── developer_resource/      # Architecture diagrams
├── migrations/              # Alembic migrations
├── tests/                   # Unit & integration tests
├── README.md
└── DEVELOPER.md
```

Detailed folder responsibilities and execution flow are documented in **docs/DEVELOPER_GUIDE.md**.

---

# 📚 Documentation

| Document | Description |
|----------|-------------|
| **README.md** | Project overview and quick start |
| **docs/DEVELOPER_GUIDE.md** | Internal architecture, execution flow, tracing and implementation details |
| **docs/** | Architecture diagrams, sequence diagrams and design resources |

---

# 🛣 Roadmap

The following features are planned for future releases.

## Workflow Planning

- [ ] Planner Module
- [ ] Multi-Agent Workflow Planning
- [ ] Dependency-aware Execution

## Execution Engine

- [ ] Parallel Agent Execution
- [ ] Retry Policies
- [ ] Workflow Resume
- [ ] Dynamic Replanning

## Observability

- [ ] Workflow Replay
- [ ] Distributed Tracing
- [ ] Execution Timeline UI

## Platform

- [ ] Plugin-based Capability Providers
- [ ] Multiple LLM Providers
- [ ] Kubernetes Deployment
- [ ] Metrics Dashboard

---

# 🤝 Contributing

Contributions are welcome.

If you'd like to improve Cortex:

1. Fork the repository.
2. Create a feature branch.

```bash
git checkout -b feature/my-feature
```

3. Commit your changes.

```bash
git commit -m "feat: add awesome feature"
```

4. Push your branch.

```bash
git push origin feature/my-feature
```

5. Open a Pull Request.

---

# 🧪 Current Status

Cortex is under active development.

Current implemented capabilities include:

- ✅ Dynamic Agent Discovery
- ✅ Capability-Based Routing
- ✅ Human-in-the-Loop Approval
- ✅ Dynamic Agent Registry
- ✅ Stateful Workflow Tracking
- ✅ Agent Invocation Tracking
- ✅ WebSocket Streaming
- ✅ PostgreSQL Persistence
- ✅ Artifact Management
- ✅ File Forwarding
- ✅ Health Monitoring

---

# 📄 License

This project is licensed under the MIT License.

See the **LICENSE** file for details.

---

# 🙌 Acknowledgements

Cortex is built using several excellent open-source technologies.

- Google ADK
- FastAPI
- LiteLLM
- PostgreSQL
- SQLAlchemy
- Alembic
- A2A Protocol

Special thanks to the open-source community for building the tools that make projects like Cortex possible.