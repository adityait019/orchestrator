import asyncio
import websockets
import json
import httpx
import os
from rich.console import Console, Group
from rich.prompt import Prompt
import uuid
from rich.panel import Panel
from rich.text import Text
from rich.table import Table
from rich.live import Live
from rich import box
from logo import nexus_logo as logo
from dotenv import load_dotenv
load_dotenv()
def render_separator():
    console.print("\n" + "-" * 70, style="dim")


def render_agent_header(agent: str):
    console.print(f"\n🤖 [bold cyan]{agent}[/bold cyan]")


def render_tool_call(name, agent):
    console.print(
        f"🛠️ [magenta]{name}[/magenta]  "
        f"[dim](agent: {agent})[/dim]"
    )


def render_tool_result(name, response):
    console.print(f"✅ [green]{name}[/green]")
    if isinstance(response, dict):
        console.print_json(json.dumps(response))
    else:
        console.print(f"[dim]{response}[/dim]")


def render_token_usage(data):
    table = Table(show_header=True, header_style="bold yellow")
    table.add_column("Agent")
    table.add_column("Input")
    table.add_column("Output")
    table.add_column("Total")

    table.add_row(
        str(data.get("agent")),
        str(data.get("input")),
        str(data.get("output")),
        str(data.get("total")),
    )

    console.print("\n💰 Token Usage")
    console.print(table)


def render_progress(agent, state):
    color = {
        "working": "cyan",
        "completed": "green",
        "failed": "red"
    }.get(state, "white")

    icon = {
        "working": "🔄",
        "completed": "✅",
        "failed": "❌"
    }.get(state, "•")

    console.print(f"{icon} [{color}]{agent} → {state}[/{color}]")


def render_debug(meta):
    console.print(
        Panel.fit(
            json.dumps(meta, indent=2),
            title="🧪 DEBUG META",
            border_style="dim"
        )
    )
console = Console()

BASE_URL = f"http://{os.getenv('ORCH_HOST', '127.0.0.1')}:{os.getenv('ORCH_PORT', 8000)}"
WS_BASE = f"ws://{os.getenv('ORCH_HOST', '127.0.0.1')}:{os.getenv('ORCH_PORT', 8000)}"
ADMIN_TOKEN = os.getenv("SECRET_KEY", "super-secret")


DEBUG=False
# Required for the WebSocket handshake. In AUTH_MODE=mock, the shared local
# .env can provide MOCK_ACCESS_TOKEN (default: dev-token); otherwise supply
# ORCH_ACCESS_TOKEN accepted by the configured identity service.

USER_ID=os.getenv("USER_ID", "test-user")
TENANT_ID=os.getenv("TENANT_ID", "test-tenant")
COUNTRY_CODE=os.getenv("COUNTRY_CODE", "US")
AUTH_MODE = os.getenv("AUTH_MODE", "external").strip().lower()
ACCESS_TOKEN = os.getenv("ORCH_ACCESS_TOKEN", "").strip()
ROLES=os.getenv("ROLES", "user").strip().lower().split(",")
if not ACCESS_TOKEN and AUTH_MODE == "mock":
    ACCESS_TOKEN = os.getenv("MOCK_ACCESS_TOKEN", "dev-token").strip()

# ------------------------------------------------------
# API HELPERS
# ------------------------------------------------------


def pretty_print_if_json(text):
    try:
        obj = json.loads(text)
        console.print_json(json.dumps(obj))
        return True
    except Exception:
        return False

async def add_agent(name, host, port):
    async with httpx.AsyncClient() as client:
        res = await client.post(
            f"{BASE_URL}/agents/add",
            headers={"x-admin-token": ADMIN_TOKEN},
            json={"name": name, "host": host, "port": int(port)},
        )
        console.print(
            f"✅ Agent [green]{name}[/green] added"
            if res.status_code == 200
            else f"❌ Failed: {res.text}",
            style=None if res.status_code == 200 else "red"
        )


async def remove_agent(name):
    async with httpx.AsyncClient() as client:
        res = await client.delete(
            f"{BASE_URL}/agents/{name}",
            headers={"x-admin-token": ADMIN_TOKEN},
        )
        console.print(
            f"🗑️ Agent [red]{name}[/red] removed"
            if res.status_code == 200
            else f"❌ Failed: {res.text}",
            style=None if res.status_code == 200 else "red"
        )


