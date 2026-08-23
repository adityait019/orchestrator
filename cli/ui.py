"""Rich presentation helpers for the interactive CLI."""
from __future__ import annotations

import json

from rich import box
from rich.console import Console, Group
from rich.live import Live
from rich.panel import Panel
from rich.table import Table

console = Console()


def render_separator() -> None:
    console.print("\n" + "-" * 70, style="dim")


def render_agent_header(agent: str) -> None:
    console.print(f"\n🤖 [bold cyan]{agent}[/bold cyan]")


def render_tool_call(name, agent) -> None:
    console.print(f"🛠️ [magenta]{name}[/magenta]  [dim](agent: {agent})[/dim]")


def render_tool_result(name, response) -> None:
    console.print(f"✅ [green]{name}[/green]")
    if isinstance(response, dict):
        console.print_json(json.dumps(response))
    else:
        console.print(f"[dim]{response}[/dim]")


def render_token_usage(data) -> None:
    table = Table(show_header=True, header_style="bold yellow")
    for column in ("Agent", "Input", "Output", "Total"):
        table.add_column(column)
    table.add_row(str(data.get("agent")), str(data.get("input", 0)),
                  str(data.get("output", 0)), str(data.get("total", 0)))
    console.print("\n💰 Token Usage")
    console.print(table)


def render_progress(agent, state) -> None:
    color = {"working": "cyan", "completed": "green", "failed": "red"}.get(state, "white")
    icon = {"working": "🔄", "completed": "✅", "failed": "❌"}.get(state, "•")
    console.print(f"{icon} [{color}]{agent} → {state}[/{color}]")


def render_debug(meta) -> None:
    console.print(Panel.fit(json.dumps(meta, indent=2), title="🧪 DEBUG META", border_style="dim"))


def pretty_print_if_json(value) -> bool:
    try:
        console.print_json(json.dumps(json.loads(value)))
        return True
    except (TypeError, ValueError, json.JSONDecodeError):
        return False


def _error_table(title: str, message: str) -> Table:
    table = Table(title=f"❌ {title}", show_header=False, box=box.SIMPLE)
    table.add_column("Error", style="red")
    table.add_row(message)
    return table


def build_overview_table(payload) -> Table:
    if not payload["ok"]:
        return _error_table("Evaluation Overview", payload["error"])
    data = payload["data"]
    table = Table(title="📊 Evaluation Overview", show_header=False, box=box.SIMPLE_HEAD)
    table.add_column("Metric", style="cyan")
    table.add_column("Value", justify="right", style="bold")
    rows = [
        ("Task success rate", f"{data.get('task_success_rate', 0)}%"),
        ("Invocation success rate", f"{data.get('invocation_success_rate', 0)}%"),
        ("Failure rate", f"{data.get('failure_rate', 0)}%"),
        ("Avg prompt latency", f"{data.get('avg_turn_latency_sec', 0)}s"),
        ("Avg invocation latency", f"{data.get('avg_invocation_latency_sec', 0)}s"),
        ("Avg tokens / invocation", f"{data.get('avg_tokens_per_invocation', 0)}"),
        ("Total tokens", f"{data.get('total_tokens', 0):,}"),
        ("Cost / successful task", f"{data.get('cost_per_successful_task', 0)}"),
        ("Artifact generation rate", f"{data.get('artifact_generation_rate', 0)}"),
        ("Event density", f"{data.get('event_density', 0)}"),
        ("Throughput / hour", f"{data.get('throughput_per_hour', 0)}"),
    ]
    for label, value in rows:
        table.add_row(label, value)
    return table


def build_leaderboard_table(payload) -> Table:
    if not payload["ok"]:
        return _error_table("Agent Leaderboard", payload["error"])
    data = payload["data"]
    table = Table(title=f"🏆 Agent Leaderboard ({data.get('total_agents', 0)} agents)", box=box.SIMPLE_HEAD)
    for col in ("Agent", "Invocations", "Success %", "Failure %", "Avg Latency (s)", "Avg Tokens", "Total Tokens", "Utilization"):
        table.add_column(col, justify="right" if col != "Agent" else "left", no_wrap=col == "Agent")
    for agent in data.get("agents", []):
        success = agent.get("success_rate", 0)
        style = "green" if success >= 90 else ("yellow" if success >= 70 else "red")
        table.add_row(agent.get("agent_name", "-"), str(agent.get("total_invocations", 0)),
                      f"[{style}]{success}[/]", str(agent.get("failure_rate", 0)),
                      str(agent.get("avg_latency_sec", 0)), str(agent.get("avg_tokens", 0)),
                      f"{agent.get('total_tokens', 0):,}", str(agent.get("utilization", 0)))
    return table


def build_timeseries_table(payload, metric: str, interval: str) -> Table:
    if not payload["ok"]:
        return _error_table("Timeseries", payload["error"])
    table = Table(title=f"📈 Timeseries — {metric} / {interval}", box=box.SIMPLE_HEAD)
    table.add_column("Timestamp", style="cyan", no_wrap=True)
    table.add_column("Value", justify="right", style="bold")
    for point in payload["data"].get("data", [])[-12:]:
        table.add_row(str(point.get("timestamp")), str(point.get("value")))
    return table


def build_registry_table(payload) -> Table:
    if not payload["ok"]:
        return _error_table("Agent Registry", payload["error"])
    agents = payload["data"] or []
    table = Table(title=f"🗂️ Agent Registry ({len(agents)})", box=box.SIMPLE_HEAD)
    for col in ("Name", "Host", "Port", "Active", "Healthy"):
        table.add_column(col, justify="right" if col == "Port" else "left")
    for agent in agents:
        table.add_row(agent.get("name", "-"), agent.get("host", "-"), str(agent.get("port", "-")),
                      "[green]✔[/]" if agent.get("is_active") else "[red]✘[/]",
                      "[green]✔[/]" if agent.get("is_healthy") else "[red]✘[/]")
    return table


def render_help() -> None:
    console.print(Panel("""[bold]Chat[/bold] — type any message to talk to Nexus
[bold]Agents[/bold] — /add, /remove, /list
[bold]Files[/bold] — /upload <file1> [file2 ...]
[bold]Dashboard[/bold] — /dashboard [live] [interval]
[bold]Session[/bold] — /help, /exit""", title="📘 Commands", border_style="cyan"))


def render_dashboard(group, live: Live | None = None) -> None:
    if live:
        live.update(group, refresh=True)
    else:
        render_separator()
        console.print(group)
        render_separator()
