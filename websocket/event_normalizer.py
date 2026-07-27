from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, List, Dict, Optional
import logging

logger = logging.getLogger(__name__)


# =========================================================
# ✅ STANDARDIZED EVENT MODEL (EXTENDED FOR FUTURE USE)
# =========================================================



@dataclass
class UnifiedEvent:
    # ✅ content
    text: Optional[str] = None
    files: List[str] = field(default_factory=list)
    data: Dict[str, Any] = field(default_factory=dict)

    # ✅ metadata (primary merged metadata)
    metadata: Dict[str, Any] = field(default_factory=dict)

    # ✅ tool abstraction
    tool_call: Optional[dict] = None
    tool_response: Optional[str] = None

    # ✅ A2A structured tracing (NEW ✅)
    a2a_state: Optional[str] = None
    a2a_task_id: Optional[str] = None
    a2a_context_id: Optional[str] = None

    # ✅ token usage (normalized)
    token_usage: Optional[Dict[str, int]] = None

    # ✅ raw debug
    raw_event: Any = None
    raw_meta: Dict[str, Any] = field(default_factory=dict)
    raw_a2a_response: Optional[Dict] = None


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



def extract_text_from_a2a_message(message: Any) -> Optional[str]:
    """
    Extract text from an A2A message dictionary:
    {
        "parts": [
            {"kind": "text", "text": "..."}
        ]
    }
    """
    if not isinstance(message, dict):
        return None

    parts = message.get("parts") or []

    chunks: list[str] = []

    for part in parts:
        if not isinstance(part, dict):
            continue

        text = part.get("text")

        if isinstance(text, str):
            cleaned = text.strip()
            if cleaned:
                chunks.append(cleaned)

    if chunks:
        return "\n".join(chunks).strip()

    return None


def extract_token_usage(event: Any) -> Optional[Dict[str, int]]:
    """Normalize provider/ADK usage metadata into the orchestration format."""
    usage = getattr(event, "usage_metadata", None)
    if usage is None:
        return None

    if hasattr(usage, "model_dump"):
        usage = usage.model_dump(exclude_none=True)
    elif not isinstance(usage, dict):
        usage = vars(usage)

    if not isinstance(usage, dict):
        return None

    def value(*keys: str) -> int:
        for key in keys:
            raw = usage.get(key)
            if raw is not None:
                try:
                    return int(raw)
                except (TypeError, ValueError):
                    return 0
        return 0

    input_tokens = value("prompt_token_count", "prompt_tokens", "input_tokens")
    output_tokens = value(
        "candidates_token_count", "completion_tokens", "output_tokens"
    )
    total_tokens = value("total_token_count", "total_tokens")
    if not total_tokens:
        total_tokens = input_tokens + output_tokens

    if not (input_tokens or output_tokens or total_tokens):
        return None

    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": total_tokens,
    }

# =========================================================
# ✅ MAIN NORMALIZER (FINAL VERSION)
# =========================================================

