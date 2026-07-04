# Add this below code to google adk for SEL std

file location: `.venv\Lib\site-packages\google\adk\flows\llm_flows\agent_transfer.py`

```python
def _build_target_agents_info(target_agent: Any) -> str:
    capabilities = getattr(target_agent, "capabilities", []) or []
    skills = getattr(target_agent, "skills", []) or []

    grouped = {
        "domain": [],
        "platform": [],
        "framework": [],
        "language": [],
        "feature": [],
        "other": [],
    }

    for c in capabilities:
        if ":" in c:
            key, value = c.split(":", 1)
            key = key.strip().lower()
            value = value.strip()

            if key in grouped:
                grouped[key].append(value)
            else:
                grouped["other"].append(c)
        else:
            # no prefix → treat as feature
            grouped["feature"].append(c)

    def fmt(title, items):
        if not items:
            return ""
        return f"{title}: {', '.join(items)}"

    capability_lines = [
        fmt("Domains", grouped["domain"]),
        fmt("Platforms", grouped["platform"]),
        fmt("Frameworks", grouped["framework"]),
        fmt("Languages", grouped["language"]),
        fmt("Features", grouped["feature"]),
        fmt("Other", grouped["other"]),
    ]

    capability_text = "\n".join(line for line in capability_lines if line)

    return f"""
Agent name: {target_agent.name}
Agent description: {target_agent.description}

Agent capabilities:
{capability_text}

Agent skills:
{chr(10).join(f"- {s}" for s in skills)}
"""
```
