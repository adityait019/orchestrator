# helpers_download.py
import os
import re
import time
import html
from pathlib import Path
from urllib.parse import urlparse, parse_qs, unquote
import httpx
import uuid
import requests

DOWNLOAD_ROOT = Path(os.getenv("CLASSIFIER_DOWNLOAD_ROOT", "./downloads"))
DOWNLOAD_ROOT.mkdir(parents=True, exist_ok=True)

# Accept .xlsx and .xlsm (case-insensitive)
# _ALLOWED_EXT = re.compile(r"\.xls[xm]?$", re.IGNORECASE)

_ALLOWED_EXT = re.compile(r"\.(xlsx|xlsm|zip)$", re.IGNORECASE)

def _sanitize_url(u: str) -> str:
    """
    Fix common transport issues:
      - HTML entity escaping (&amp; -> &)
      - Strip accidental whitespace
    """
    if not u:
        raise ValueError("Empty file URL.")
    return html.unescape(u).strip()



def _parse_signed_url(file_url: str) -> tuple[str, str]:
    """
    Extract (file_id, filename) from:
    /files/{tenant_id}/{user_id}/{session_id}/{file_id}/{filename}
    """
    file_url = _sanitize_url(file_url)

    parts = urlparse(file_url)
    path_parts = parts.path.strip("/").split("/")

    if len(path_parts) < 6 or path_parts[0] != "files":
        raise ValueError(f"Unexpected file URL format: {parts.path}")

    file_id = path_parts[4]
    filename = unquote(path_parts[5])

    return file_id, filename





async def fetch_remote_file(
    file_url: str,
    dest_root: Path = DOWNLOAD_ROOT,
    timeout: int = 120,
) -> tuple[str, str, str]:
    """
    Download a remote file.

    Supports:
    - Orchestrator-signed URLs
    - External / tool-generated URLs
    """

    file_url = _sanitize_url(file_url)

    # ✅ Initialize first (important for static analyzers)
    file_id: str | None = None
    filename: str | None = None

    # -------------------------------------------------
    # MODE 1: Orchestrator-signed URL
    # -------------------------------------------------
    try:
        file_id, filename = _parse_signed_url(file_url)
        orchestrator_managed = True
    except ValueError:
        orchestrator_managed = False

    # -------------------------------------------------
    # MODE 2: External / legacy URL
    # -------------------------------------------------
    if not orchestrator_managed:
        parsed = urlparse(file_url)

        filename = unquote(Path(parsed.path).name)
        if not filename:
            raise ValueError("Could not determine filename from external URL")

        file_id = f"external-{uuid.uuid4().hex}"

    # -------------------------------------------------
    # ✅ Final safety check (defensive programming)
    # -------------------------------------------------
    if not file_id or not filename:
        raise RuntimeError(
            f"Internal error: file_id or filename not resolved "
            f"(file_id={file_id}, filename={filename})"
        )

    # -------------------------------------------------
    # Download
    # -------------------------------------------------
    dest_dir = dest_root / file_id
    dest_dir.mkdir(parents=True, exist_ok=True)
    local_path = dest_dir / filename

    async with httpx.AsyncClient(
        timeout=timeout,
        follow_redirects=True,
    ) as client:
        resp = await client.get(file_url)

        if resp.status_code != 200:
            raise RuntimeError(
                f"Failed to download file (HTTP {resp.status_code}): "
                f"{resp.text[:200]}"
            )

        with open(local_path, "wb") as f:
            async for chunk in resp.aiter_bytes(chunk_size=8192):
                f.write(chunk)

    return file_id, filename, str(local_path.resolve())
