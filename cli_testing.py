import asyncio
import websockets
import json
import httpx
import os
from rich.console import Console
from rich.prompt import Prompt
import uuid
from rich.panel import Panel
from rich.text import Text
from rich.table import Table
from dotenv import load_dotenv
load_dotenv(override=True)

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

BASE_URL = os.getenv("PUBLIC_BASE_URL", "http://localhost:8000")
WS_BASE = os.getenv("WS_BASE_URL", "ws://localhost:8000")
ADMIN_TOKEN = os.getenv("SECRET_KEY", "super-secret")

DEBUG=True
USER_ID = "aditya"
TENANT_ID = "personal-resume-testing"
ACCESS_TOKEN = "dev-token"

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

            headers = {
                "X-Middleware": "bff",
                "X-Forwarded-User": USER_ID,
                "X-Forwarded-Tenant": TENANT_ID,
            }

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
                    console.print(f"- {f}")

            # ✅ DEBUG
            elif msg_type == "debug_meta":
                if DEBUG:
                    render_debug(data.get("meta"))

# ------------------------------------------------------
# MAIN LOOP (SESSION FIX HERE)
# ------------------------------------------------------

async def chat():

    session_id = str(uuid.uuid4())

    ws_url = f"{WS_BASE}/ws/{session_id}"

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
            "roles": ["user"]
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