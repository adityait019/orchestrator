#state/orchestration_state.py
from typing import Dict, Any, List, Optional, TypedDict


class TaskStateDict(TypedDict, total=False):
    owner: str
    state: str
    task_id: str
    interaction: str


class OrchestrationState:

    def __init__(self, data: dict | None = None):
        data = data or {}

        self.current_step: Optional[str] = data.get("current_step")
        self.active_agent: Optional[str] = data.get("active_agent")
        self.last_output: Optional[str] = data.get("last_output")

        self.artifacts: List[dict] = data.get("artifacts", [])
        self.memory: Dict[str, Any] = data.get("memory", {})

        # ✅ typed task
        self.task: Optional[TaskStateDict] = data.get("task")

    def to_dict(self):
        return {
            "current_step": self.current_step,
            "active_agent": self.active_agent,
            "last_output": self.last_output,
            "artifacts": self.artifacts,
            "memory": self.memory,
            "task": self.task,
        }