async def list_agents():
    async with httpx.AsyncClient() as client:
        res = await client.get(f"{BASE_URL}/agents/active")
        data = res.json()

        console.print("\n📡 Active Agents:", style="bold cyan")
        if not data:
            console.print("No active agents", style="yellow")
            return

        for agent in data:
            console.print(f"- {agent['name']} ({agent['host']}:{agent['port']})")


# ------------------------------------------------------
# ADMIN DASHBOARD (/admin/evaluation/*, /agents/total_agents)
# ------------------------------------------------------

async def fetch_admin_json(client: httpx.AsyncClient, path: str, params: dict | None = None):
    try:
        res = await client.get(
            f"{BASE_URL}{path}",
            headers={"x-admin-token": ADMIN_TOKEN},
            params=params,
            timeout=8.0,
        )
        res.raise_for_status()
        return {"ok": True, "data": res.json()}
    except httpx.HTTPStatusError as e:
        return {"ok": False, "error": f"HTTP {e.response.status_code}: {e.response.text[:150]}"}
    except httpx.RequestError as e:
        return {"ok": False, "error": f"Request failed: {e!r}"}
    except Exception as e:
        return {"ok": False, "error": f"Unexpected error: {e!r}"}


def _error_table(title: str, message: str) -> Table:
    table = Table(title=f"❌ {title}", show_header=False, box=box.SIMPLE)
    table.add_column("Error", style="red")
    table.add_row(message)
    return table


def build_overview_table(payload) -> Table:
    if not payload["ok"]:
        return _error_table("Evaluation Overview", payload["error"])

    d = payload["data"]
    table = Table(title="📊 Evaluation Overview", show_header=False, box=box.SIMPLE_HEAD)
    table.add_column("Metric", style="cyan")
    table.add_column("Value", justify="right", style="bold")

    rows = [
        ("Task success rate", f"{d.get('task_success_rate', 0)}%"),
        ("Invocation success rate", f"{d.get('invocation_success_rate', 0)}%"),
        ("Failure rate", f"{d.get('failure_rate', 0)}%"),
        ("Avg prompt latency", f"{d.get('avg_turn_latency_sec', 0)}s"),
        ("Avg invocation latency", f"{d.get('avg_invocation_latency_sec', 0)}s"),
        ("Avg tokens / invocation", f"{d.get('avg_tokens_per_invocation', 0)}"),
        ("Total tokens", f"{d.get('total_tokens', 0):,}"),
        ("Cost / successful task", f"{d.get('cost_per_successful_task', 0)}"),
        ("Artifact generation rate", f"{d.get('artifact_generation_rate', 0)}"),
        ("Event density", f"{d.get('event_density', 0)}"),
        ("Throughput / hour", f"{d.get('throughput_per_hour', 0)}"),
    ]
    for label, value in rows:
        table.add_row(label, value)
    return table


def build_leaderboard_table(payload) -> Table:
    if not payload["ok"]:
        return _error_table("Agent Leaderboard", payload["error"])

    d = payload["data"]
    table = Table(title=f"🏆 Agent Leaderboard ({d.get('total_agents', 0)} agents)", box=box.SIMPLE_HEAD)
    table.add_column("Agent", style="magenta", no_wrap=True)
    table.add_column("Invocations", justify="right")
    table.add_column("Success %", justify="right")
    table.add_column("Failure %", justify="right")
    table.add_column("Avg Latency (s)", justify="right")
    table.add_column("Avg Tokens", justify="right")
    table.add_column("Total Tokens", justify="right")
    table.add_column("Utilization", justify="right")

    for a in d.get("agents", []):
        success = a["success_rate"]
        success_style = "green" if success >= 90 else ("yellow" if success >= 70 else "red")
        table.add_row(
            a["agent_name"],
            str(a["total_invocations"]),
            f"[{success_style}]{success}[/]",
            f"{a['failure_rate']}",
            f"{a['avg_latency_sec']}",
            f"{a['avg_tokens']}",
            f"{a['total_tokens']:,}",
            f"{a['utilization']}",
        )
    return table