def normalize_event(event: Any) -> UnifiedEvent:
    ue = UnifiedEvent(raw_event=event)

    raw_meta = getattr(event, "custom_metadata", {}) or {}
    ue.raw_meta = raw_meta

    logger.debug("[INITIAL RAW META]: %s", raw_meta)

    # =========================================================
    # ✅ Preserve identifiers EARLY
    # =========================================================
    for key in ["a2a:task_id", "a2a:context_id"]:
        if key in raw_meta:
            ue.metadata[key] = raw_meta[key]

    ue.a2a_task_id = raw_meta.get("a2a:task_id")
    ue.a2a_context_id = raw_meta.get("a2a:context_id")

    # ADK/LiteLLM emits usage on ``event.usage_metadata``. A2A metadata below
    # remains supported for remote agents and fills in when direct usage is
    # unavailable.
    token_usage = extract_token_usage(event)

    try:
        a2a_resp = raw_meta.get("a2a:response")
        ue.raw_a2a_response = a2a_resp

        if isinstance(a2a_resp, dict):
            logger.debug("[A2A RESPONSE FOUND]")

            # =========================================================
            # ✅ FILE EXTRACTION
            # =========================================================
            for source in ["artifacts", "history"]:
                items = a2a_resp.get(source, [])
                if isinstance(items, list):
                    for item in items:
                        parts = item.get("parts", [])
                        for part in parts:
                            if isinstance(part, dict):
                                file_obj = part.get("file")
                                if isinstance(file_obj, dict):
                                    uri = file_obj.get("uri")
                                    if isinstance(uri, str) and uri.strip():
                                        ue.files.append(uri.strip())

            # =========================================================
            # ✅ METADATA EXTRACTION (CRITICAL FIX)
            # =========================================================
            resp_meta = a2a_resp.get("metadata")
            if isinstance(resp_meta, dict):

                # ✅ merge FULL metadata
                ue.metadata.update(resp_meta)
                tool_call_id = resp_meta.get("tool_call_id")

                if tool_call_id:
                    ue.metadata['tool_call_id']=tool_call_id
                # ✅ extract token usage safely
                token_usage = resp_meta.get("token_usage")

                if not token_usage:
                    if any(k in resp_meta for k in ["input_tokens", "output_tokens", "total_tokens"]):
                        token_usage = {
                            "input_tokens": int(resp_meta.get("input_tokens") or 0),
                            "output_tokens": int(resp_meta.get("output_tokens") or 0),
                            "total_tokens": int(resp_meta.get("total_tokens") or 0),
                        }

            # =========================================================
            # ✅ STATUS EXTRACTION
            # =========================================================
            status = a2a_resp.get("status")

            if isinstance(status, dict):
                state = (status.get("state") or "").lower()
                ts = status.get("timestamp")
                msg = status.get("message")
                # ✅ Extract user-facing A2A status message text for ALL states,
                # including input-required and completed.
                
                status_text = extract_text_from_a2a_message(msg)

                if status_text:
                    if ue.text:
                        ue.text = f"{ue.text}\n{status_text}".strip()
                    else:
                        ue.text = status_text
                if state:
                    ue.metadata["a2a:state"] = state
                    ue.a2a_state = state

                if ts:
                    ue.metadata["a2a:timestamp"] = ts

                # ✅ failure handling
                if state == "failed":
                    ue.metadata["a2a:error_struct"] = msg

                    if isinstance(msg, dict):
                        parts = msg.get("parts", [])
                        for part in parts:
                            text = part.get("text")
                            if isinstance(text, str) and text.strip():
                                ue.metadata["a2a:error_text"] = text.strip()

                            file_obj = part.get("file")
                            if isinstance(file_obj, dict):
                                uri = file_obj.get("uri")
                                if isinstance(uri, str) and uri.strip():
                                    ue.files.append(uri.strip())

                    elif isinstance(msg, str):
                        ue.metadata["a2a:error_text"] = msg

                # ✅ fallback token_usage
                if not token_usage:
                    meta2 = status.get("metadata")
                    if isinstance(meta2, dict):
                        token_usage = meta2.get("token_usage")
            # ✅ Fallback: if status.message did not provide text,
            
            # extract the latest text from A2A history.
            if not ue.text:
                history = a2a_resp.get("history") or []

                if isinstance(history, list):
                    for history_msg in reversed(history):
                        history_text = extract_text_from_a2a_message(history_msg)

                        if history_text:
                            ue.text = history_text
                            break
        if token_usage:
            logger.debug("[✅ TOKEN USAGE FOUND]: %s", token_usage)

    except Exception:
        logger.exception("[TOKEN + ERROR EXTRACTION ERROR]")

    # =========================================================
    # ✅ Inject normalized token usage
    # =========================================================
    if isinstance(token_usage, dict):
        ue.token_usage = token_usage
        ue.metadata["token_usage"] = token_usage
        ue.metadata["tool_usage"] = token_usage

    # =========================================================
    # ✅ TOOL EVENT NORMALIZATION
    # =========================================================
    meta_type = raw_meta.get("type") or ue.metadata.get("type")

    if meta_type:
        ue.metadata["type"] = meta_type

    if meta_type in ("tool_event", "usage"):
        phase = raw_meta.get("phase") or ue.metadata.get("phase")
        tool_name = raw_meta.get("tool_name") or ue.metadata.get("tool_name")

        if phase == "call":
            ue.tool_call = {"name": tool_name or "unknown_tool"}

        elif phase == "response":
            ue.tool_call = ue.tool_call or {"name": tool_name or "unknown_tool"}
            data = raw_meta.get("data") or ue.metadata.get("data")
            ue.tool_response = "" if data is None else str(data)

    # =========================================================
    # ✅ CONTENT EXTRACTION
    # =========================================================
    content = getattr(event, "content", None)
    parts = getattr(content, "parts", None) or []

    text_chunks = []

    for part in parts:

        for file_url in extract_files_from_part(part):
            ue.files.append(file_url)

        if getattr(part, "type", None) == "data":
            data_content = getattr(part, "data", None)
            if isinstance(data_content, dict):
                ue.data.update(data_content)

        text = extract_text_from_part(part)
        if text:
            text_chunks.append(text)

    ue.text = ("\n".join(text_chunks).strip() or None)

    # ✅ remove duplicates
    if ue.files:
        ue.files = list(dict.fromkeys(ue.files))

    # =========================================================
    # ✅ FINAL DEBUG LOG
    # =========================================================
    logger.debug(
        "[✅ FINAL NORMALIZED EVENT] text=%s files=%s metadata=%s",
        ue.text,
        ue.files,
        ue.metadata,
    )

    return ue
