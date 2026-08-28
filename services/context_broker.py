"""Build small, task-specific context envelopes for planners and agents."""
from __future__ import annotations

import json
from typing import Any


class ContextBroker:
    """Context selection boundary owned by Nexus.

    This deliberately does not expose the full ADK transcript to the planner.
    It returns active workflow facts and bounded plan outputs only.
    """

    def build_planner_context(self, *, orchestration_state: Any, prompt: str) -> dict:
        state = orchestration_state
        task = getattr(state, "task", None) or {}
        plan = getattr(state, "plan", None) or {}
        nodes = []
        for node in plan.get("nodes", []):
            if node.get("status") == "completed":
                nodes.append({
                    "node_id": node.get("node_id"),
                    "agent_name": node.get("agent_name"),
                    "output": self._bounded(node.get("output")),
                })
        return {
            "current_request": prompt,
            "active_task": {
                key: task.get(key)
                for key in ("owner", "state", "interaction", "task_id", "context_id")
                if task.get(key)
            },
            "active_plan": {
                "plan_id": plan.get("plan_id"),
                "status": plan.get("status"),
                "current_node_id": plan.get("current_node_id"),
                "completed_nodes": nodes,
            } if plan else None,
        }

    @staticmethod
    def _bounded(value: Any, limit: int = 2000) -> Any:
        if value is None:
            return None
        if isinstance(value, str):
            return value[:limit]
        try:
            encoded = json.dumps(value, default=str)
            return json.loads(encoded[:limit]) if len(encoded) <= limit else encoded[:limit]
        except Exception:
            return str(value)[:limit]
