# 📘 HITL Implementation Rulebook (A2A Agent System)

> ⚠️ **STRICT COMPLIANCE REQUIRED**  
> Any deviation from this guideline **WILL BREAK the system** (especially streaming + HITL behavior).

---

# 🎯 1. Purpose of This Document

This guide ensures:

- ✅ Consistent HITL behavior
- ✅ Zero protocol mismatch
- ✅ Safe agent execution lifecycle
- ✅ Prevents breaking A2A orchestration

---

# 🧠 2. HITL Definition (System-Specific)

HITL =

> The agent **pauses execution**, asks structured questions, and **waits for user input** before continuing.

---

# 🔴 3. CRITICAL CONTRACT (DO NOT BREAK)

## ✅ Agent MUST return EXACT JSON schema

```json
{
  "type": "answer" | "question",
  "content": "string or null",
  "questions": ["string"] or null,
  "interaction": "complete" | "request_input"
}
```

---

## 🚨 STRICT RULES

| Field         | Requirement                               |
| ------------- | ----------------------------------------- |
| `type`        | ONLY `"answer"` or `"question"`           |
| `interaction` | ONLY `"complete"` or `"request_input"`    |
| `questions`   | REQUIRED if type = question               |
| `content`     | REQUIRED if type = answer                 |
| Format        | MUST be valid JSON (no text outside JSON) |

---

## ❌ COMMON BREAKERS

❌ Wrong values:

```json
"type": "ask"
"interaction": "waiting"
```

❌ Missing fields:

```json
{ "type": "question" }
```

❌ Plain text:

```
Please provide input
```

---

# 🔁 4. HITL FLOW (MANDATORY BEHAVIOR)

```
Agent detects missing input
    ↓
Returns:
  type = "question"
  interaction = "request_input"
    ↓
Executor → TaskState.input_required
    ↓
SYSTEM PAUSES
    ↓
Client sends user input (same context_id)
    ↓
Agent resumes execution
```

---

# ⚙️ 5. IMPLEMENTATION RULES

---

# ✅ RULE 1: STOP EXECUTION AFTER HITL

### ✅ Correct

```python
if parsed.type == "question":
    yield {
        "type": "agent_response",
        "payload": parsed.questions,
        "interaction": "request_input"
    }
    return   # ✅ MANDATORY
```

---

### ❌ WRONG

```python
yield {...}
# continues execution → breaks HITL ❌
```

---

# ✅ RULE 2: USE CORRECT TASK STATE

Inside executor:

### ✅ Correct

```python
TaskState.input_required
```

---

### ❌ WRONG

```python
TaskState.working   # ❌ breaks UI + flow
TaskState.completed # ❌ ends task prematurely
```

---

# ✅ RULE 3: ONLY agent_response CONTROLS FLOW

✅ Source of truth:

```python
if ev_type == "agent_response":
```

❌ DO NOT:

- Use tool events for lifecycle decisions
- Use usage events for control

---

# ✅ RULE 4: NEVER MODIFY KEYWORDS

These are **SYSTEM KEYWORDS – DO NOT CHANGE**

| Keyword     | Allowed Values                         |
| ----------- | -------------------------------------- |
| type        | answer, question                       |
| interaction | complete, request_input                |
| event.type  | tool_call, tool_output, agent_response |

---

### ❌ THIS WILL BREAK SYSTEM

```json
"interaction": "need_input"
"interaction": "pending"
"type": "query"
```

---

# ✅ RULE 5: ALWAYS PRESERVE CONTEXT_ID

Client MUST resend:

```json
"context_id": SAME_ID
```

---

### ❌ If changed

| Issue          | Result      |
| -------------- | ----------- |
| New context_id | Memory lost |
| HITL step      | Restarted   |
| Tools          | Re-executed |

---

# 🧩 6. AGENT DESIGN RULES FOR HITL

---

## ✅ 6.1 Ask Questions ONLY When Needed

### ✅ Good

```text
If code snippet missing → ask for it
```

---

### ❌ Bad

- Asking unnecessary questions
- Asking after running tools

---

---

## ✅ 6.2 Ask CLEAR + ACTIONABLE QUESTIONS

### ✅ Good

```json
"questions": [
  "Provide JSP file for analysis",
  "Specify database type"
]
```

---

### ❌ Bad

```json
"questions": ["Provide more info"]
```

---

---

