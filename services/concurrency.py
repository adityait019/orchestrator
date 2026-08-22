"""Process-local concurrency controls for the ASGI worker.

Ordering rule: one conversation executes one turn at a time. Different
conversations may run concurrently, capped by the global turn semaphore.
For multi-worker deployments this must be complemented by a distributed lock.
"""
from __future__ import annotations

import asyncio
import os
from contextlib import asynccontextmanager


class SessionExecutionCoordinator:
    def __init__(self, max_concurrent_turns: int | None = None):
        limit = max_concurrent_turns or int(os.getenv("MAX_CONCURRENT_TURNS", "20"))
        self._capacity = asyncio.Semaphore(limit)
        self._locks: dict[tuple[str, str], asyncio.Lock] = {}
        self._guard = asyncio.Lock()

    async def _lock_for(self, user_id: str, session_id: str) -> asyncio.Lock:
        key = (user_id, session_id)
        async with self._guard:
            return self._locks.setdefault(key, asyncio.Lock())

    @asynccontextmanager
    async def turn(self, user_id: str, session_id: str):
        lock = await self._lock_for(user_id, session_id)
        async with self._capacity:
            async with lock:
                yield


# The application has one coordinator per process. This deliberately avoids
# unbounded runner/remote-agent work when many WebSocket sessions arrive.
session_execution_coordinator = SessionExecutionCoordinator()

# Artifact downloads are usually the most expensive auxiliary operation.
external_io_semaphore = asyncio.Semaphore(int(os.getenv("MAX_CONCURRENT_EXTERNAL_IO", "20")))
