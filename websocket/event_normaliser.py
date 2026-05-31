#websocket/event_normalizer.py
from __future__ import annotations
import json
import re
from dataclasses import dataclass, field
from typing import Any, List, Dict, Optional
import logging

logger = logging.getLogger(__name__)

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


# =========================================================
# ✅ BASIC EXTRACTORS
# =========================================================

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

    # ADK format
    fd = getattr(part, "file_data", None)
    if fd:
        uri = getattr(fd, "file_uri", None)
        if isinstance(uri, str) and uri.strip():
            files.append(uri.strip())

    # Root-wrapped format
    root = getattr(part, "root", None)
    if root is not None:
        file_obj = getattr(root, "file", None)
        if file_obj:
            uri = getattr(file_obj, "uri", None)
            if isinstance(uri, str) and uri.strip():
                files.append(uri.strip())

    # Direct URI
    uri = getattr(part, "uri", None)
    if isinstance(uri, str) and uri.strip():
        files.append(uri.strip())

    return files


# =========================================================
# ✅ SEMANTIC TEXT PROCESSING
# =========================================================

def _ingest_semantic_text(text: str, ue: UnifiedEvent) -> bool:
    if not text or not text.strip():
        return False

    stripped = text.strip()

    # ✅ A2A PROGRESS
    if stripped.startswith(A2A_PROGRESS_PREFIX):
        raw = stripped[len(A2A_PROGRESS_PREFIX):].strip()
        try:
            payload = json.loads(raw)
        except Exception:
            return True

        if isinstance(payload, dict):
            existing = ue.metadata.get("a2a:progress")
            if isinstance(existing, dict):
                merged = dict(existing)
                merged.update(payload)
                ue.metadata["a2a:progress"] = merged
            else:
                ue.metadata["a2a:progress"] = payload

            event_type = payload.get("event")
            name = payload.get("tool_name") or payload.get("name")

            if event_type == "tool_call":
                ue.tool_call = {"name": name or "remote_tool"}
            elif event_type == "tool_response":
                ue.tool_call = ue.tool_call or {"name": name or "remote_tool"}
                resp = payload.get("tool_response")
                ue.tool_response = "" if resp is None else str(resp)

        return True

    # ✅ TOKEN USAGE
    m = META_TOKEN_RE.match(stripped)
    if m:
        try:
            payload = json.loads(m.group(1))
            if isinstance(payload, dict):
                existing = ue.metadata.get("tool_usage")
                merged = {**existing, **payload} if isinstance(existing, dict) else payload
                ue.metadata["tool_usage"] = merged
                ue.metadata["token_usage"] = merged
        except Exception:
            pass
        return True

    # ✅ TOOL CALL (fallback)
    m2 = TOOL_CALL_RE.match(stripped)
    if m2:
        ue.tool_call = {"name": m2.group(1).strip()}
        return True

    # ✅ TOOL RESPONSE (fallback)
    m3 = TOOL_RESPONSE_RE.match(stripped)
    if m3:
        ue.tool_response = m3.group(1).strip()
        return True

    return False


# =========================================================
# ✅ MAIN NORMALIZER (FIXED)
# =========================================================

def normalize_event(event: Any) -> UnifiedEvent:
    ue = UnifiedEvent(raw_event=event)

    raw_meta = getattr(event, "custom_metadata", {}) or {}
    logger.debug("[INITIAL RAW META]: %s", raw_meta)

    token_usage = None

    try:
        a2a_resp = raw_meta.get("a2a:response")

        if isinstance(a2a_resp, dict):
            logger.debug("[A2A RESPONSE FOUND]")

            # ✅ Direct metadata
            resp_meta = a2a_resp.get("metadata")
            if isinstance(resp_meta, dict):
                token_usage = resp_meta.get("token_usage")

            # ✅ Status section
            status = a2a_resp.get("status")

            if isinstance(status, dict):
                msg = status.get("message")

                # ✅ ✅ STORE STRUCTURED ERROR SAFELY
                ue.metadata["a2a:error_struct"] = msg

                if isinstance(msg, dict):
                    parts = msg.get("parts", [])

                    for part in parts:

                        # ✅ TEXT
                        text = part.get("text")
                        if isinstance(text, str) and text.strip():
                            ue.metadata["a2a:error_text"] = text.strip()

                        # ✅ ✅ ✅ CRITICAL FIX: FILE EXTRACTION
                        file_obj = part.get("file")
                        if isinstance(file_obj, dict):
                            uri = file_obj.get("uri")
                            if isinstance(uri, str) and uri.strip():
                                ue.files.append(uri.strip())

                elif isinstance(msg, str):
                    ue.metadata["a2a:error_text"] = msg

                # ✅ fallback token usage
                if not token_usage:
                    meta2 = status.get("metadata")
                    if isinstance(meta2, dict):
                        token_usage = meta2.get("token_usage")

        if token_usage:
            logger.debug("[✅ TOKEN USAGE FOUND]: %s", token_usage)

    except Exception:
        logger.exception("[TOKEN + ERROR EXTRACTION ERROR]")

    # ✅ Inject token usage
    if isinstance(token_usage, dict):
        ue.metadata["token_usage"] = token_usage
        ue.metadata["tool_usage"] = token_usage

    # ✅ Progress metadata
    progress = raw_meta.get("a2a:progress")
    if isinstance(progress, dict):
        ue.metadata["a2a:progress"] = progress

    recovered = raw_meta.get("recovered_progress_events")
    if isinstance(recovered, list):
        ue.metadata["recovered_progress_events"] = recovered

    # =========================================================
    # ✅ STANDARD CONTENT EXTRACTION
    # =========================================================
    content = getattr(event, "content", None)
    parts = getattr(content, "parts", None) or []

    text_chunks = []

    for part in parts:

        # ✅ files from standard ADK
        for file_url in extract_files_from_part(part):
            ue.files.append(file_url)

        # ✅ data blocks
        if getattr(part, "type", None) == "data":
            data_content = getattr(part, "data", None)
            if isinstance(data_content, dict):
                ue.data.update(data_content)

        text = extract_text_from_part(part)
        if not text:
            continue

        if _ingest_semantic_text(text, ue):
            continue

        text_chunks.append(text)

    ue.text = ("\n".join(text_chunks).strip() or None)

    # ✅ Deduplicate files
    if ue.files:
        ue.files = list(dict.fromkeys(ue.files))

    logger.debug(
        "[✅ FINAL NORMALIZED EVENT] text=%s files=%s metadata=%s",
        ue.text,
        ue.files,
        ue.metadata,
    )

    return ue