## ✅ 6.3 NEVER ASK SAME QUESTION AGAIN

Use memory to avoid repetition.

---

---

## ✅ 6.4 MULTIPLE QUESTIONS ALLOWED

```json
"questions": ["Q1", "Q2"]
```

---

# 🔄 7. RESUME EXECUTION RULES

---

## ✅ When user responds

System must:

1. Reuse same `context_id`
2. Recreate session:

```python
SQLiteSession(session_id=context_id)
```

---

## ✅ Result

| Behavior            | Outcome |
| ------------------- | ------- |
| Memory reused       | YES     |
| Tool results cached | YES     |
| Agent resumes       | YES     |

---

# ⚠️ 8. STRICT VALIDATION CHECKLIST

Before committing code, validate:

---

## ✅ Agent Output

- [ ] JSON valid
- [ ] Matches schema
- [ ] No extra text

---

## ✅ HITL Behavior

- [ ] Returns `request_input`
- [ ] Stops execution (`return`)
- [ ] No further events emitted

---

## ✅ Executor Behavior

- [ ] Uses `TaskState.input_required`
- [ ] Marks `final=True`
- [ ] Does NOT continue loop

---

## ✅ Context Handling

- [ ] Uses `context_id`
- [ ] Session initialized correctly

---

# 🧪 9. TEST CASES (MANDATORY)

Run all before merging:

---

## ✅ Test 1: Missing Input

Input:

```
Analyze system
```

Expected:

- Agent asks question
- Execution pauses

---

---

## ✅ Test 2: Resume

Input:

```
Provide code snippet
```

Expected:

- Agent continues execution
- Final answer returned

---

---

## ✅ Test 3: Wrong JSON (Negative)

Simulate invalid JSON

Expected:

- System fallback triggers
- No crash

---

---

## ✅ Test 4: Keyword Integrity

Change:

```
request_input → need_input
```

Expected:

- System breaks ❌ (verify sensitivity)

---

# 🚨 10. TOP FAILURE SCENARIOS

| Issue                 | Root Cause              |
| --------------------- | ----------------------- |
| Agent doesn't pause   | Missing `return`        |
| UI doesn't show input | Wrong interaction value |
| Agent restarts        | context_id mismatch     |
| Infinite loop         | memory not used         |
| Crash                 | invalid JSON            |

---

# 🧠 11. GOLDEN RULES (MEMORIZE)

✅ HITL = `request_input`  
✅ STOP execution immediately  
✅ NEVER change keywords  
✅ ALWAYS reuse context_id  
✅ Agent response = single source of truth

---

# 🔚 12. FINAL WARNING

> ⚠️ Even a **single keyword mismatch or missing `return`** can:

- Break streaming
- Break UI
- Break task lifecycle
- Cause production failures

---

# ✅ 13. RECOMMENDED PRACTICE

Before merging any agent:

✔ Run HITL flow manually  
✔ Validate JSON strictly  
✔ Inspect streaming logs  
✔ Verify pause + resume behavior

---

# 🎯 Conclusion

This HITL implementation is:

✅ Deterministic  
✅ Protocol-driven  
✅ Extremely strict

Following this guide ensures:

- Reliable human interaction
- Stable A2A communication
- Production-safe agents

---

# Working Agent Code Example

