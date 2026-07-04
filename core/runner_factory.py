from google.adk.runners import Runner
from agents.agent import root_agent


def create_runner(session_service,memory_service):
    runner= Runner(
        agent=root_agent,
        app_name="my_agent_app",
        session_service=session_service,
        memory_service=memory_service,
    )
    return runner