# utils/agent_card_extractors.py

from typing import Any, Dict, List, Tuple

def extract_description_capabilities_skills(card: Dict[str, Any]) -> Tuple[str, List[str], List[str], List[Dict[str, Any]]]:
    """
    Extracts:
      - description: str
      - capabilities: list[str]  (normalized)
      - skills: list[str]        (skill names)
      - skills_full: list[dict]  (original skill objects when available)

    Supports:
      - description at top-level or under metadata.description
      - capabilities as:
          • dict/object (use keys as capability names)
          • list[str]   (use as-is)
          • list[dict]  (extract name or id)
      - skills as:
          • list[dict] with name/id
          • list[str]
    """
    md = card.get("metadata") or {}

    # --- description ---
    description = (
        card.get("description")
        or md.get("description")
        or ""
    )

    # --- capabilities ---
    capabilities_raw = card.get("capabilities") or md.get("capabilities")
    caps: List[str] = []

    if isinstance(capabilities_raw, dict):
        # common in many cards: use keys as capability names
        caps = [str(k) for k in capabilities_raw.keys()]
    elif isinstance(capabilities_raw, list):
        # could be list[str] or list[dict]
        for item in capabilities_raw:
            if isinstance(item, str):
                caps.append(item)
            elif isinstance(item, dict):
                name = item.get("name") or item.get("id") or item.get("title")
                if name:
                    caps.append(str(name))
    elif isinstance(capabilities_raw, str) and capabilities_raw.strip():
        # rare: comma-separated
        caps = [s.strip() for s in capabilities_raw.split(",") if s.strip()]
    else:
        caps = []

    # --- skills ---
    skills_raw = card.get("skills") or md.get("skills") or []
    skills: List[str] = []
    skills_full: List[Dict[str, Any]] = []

    if isinstance(skills_raw, list):
        for s in skills_raw:
            if isinstance(s, str):
                skills.append(s)
                skills_full.append({"name": s})
            elif isinstance(s, dict):
                name = s.get("name") or s.get("id") or s.get("title")
                if name:
                    skills.append(str(name))
                # Keep full object for downstream UIs:
                skills_full.append(s)
    elif isinstance(skills_raw, dict):
        # If provided as dict of skillName -> details
        for k, v in skills_raw.items():
            skills.append(str(k))
            if isinstance(v, dict):
                skills_full.append({"name": k, **v})
            else:
                skills_full.append({"name": k, "value": v})
    elif isinstance(skills_raw, str) and skills_raw.strip():
        # comma-separated fallback
        for s in [x.strip() for x in skills_raw.split(",") if x.strip()]:
            skills.append(s)
            skills_full.append({"name": s})

    return description, caps, skills, skills_full