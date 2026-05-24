from __future__ import annotations
import json
import re
from dataclasses import dataclass, field
from typing import Any, List, Dict, Optional

A2A_PROGRESS_PREFIX = "[A2A_PROGRESS]"
META_TOKEN_RE = re.compile(r"^\[META:TOKEN_USAGE\]\s*(\{.*\})\s*$")
TOOL_CALL_RE = re.compile(r"^🛠\s*Tool called:\s*(.+)$", re.DOTALL)
TOOL_RESPONSE_RE = re.compile(r"^📦\s*Tool response:\s*(.*)$", re.DOTALL)

@dataclass
class UnifiedEvent:
    text: Optional[str] = None
    files: List[str] = field(default_factory=list)
    data: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
    tool_call: Optional[dict] = None
    tool_response: Optional[str] = None
    raw_event: Any = None

def extract_text_from_part(part: Any) -> Optional[str]:
    text = getattr(part, "text", None)
    if isinstance(text, str):
        cleaned = text.strip()
        if cleaned:
            return cleaned
    root = getattr(part, "root", None)
    if root is not None:
        root_text = getattr(root, "text", None)
        if isinstance(root_text, str):
            cleaned = root_text.strip()
            if cleaned:
                return cleaned
    return None

def extract_files_from_part(part: Any) -> List[str]:
    files: List[str] = []
    fd = getattr(part, "file_data", None)
    if fd:
        uri = getattr(fd, "file_uri", None)
        if isinstance(uri, str) and uri.strip():
            files.append(uri.strip())
    root = getattr(part, "root", None)
    if root is not None:
        file_obj = getattr(root, "file", None)
        if file_obj:
            uri = getattr(file_obj, "uri", None)
            if isinstance(uri, str) and uri.strip():
                files.append(uri.strip())
    uri = getattr(part, "uri", None)
    if isinstance(uri, str) and uri.strip():
        files.append(uri.strip())
    return files

def _ingest_semantic_text(text: str, ue: UnifiedEvent) -> bool:
    """Handle semantic markers in a text chunk."""
    if not text or not text.strip():
        return False
    stripped = text.strip()

    # Our custom [A2A_PROGRESS] marker
    if stripped.startswith(A2A_PROGRESS_PREFIX):
        raw = stripped[len(A2A_PROGRESS_PREFIX):].strip()
        try:
            payload = json.loads(raw)
        except Exception:
            return True  # consumed by marker even if invalid JSON
        if isinstance(payload, dict):
            # Merge into metadata
            existing = ue.metadata.get("a2a:progress")
            if isinstance(existing, dict):
                merged = dict(existing)
                merged.update(payload)
                ue.metadata["a2a:progress"] = merged
            else:
                ue.metadata["a2a:progress"] = payload
            # Also record structured tool events (backward-compatible)
            event_type = payload.get("event")
            name = payload.get("tool_name") or payload.get("name")
            if event_type == "tool_call":
                ue.tool_call = {"name": name or "remote_tool"}
            elif event_type == "tool_response":
                ue.tool_call = ue.tool_call or {"name": name or "remote_tool"}
                resp = payload.get("tool_response")
                ue.tool_response = "" if resp is None else str(resp)
        return True

    # # META token (unchanged)
    # m = META_TOKEN_RE.match(stripped)
    # if m:
    #     try:
    #         payload = json.loads(m.group(1))
    #         if isinstance(payload, dict):
    #             existing = ue.metadata.get("tool_usage")
    #             if isinstance(existing, dict):
    #                 merged = dict(existing)
    #                 merged.update(payload)
    #                 ue.metadata["tool_usage"] = merged
    #             else:
    #                 ue.metadata["tool_usage"] = payload
    #     except Exception:
    #         pass
    #     return True


    # META token
    m = META_TOKEN_RE.match(stripped)
    if m:
        try:
            payload = json.loads(m.group(1))
            if isinstance(payload, dict):
                existing = ue.metadata.get("tool_usage")
                merged = {**existing, **payload} if isinstance(existing, dict) else payload
                ue.metadata["tool_usage"] = merged
                ue.metadata["token_usage"] = merged  # ✅ canonical alias
        except Exception:
            pass
        return True


    # Emoji-based markers (unchanged fallback)
    m2 = TOOL_CALL_RE.match(stripped)
    if m2:
        ue.tool_call = {"name": m2.group(1).strip()}
        return True
    m3 = TOOL_RESPONSE_RE.match(stripped)
    if m3:
        ue.tool_response = m3.group(1).strip()
        return True

    return False

def normalize_event(event: Any) -> UnifiedEvent:
    ue = UnifiedEvent(raw_event=event)

    # Merge any existing metadata (including our recovered progress events)
    raw_meta = getattr(event, "custom_metadata", {}) or {}
    if isinstance(raw_meta, dict):
        # Existing progress if any
        progress = raw_meta.get("a2a:progress")
        if isinstance(progress, dict):
            ue.metadata["a2a:progress"] = progress
        # Recovered events list
        rec = raw_meta.get("recovered_progress_events")
        if isinstance(rec, list):
            # If needed, we could flatten or handle each one; 
            # For simplicity, keep as-is (processor will handle list).
            ue.metadata["recovered_progress_events"] = rec
        # Token usage, UI files as before
        token_usage = raw_meta.get("tool_usage") or raw_meta.get("token_usage")
        if isinstance(token_usage, dict):
            ue.metadata["tool_usage"] = token_usage
            ue.metadata["token_usage"] = token_usage
        if isinstance(raw_meta.get("ui_files"), list):
            for item in raw_meta["ui_files"]:
                if isinstance(item, dict):
                    url = item.get("url")
                    if isinstance(url, str) and url.strip():
                        ue.files.append(url.strip())

    # Process parts (text and files)
    content = getattr(event, "content", None)
    parts = getattr(content, "parts", None) or []
    text_chunks: List[str] = []
    for part in parts:
        # File URLs
        for file_url in extract_files_from_part(part):
            ue.files.append(file_url)
        # Data parts
        if getattr(part, "type", None) == "data":
            data_content = getattr(part, "data", None)
            if isinstance(data_content, dict):
                ue.data.update(data_content)
        # Text parts
        text = extract_text_from_part(part)
        if not text:
            continue
        if _ingest_semantic_text(text, ue):
            # Consumed by semantic marker, do not add to normal text
            continue
        text_chunks.append(text)
    ue.text = ("\n".join(text_chunks).strip() or None)
    return ue
