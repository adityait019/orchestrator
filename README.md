# 🧠 Nexus

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

**Nexus** is a capability-driven orchestration platform that discovers, coordinates, and interacts with distributed AI agents using the **A2A (Agent-to-Agent) protocol**.

Unlike traditional applications that tightly couple business logic to specific agents, Nexus dynamically discovers remote Agent Cards, builds a capability registry, selects the most appropriate agent for a task, and orchestrates the complete execution lifecycle.

The platform acts as an orchestration layer between clients and distributed AI agents while providing workflow tracking, Human-in-the-Loop approvals, real-time streaming, and persistent execution metadata.

---

# 🚀 Why Nexus?

Modern AI systems often require multiple specialized agents.

Instead of hardcoding connections to every agent, Nexus introduces a capability-driven orchestration layer that:

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

![System Architecture](https://github.com/adityait019/orchestrator/blob/main/docs/architecture-diagram/architecture_diagram.png)

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
               Nexus Orchestrator
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
| **Nexus Orchestrator** | Capability matching, delegation, workflow coordination |
| **Human-in-the-Loop** | User approval before agent delegation |
| **Dynamic Agent Registry** | Agent discovery, capability loading, health monitoring |
| **Agent Invocation Layer** | Session/context mapping and remote invocation |
| **Pure A2A Runtime** | JSON-RPC communication with remote agents |
| **Core Services** | Workflow, state, artifacts, files and chat history |
| **Persistence Layer** | Workflow state, sessions, registry and artifacts |

---

# 🎯 Design Principles

Nexus is designed around a few architectural principles:

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

# Start Nexus
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
(orchestrator) PS C:\Users\adity\project\orchestrator> uv run -m cli.cli_testing

                                      ███╗   ██╗███████╗██╗  ██╗██╗   ██╗███████╗
                                      ████╗  ██║██╔════╝╚██╗██╔╝██║   ██║██╔════╝
                                      ██╔██╗ ██║█████╗   ╚███╔╝ ██║   ██║███████╗
                                      ██║╚██╗██║██╔══╝   ██╔██╗ ██║   ██║╚════██║
                                      ██║ ╚████║███████╗██╔╝ ██╗╚██████╔╝███████║
                                      ╚═╝  ╚═══╝╚══════╝╚═╝  ╚═╝ ╚═════╝ ╚══════╝

                                            AI Multi-Agent Orchestration Platform

🔌 Connecting to ws://192.168.1.10:8000/ws/4fca7f9b-a2ac-4053-b3f0-484255e15955
🔌 Server: connection_established
✅ Authentication successful
🤖 Connected to Orchestrator
🧠 Session ID: 4fca7f9b-a2ac-4053-b3f0-484255e15955

Tip: /help for commands · Ctrl+C to exit
You: /list

📡 Active Agents:
• OrderAgent (192.168.1.10:10100)
• InventoryAgent (192.168.1.10:10101)
You: Create a new order record for customer ID CUST-90412 with 2 units of item SKU-1001 priced at $25.00 each

Nexus:

🤖 Nexus
Proposed plan: Check inventory for SKU-1001, then create a new order record for customer CUST-90412 with 2 units of that
item.

1. InventoryAgent: {"sku":"SKU-1001","quantity":2}
2. OrderAgent: {"customer_id":"CUST-90412","line_items":[{"sku":"SKU-1001","quantity":2,"unit_price":25.00}]}

Proceed? (yes/no)

----------------------------------------------------------------------
You: yes

Nexus:
• InventoryAgent → submitted
🔄 InventoryAgent → working
🔄 InventoryAgent → working

🤖 InventoryAgent
org.ecommerce.inventory_agent.v1 started processing
🔄 InventoryAgent → working
🛠️ check_availability  (agent: InventoryAgent)
🔄 InventoryAgent → working
🔄 InventoryAgent → working
{
  "success": false,
  "error": "SKU-1001 not found"
}
🔄 InventoryAgent → working

💰 Token Usage
┏━━━━━━━━━━━━━━━━┳━━━━━━━┳━━━━━━━━┳━━━━━━━┓
┃ Agent          ┃ Input ┃ Output ┃ Total ┃
┡━━━━━━━━━━━━━━━━╇━━━━━━━╇━━━━━━━━╇━━━━━━━┩
│ InventoryAgent │ 2557  │ 41     │ 2598  │
└────────────────┴───────┴────────┴───────┘
✅ InventoryAgent → completed
• OrderAgent → submitted
🔄 OrderAgent → working
🔄 OrderAgent → working

🤖 OrderAgent
org.ecommerce.order_agent.v1 started processing
🔄 OrderAgent → working
{
  "success": false,
  "error": "The SKU 'SKU-1001' is not found in inventory. Please check the SKU and try again."
}
🔄 OrderAgent → working

💰 Token Usage
┏━━━━━━━━━━━━┳━━━━━━━┳━━━━━━━━┳━━━━━━━┓
┃ Agent      ┃ Input ┃ Output ┃ Total ┃
┡━━━━━━━━━━━━╇━━━━━━━╇━━━━━━━━╇━━━━━━━┩
│ OrderAgent │ 835   │ 37     │ 872   │
└────────────┴───────┴────────┴───────┘
✅ OrderAgent → completed

🤖 Nexus
Plan completed.
✅ Plan completed
Total tokens: 3470

----------------------------------------------------------------------
You: do for SKU-001

Nexus:

🤖 Nexus
Proposed plan: Check SKU-001 inventory availability and create an order if available

1. InventoryAgent: Check availability and stock count for SKU-001
2. OrderAgent: Create an order record for SKU-001 if inventory is available

Proceed? (yes/no)

----------------------------------------------------------------------
You: yes

Nexus:
• InventoryAgent → submitted
🔄 InventoryAgent → working
🔄 InventoryAgent → working

🤖 InventoryAgent
org.ecommerce.inventory_agent.v1 started processing
🔄 InventoryAgent → working
🛠️ check_availability  (agent: InventoryAgent)
🔄 InventoryAgent → working
🔄 InventoryAgent → working
{
  "success": true,
  "sku": "SKU-001",
  "name": "Wireless Headphones",
  "quantity_available": 50,
  "price": 79.99,
  "in_stock": true,
  "status": "available",
  "message": "SKU-001 (Wireless Headphones) is available with a stock count of 50 units."
}
🔄 InventoryAgent → working

💰 Token Usage
┏━━━━━━━━━━━━━━━━┳━━━━━━━┳━━━━━━━━┳━━━━━━━┓
┃ Agent          ┃ Input ┃ Output ┃ Total ┃
┡━━━━━━━━━━━━━━━━╇━━━━━━━╇━━━━━━━━╇━━━━━━━┩
│ InventoryAgent │ 2579  │ 101    │ 2680  │
└────────────────┴───────┴────────┴───────┘
✅ InventoryAgent → completed
• OrderAgent → submitted
🔄 OrderAgent → working
🔄 OrderAgent → working

🤖 OrderAgent
org.ecommerce.order_agent.v1 started processing
🔄 OrderAgent → working
🛠️ create_order_record  (agent: OrderAgent)
🔄 OrderAgent → working
🔄 OrderAgent → working
{
  "success": true,
  "order_id": "ORD-3C7E672B",
  "status": "created",
  "message": "Order for SKU-001 (Wireless Headphones) has been successfully created with order ID ORD-3C7E672B."
}
🔄 OrderAgent → working

💰 Token Usage
┏━━━━━━━━━━━━┳━━━━━━━┳━━━━━━━━┳━━━━━━━┓
┃ Agent      ┃ Input ┃ Output ┃ Total ┃
┡━━━━━━━━━━━━╇━━━━━━━╇━━━━━━━━╇━━━━━━━┩
│ OrderAgent │ 1914  │ 106    │ 2020  │
└────────────┴───────┴────────┴───────┘
✅ OrderAgent → completed

🤖 Nexus
Plan completed.
✅ Plan completed
Total tokens: 4700

----------------------------------------------------------------------
You:
```

# 📂 Project Structure

```
Nexus
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

If you'd like to improve Nexus:

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

Nexus is under active development.

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

Nexus is built using several excellent open-source technologies.

- Google ADK
- FastAPI
- LiteLLM
- PostgreSQL
- SQLAlchemy
- Alembic
- A2A Protocol

Special thanks to the open-source community for building the tools that make projects like Nexus possible.
