# services/invocation_context.py

from dataclasses import dataclass, field
from typing import Optional, Dict, Any, Set

from state.orchestration_state import OrchestrationState


@dataclass
class AgentRuntime:
    invocation_id: int
    agent_name: str

    buffer: str = ""
    output_payload: dict | None = None

    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0

    last_emitted_text: Optional[str] = None

    last_hash: Optional[str] = None
    last_tool_response: Optional[Any] = None

    applied_token_usage_keys: Set[tuple] = field(default_factory=set)  # ✅ ADD — dedupes cumulative token_usage snapshots
    processed_file_urls: Set[str] = field(default_factory=set)   # ✅ ADD

    input_artifacts: list = field(default_factory=list)
    output_artifacts: list = field(default_factory=list)

    completed: bool = False
    failed: bool = False
    
@dataclass
class InvocationContext:
    # ✅ runtime tracking
    runtimes: Dict[int, AgentRuntime] = field(default_factory=dict)
    active_invocation_id: Optional[int] = None
    # Root invocation for the current prompt/approved plan. Child agent
    # invocations link back to this value through parent_invocation_id.
    root_invocation_id: Optional[int] = None

    # ✅ orchestration state (MAIN FIX)
    orch_state: Optional[OrchestrationState] = None

    # ✅ execution planning
    plan_id: Optional[str] = None
    task_node_id: Optional[str] = None

    # ✅ routing decisions
    approved_agent: Optional[str] = None

    # ✅ service references (optional, but OK)
    state_manager: Any = None

    pending_state_update: bool = False

    # Correlation identifiers for a complete conversation turn and its graph
    # of planner, invocation, transfer, and A2A events.
    trace_id: Optional[str] = None
    turn_id: Optional[str] = None
    active_span_id: Optional[str] = None
