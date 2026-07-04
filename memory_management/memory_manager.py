# memory_management/memory_manager.py

"""Plug DatabaseMemoryService into an ADK Runner so an agent can recall past sessions.

This script:
  1. Persists a prior conversation into SQLite-backed memory.
  2. Runs a fresh agent turn that calls the built-in `load_memory` tool.
  3. The agent can then reason over what it remembered from the earlier session.

Run:
    pip install "adk-database-memory[sqlite]"
    pip install google-adk  # for the Agent / Runner imports
    export GOOGLE_API_KEY=...   # any provider supported by your ADK Agent setup
    python examples/with_runner.py
"""

from __future__ import annotations

import asyncio

from google.adk.agents import Agent
from google.adk.events.event import Event
from google.adk.runners import InMemoryRunner
from google.adk.sessions.session import Session
from google.adk.tools.load_memory_tool import load_memory_tool
from google.genai import types
import os
from dotenv import load_dotenv
from adk_database_memory import DatabaseMemoryService
from core.config import APP_NAME

load_dotenv(override=True)
DB_URL = os.getenv("DATABASE_URL","not-provided")
USER_ID = "alice"


def prior_session() -> Session:
    return Session(
        app_name=APP_NAME,
        user_id=USER_ID,
        id="prior-session",
        last_update_time=1.0,
        events=[
            Event(
                id="p1",
                invocation_id="inv-p1",
                author="user",
                timestamp=1.0,
                content=types.Content(
                    parts=[types.Part(text="My favorite programming language is Python.")]
                ),
            ),
            Event(
                id="p2",
                invocation_id="inv-p2",
                author="user",
                timestamp=2.0,
                content=types.Content(
                    parts=[types.Part(text="I work mostly on agent frameworks and RAG systems.")]
                ),
            ),
        ],
    )


async def main() -> None:
    memory = DatabaseMemoryService(DB_URL)

    async with memory:
        await memory.add_session_to_memory(prior_session())

        agent = Agent(
            name="recall_assistant",
            model="gemini-flash-latest",
            instruction=(
                "You are a helpful assistant. When the user asks about themselves, "
                "use the load_memory tool to recall what you know about them before "
                "answering."
            ),
            tools=[load_memory_tool],
        )

        runner = InMemoryRunner(agent=agent, app_name=APP_NAME)
        runner.memory_service = memory

        session = await runner.session_service.create_session(
            app_name=APP_NAME, user_id=USER_ID
        )

        user_message = types.Content(
            parts=[types.Part(text="What do you remember about me?")]
        )
        async for event in runner.run_async(
            user_id=USER_ID, session_id=session.id, new_message=user_message
        ):
            if event.content and event.content.parts:
                for part in event.content.parts:
                    if part.text:
                        print(f"[{event.author}] {part.text}")


if __name__ == "__main__":
    asyncio.run(main())