```python


import os
import logging
import json
import time
import re
import requests
import httpx
import asyncio
from typing import Optional, AsyncGenerator
from dotenv import load_dotenv
from agents import Agent, Runner, function_tool
from openai import AsyncAzureOpenAI
from pathlib import Path
from fastapi import FastAPI
from pydantic import BaseModel
import uvicorn

# ---> ADDED IMPORT FOR MCP <---
# from agents.mcp import MCPServerStdio
# ---> ADDED IMPORT FOR MCP <---
# from agents.mcp import MCPServerStreamableHttp,MCPServerStreamableHttpParams

load_dotenv(override=True)

# JIRA_SERVER="http://10.73.89.35:8005/mcp"


# mcp_server = MCPServerStreamableHttp(params=MCPServerStreamableHttpParams(url=JIRA_SERVER),cache_tools_list=True)

# --- Shared class definitions ---
# No required class definitions found.

# --- Tool definitions ---

# --- ADD THIS (STRICT SCHEMAS) ---
from pydantic import BaseModel
from typing import List,Optional


class Entities(BaseModel):
    classes: List[str]
    tables: List[str]
    apis: List[str]


class DependencyInput(BaseModel):
    entities: Entities


from typing import Literal

type: Literal["answer", "question"]
interaction: Literal["complete", "request_input"]

class AgentResponse(BaseModel):
    type: str  # "answer" | "question"
    content: Optional[str] = None
    questions: Optional[List[str]] = None
    interaction: str  # "complete" | "request_input"

@function_tool
def rag_search(query: str, top_k: int = 5) -> str:
    """
    Search the RAG knowledge base using the orchestrator client.

    Args:
        query: Natural language search query.
        top_k: Number of document snippets to return (default 5).

    Returns:
        Concatenated snippets or error message.
    """
    # 1. Locate the JWT token saved by the main orchestrator.
    current_dir = Path(__file__).parent
    token_path = current_dir.parent / "data" / "rag_tokens.json"

    if not os.path.exists(token_path):
        return "Error: No RAG token found. Please authenticate first."

    try:
        with open(token_path, "r") as f:
            tokens = json.load(f)
        access_token = tokens.get("access_token")
        if not access_token:
            return "Error: RAG token file missing 'access_token'."
    except Exception as e:
        return f"Error reading token file: {e}"

    # 2. Orchestrator client endpoint (can be overridden by env)
    base_orchestrator_url = os.getenv(
        "RAG_ORCHESTRATOR_URL",
        "http://10.73.83.97:8000/retrieval/search"
    )

    # Append the token as a query parameter
    orchestrator_url = f"{base_orchestrator_url}"

    headers = {"Content-Type": "application/json",
               "Authorization": f"Bearer {access_token}"}
    payload = {
        "query": query,
        "collection_type": "documentation",
        "search_type": "hybrid",
        "top_k": top_k,
        "rerank": True,
        "multi_query": False,
    }

    try:
        resp = requests.post(orchestrator_url, json=payload, headers=headers, timeout=30)
        logging.info(f"RAG search response status: {resp}")
        if resp.status_code == 401:
            return "Error: RAG token expired. Please re-authenticate."
        resp.raise_for_status()
        data = resp.json()

        # Extract snippets – adjust according to actual response structure
        snippets = data.get("results", [])
        if not snippets:
            return "No relevant documents found."

        output = []
        for i, item in enumerate(snippets, 1):
            text = item.get("content", item.get("text", ""))
            source = item.get("source", "unknown")
            output.append(f"[{i}] {text}\n(Source: {source})")
        return "\n\n".join(output)

    except requests.RequestException as e:
        return f"RAG search failed: {e}"


@function_tool
def extract_entities(code_snippet: str) -> Entities:
    """
    Extracts entities like classes, tables, APIs from code.
    """
    classes = re.findall(r'class\s+(\w+)', code_snippet)
    tables = re.findall(r'SELECT .* FROM (\w+)', code_snippet, re.IGNORECASE)
    apis = re.findall(r'fetch\(["\'](.*?)["\']\)', code_snippet)

    return Entities(
        classes=classes,
        tables=tables,
        apis=apis
    )


@function_tool
def analyze_dependencies(input: DependencyInput) -> str:
    """
    Builds dependency relationships across extracted entities.
    """
    entities = input.entities

    result = []
    for c in entities.classes:
        if entities.tables:
            result.append(
                f"{c} depends on DB tables: {', '.join(entities.tables)}"
            )

    if not result:
        return "No strong dependencies detected."

    return "\n".join(result)

@function_tool
def summarize_findings(dependency_report: str, rag_context: str) -> str:
    """
    Combines dependency graph + RAG knowledge into final insight.
    """
    return f"""
=== Dependency Report ===
{dependency_report}

=== Supporting Knowledge (RAG) ===
{rag_context}

=== Final Insight ===
This legacy system shows tight coupling between business logic and database layers.
Recommended: Introduce service abstraction layer before modernization.
"""


# --- System instruction ---
SYSTEM_INSTRUCTION = """The LegacyApplicationDiscoveryAgent is an AI agent specialized in static analysis of legacy JSP (JavaServer Pages) systems. Its primary purpose is to analyze existing JSP and Java codebases to uncover the internal structure, component relationships, and database interactions within legacy applications. This analysis supports modernization efforts by providing a clear understanding of how the legacy system is organized and how its parts depend on each other.

Key responsibilities of the LegacyApplicationDiscoveryAgent include:

- Extracting the architectural structure and individual components from JSP and Java source code.
- Identifying dependencies between modules, APIs, and database calls to map out how different parts of the system interact.
- Constructing detailed dependency graphs that visualize these relationships, aiding developers and architects in planning modernization strategies.
- Utilizing specialized tools and techniques tailored for JSP, servlets, and legacy Java/JSP modernization contexts to perform accurate and comprehensive static analysis.

Overall, this agent serves as a critical asset in legacy system modernization projects by delivering actionable insights into complex JSP-based applications, enabling informed decision-making and efficient migration or refactoring processes."""


# --- Azure OpenAI async client ---
client = AsyncAzureOpenAI(
    azure_endpoint=os.getenv("AZURE_OPENAI_API_BASE",""),
    api_key=os.getenv("AZURE_OPENAI_API_KEY",""),
    api_version=os.getenv("AZURE_OPENAI_API_VERSION","")
)


from agents.models.openai_responses import OpenAIResponsesModel

model = OpenAIResponsesModel(
    model=os.getenv("DEPLOYMENT_NAME",""),
    openai_client=client
)


SYSTEM_INSTRUCTION += """

IMPORTANT:
You MUST respond only in JSON format matching this schema:

{
  "type": "answer" | "question",
  "content": "...",
  "questions": [...],
  "interaction": "complete" | "request_input"
}

Rules:
- If you need more input → use type="question" and interaction="request_input"
- If task is finished → use type="answer" and interaction="complete"
- Do NOT return plain text
"""
# --- Create Agent ---
agent = Agent(
    name="LegacyApplicationDiscoveryAgent",
    instructions=SYSTEM_INSTRUCTION + """
You MUST follow this workflow when analyzing code:

1. Extract entities using extract_entities
2. Analyze dependencies using analyze_dependencies
3. If more context needed, call rag_search
4. Finally summarize using summarize_findings

Reuse previous results if already available in conversation.
""",
    model=model,
    tools=[
        extract_entities,
        analyze_dependencies,
        summarize_findings,
        rag_search
    ]
)

from agents.memory import SQLiteSession
# session=SQLiteSession()
async def execute_agent(query: str,session_id:str) -> AsyncGenerator[dict, None]:


    session=SQLiteSession(session_id=session_id,db_path='./session_db.db')
    streamed = Runner.run_streamed(agent, query,session=session)

    async for event in streamed.stream_events():
        if event.type == "run_item_stream_event":
            item = event.item

            if item.type == "tool_call_item":

                raw = item.raw_item

                tool_call_id = (
                    raw.get("call_id") if isinstance(raw, dict)
                    else getattr(raw, "call_id", None)
                )

                tool_name = (
                    raw.get("name") if isinstance(raw, dict)
                    else getattr(raw, "name", None)
                )

                arguments = (
                    raw.get("arguments") if isinstance(raw, dict)
                    else getattr(raw, "arguments", None)
                )

                yield {
                    "type": "tool_call",
                    "payload": {
                        "tool_name": tool_name,
                        "tool_call_id": tool_call_id,
                        "input": arguments,
                    },
                }


            elif item.type == "tool_call_output_item":

                raw = item.raw_item

                tool_call_id = (
                    raw.get("call_id") if isinstance(raw, dict)
                    else getattr(raw, "call_id", None)
                )

                yield {
                    "type": "tool_output",
                    "payload": {
                        "output": item.output,
                        "tool_call_id": tool_call_id,
                    }
                }


            elif item.type == "message_output_item":
                raw_text = item.raw_item.content[0].text if item.raw_item.content else ""  # type: ignore
                raw_text = (raw_text or "").strip()

                interaction = "complete"
                payload_to_emit = raw_text

                # -------------------------------------------------
                # 1. First try your strict Pydantic model
                # -------------------------------------------------
                parsed = None

                try:
                    parsed = AgentResponse.model_validate_json(raw_text)
                except Exception:
                    parsed = None

                if parsed:
                    if parsed.type == "question":
                        yield {
                            "type": "agent_response",
                            # ✅ keep full structured response, not only questions
                            "payload": raw_text,
                            "interaction": "request_input",
                        }
                        return

                    elif parsed.type == "answer":
                        yield {
                            "type": "agent_response",
                            "payload": parsed.content,
                            "interaction": "complete",
                        }
                        continue

                # -------------------------------------------------
                # 2. Robust fallback: inspect raw JSON manually
                # -------------------------------------------------
                try:
                    raw_json = json.loads(raw_text)

                    if isinstance(raw_json, dict):
                        raw_type = str(raw_json.get("type") or "").lower().strip()
                        raw_interaction = str(raw_json.get("interaction") or "").lower().strip()

                        if raw_type == "question" or raw_interaction == "request_input":
                            yield {
                                "type": "agent_response",
                                "payload": raw_text,
                                "interaction": "request_input",
                            }
                            return

                        if raw_type == "answer":
                            yield {
                                "type": "agent_response",
                                "payload": raw_json.get("content", raw_text),
                                "interaction": "complete",
                            }
                            continue

                except Exception:
                    pass

                # -------------------------------------------------
                # 3. Final fallback
                # -------------------------------------------------
                yield {
                    "type": "agent_response",
                    "payload": raw_text,
                    "interaction": "complete" if raw_text else "request_input",
                }


        else:
            print(f"Received non-run_item_stream_event: {event.type}")
    # ✅ Wait for streaming to fully complete (typed)
    if streamed.run_loop_task is not None:
        await streamed.run_loop_task

    # ✅ Aggregate usage in a type-safe way
    input_tokens = 0
    output_tokens = 0
    total_tokens = 0

    for response in streamed.raw_responses:
        if response.usage:
            input_tokens += response.usage.input_tokens
            output_tokens += response.usage.output_tokens
            total_tokens += response.usage.total_tokens

    yield {
        "type": "usage",
        "payload": {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": total_tokens,
        },
    }

    yield {"type": "done", "payload": ""}



```

