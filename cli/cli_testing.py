"""Interactive development client for the Orchestrator WebSocket API."""
from __future__ import annotations

import asyncio
import json
import uuid

import websockets
from rich.prompt import Prompt

from cli.config import config, console
from cli.logo import nexus_logo
from cli.services import add_agent, list_agents, remove_agent, show_dashboard, upload_file
from cli.ui import (pretty_print_if_json, render_agent_header, render_debug,
                    render_help, render_progress, render_separator,
                    render_token_usage, render_tool_call, render_tool_result)


async def receive_chat_stream(ws) -> None:
    """Render one server response until its ``done`` marker."""
    current_agent = None
    while True:
        try:
            raw = await ws.recv()
        except websockets.exceptions.ConnectionClosed:
            console.print("⚠️ Connection closed safely", style="yellow")
            return
        try:
            data = json.loads(raw)
        except (TypeError, json.JSONDecodeError):
            console.print(f"⚠️ Invalid server message: {raw}", style="yellow")
            continue
        if config.debug:
            console.print(f"\n[dim]RAW: {data}[/dim]")
        msg_type = data.get("type")
        if msg_type == "done" or data.get("stage") == "done":
            render_separator()
            return
        if msg_type == "bot_message":
            agent = data.get("agent") or "Nexus"
            if agent != current_agent:
                current_agent = agent
                render_agent_header(agent)
            if not pretty_print_if_json(data.get("content", "")):
                console.print(data.get("content", ""))
        elif msg_type == "waiting_for_input":
            console.print("\n⏸️ [bold yellow]Input required[/bold yellow]")
            console.print(data.get("question") or "Please provide the requested input.")
            console.print("[dim]Reply normally or send a user_response message.[/dim]")
        elif msg_type == "plan_completed":
            console.print("✅ [bold green]Plan completed[/bold green]")
            console.print(f"Total tokens: {data.get('total_tokens', 0)}")
        elif msg_type == "plan_cancelled":
            console.print("🛑 Plan cancelled.", style="yellow")
        elif msg_type == "tool_call":
            render_tool_call(data.get("name"), data.get("agent"))
            args = data.get("args") or {}
            if args.get("agent_name"):
                console.print(f"🔄 Switching → [yellow]{args['agent_name']}[/yellow]")
        elif msg_type == "tool_result":
            render_tool_result(data.get("name"), data.get("response"))
        elif msg_type == "token_usage":
            render_token_usage(data)
        elif msg_type == "agent_progress":
            render_progress(data.get("agent"), data.get("state"))
        elif msg_type == "status":
            if data.get("stage") == "tool_started":
                console.print(f"\n🚀 Starting agent: [yellow]{data.get('agent')}[/yellow]")
            if data.get("message"):
                console.print(f"⚙️ {data['message']}")
        elif msg_type == "file_processed":
            console.print("\n📁 Generated Files:", style="green")
            for file_url in data.get("files", []):
                filename = file_url.split("/")[-1].split("?")[0]
                console.print(f"• [link={file_url}]{filename}[/link]")
        elif msg_type == "debug_meta" and config.debug:
            render_debug(data.get("meta"))
        elif msg_type == "error":
            console.print(f"❌ {data.get('message', 'Unknown server error')}", style="red")


async def handle_command(ws, session_id: str, command: str) -> bool:
    parts = command.split()
    name = parts[0].lower() if parts else ""
    if name in {"/exit", "/quit"}:
        console.print("👋 Goodbye!", style="cyan")
        return False
    if name == "/help":
        render_help()
    elif name == "/add":
        if len(parts) != 4:
            console.print("Usage: /add <name> <host> <port>", style="yellow")
        else:
            await add_agent(config, parts[1], parts[2], parts[3])
    elif name == "/remove":
        if len(parts) != 2:
            console.print("Usage: /remove <name>", style="yellow")
        else:
            await remove_agent(config, parts[1])
    elif name == "/list":
        await list_agents(config)
    elif name == "/upload":
        if len(parts) < 2:
            console.print("Usage: /upload <file1> [file2 ...]", style="yellow")
        else:
            await upload_file(config, parts[1:], session_id)
    elif name == "/dashboard":
        args = parts[1:]
        live = bool(args) and args[0].lower() == "live"
        interval = 5.0
        if live and len(args) > 1:
            try:
                interval = max(1.0, float(args[1]))
            except ValueError:
                console.print("⚠️ Invalid interval; using 5 seconds.", style="yellow")
        await show_dashboard(config, live=live, interval=interval)
    else:
        console.print("❌ Unknown command. Type /help to see available commands.", style="red")
    return True