def build_timeseries_table(payload, metric: str, ts_interval: str) -> Table:
    if not payload["ok"]:
        return _error_table("Timeseries", payload["error"])

    d = payload["data"]
    table = Table(title=f"📈 Timeseries — {metric} / {ts_interval}", box=box.SIMPLE_HEAD)
    table.add_column("Timestamp", style="cyan", no_wrap=True)
    table.add_column("Value", justify="right", style="bold")

    for point in d.get("data", [])[-12:]:
        table.add_row(str(point.get("timestamp")), str(point.get("value")))
    return table


def build_registry_table(payload) -> Table:
    if not payload["ok"]:
        return _error_table("Agent Registry", payload["error"])

    agents = payload["data"] or []
    table = Table(title=f"🗂️ Agent Registry ({len(agents)})", box=box.SIMPLE_HEAD)
    table.add_column("Name", style="cyan")
    table.add_column("Host", no_wrap=True)
    table.add_column("Port", justify="right")
    table.add_column("Active", justify="center")
    table.add_column("Healthy", justify="center")

    for a in agents:
        table.add_row(
            a.get("name", "-"),
            a.get("host", "-"),
            str(a.get("port", "-")),
            "[green]✔[/]" if a.get("is_active") else "[red]✘[/]",
            "[green]✔[/]" if a.get("is_healthy") else "[red]✘[/]",
        )
    return table


async def _gather_dashboard_data(client: httpx.AsyncClient, metric: str, ts_interval: str):
    overview, agents, timeseries, registry = await asyncio.gather(
        fetch_admin_json(client, "/admin/evaluation/overview"),
        fetch_admin_json(client, "/admin/evaluation/agents"),
        fetch_admin_json(client, "/admin/evaluation/timeseries", {"metric": metric, "interval": ts_interval}),
        fetch_admin_json(client, "/agents/total_agents"),
    )
    return overview, agents, timeseries, registry


async def show_dashboard(
    live: bool = False,
    interval: float = 5.0,
    metric: str = "success_rate",
    ts_interval: str = "hour",
):
    """
    /dashboard            -> one-shot snapshot of overview + leaderboard +
                              timeseries + registry
    /dashboard live [sec]  -> same panels, auto-refreshing every `sec`
                              seconds until Ctrl+C
    """
    async with httpx.AsyncClient() as client:
        if not live:
            overview, agents, timeseries, registry = await _gather_dashboard_data(
                client, metric, ts_interval
            )
            render_separator()
            console.print(build_overview_table(overview))
            console.print(build_leaderboard_table(agents))
            console.print(build_timeseries_table(timeseries, metric, ts_interval))
            console.print(build_registry_table(registry))
            render_separator()
            return

        console.print(
            "\n📡 [bold cyan]Live dashboard[/bold cyan] — Ctrl+C to return to chat\n"
        )
        try:
            with Live(console=console, auto_refresh=False, screen=False) as live_view:
                while True:
                    overview, agents, timeseries, registry = await _gather_dashboard_data(
                        client, metric, ts_interval
                    )
                    group = Group(
                        build_overview_table(overview),
                        build_leaderboard_table(agents),
                        build_timeseries_table(timeseries, metric, ts_interval),
                        build_registry_table(registry),
                    )
                    live_view.update(group, refresh=True)
                    await asyncio.sleep(interval)
        except KeyboardInterrupt:
            console.print("\n👋 Returning to chat...\n", style="cyan")


async def upload_file(paths: list[str], session_id: str):
    valid_files = []

    for path in paths:
        if not os.path.exists(path):
            console.print(f"❌ File not found: {path}", style="red")
            continue
        valid_files.append(path)

    if not valid_files:
        console.print("❌ No valid files to upload", style="red")
        return

    async with httpx.AsyncClient(timeout=120) as client:
        try:
            files = []

            opened_files = []  # keep references to close later

            for path in valid_files:
                f = open(path, "rb")
                opened_files.append(f)

                filename = os.path.basename(path)

                files.append(
                    ("files", (filename, f, "application/octet-stream"))
                )

            data = {
                "session_id": session_id
            }

            headers = {"Authorization": f"Bearer {ACCESS_TOKEN}"}

            res = await client.post(
                f"{BASE_URL}/upload/",
                files=files,
                data=data,
                headers=headers
            )

            # ✅ close all opened files
            for f in opened_files:
                f.close()

            if res.status_code != 200:
                console.print(f"❌ Upload failed: {res.status_code}", style="red")
                console.print(res.text)
                return

            result = res.json()

            # ✅ Pretty output
            console.print("\n📁 Upload Success", style="bold green")
            console.print(f"File ID: {result.get('file_id')}")
            console.print(f"Session: {result.get('session_id')}")
            console.print(f"File Count: {result.get('file_count')}")

            console.print("\n📄 Files:", style="cyan")
            for f in result.get("files", []):
                console.print(f"- {f['file_name']} ({f['file_size']} bytes)")

            if result.get("file_urls"):
                console.print("\n🔗 Signed URLs:", style="cyan")
                for url in result["file_urls"]:
                    console.print(url)

            console.print("\n💡 Files are now attached to your session", style="yellow")

        except Exception as e:
            console.print(f"❌ Upload error: {e}", style="red")


