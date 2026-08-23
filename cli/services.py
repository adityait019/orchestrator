"""HTTP and dashboard operations used by the interactive CLI."""
from __future__ import annotations

import asyncio
import os

import httpx
from rich.console import Group
from rich.live import Live

from .config import CLIConfig, console
from .ui import (build_leaderboard_table, build_overview_table, build_registry_table,
                 build_timeseries_table, render_dashboard)


async def add_agent(config: CLIConfig, name: str, host: str, port: str) -> None:
    try:
        port_number = int(port)
    except ValueError:
        console.print("❌ Port must be a number.", style="red")
        return
    async with httpx.AsyncClient(timeout=10) as client:
        try:
            response = await client.post(f"{config.base_url}/agents/add",
                                         headers={"x-admin-token": config.admin_token},
                                         json={"name": name, "host": host, "port": port_number})
            if response.is_success:
                console.print(f"✅ Agent [green]{name}[/green] added")
            else:
                console.print(f"❌ Failed ({response.status_code}): {response.text[:300]}", style="red")
        except httpx.RequestError as exc:
            console.print(f"❌ Could not reach orchestrator: {exc}", style="red")


async def remove_agent(config: CLIConfig, name: str) -> None:
    async with httpx.AsyncClient(timeout=10) as client:
        try:
            response = await client.delete(f"{config.base_url}/agents/{name}",
                                           headers={"x-admin-token": config.admin_token})
            if response.is_success:
                console.print(f"🗑️ Agent [red]{name}[/red] removed")
            else:
                console.print(f"❌ Failed ({response.status_code}): {response.text[:300]}", style="red")
        except httpx.RequestError as exc:
            console.print(f"❌ Could not reach orchestrator: {exc}", style="red")


async def list_agents(config: CLIConfig) -> None:
    async with httpx.AsyncClient(timeout=10) as client:
        try:
            response = await client.get(f"{config.base_url}/agents/active")
            response.raise_for_status()
            agents = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            console.print(f"❌ Could not load agents: {exc}", style="red")
            return
    console.print("\n📡 Active Agents:", style="bold cyan")
    if not agents:
        console.print("No active agents", style="yellow")
        return
    for agent in agents:
        console.print(f"• [bold]{agent.get('name', '-')}[/bold] ({agent.get('host', '-')}:{agent.get('port', '-')})")


async def upload_file(config: CLIConfig, paths: list[str], session_id: str) -> None:
    valid_paths = [path for path in paths if os.path.isfile(path)]
    for path in set(paths) - set(valid_paths):
        console.print(f"⚠️ File not found: {path}", style="yellow")
    if not valid_paths:
        console.print("❌ No valid files to upload", style="red")
        return
    handles = []
    try:
        files = []
        for path in valid_paths:
            handle = open(path, "rb")
            handles.append(handle)
            files.append(("files", (os.path.basename(path), handle, "application/octet-stream")))
        headers = {
            "Authorization": f"Bearer {config.resolved_access_token}",
            "X-Dev-User-Id": config.user_id,
            "X-Dev-Tenant-Id": config.tenant_id,
            "X-Country-Code": config.country_code,
            "X-Dev-Roles": ",".join(config.roles),
        }
        async with httpx.AsyncClient(timeout=120) as client:
            response = await client.post(f"{config.base_url}/upload/", files=files,
                                         data={"session_id": session_id}, headers=headers)
        if not response.is_success:
            console.print(f"❌ Upload failed ({response.status_code}): {response.text[:300]}", style="red")
            return
        result = response.json()
        console.print(f"✅ Uploaded {result.get('file_count', len(valid_paths))} file(s) to this session.", style="green")
        for file_info in result.get("files", []):
            console.print(f"• {file_info.get('file_name', '-')} ({file_info.get('file_size', 0)} bytes)")
    except (OSError, httpx.HTTPError, ValueError) as exc:
        console.print(f"❌ Upload failed: {exc}", style="red")
    finally:
        for handle in handles:
            handle.close()


async def fetch_admin_json(client: httpx.AsyncClient, config: CLIConfig, path: str, params=None):
    try:
        response = await client.get(f"{config.base_url}{path}",
                                    headers={"x-admin-token": config.admin_token},
                                    params=params, timeout=8)
        response.raise_for_status()
        return {"ok": True, "data": response.json()}
    except httpx.HTTPStatusError as exc:
        return {"ok": False, "error": f"HTTP {exc.response.status_code}: {exc.response.text[:150]}"}
    except (httpx.RequestError, ValueError) as exc:
        return {"ok": False, "error": str(exc)}


async def show_dashboard(config: CLIConfig, live: bool = False, interval: float = 5.0,
                         metric: str = "success_rate", ts_interval: str = "hour") -> None:
    async with httpx.AsyncClient() as client:
        async def snapshot():
            return await asyncio.gather(
                fetch_admin_json(client, config, "/admin/evaluation/overview"),
                fetch_admin_json(client, config, "/admin/evaluation/agents"),
                fetch_admin_json(client, config, "/admin/evaluation/timeseries",
                                 {"metric": metric, "interval": ts_interval}),
                fetch_admin_json(client, config, "/agents/total_agents"),
            )

        async def make_group():
            overview, agents, timeseries, registry = await snapshot()
            return Group(build_overview_table(overview), build_leaderboard_table(agents),
                         build_timeseries_table(timeseries, metric, ts_interval),
                         build_registry_table(registry))

        if not live:
            render_dashboard(await make_group())
            return
        console.print("\n📡 [bold cyan]Live dashboard[/bold cyan] — Ctrl+C to return to chat\n")
        try:
            with Live(console=console, auto_refresh=False, screen=False) as view:
                while True:
                    render_dashboard(await make_group(), view)
                    await asyncio.sleep(max(1.0, interval))
        except KeyboardInterrupt:
            console.print("\n👋 Returning to chat...\n", style="cyan")
