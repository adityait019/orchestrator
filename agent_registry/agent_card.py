
import json
import urllib.request
from urllib.error import URLError, HTTPError
from remote_agents import pricing_model_agent

def print_agent_card_fields(url: str):
    """
    Fetches an Agent Card JSON from `url`, validates core fields,
    and prints selected information.
    """
    try:
        with urllib.request.urlopen(url, timeout=10) as resp:
            content_type = resp.headers.get("Content-Type", "")
            data = resp.read().decode("utf-8")
    except (HTTPError, URLError) as e:
        print(f"[ERROR] Failed to fetch URL: {e}")
        return

    try:
        card = json.loads(data)
    except json.JSONDecodeError as e:
        print(f"[ERROR] Invalid JSON: {e}")
        return

    # Basic validation
    required_fields = ["id", "name", "description", "protocolVersion", "skills"]
    missing = [f for f in required_fields if f not in card]
    if missing:
        print(f"[WARN] Missing required fields: {missing}")
# Skills
    skills = card.get("skills", [])
    # Print summary
    print("=== Agent Card Summary ===")
    # print(f"ID:            {card.get('id')}")
    print(f"Name:          {card.get('name')}")
    print(f"Description:   {card.get('description')}")
    print(f"Protocol:      {card.get('protocolVersion')}")
    print(f"Transport:     {card.get('preferredTransport')}")
    print(f"URL:           {card.get('url')}")
    print(f"Version:       {card.get('version')}")
    print(f"Created At:    {card.get('createdAt')}")

    # Capabilities / Modes
    print("\n-- Modes --")
    print(f"Input Modes:   {', '.join(card.get('defaultInputModes', [])) or 'n/a'}")
    print(f"Output Modes:  {', '.join(card.get('defaultOutputModes', [])) or 'n/a'}")

    print("\n-- Skills --")
    if not skills:
        print("No skills defined")
    else:
        for i, s in enumerate(skills, start=1):
            s_id = s.get("id", "n/a")
            s_name = s.get("name", "n/a")
            s_desc = s.get("description", "n/a")
            s_tags = ", ".join(s.get("tags", [])) if s.get("tags") else "n/a"
            print(f"[{i}] ID={s_id}  name={s_name} tags={s_tags}")
            print(f"    desc: {s_desc}")

    # Capabilities
    caps = card.get("capabilities", {})
    print("\n-- Capabilities --")
    if caps:
        print(json.dumps(caps, indent=2))
    else:
        print("No capabilities")


def print_agent_status_fields(url: str):
    """
    Fetches an Agent Card JSON from `url`, validates core fields,
    and prints selected information.
    """
    try:
        with urllib.request.urlopen(url, timeout=10) as resp:
            content_type = resp.headers.get("Content-Type", "")
            data = resp.read().decode("utf-8")
    except (HTTPError, URLError) as e:
        print(f"[ERROR] Failed to fetch URL: {e}")
        return

    try:
        card = json.loads(data)
    except json.JSONDecodeError as e:
        print(f"[ERROR] Invalid JSON: {e}")
        return

    # Basic validation
    required_fields = ["status", "timestamp", "service",]
    missing = [f for f in required_fields if f not in card]
    if missing:
        print(f"[WARN] Missing required fields: {missing}")
# Skills
    # Print summary
    print("=== Agent Status Summary ===")
    # print(f"ID:            {card.get('id')}")
    print(f"Name:          {card.get('service')}")
    print(f"Status:      {card.get('status')}")
    print(f"Timestamp:     {card.get('timestamp')}")
    
   
# Example usage:

print_agent_status_fields(f"{pricing_model_agent._agent_card}")


