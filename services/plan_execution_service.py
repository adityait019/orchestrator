"""Deterministic sequential execution of an approved agent plan."""
from __future__ import annotations

import json
import logging
from types import SimpleNamespace
from typing import Any

from google.genai.types import FileData, Part

from database.models import AgentDependency
from services.invocation_context import AgentRuntime

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
    ) -> dict[str, Any]:
        agent_map = {agent.name: agent for agent in agents}
        outputs: dict[str, Any] = {}
        parent_by_node: dict[str, int] = {}
        previous_invocation_id = root_invocation_id

        for node in plan["nodes"]:
            agent = agent_map.get(node["agent_name"])
            if not agent:
                raise RuntimeError(f"Planned agent is no longer available: {node['agent_name']}")

            query = self._upstream_text(node, outputs)
            input_urls = plan.get("uploaded_file_urls", []) if node.get("use_uploaded_files") else []
            invocation, _ = await self.agent_service.start_invocation(
                workflow_id=workflow_id,
                user_id=user_id,
                session_id=session_id,
                agent_name=node["agent_name"],
                prompt=query,
                args={"plan_id": plan["plan_id"], "task_node_id": node["node_id"]},
                plan_id=plan["plan_id"],
                task_node_id=node["node_id"],
                parent_invocation_id=previous_invocation_id,
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
            }
            await processor.emitter.status("plan_node_started", agent=node["agent_name"], node_id=node["node_id"])
            async for parsed in agent._adapter.stream_message(
                message=query,
                extra_genai_parts=self._file_parts(input_urls),
            ):
                await processor.process(agent._build_adk_event(parsed, adapter_context), event_context)

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
            node["status"] = "completed"

        plan["status"] = "completed"
        return outputs
