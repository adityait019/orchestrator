# state/state_manager.py

import logging
import threading
from typing import Dict

from state.models import RemoteAgentState
from state.orchestration_state import OrchestrationState

logger = logging.getLogger(__name__)


class StateManager:

    def __init__(self, session_manager):
        self.session_manager = session_manager

        # ✅ In-memory cache:
        # (user_id, session_id) -> { scope_key:agent_name : RemoteAgentState }
        self._inmemory_state: Dict[tuple, Dict[str, RemoteAgentState]] = {}
        self._inmemory_state_lock = threading.RLock()

    # =============================
    # ORCHESTRATION STATE ✅ (ADK-backed)
    # =============================

    async def load_orchestration_state(self, user_id: str, session_id: str) -> OrchestrationState:
        session = await self.session_manager.get_session(user_id, session_id)

        raw = session.state.get("orchestrator", {}) if session and session.state else {}

        return OrchestrationState(raw)

    async def save_orchestration_state(self, user_id: str, session_id: str, state: OrchestrationState):
        session = await self.session_manager.ensure_session(user_id, session_id)

        event = self.session_manager._build_state_event({
            "orchestrator": state.to_dict()
        })

        await self.session_manager.session_service.append_event(
            session=session,
            event=event
        )

    # =============================
    # REMOTE AGENT STATE (CACHE ONLY ✅)
    # =============================

    async def save_remote_state(
        self,
        user_id: str,
        session_id: str,
        state: RemoteAgentState
    ):
        """
        ✅ Store ONLY in memory → prevents DB contention
        """
        key = f"{state.scope_key}:{state.agent_name}"
        cache_key = (user_id, session_id)

        with self._inmemory_state_lock:
            if cache_key not in self._inmemory_state:
                self._inmemory_state[cache_key] = {}
            self._inmemory_state[cache_key][key] = state

        logger.info(
            "[STATE CACHE UPDATED] %s -> %s",
            key,
            state.remote_context_id
        )

    def get_cached_remote_state(
        self,
        user_id: str,
        session_id: str,
        agent_name: str,
        scope_key: str,
    ) -> RemoteAgentState:
        """
        ✅ Fast in-memory read (sync safe)
        """
        key = f"{scope_key}:{agent_name}"
        cache_key = (user_id, session_id)

        with self._inmemory_state_lock:
            store = self._inmemory_state.get(cache_key, {})
            state = store.get(key)

        if state:
            return state

        return RemoteAgentState(agent_name=agent_name, scope_key=scope_key)