# ------------------------------------------------------
# CHAT LOOP (USES SAME SESSION ID)
# ------------------------------------------------------

async def chat_loop(ws, session_id: str):

    while True:
        # user_input = Prompt.ask("[bold yellow]You[/bold yellow]")
        user_input = await asyncio.to_thread(Prompt.ask, "[bold yellow]You[/bold yellow]")

        if user_input.lower() in ("exit", "quit", "bye"):
            console.print("👋 Goodbye!", style="cyan")
            return

        # ======================================
        # ✅ COMMAND HANDLING
        # ======================================
        if user_input.startswith("/"):
            parts = user_input.split()

            if not parts:
                continue

            if parts[0] == "/help":
                console.print("""
📘 Commands:
/add <name> <host> <port>
/remove <name>
/list
/upload <file1> [file2 file3 ...]
/dashboard                 — one-shot snapshot (overview, leaderboard, timeseries, registry)
/dashboard live [interval] — auto-refreshing view, Ctrl+C to return here (default 5s)
/exit
""")
                continue

            if parts[0] == "/add" and len(parts) == 4:
                await add_agent(parts[1], parts[2], parts[3])
                continue

            if parts[0] == "/remove" and len(parts) == 2:
                await remove_agent(parts[1])
                continue

            if parts[0] == "/list":
                await list_agents()
                continue

            # ✅ ADMIN DASHBOARD (snapshot or live)
            if parts[0] == "/dashboard":
                args = parts[1:]
                is_live = bool(args) and args[0] == "live"

                interval = 5.0
                if is_live and len(args) >= 2:
                    try:
                        interval = float(args[1])
                    except ValueError:
                        console.print(
                            f"⚠️ Invalid interval '{args[1]}', using default 5s",
                            style="yellow",
                        )

                await show_dashboard(live=is_live, interval=interval)
                continue

            # ✅ ✅ MULTI FILE UPLOAD
            if parts[0] == "/upload" and len(parts) >= 2:
                console.print("\n⏳ Uploading files...", style="cyan")

                await upload_file(parts[1:], session_id)

                console.print(
                    "\n💡 Files attached to this session. "
                    "Ask something about them.",
                    style="yellow"
                )
                continue

            console.print("❌ Invalid command", style="red")
            continue

        # ======================================
        # ✅ SEND CHAT MESSAGE
        # ======================================
        payload = {"prompt": user_input}

        await ws.send(json.dumps(payload))

        console.print("\n[bold green]Bot[/bold green]:")

        # ======================================
        # ✅ RECEIVE STREAM
        # ======================================


        current_agent = None

        while True:
            try:
                msg = await ws.recv()
            except websockets.exceptions.ConnectionClosed:
                console.print("⚠️ Connection closed safely", style="yellow")
                break

            try:
                data = json.loads(msg)
            except Exception:
                console.print(f"⚠️ Invalid message: {msg}")
                continue

            if DEBUG:
                console.print(f"\n[dim]RAW: {data}[/dim]")

            msg_type = data.get("type")

            # ✅ DONE
            if msg_type == "done" or data.get("stage") == "done":
                render_separator()
                break

            # ✅ BOT MESSAGE
            if msg_type == "bot_message":
                content = data.get("content", "")
                agent = data.get("agent") or "unknown"

                if agent != current_agent:
                    current_agent = agent
                    render_agent_header(agent)

                if pretty_print_if_json(content):
                    continue

                console.print(content)

            # ✅ TOOL CALL
            elif msg_type == "tool_call":
                render_tool_call(
                    data.get("name"),
                    data.get("agent")
                )

                args = data.get("args", {})
                if args.get("agent_name"):
                    console.print(
                        f"🔄 Switching → [yellow]{args.get('agent_name')}[/yellow]"
                    )

            # ✅ TOOL RESULT
            elif msg_type == "tool_result":
                render_tool_result(
                    data.get("name"),
                    data.get("response")
                )

            # ✅ TOKEN USAGE
            elif msg_type == "token_usage":
                render_token_usage(data)

            # ✅ AGENT PROGRESS
            elif msg_type == "agent_progress":
                render_progress(
                    data.get("agent"),
                    data.get("state")
                )

            # ✅ STATUS
            elif msg_type == "status":
                stage = data.get("stage")

                if stage == "tool_started":
                    console.print(
                        f"\n🚀 Starting agent: [yellow]{data.get('agent')}[/yellow]"
                    )

                if data.get("message"):
                    console.print(f"⚙️ {data.get('message')}")

            # ✅ FILE OUTPUT
            elif msg_type == "file_processed":
                console.print("\n📁 Generated Files:", style="green")
                for f in data.get("files", []):
                    filename=f.split("/")[-1].split("?")[0]

                    console.print(f"-[link={f}]{filename}[/link]")

            # ✅ DEBUG
            elif msg_type == "debug_meta":
                if DEBUG:
                    render_debug(data.get("meta"))

