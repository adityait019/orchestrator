# Agentic AI Orchestrator

### Dynamic Multi-Agent Platform Built with FastAPI, Google ADK, A2A Protocol & PostgreSQL

---

## Overview

Agentic AI Orchestrator is a production-oriented multi-agent platform designed to dynamically discover, register, monitor, and coordinate AI agents through the A2A (Agent-to-Agent) protocol.

The platform acts as a central orchestration layer that understands user intent, selects the most appropriate agents based on capabilities, manages execution workflows, tracks agent performance, and streams results back to users in real time.

Unlike traditional chatbot architectures, the orchestrator supports dynamic agent ecosystems where agents can be added, removed, monitored, and routed without code changes.

---

## Key Features

### Multi-Agent Orchestration

* Capability-based agent routing
* Dynamic agent selection
* Multi-agent workflow execution
* Root-agent driven coordination
* Context preservation across executions

### A2A Protocol Integration

* Agent Card discovery
* Dynamic remote agent registration
* JSON-RPC communication
* Streaming response support
* Capability extraction from Agent Cards

### Real-Time Communication

* WebSocket-based streaming
* Live status updates
* Tool execution events
* Agent progress notifications
* Real-time artifact delivery

### Workflow Tracking

* Workflow lifecycle management
* Agent invocation tracking
* Execution timeline monitoring
* Step-by-step orchestration visibility
* Structured execution persistence

### Observability & Evaluation

* Agent performance leaderboard
* Token consumption tracking
* Success/failure metrics
* Latency analytics
* Time-series evaluation APIs
* Operational dashboards

### Artifact Management

* Multi-file uploads
* Secure signed URLs
* Artifact persistence
* Artifact forwarding between agents
* User-scoped file ownership

### Session & Memory

* Persistent conversations
* Session-aware execution
* Chat history APIs
* Multi-user support
* Multi-tenant architecture

### Deployment Modes

* PostgreSQL backend
* Local JSON storage mode
* Dynamic health monitoring
* Automatic agent synchronization

---

## Architecture

(Insert Mermaid diagram here)

---

## Core Components

### Cortex Root Agent

Cortex is the orchestration brain of the platform.

Responsibilities:

* Intent understanding
* Capability matching
* Agent selection
* Multi-agent coordination
* Artifact forwarding
* Execution monitoring

Cortex never performs specialized work itself. Instead, it delegates tasks to the most suitable remote agents.

---

### Dynamic Agent Registry

Agents are not hardcoded.

The orchestrator dynamically discovers and manages agents through:

* Agent registration APIs
* Agent Card discovery
* Health monitoring
* Runtime synchronization

Only active and healthy agents participate in orchestration decisions.

---

### Workflow Engine

Every user request creates a structured workflow.

The workflow engine tracks:

* Workflow lifecycle
* Execution state
* Agent invocations
* Artifacts
* Token usage
* Performance metrics

This provides full observability into orchestration execution.

---

### Event Processing Pipeline

Incoming agent responses pass through:

1. Event Normalization
2. Progress Extraction
3. Token Usage Tracking
4. Artifact Detection
5. WebSocket Streaming
6. Persistence Layer

This creates a unified execution model across different agent implementations.

---

### File & Artifact System

Files are handled through a secure artifact pipeline:

```text
Upload
  ↓
Signed URL Generation
  ↓
Session Attachment
  ↓
Agent Forwarding
  ↓
Artifact Tracking
  ↓
Secure Retrieval
```

Features:

* Tenant isolation
* User isolation
* Session isolation
* HMAC signed URLs
* Artifact ownership enforcement

---

## Technology Stack

### Backend

* FastAPI
* Python
* WebSockets
* SQLAlchemy
* PostgreSQL

### AI & Agent Frameworks

* Google ADK
* A2A Protocol
* Azure OpenAI
* LiteLLM

### Infrastructure

* JSON-RPC
* AsyncIO
* Alembic
* HTTPX

### Storage

* PostgreSQL
* Local JSON Store

---

## Execution Flow

```text
User Prompt
    ↓
WebSocket Handler
    ↓
Workflow Creation
    ↓
Cortex Root Agent
    ↓
Capability-Based Routing
    ↓
Remote A2A Agent
    ↓
Streaming Response
    ↓
Event Processing
    ↓
Artifact Handling
    ↓
Workflow Completion
    ↓
Persist Metrics & History
```

---

## Observability

The platform provides built-in operational visibility:

* Workflow Dashboard
* Agent Performance Metrics
* Token Usage Analytics
* Success Rate Tracking
* Latency Monitoring
* Invocation History
* Artifact Auditing

---

## Future Roadmap

* Human-in-the-loop workflows
* MCP integration
* Agent marketplace
* Distributed orchestration
* Workflow replay engine
* Multi-model routing
* Cost optimization engine
* Agent evaluation benchmarks

---

## Why This Project?

Most agent frameworks focus on individual agents.

This project focuses on orchestrating entire agent ecosystems by combining:

* Dynamic agent discovery
* Capability-based routing
* Real-time observability
* Workflow execution tracking
* Production-grade orchestration patterns

making it suitable for building scalable multi-agent systems.

---

## License

MIT License

---