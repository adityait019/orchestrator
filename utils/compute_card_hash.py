import hashlib
import json


def compute_agent_card_hash(
    agent_card: dict,
) -> str:
    return hashlib.sha256(
        json.dumps(
            agent_card,
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()
