#agent.py
from google.genai.types import GenerateContentConfig,ThinkingConfig
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
HITL Rules:
1. Always ask for user confirmation before executing any action that could have significant consequences.
2. If the user provides a vague or ambiguous instruction, ask clarifying questions to ensure you understand their intent.
3. If the user asks you to perform a task that is outside your capabilities, inform them and suggest alternative approaches or resources.

PLANNING Rules:
1. When transferring a task to a sub-agent, provide clear instructions and context to ensure they understand the user's intent.

Sub-agent Coordination:
1. When a task requires the expertise of a specialized sub-agent, transfer the task to that sub-agent.
2. If a sub-agent is unable to complete a task, escalate the issue back to the root agent for further guidance.
3. if sub-agent responds and user is ask to do task for the generated response, then transfer the task to that sub-agent for execution.

MANDATORY:
1. Always understand the user's request and the context before taking any action.
some times user may ask to do task for the generated response, then transfer the task to that sub-agent for execution.
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

## set ENV variables
# NVIDIA_NIM_API_KEY = os.environ["NVIDIA_NIM_API_KEY"] 
# NVIDIA_NIM_API_BASE = os.environ["NVIDIA_NIM_API_BASE"]

# model="nvidia_nim/nvidia/nemotron-3-ultra-550b-a55b"


# llm=LiteLlm(
#     model=model,
#     api_key=NVIDIA_NIM_API_KEY,
#     api_base=NVIDIA_NIM_API_BASE,
# )


root_agent = LlmAgent(
    name='Nexus',
    model=llm,
    description='A central orchestrator that understands user intent and coordinates specialized agents to complete tasks.',
    sub_agents=[],
    generate_content_config=content_config,
    # The provided HITL callback's signature doesn't match the LlmAgent
    # expected type in this environment. Omit it to avoid type errors.
    after_model_callback=hitl_after_model_callback,
    before_model_callback=hitl_before_model_callback,
    instruction=BASE_INSTRUCTION,
    # tools=[load_memory_tool]
    

)



