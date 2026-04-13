# services/invocation_context.py

from dataclasses import dataclass

@dataclass
class InvocationContext:
    """
    Runtime-only state for ONE agent invocation chain.
    Lives only for a single user turn.
    NEVER talks to DB.
    """

    # Current DB invocation row id
    invocation_id: int | None = None

    # Logical agent identity (for debugging / routing)
    agent_name: str | None = None

    # Session id used by the agent runner
    agent_session_id: str | None = None

    # Streaming text buffer (accumulates partial output)
    buffer: str = ""

    # Token accounting (optional but useful)
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
