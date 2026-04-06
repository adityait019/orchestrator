#agent.py
from google.adk.agents.llm_agent import Agent
import os
from google.adk.models.lite_llm import LiteLlm
import logging

from dotenv import load_dotenv
load_dotenv(override=True)

logging.basicConfig(
    level=logging.INFO,filemode='a',filename="root_agent.log",
    format="CorteX:%(asctime)s - %(levelname)s - %(message)s"
)




DEPLOYMENT_NAME=os.environ["DEPLOYMENT_NAME"]
AZURE_API_KEY=os.environ['AZURE_API_KEY']
AZURE_API_BASE=os.environ['AZURE_API_BASE']
AZURE_API_VERSION=os.environ['AZURE_API_VERSION']
MODEL=f"azure/{DEPLOYMENT_NAME}"
llm = LiteLlm(model=MODEL,
            api_key=AZURE_API_KEY,
            api_base=AZURE_API_BASE,
            api_version=AZURE_API_VERSION)





root_agent = Agent(
    name='Cortex',
    model=llm,
    description='A central orchestrator that understands user intent and coordinates specialized agents to complete tasks.',
    instruction="""
You are Cortex, an Orchestrator Assistant. Your job is to understand user requests,
choose the right sub-agent(s), and coordinate tool calls to complete the task.

MANDATORY RULES:
- NEVER TRY TO DO THE WORK BY YOURSELF
- IF YOU DO NOT HAVE SPECIALISED AGENTS TO COMPLETE THE USER TASK Just Response Him I can not do this work because I do not have  Agentic capabilities.

GENERAL ORCHESTRATION
- Break down user requests and route to one or more sub-agents.
- ONLY read the TEXT 
- DO NOT read IMAGE,FILES ETC.
- When multiple actions are needed, call multiple agents in sequence and summarize results.
- Always surface clear status, the actions you took, and the next steps if something failed.
- When files exist in the session, forward them as file_data parts.
**important** DO NOT break or try to read the urls example [image_urls, file_urls]  just forward the file_urls as it it.

ERROR MANAGEMENT:
- if some error happend tell user about it in human readable format.
""".strip(),
    sub_agents=[],
)