def read_multiline_input() -> str:
    """Read a prompt until the user submits an empty continuation line.

    Slash commands remain single-line commands. For normal prompts, the first
    line is entered at the usual prompt and subsequent lines use ``...``.
    """
    first_line = Prompt.ask("[bold yellow]You[/bold yellow]")
    if not first_line.strip():
        return ""
    if first_line.lstrip().startswith("/"):
        if first_line.strip().lower() == "/paste":
            console.print("[dim]Paste your full prompt. Type /end on a separate line when finished.[/dim]")
            lines = []
            while True:
                line = console.input("")
                if line.strip().lower() == "/end":
                    return "\n".join(lines).strip()
                lines.append(line.rstrip())
        return first_line.strip()

    lines = [first_line.rstrip()]
    while True:
        line = console.input("[bold yellow]...[/bold yellow] ")
        if not line.strip():
            break
        lines.append(line.rstrip())
    return "\n".join(lines).strip()


async def chat_loop(ws, session_id: str) -> None:
    console.print("[dim]Tip: /help for commands · Enter a blank line to send a multi-line prompt · Ctrl+C to exit[/dim]")
    while True:
        try:
            user_input = await asyncio.to_thread(read_multiline_input)
        except (EOFError, KeyboardInterrupt):
            console.print("\n👋 Exiting...", style="cyan")
            return
        if not user_input:
            continue
        if user_input.startswith("/"):
            if not await handle_command(ws, session_id, user_input):
                return
            continue
        await ws.send(json.dumps({"prompt": user_input}))
        console.print("\n[bold green]Nexus[/bold green]:")
        await receive_chat_stream(ws)


async def chat() -> None:
    access_token = config.resolved_access_token
    if not access_token:
        console.print("❌ Set ORCH_ACCESS_TOKEN, or use AUTH_MODE=mock for local testing.", style="red")
        return
    session_id = str(uuid.uuid4())
    ws_url = f"{config.ws_base}/ws/{session_id}"
    console.print(nexus_logo, style="bold bright_cyan", justify="center")
    console.print(f"🔌 Connecting to [cyan]{ws_url}[/cyan]", style="dim")
    try:
        async with websockets.connect(ws_url, open_timeout=20, ping_interval=20, ping_timeout=120) as ws:
            first = json.loads(await ws.recv())
            console.print(f"🔌 Server: {first.get('type', 'connected')}", style="dim")
            await ws.send(json.dumps({
                "type": "auth", "access_token": access_token,
                "user_id": config.user_id, "tenant_id": config.tenant_id,
                "country_code": config.country_code, "roles": list(config.roles),
            }))
            auth = json.loads(await ws.recv())
            if auth.get("type") != "auth_ok":
                console.print(f"❌ Authentication failed: {auth.get('detail', auth)}", style="red")
                return
            console.print("✅ Authentication successful", style="green")
            console.print("🤖 Connected to Orchestrator", style="bold green")
            console.print(f"🧠 Session ID: {session_id}\n")
            await chat_loop(ws, session_id)
    except (OSError, websockets.exceptions.WebSocketException) as exc:
        console.print(f"❌ Connection failed: {exc}", style="red")


if __name__ == "__main__":
    try:
        asyncio.run(chat())
    except KeyboardInterrupt:
        console.print("\n👋 Exiting...", style="cyan")
