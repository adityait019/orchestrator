"""Structured, plan-first routing for multi-agent requests."""
from __future__ import annotations

import json
import logging
import os
import uuid
from typing import Any

from litellm import acompletion

logger = logging.getLogger(__name__)


class PlanningService:
    """Ask the configured model for a constrained sequential execution plan."""

    def _catalog(self, agents: list[Any]) -> list[dict[str, Any]]:
        return [
            {
                "name": agent.name,
                "description": getattr(agent, "description", ""),
                "capabilities": list(getattr(agent, "capabilities", []) or []),
                "skills": list(getattr(agent, "skills_full", []) or []),
            }
            for agent in agents
        ]

    async def create_plan(
        self,
        *,
        prompt: str,
        agents: list[Any],
        uploaded_file_urls: list[str],
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        if not agents:
            return None

        deployment = os.getenv("DEPLOYMENT_NAME")
        if not deployment:
            logger.warning("Planner skipped: DEPLOYMENT_NAME is not configured")
            return None

        request = {
            "user_request": prompt,
            "uploaded_files": uploaded_file_urls,
            "agent_catalog": self._catalog(agents),
            # This is a bounded task envelope selected by Nexus, not a raw
            # transcript. The planner remains stateless.
            "context": context or {},
        }
        instruction = """You are Nexus's planning component. Decide whether this request needs one or more
remote agents. Return JSON only, with this exact shape:
{
  "requires_plan": true|false,
  "summary": "short user-facing plan summary",
  "nodes": [{
    "node_id": "n1", "agent_name": "exact catalog name", "query": "specific instruction",
    "depends_on": [], "use_uploaded_files": false
  }]
}
Use a plan only when a remote agent can materially help. Nexus owns the conversation and will
compose the final user-facing answer; do not ask the planner to summarize the transcript.
For a plan, make nodes sequential. Each dependency must refer to an earlier node, and every
node must list all earlier nodes whose output it needs. In particular, a notification node
that reports payment or shipping must depend on the payment and shipping nodes, not only the
order node. Set use_uploaded_files only for nodes that actually need the original files.
Downstream nodes receive the outputs of every declared dependency automatically. If a required
user input is missing, keep the node in the plan and let that agent return input-required.
Never invent agents or include markdown."""

        try:
            # LiteLLM's type stub exposes a stream wrapper even for non-streaming
            # calls; the configured JSON response is the regular completion shape.
            response: Any = await acompletion(
                model=f"azure/{deployment}",
                api_key=os.getenv("AZURE_API_KEY"),
                api_base=os.getenv("AZURE_API_BASE"),
                api_version=os.getenv("AZURE_API_VERSION"),
                messages=[
                    {"role": "system", "content": instruction},
                    {"role": "user", "content": json.dumps(request)},
                ],
                response_format={"type": "json_object"},
                temperature=0,
            )
            content = response.choices[0].message.content or "{}"
            raw = json.loads(content)
        except Exception:
            logger.exception("Plan generation failed; falling back to reactive routing")
            return None

        return self._validate(raw, agents, uploaded_file_urls, prompt)

    def _validate(
        self,
        raw: Any,
        agents: list[Any],
        uploaded_file_urls: list[str],
        prompt: str,
    ) -> dict[str, Any] | None:
        if not isinstance(raw, dict) or not raw.get("requires_plan"):
            return None

        names = {agent.name for agent in agents}
        nodes = raw.get("nodes")
        if not isinstance(nodes, list) or not nodes:
            return None

        validated: list[dict[str, Any]] = []
        known_ids: set[str] = set()
        for position, node in enumerate(nodes, start=1):
            if not isinstance(node, dict) or node.get("agent_name") not in names:
                return None
            node_id = str(node.get("node_id") or f"n{position}")
            if node_id in known_ids:
                return None
            dependencies = node.get("depends_on") or []
            if not isinstance(dependencies, list) or any(dep not in known_ids for dep in dependencies):
                return None
            query = str(node.get("query") or prompt).strip()
            if not query:
                return None
            validated.append(
                {
                    "node_id": node_id,
                    "agent_name": node["agent_name"],
                    "query": query,
                    "depends_on": dependencies,
                    "use_uploaded_files": bool(node.get("use_uploaded_files")),
                    "status": "pending",
                }
            )
            known_ids.add(node_id)

        return {
            "plan_id": str(uuid.uuid4()),
            "status": "awaiting_approval",
            "summary": str(raw.get("summary") or "Execute the proposed agent plan."),
            "original_prompt": prompt,
            "uploaded_file_urls": uploaded_file_urls,
            "nodes": validated,
        }
