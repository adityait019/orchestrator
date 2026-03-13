from google.adk.agents.remote_a2a_agent import AGENT_CARD_WELL_KNOWN_PATH
from google.adk.agents.remote_a2a_agent import RemoteA2aAgent

pmo_agent = RemoteA2aAgent(
    name="project_management_agent",
    description="A helpful Assistant who Manage Project",
    agent_card=(
        f"http://10.73.83.83:8010/{AGENT_CARD_WELL_KNOWN_PATH}"
    ),
)

rocket_analyzer_agent=RemoteA2aAgent(
    name="rocket_analyzer_agent",
    description="Expert agent for analyzing Rocket UniVerse codebase architecture and generating PlantUML diagrams. Accepts uploaded files as additional context",
    agent_card=(
        f"http://10.73.89.35:8000/{AGENT_CARD_WELL_KNOWN_PATH}"
    )
)

code_reviewer_agent=RemoteA2aAgent(
    name='code_reviewer_agent',
    description='A helpful Assistant who review code.',
    agent_card=(
        f"http://10.73.83.83:9999/{AGENT_CARD_WELL_KNOWN_PATH}"
    )
)

pricing_model_agent=RemoteA2aAgent(
    name='classification_bot',
    description=(
        "Consumes signed file URLs from the Orchestrator upload service, downloads locally, "
        "applies SUPER/TUNED and finalize logic, and runs Step‑0 classification. "
        "All classified rows remain 'PENDING' for manual approval."
    ),
    agent_card=(
        f"http://10.73.83.83:8016/{AGENT_CARD_WELL_KNOWN_PATH}"
    ),
    full_history_when_stateless=True

)

pricing_scoring_agent=RemoteA2aAgent(
    name='pricing_scoring_bot',
    description=(
        
    "Consumes signed file URLs from the Orchestrator upload service, downloads locally, "
    "and runs Step‑2 scoring with a control plane ZIP and an answers workbook. "
    "Outputs are written to the specified out_dir for HITL review."

    ),
    agent_card=(
        f"http://10.73.83.83:8018/{AGENT_CARD_WELL_KNOWN_PATH}"
    )


)

