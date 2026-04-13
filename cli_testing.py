import asyncio
import websockets
import json
import httpx
import os
from rich.console import Console
from rich.prompt import Prompt
import uuid

console = Console()

BASE_URL = "http://192.168.1.5:8000"
WS_BASE = "ws://192.168.1.5:8000"
ADMIN_TOKEN = os.getenv("SECRET_KEY", "super-secret")

# ------------------------------------------------------
# API HELPERS
# ------------------------------------------------------

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


async def upload_file(path: str, session_id: str):
    if not os.path.exists(path):
        console.print("❌ File not found", style="red")
        return

    async with httpx.AsyncClient() as client:
        with open(path, "rb") as f:
            files = {
                "files": (os.path.basename(path), f)
            }
            data = {
                "session_id": session_id
            }

            res = await client.post(
                f"{BASE_URL}/upload/",
                files=files,
                data=data,
            )

    console.print(f"📁 Uploaded: {res.json()}", style="green")


# ------------------------------------------------------
# CHAT LOOP (USES SAME SESSION ID)
# ------------------------------------------------------

async def chat_loop(ws, session_id: str):

    while True:
        user_input = Prompt.ask("[bold yellow]You[/bold yellow]")

        if user_input.lower() in ("exit", "quit", "bye"):
            console.print("👋 Goodbye!", style="cyan")
            return

        if user_input.startswith("/"):
            parts = user_input.split()

            if parts[0] == "/help":
                console.print("""
📘 Commands:
/add <name> <host> <port>
/remove <name>
/list
/upload <file_path>
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

            if parts[0] == "/upload" and len(parts) == 2:
                await upload_file(parts[1], session_id)
                continue

            console.print("❌ Invalid command", style="red")
            continue

        # ----------------------
        # SEND MESSAGE
        # ----------------------
        payload = {"prompt": user_input}

        await ws.send(json.dumps(payload))
        console.print("\n[bold green]Bot[/bold green]:")

        while True:
            msg = await ws.recv()
            data = json.loads(msg)

            if data.get("type") == "done" or data.get("stage") == "done":
                console.print("\n" + "-" * 60)
                break

            if data.get("type") == "message":
                console.print(data.get("content", ""), end="")

            elif data.get("type") == "status":
                if data.get("message"):
                    console.print(f"\n⚙️ {data['message']}")

            elif data.get("type") == "file_processed":
                console.print(f"\n📁 Files ready: {data.get('files')}")


# ------------------------------------------------------
# MAIN LOOP (SESSION FIX HERE)
# ------------------------------------------------------

async def chat():

    # ✅ ONE session_id for BOTH upload and websocket
    session_id = str(uuid.uuid4())

    ws_url = f"{WS_BASE}/ws/{session_id}"

    async with websockets.connect(
        ws_url,
        open_timeout=20,
        ping_interval=20,
        ping_timeout=60,
    ) as ws:

        console.print("🤖 Connected to Orchestrator", style="bold green")
        console.print(f"🧠 Session ID: {session_id}", style="dim")
        console.print("Type /help for commands\n")

        await chat_loop(ws, session_id)


# ------------------------------------------------------
# ENTRY
# ------------------------------------------------------

if __name__ == "__main__":
    try:
        asyncio.run(chat())
    except KeyboardInterrupt:
        console.print("\n👋 Exiting...", style="cyan")