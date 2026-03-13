# helpers_download.py
import os
import re
import time
import html
from pathlib import Path
from urllib.parse import urlparse, parse_qs, unquote
import httpx
import requests  # ensure available in your classification service env

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


def _parse_signed_url(file_url: str) -> tuple[str, str, int]:
    """
    Extract file_id, decoded filename, and 'exp' from a signed URL of the form:
      http(s)://<host>/files/<file_id>/<encoded_filename>?exp=<int>&sig=<hex>
    Tolerates HTML-escaped URLs (e.g., '&amp;' in query string).
    """
    file_url = _sanitize_url(file_url)

    parts = urlparse(file_url)
    path_parts = parts.path.strip("/").split("/")
    if len(path_parts) < 3 or path_parts[0] != "files":
        raise ValueError(f"Unexpected file URL path format: {parts.path!r}")
    file_id = path_parts[1]
    # filename may be percent-encoded in the URL path; decode it for local filesystem use
    filename = unquote(path_parts[2])

    # Parse query robustly; keep blank values if present
    qs = parse_qs(parts.query, keep_blank_values=True)

    exp_vals = qs.get("exp", [])
    if not exp_vals or not exp_vals[0]:
        # If the URL had '&amp;', html.unescape above already fixed it; if still missing, error out
        raise ValueError("Missing 'exp' in signed URL.")
    exp_str = exp_vals[0]
    try:
        exp = int(exp_str)
    except ValueError as e:
        raise ValueError(f"Invalid 'exp' value in signed URL: {exp_str!r}") from e

    # We don't need 'sig' for the client, but parsing it here can help with debugging
    # sig_vals = qs.get("sig", [])
    # if not sig_vals or not sig_vals[0]:
    #     raise ValueError("Missing 'sig' in signed URL.")

    return file_id, filename, exp


async def fetch_remote_file(file_url: str, dest_root: Path = DOWNLOAD_ROOT, timeout: int = 120):
    """
    Download the file pointed to by the signed URL into a local cache folder:
      <dest_root>/<file_id>/<filename>

    Raises:
      ValueError on signature param issues, expired links, or unsupported extension.
      RuntimeError on HTTP or content-type issues.
    """
    # Parse and validate URL and expiry
    file_id, filename, exp = _parse_signed_url(file_url)

    # Validate expiry BEFORE making the request
    now = int(time.time())
    if exp < now:
        raise ValueError("Signed URL is expired. Please re-upload to get a fresh link.")

    # Optional: validate extension on the *decoded* filename

    # Prepare destination path
    dest_dir = dest_root / file_id
    dest_dir.mkdir(parents=True, exist_ok=True)
    local_path = dest_dir / filename

    # Sanitize URL again in case upstream passed escaped entities
    safe_url = _sanitize_url(file_url)

    # Stream download to file
    async with httpx.AsyncClient(timeout=timeout) as client:
        try:
            resp = await client.get(safe_url)
        except Exception as e:
            raise RuntimeError(f"Failed to perform GET on signed URL: {e}") from e

        if resp.status_code != 200:
            # Bubble the status to help orchestration decide on re-sign/re-upload
            raise RuntimeError(f"Failed to download file (HTTP {resp.status_code}).")

  

        # Write to disk
        with open(local_path, "wb") as f:
            f.write(resp.content)

    return file_id, filename, str(local_path.resolve())




def upload_to_orchestrator(file_path: str, session_id: str):
    url = "http://10.73.83.83:8000/upload"

    with open(file_path, "rb") as f:
        files = {
            "files": (Path(file_path).name, f)
        }
        data = {
            "session_id": session_id
        }

        resp = requests.post(url, files=files, data=data, timeout=120)
        resp.raise_for_status()
