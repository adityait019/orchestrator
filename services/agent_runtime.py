"""Shared synchronization primitives for the in-memory ADK agent registry."""

import asyncio


# All routes and background tasks mutate ``root_agent.sub_agents`` through
# this one lock.  Separate module-level locks do not protect shared state.
agent_runtime_lock = asyncio.Lock()