# ------------------------------------------------------
# MAIN LOOP (SESSION FIX HERE)
# ------------------------------------------------------

async def chat():

    if not ACCESS_TOKEN:
        console.print(
            "Authentication requires ORCH_ACCESS_TOKEN. Alternatively, set "
            "AUTH_MODE=mock and configure MOCK_ACCESS_TOKEN for local testing.",
            style="red",
        )
        return

    session_id = str(uuid.uuid4())

    ws_url = f"{WS_BASE}/ws/{session_id}"
    console.print(logo, style="bold bright_cyan",justify="center")

    console.print(
        f"🔌 Connecting to Orchestrator at [cyan]{ws_url}[/cyan] with session ID [yellow]{session_id}[/yellow]",
        style="dim"
    )
    async with websockets.connect(
        ws_url,
        open_timeout=20,
        ping_interval=20,
        ping_timeout=120,
    ) as ws:

        # --------------------------------------------------
        # RECEIVE INITIAL CONNECTION MESSAGE
        # --------------------------------------------------
        try:
            first_msg = json.loads(await ws.recv())

            if first_msg.get("type"):
                console.print(
                    f"🔌 Server: {first_msg.get('type')}",
                    style="dim"
                )

        except Exception as e:
            console.print(
                f"❌ Failed during connection: {e}",
                style="red"
            )
            return

        # --------------------------------------------------
        # AUTH HANDSHAKE
        # --------------------------------------------------
        auth_payload = {
            "type": "auth",
            "access_token": ACCESS_TOKEN,
            "user_id": USER_ID,
            "tenant_id": TENANT_ID,
            "country_code": COUNTRY_CODE,
            "roles": ROLES

        }
        await ws.send(json.dumps(auth_payload))

        try:
            auth_response = json.loads(await ws.recv())

            if auth_response.get("type") == "auth_failed":
                console.print(
                    f"❌ Authentication failed: "
                    f"{auth_response.get('detail')}",
                    style="red"
                )
                return

            if auth_response.get("type") == "auth_ok":
                console.print(
                    "✅ Authentication successful",
                    style="green"
                )

        except Exception as e:
            console.print(
                f"❌ Auth handshake failed: {e}",
                style="red"
            )
            return

        # --------------------------------------------------
        # CHAT READY
        # --------------------------------------------------

        console.print(
            "🤖 Connected to Orchestrator",
            style="bold green"
        )

        console.print(
            f"🧠 Session ID: {session_id}",
            style="dim"
        )

        console.print(
            "Type /help for commands\n"
        )

        await chat_loop(ws, session_id)

# ------------------------------------------------------
# ENTRY
# ------------------------------------------------------

if __name__ == "__main__":
    try:
        asyncio.run(chat())
    except KeyboardInterrupt:
        console.print("\n👋 Exiting...", style="cyan")
