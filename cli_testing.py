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
ADMIN_TOKEN = os.getenv("SECRET_KEY", "super-secret")


# ----------------------------
# API HELPERS
# ----------------------------

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


async def upload_file(path):
    if not os.path.exists(path):
        console.print("❌ File not found", style="red")
        return

    async with httpx.AsyncClient() as client:
        with open(path, "rb") as f:
            files = {"files": (os.path.basename(path), f)}
            res = await client.post(f"{BASE_URL}/upload/", files=files)

        console.print(f"📁 Uploaded: {res.json()}")


# ----------------------------
# CHAT LOOP (CORE LOGIC)
# ----------------------------

async def chat_loop(ws):

    while True:
        user_input = Prompt.ask("[bold yellow]You[/bold yellow]")

        # EXIT
        if user_input.lower() in ["exit", "quit", "bye"]:
            console.print("👋 Goodbye!", style="cyan")
            return

        # COMMANDS
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

            elif parts[0] == "/add" and len(parts) == 4:
                await add_agent(parts[1], parts[2], parts[3])
                continue

            elif parts[0] == "/remove" and len(parts) == 2:
                await remove_agent(parts[1])
                continue

            elif parts[0] == "/list":
                await list_agents()
                continue

            elif parts[0] == "/upload" and len(parts) == 2:
                await upload_file(parts[1])
                continue

            else:
                console.print("❌ Invalid command", style="red")
                continue

        # SEND MESSAGE
        payload = {"prompt": user_input}

        try:
            await ws.send(json.dumps(payload))
        except websockets.exceptions.ConnectionClosed:
            console.print("⚠️ Connection lost", style="yellow")
            raise  # handled in outer loop

        console.print("\n[bold green]Bot[/bold green]: ", end="")

        connection_broken = False

        while True:
            try:
                msg = await asyncio.wait_for(ws.recv(), timeout=120)
                data = json.loads(msg)

                # DONE
                if data.get("stage") == "done" or data.get("type") == "done":
                    console.print()
                    console.print("-" * 50)
                    break

                # MESSAGE
                elif data.get("type") == "message":
                    console.print(data.get("content", ""), end="")

                # STATUS
                elif data.get("type") == "status":
                    if data.get("message"):
                        console.print(f"\n⚙️ {data.get('message')}")

                # FILE
                elif data.get("type") == "file_processed":
                    console.print(f"\n📁 Files: {data.get('files')}")

            except asyncio.TimeoutError:
                console.print("\n⏱️ Response timeout", style="yellow")
                connection_broken = True
                break

            except websockets.exceptions.ConnectionClosed:
                console.print("\n⚠️ Connection closed by server", style="yellow")
                connection_broken = True
                break

            except Exception as e:
                console.print(f"\n❌ Error: {e}", style="red")
                connection_broken = True
                break

        if connection_broken:
            raise Exception("Reconnect required")


# ----------------------------
# MAIN CHAT (RECONNECT LOOP)
# ----------------------------

async def chat():

    while True:
        session_id = str(uuid.uuid4())
        WS_URL = f"ws://192.168.1.5:8000/ws/{session_id}"

        try:
            async with websockets.connect(
                WS_URL,
                open_timeout=20,
                ping_interval=20,
                ping_timeout=60
            ) as ws:

                console.print("🤖 Connected to Orchestrator", style="bold green")
                console.print("Type /help for commands\n")

                await chat_loop(ws)

        except Exception as e:
            console.print(f"⚠️ Connection error: {e}", style="yellow")
            console.print("🔄 Reconnecting in 2 sec...\n", style="yellow")
            await asyncio.sleep(2)


# ----------------------------
# ENTRY
# ----------------------------

if __name__ == "__main__":
    try:
        asyncio.run(chat())
    except KeyboardInterrupt:
        console.print("\n👋 Exiting...", style="cyan")