# Working AgentExecutor Example (A2a wrapper on any Framework)

```python
from __future__ import annotations

import inspect
import uuid
import logging
import asyncio
import json
from typing import Any

from a2a.server.agent_execution import AgentExecutor
from a2a.server.agent_execution.context import RequestContext
from a2a.server.events.event_queue import EventQueue
from a2a.server.tasks import TaskUpdater
from a2a.types import (
    Message,
    Part,
    Role,
    TaskState,
    TextPart,
    UnsupportedOperationError,
)
from a2a.utils.errors import ServerError

logger = logging.getLogger(__name__)


class DynamicFunctionAgentExecutor(AgentExecutor):
    def __init__(self, agent_id: str, execute_fn):
        self.agent_id = agent_id
        self.execute_fn = execute_fn

    def _coerce_text(self, payload: Any) -> str:
        if payload is None:
            return ""

        if isinstance(payload, str):
            return payload

        if isinstance(payload, (dict, list, tuple)):
            try:
                return json.dumps(payload, indent=2, ensure_ascii=False, default=str)
            except Exception:
                return str(payload)

        return str(payload)

    def _make_text_part(self, text: str) -> Part:
        return Part(root=TextPart(text=text))

    def _make_message(self, text: str) -> Message:
        return Message(
            message_id=str(uuid.uuid4()),
            role=Role.agent,
            parts=[self._make_text_part(text)],
        )


    def _extract_interaction(self, ev: dict, text_payload: str) -> str:
        interaction = ev.get("interaction")

        if isinstance(interaction, str) and interaction.strip():
            return interaction.strip()

        try:
            parsed = json.loads(text_payload)
            if isinstance(parsed, dict):
                value = parsed.get("interaction")
                if isinstance(value, str) and value.strip():
                    return value.strip()
        except Exception:
            pass

        return "complete"

    def _extract_query_text(self, context: RequestContext) -> str:
        if not context.message or not context.message.parts:
            raise ValueError("RequestContext must contain message parts")

        first_part = context.message.parts[0]

        root = getattr(first_part, "root", None)
        if root is not None:
            text = getattr(root, "text", None)
            if isinstance(text, str) and text.strip():
                return text.strip()

        text = getattr(first_part, "text", None)
        if isinstance(text, str) and text.strip():
            return text.strip()

        raise ValueError("Could not extract query text")

    async def execute(
        self,
        context: RequestContext,
        event_queue: EventQueue,
    ):
        if not context.task_id:
            raise ValueError("RequestContext missing task_id")

        if not context.context_id:
            raise ValueError("RequestContext missing context_id")

        updater = TaskUpdater(
            event_queue,
            context.task_id,
            context.context_id,
        )

        active_tool_name = "unknown_tool"
        final_response_text = ""

        try:
            if not context.current_task:
                await updater.submit()

            await updater.start_work()

            query = self._extract_query_text(context)

            logger.info("[%s] Received query: %s", self.agent_id, query[:200])

            # ✅ Human-readable status
            await updater.update_status(
                TaskState.working,
                message=updater.new_agent_message(
                    [self._make_text_part(f"{self.agent_id} started processing")]
                ),
            )

            out = self.execute_fn(query, context.context_id)

            # ✅ STREAMING CASE
            if inspect.isasyncgen(out):

                final_interaction = None
                final_response_text = ""

                async for ev in out:
                    await asyncio.sleep(0)

                    ev_type = ev.get("type")
                    payload = ev.get("payload")

                    # ================================
                    # ✅ TOOL CALL
                    # ================================
                    if ev_type == "tool_call":
                        tool_name = payload.get("tool_name")
                        tool_call_id = payload.get("tool_call_id")

                        active_tool_name = tool_name or "unknown_tool"

                        await updater.update_status(
                            TaskState.working,
                            metadata={
                                "type": "tool_event",
                                "phase": "call",
                                "tool_name": active_tool_name,
                                "tool_call_id": tool_call_id,
                            },
                        )

                        continue

                    # ================================
                    # ✅ TOOL OUTPUT
                    # ================================
                    if ev_type == "tool_output":
                        await updater.update_status(
                            TaskState.working,
                            metadata={
                                "type": "tool_event",
                                "phase": "response",
                                "tool_name": active_tool_name,
                                "tool_call_id": payload.get("tool_call_id"),
                                "data": payload.get("output"),
                            },
                        )
                        continue

                    # ================================
                    # ✅ AGENT RESPONSE (SOURCE OF TRUTH)
                    # ================================
                    if ev_type == "agent_response":

                        # interaction = ev.get("interaction", "complete")
                        # final_interaction = interaction  # ✅ ONLY set here
                        interaction = self._extract_interaction(ev, payload)
                        final_interaction = interaction

                        if isinstance(payload, list):
                            text_payload = "\n".join(
                                [f"{i+1}. {q}" for i, q in enumerate(payload)]
                            )
                        else:
                            text_payload = self._coerce_text(payload).strip()

                        final_response_text = text_payload

                        # ✅ FIX: use requires_input instead of working
                        if interaction == "request_input":
                            await updater.update_status(
                                TaskState.input_required,
                                message=updater.new_agent_message(
                                    [self._make_text_part(text_payload)]
                                ),
                                final=True
                            )
                            return
                        else:
                            await updater.update_status(
                                TaskState.working,
                                message=updater.new_agent_message(
                                    [self._make_text_part(text_payload)]
                                )
                            )

                        continue

                    # ================================
                    # ✅ USAGE (IGNORE FOR LIFECYCLE)
                    # ================================
                    if ev_type == "usage":
                        await updater.update_status(
                            TaskState.working,
                            metadata={
                                "type": "usage",
                                "input_tokens": payload.get("input_tokens"),
                                "output_tokens": payload.get("output_tokens"),
                                "total_tokens": payload.get("total_tokens"),
                            },
                        )
                        continue


                # return
                # ✅ IMPORTANT:
                # If the stream finished normally and did not request user input,
                # mark the A2A task as completed.
                if final_interaction == "request_input":
                    return

                await updater.complete(
                    message=self._make_message(
                        final_response_text or "Task completed"
                    )
                )

                return

            # ✅ NON-STREAMING CASE
            result = await out if inspect.isawaitable(out) else out
            result_text = self._coerce_text(result).strip()

            final_text = result_text or "Task completed"

            await updater.update_status(
                TaskState.working,
                message=updater.new_agent_message(
                    [self._make_text_part(final_text)]
                ),
            )

            await updater.complete(
                message=self._make_message(final_text)
            )

        except Exception as exc:
            logger.exception("Executor error for %s", self.agent_id)

            await updater.failed(
                message=self._make_message(f"Server Error: {exc}")
            )

    async def cancel(
        self,
        context: RequestContext,
        event_queue: EventQueue,
    ):
        raise ServerError(error=UnsupportedOperationError())

```

# OUTPUT on test

```bash
orchestrator) PS C:\git_clones\cto_kolkata_repos\aditya\orchestrator_v2> uv run .\cli_testing.py
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
