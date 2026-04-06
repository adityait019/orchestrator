from google.adk.runners import Runner
from agents.agent import root_agent

def create_runner(session_service):
    return Runner(
        agent=root_agent,
        app_name="my_agent_app",
        session_service=session_service,
    )