from typing import Any, Dict, List, Tuple
from agents.agent import root_agent,BASE_INSTRUCTION
import logging

logger=logging.getLogger(__name__)

def extract_description_capabilities_skills(
    card: Dict[str, Any]
) -> Tuple[str, List[str], List[str], List[Dict[str, Any]]]:

    md = card.get("metadata") or {}

    # -------------------------
    # DESCRIPTION
    # -------------------------
    description = (
        card.get("description")
        or md.get("description")
        or ""
    )

    # -------------------------
    # CAPABILITIES (ENRICHED)
    # -------------------------
    capabilities_raw = card.get("capabilities") or md.get("capabilities")
    caps: List[str] = []

    # ✅ Base capability keys (streaming, extensions etc.)
    if isinstance(capabilities_raw, dict):
        caps.extend([str(k) for k in capabilities_raw.keys()])

        # ✅ Extract deep extension intelligence
        extensions = capabilities_raw.get("extensions", [])
        if isinstance(extensions, list) and extensions:
            params = extensions[0].get("params", {})

            # --- specialization ---
            spec = params.get("specialization", {})
            primary = spec.get("primary")
            if primary:
                caps.append(f"domain:{primary}")

            for d in spec.get("domain_specific", []):
                caps.append(f"domain:{d}")

            # --- platforms ---
            cap_block = params.get("capabilities", {})
            for p in cap_block.get("platforms", []):
                caps.append(f"platform:{p}")

            # --- frameworks ---
            for f in cap_block.get("frameworks", []):
                caps.append(f"framework:{f}")

            # --- languages ---
            for l in cap_block.get("languages", []):
                caps.append(f"language:{l}")

            # --- HITL flag ---
            if params.get("human_in_loop"):
                caps.append("requires_human_approval")

    elif isinstance(capabilities_raw, list):
        for item in capabilities_raw:
            if isinstance(item, str):
                caps.append(item)
            elif isinstance(item, dict):
                name = item.get("name") or item.get("id")
                if name:
                    caps.append(str(name))

    # -------------------------
    # SKILLS (ENRICHED WITH DESCRIPTION)
    # -------------------------
    skills_raw = card.get("skills") or md.get("skills") or []
    skills: List[str] = []
    skills_full: List[Dict[str, Any]] = []

    if isinstance(skills_raw, list):
        for s in skills_raw:
            if isinstance(s, dict):
                name = s.get("name") or s.get("id")
                desc = s.get("description", "")

                # ✅ combine name + description for LLM reasoning
                if name and desc:
                    skills.append(f"{name}: {desc}")
                elif name:
                    skills.append(name)

                skills_full.append(s)

            elif isinstance(s, str):
                skills.append(s)
                skills_full.append({"name": s})

    # -------------------------
    # DEDUP
    # -------------------------
    caps = list(dict.fromkeys(caps))
    skills = list(dict.fromkeys(skills))

    return description, caps, skills, skills_full



def build_reasoning_profile(name, description, caps, skills):
    return f"""
Agent: {name}

Description:
{description}

Capabilities:
{chr(10).join(f"- {c}" for c in caps)}

Skills:
{chr(10).join(f"- {s}" for s in skills)}
""".strip()



async def build_agent_prompt(agents):

    logger.info('Building Agent prompt..')
    blocks = []

    for a in agents:
        caps = getattr(a, "capabilities", [])
        skills = getattr(a, "skills", [])

        block = f"""
Agent name: {a.name}

Agent description:
{a.description}

Agent capabilities:
{chr(10).join(f"- {c}" for c in caps)}

Agent skills:
{chr(10).join(f"- {s}" for s in skills)}
"""
        blocks.append(block.strip())

    return "\n\n---\n\n".join(blocks)


async def dynamic_instruction(ctx):
    agents = root_agent.sub_agents
    agent_context = await build_agent_prompt(agents)
    
    return f"""
{BASE_INSTRUCTION}

AVAILABLE AGENTS:
{agent_context}

AGENT SELECTION POLICY:
- Select based on skills, domain, capabilities
- DO NOT rely only on description

""".strip()