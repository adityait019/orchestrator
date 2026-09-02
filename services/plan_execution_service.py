"""Deterministic sequential execution of an approved agent plan."""
from __future__ import annotations

import json
import logging
from types import SimpleNamespace
from typing import Any

from google.genai.types import FileData, Part

from database.models import AgentDependency
from services.invocation_context import AgentRuntime
from observability import trace_span

logger = logging.getLogger(__name__)


class PlanExecutionService:
    def __init__(self, db_session_factory, agent_service):
        self.db = db_session_factory
        self.agent_service = agent_service

    async def _record_dependency(self, parent_id: int, child_id: int) -> None:
        async with self.db() as db:
            db.add(
                AgentDependency(
                    parent_invocation_id=parent_id,
                    child_invocation_id=child_id,
                    dependency_type="plan_output",
                )
            )
            await db.commit()

    @staticmethod
    def _upstream_text(node: dict[str, Any], outputs: dict[str, Any]) -> str:
        upstream = {dep: outputs.get(dep) for dep in node.get("depends_on", [])}
        if not upstream:
            return node["query"]
        serialized = json.dumps(upstream, default=str)
        return f"{node['query']}\n\nUpstream outputs (use these as input):\n{serialized}"

    @staticmethod
    def _file_parts(urls: list[str]) -> list[Part]:
        return [
            Part(file_data=FileData(file_uri=url, mime_type="application/octet-stream"))
            for url in urls
        ]

    async def execute(
        self,
        *,
        plan: dict[str, Any],
        root_invocation_id: int,
        workflow_id: str,
        user_id: str,
        session_id: str,
        agents: list[Any],
        processor: Any,
        invocation_ctx: Any,
        tenant_id: str | None,
        resume_input: str | None = None,
    ) -> dict[str, Any]:
        agent_map = {agent.name: agent for agent in agents}
        # Keep completed node results in the plan so a later websocket turn can
        # resume without replaying already-finished agents.
        outputs: dict[str, Any] = {
            n["node_id"]: n.get("output")
            for n in plan.get("nodes", [])
            if n.get("status") == "completed" and "output" in n
        }
        parent_by_node: dict[str, int] = {}
        previous_invocation_id = root_invocation_id

        resume_node_id = plan.get("current_node_id")
        if resume_input is not None and not resume_node_id:
            resume_node_id = next(
                (n["node_id"] for n in plan.get("nodes", []) if n.get("status") == "awaiting_input"),
                None,
            )
        if resume_input is not None and not resume_node_id:
            raise RuntimeError("Plan is awaiting input but has no resumable node")

        for node in plan["nodes"]:
            if node.get("status") == "completed":
                if node.get("invocation_id"):
                    parent_by_node[node["node_id"]] = int(node["invocation_id"])
                    previous_invocation_id = int(node["invocation_id"])
                continue
            if resume_input is not None and node["node_id"] != resume_node_id:
                continue
            agent = agent_map.get(node["agent_name"])
            if not agent:
                raise RuntimeError(f"Planned agent is no longer available: {node['agent_name']}")

            query = self._upstream_text(node, outputs)
            if resume_input is not None and node["node_id"] == resume_node_id:
                query = f"{query}\n\nUser response to the requested input:\n{resume_input}"
            input_urls = plan.get("uploaded_file_urls", []) if node.get("use_uploaded_files") else []
            invocation, _ = await self.agent_service.start_invocation(
                workflow_id=workflow_id,
                user_id=user_id,
                session_id=session_id,
                agent_name=node["agent_name"],
                prompt=query,
                args={
                    "plan_id": plan["plan_id"],
                    "task_node_id": node["node_id"],
                    "trace_id": invocation_ctx.trace_id,
                    "turn_id": invocation_ctx.turn_id,
                    "parent_span_id": invocation_ctx.active_span_id,
                },
                plan_id=plan["plan_id"],
                task_node_id=node["node_id"],
                # A resumed node is a child of its paused attempt; a fresh node
                # is linked to the preceding plan node (or the root).
                parent_invocation_id=(
                    int(node["invocation_id"])
                    if resume_input is not None and node.get("invocation_id")
                    else previous_invocation_id
                ),
                input_artifacts=[{"url": url} for url in input_urls],
            )
            for dependency in node.get("depends_on", []):
                await self._record_dependency(parent_by_node[dependency], invocation.id)

            runtime = AgentRuntime(invocation_id=invocation.id, agent_name=node["agent_name"])
            invocation_ctx.runtimes[invocation.id] = runtime
            invocation_ctx.active_invocation_id = invocation.id
            invocation_ctx.orch_state.current_step = node["node_id"]
            invocation_ctx.orch_state.active_agent = node["agent_name"]
            node["status"] = "running"

            adapter_context = SimpleNamespace(invocation_id=str(invocation.id), branch=None)
            event_context = {
                "workflow_id": workflow_id,
                "user_id": user_id,
                "session_id": session_id,
                "prompt": query,
                "tenant_id": tenant_id,
                "invocation_ctx": invocation_ctx,
                "trace_id": invocation_ctx.trace_id,
                "turn_id": invocation_ctx.turn_id,
            }
            await processor.emitter.status("plan_node_started", agent=node["agent_name"], node_id=node["node_id"])
            stream_kwargs = {"message": query, "extra_genai_parts": self._file_parts(input_urls)}
            task = invocation_ctx.orch_state.task or {}
            if resume_input is not None and node["node_id"] == resume_node_id and task.get("owner") == node["agent_name"]:
                if task.get("task_id"):
                    stream_kwargs["task_id"] = task["task_id"]
                if task.get("context_id"):
                    stream_kwargs["context_id"] = task["context_id"]
            with trace_span("a2a.agent.invoke", **{
                "agent.name": node["agent_name"],
                "plan.id": plan["plan_id"],
                "task.node.id": node["node_id"],
                "invocation.id": str(invocation.id),
            }):
                async for parsed in agent._adapter.stream_message(**stream_kwargs):
                    await processor.process(agent._build_adk_event(parsed, adapter_context), event_context)

            task = invocation_ctx.orch_state.task or {}
            if task.get("interaction") == "request_input" and not runtime.completed:
                node["status"] = "awaiting_input"
                node["invocation_id"] = invocation.id
                node["output"] = runtime.output_payload or runtime.buffer
                plan["status"] = "awaiting_input"
                plan["current_node_id"] = node["node_id"]
                return outputs

            if runtime.failed:
                node["status"] = "failed"
                node["invocation_id"] = invocation.id
                node["output"] = runtime.output_payload or runtime.buffer
                plan["status"] = "failed"
                plan["error"] = node["output"]
                logger.warning(
                    "Plan %s stopped after failed node %s (%s)",
                    plan.get("plan_id"), node["node_id"], node["agent_name"],
                )
                return outputs

            if not runtime.completed:
                await self.agent_service.complete_invocation(
                    runtime.invocation_id,
                    runtime.output_payload or runtime.buffer,
                    runtime.input_tokens,
                    runtime.output_tokens,
                    runtime.total_tokens,
                )
                runtime.completed = True

            outputs[node["node_id"]] = runtime.output_payload or runtime.buffer
            parent_by_node[node["node_id"]] = invocation.id
            previous_invocation_id = invocation.id
            node["invocation_id"] = invocation.id
            node["output"] = outputs[node["node_id"]]
            node["status"] = "completed"

        plan["status"] = "completed"
        plan.pop("current_node_id", None)
        return outputs
