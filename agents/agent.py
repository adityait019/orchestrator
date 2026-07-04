#agent.py
from google.genai.types import GenerateContentConfig
from google.adk.agents.llm_agent import LlmAgent
import os
from google.adk.models.lite_llm import LiteLlm
import logging
from agents.hitl_handler import hitl_after_model_callback,hitl_before_model_callback
from google.adk.tools.load_memory_tool import load_memory_tool
from dotenv import load_dotenv
load_dotenv(override=True)

logger = logging.getLogger(__name__)
content_config=GenerateContentConfig(
    temperature=0.1,
    top_p=0.9,
    max_output_tokens=1024,
    stop_sequences=["<END_PLAN>"],
)
BASE_INSTRUCTION = """
You are an orchestrator that can either:

1. Respond directly if the request is simple or general
2. Delegate to an agent if the task requires specific capabilities or skills

When deciding:

- Compare user intent with:
  • agent capabilities
  • agent skills
  • domains

- Prefer agents when:
  • specialized processing is needed
  • external systems are involved
  • actions must be executed

- Prefer self-response when:
  • the request is general conversation
  • no agent adds value

When transferring:
- Select the most relevant agent based on capabilities and skills
- Do not guess — rely on metadata provided
""".strip()

DEPLOYMENT_NAME=os.environ["DEPLOYMENT_NAME"]
AZURE_API_KEY=os.environ['AZURE_API_KEY']
AZURE_API_BASE=os.environ['AZURE_API_BASE']
AZURE_API_VERSION=os.environ['AZURE_API_VERSION']
MODEL=f"azure/{DEPLOYMENT_NAME}"
llm = LiteLlm(model=MODEL,
            api_key=AZURE_API_KEY,
            api_base=AZURE_API_BASE,
            api_version=AZURE_API_VERSION)





root_agent = LlmAgent(
    name='Cortex',
    model=llm,
    description='A central orchestrator that understands user intent and coordinates specialized agents to complete tasks.',
    sub_agents=[],
    generate_content_config=content_config,
    after_model_callback=hitl_after_model_callback,
    before_model_callback=hitl_before_model_callback,
    tools=[load_memory_tool]
    

)



