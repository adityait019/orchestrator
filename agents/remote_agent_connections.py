
# agents/display_files_remote_a2a_agent.py

import logging
from urllib.parse import urlparse

from google.adk.agents.remote_a2a_agent import RemoteA2aAgent, A2A_METADATA_PREFIX
import httpx
import asyncio
from typing import Dict , List,Any,Optional
from a2a.client import A2AClient
from utils.agent_card_extractor import extract_description_capabilities_skills
from a2a.client.card_resolver import A2ACardResolver
from pydantic import PrivateAttr
logger = logging.getLogger(__name__)



class RemoteAgentInfo:
    def __init__(self,name,description,endpoint,capabilities=None,skills=None):
        self.name=name
        self.description=description
        self.endpoint=endpoint
        self.capabilities=capabilities or []
        self.skills=skills or []



class RemoteServerManager(RemoteA2aAgent):
    """
    Remote A2A agent that:
      - Sends ONLY the last user event to the remote agent (prevents token bleed).
      - Preserves remote server state via context_id when available.
      - Logs a concise summary of outbound parts for debugging.
      - On response: extracts file parts into event.custom_metadata["ui_files"],
        and keeps ONLY text parts in the content (drops function/tool/images/etc.).
    """

    _capabilities: List[str] = PrivateAttr(default_factory=list)
    _skills: List[str] = PrivateAttr(default_factory=list)
    _skills_full: List[Dict[str, Any]] = PrivateAttr(default_factory=list)
    _card_url: Optional[str] = PrivateAttr(default=None)
    _version: Optional[str] = PrivateAttr(default=None)

    def __init__(
        self,
        *args,
        filter_orchestration_noise: bool = True,
        text_preview_len: int = 160,
        max_text_previews: int = 6,
        **kwargs,
    ):
        """
        Args:
          filter_orchestration_noise: If True, drops orchestrator/tool-chatter text
            from the last user event (e.g., "For context:", backticked tool dumps).
          text_preview_len: Max chars per text preview in DEBUG logs.
          max_text_previews: Max number of text previews to include in DEBUG logs.
        """
 
        super().__init__(*args, **kwargs)
        self._filter_orchestration_noise = filter_orchestration_noise
        self._text_preview_len = text_preview_len
        self._max_text_previews = max_text_previews


    # ----- Properties that map to private attrs -----
    @property
    def capabilities(self) -> List[str]:
        return self._capabilities

    @capabilities.setter
    def capabilities(self, value: Optional[List[str]]) -> None:
        self._capabilities = list(value or [])

    @property
    def skills(self) -> List[str]:
        return self._skills

    @skills.setter
    def skills(self, value: Optional[List[str]]) -> None:
        self._skills = list(value or [])

    @property
    def skills_full(self) -> List[Dict[str, Any]]:
        return self._skills_full

    @skills_full.setter
    def skills_full(self, value: Optional[List[Dict[str, Any]]]) -> None:
        self._skills_full = list(value or [])

    @property
    def card_url(self) -> Optional[str]:
        return self._card_url

    @card_url.setter
    def card_url(self, value: Optional[str]) -> None:
        self._card_url = value

    @property
    def version(self) -> Optional[str]:
        return self._version

    @version.setter
    def version(self, value: Optional[str]) -> None:
        self._version = value


    async def ensure_metadata(self):
        if getattr(self, "_metadata_hydrated", False):
            return
        try:
            # Resolve the card if not already resolved
            await self._ensure_httpx_client()
            if getattr(self, "_agent_card_source", None):
                self.card_url = self._agent_card_source
                parsed = urlparse(self._agent_card_source)
                base = f"{parsed.scheme}://{parsed.netloc}"
                resolver = A2ACardResolver(httpx_client=self._httpx_client, base_url=base)
                agent_card = await resolver.get_agent_card(relative_card_path=parsed.path)
                self._agent_card = agent_card
            card_dict = self._agent_card.model_dump(exclude_none=True, by_alias=True) if getattr(self, "_agent_card", None) else {}
            desc, caps, skills, skills_full = extract_description_capabilities_skills(card_dict)
            if not self.description and desc:
                self.description = desc
            self.capabilities = caps
            self.skills = skills
            self.skills_full = skills_full
        except Exception as e:
            logging.debug("[%s] ensure_metadata failed: %s", self.name, e)
        finally:
            self._metadata_hydrated = True

    # -------------------------------------------------------------------------
    # Outbound construction: LAST USER TURN ONLY + optional noise filtering
    # -------------------------------------------------------------------------
    def _construct_message_parts_from_session(self, ctx):
        """
        Build A2A message parts using ONLY the last user event to prevent
        token bleeding. Optionally filters orchestrator/tool chatter text.
        Also attaches a known context_id (remote state), if present.
        """
        events = ctx.session.events or []
        last_user_event = None

        for e in reversed(events):
            if e.author == "user":
                last_user_event = e
                break

        if not last_user_event or not getattr(last_user_event, "content", None):
            if logger.isEnabledFor(logging.DEBUG):
                logger.debug("[%s] No last user event (with content) found; nothing to send.", self.name)
            return [], None

        message_parts = []
        parts = getattr(last_user_event.content, "parts", None) or []
        for part in parts:
            # Optionally skip orchestration noise (only for plain text parts)
            if self._filter_orchestration_noise:
                text = getattr(part, "text", None)
                if isinstance(text, str) and self._is_noise_text(text):
                    continue

            converted = self._genai_part_converter(part)
            if not isinstance(converted, list):
                converted = [converted] if converted else []
            message_parts.extend(converted)

        # Attach latest known remote context_id (if any) so the server can retain state.
        context_id = None
        for e in reversed(events):
            md = getattr(e, "custom_metadata", {}) or {}
            if md.get(A2A_METADATA_PREFIX + "context_id"):
                context_id = md[A2A_METADATA_PREFIX + "context_id"]
                break

        # DEBUG summary of what we will send (safe, concise)
        if logger.isEnabledFor(logging.DEBUG):
            try:
                summary = self._summarize_parts_for_log(
                    message_parts,
                    text_preview_len=self._text_preview_len,
                    max_text_previews=self._max_text_previews,
                )
                approx_tokens = self._estimate_tokens(summary.get("total_text_chars", 0))
                logger.debug(
                    (
                        "[%s] A2A outbound summary | parts=%d | text_parts=%d | file_parts=%d "
                        "| approx_tokens=%d | context_id=%s\n"
                        "Text previews:\n%s\n"
                        "Files:\n%s"
                    ),
                    self.name,
                    summary["total_parts"],
                    summary["text_parts_count"],
                    summary["file_parts_count"],
                    approx_tokens,
                    (context_id[:8] + "…") if context_id else None,
                    summary["text_previews_str"],
                    summary["file_previews_str"],
                )
            except Exception as log_ex:
                # Never allow logging to disrupt flow
                logger.debug("[%s] Error summarizing outbound parts: %s", self.name, log_ex)

        return message_parts, context_id

    # -------------------------------------------------------------------------
    # Inbound handling: keep text-only + surface file parts for UI
    # -------------------------------------------------------------------------
    async def _handle_a2a_response(self, a2a_response, ctx):
        """
        Uses base conversion, then:
          - Extracts file parts to event.custom_metadata["ui_files"] for UI use.
          - Keeps only text parts in event.content (drops images/tools/etc.).
        """
        event = await super()._handle_a2a_response(a2a_response, ctx)
        if not event:
            return event

        content = getattr(event, "content", None)
        parts = getattr(content, "parts", None) if content else None
        if not parts:
            return event

        ui_files = []
        keep_text_parts = []

        for p in parts:
            fd = getattr(p, "file_data", None)
            if fd and getattr(fd, "file_uri", None):
                ui_files.append(
                    {
                        "url": fd.file_uri,
                        "mime_type": getattr(fd, "mime_type", None),
                    }
                )
                continue

            if getattr(p, "text", None):
                keep_text_parts.append(p)

            # Drop everything else (function_call, function_response, images, etc.)

        if ui_files:
            event.custom_metadata = event.custom_metadata or {}
            event.custom_metadata["ui_files"] = ui_files

        if content is not None:
            content.parts = keep_text_parts

        return event

    # -------------------------------------------------------------------------
    # Helpers
    # -------------------------------------------------------------------------
    def _is_noise_text(self, s: str) -> bool:
        """
        Identify orchestration/tool-chatter lines you don't want to forward.
        Tune the predicates as your orchestrator evolves.
        """
        s_strip = (s or "").strip()
        return (
            s_strip.startswith("For context:")
            or s_strip.startswith("[Cortex]")
            or "`transfer_to_agent`" in s_strip
            or s_strip.startswith("[Tool]")
        )



    def _summarize_parts_for_log(self, a2a_parts, *, text_preview_len: int, max_text_previews: int):
            """
            Produce a concise, safe summary of the parts being sent:
            - Counts (total, text, files)
            - Short text previews (truncated, single-line)
            - Shortened file URIs (query stripped, tail of path only)

            Supports BOTH:
            • GenAI parts (e.g., .text, .file_data.file_uri, .file_data.mime_type)
            • A2A parts   (e.g., Part(root=TextPart|FilePart), with root.text or root.file.uri)
            """
            text_previews = []
            file_previews = []
            text_parts_count = 0
            file_parts_count = 0
            total_text_chars = 0

            for p in a2a_parts:
                # ---- GenAI-style TEXT ----
                text = getattr(p, "text", None)
                if isinstance(text, str) and text.strip():
                    text_parts_count += 1
                    total_text_chars += len(text)
                    if len(text_previews) < max_text_previews:
                        one_line = " ".join(text.split())
                        preview = (one_line[:text_preview_len] + "…") if len(one_line) > text_preview_len else one_line
                        text_previews.append(f"- {preview}")
                    continue

                # ---- GenAI-style FILE ----
                fd = getattr(p, "file_data", None)
                if fd and getattr(fd, "file_uri", None):
                    file_parts_count += 1
                    uri = getattr(fd, "file_uri", "")
                    mime = getattr(fd, "mime_type", None)
                    safe_uri = self._shorten_uri(uri)
                    file_previews.append(f"- {mime or 'unknown'} | {safe_uri}")
                    continue

                # ---- A2A-style (wrapper with .root) ----
                root = getattr(p, "root", None)
                if root is not None:
                    # A2A TextPart: root.text
                    r_text = getattr(root, "text", None)
                    if isinstance(r_text, str) and r_text.strip():
                        text_parts_count += 1
                        total_text_chars += len(r_text)
                        if len(text_previews) < max_text_previews:
                            one_line = " ".join(r_text.split())
                            preview = (one_line[:text_preview_len] + "…") if len(one_line) > text_preview_len else one_line
                            text_previews.append(f"- {preview}")
                        continue

                    # A2A FilePart: root.file.uri (+ mime_type/mimeType)
                    file_obj = getattr(root, "file", None)
                    if file_obj is not None:
                        uri = getattr(file_obj, "uri", None)
                        if uri:
                            file_parts_count += 1
                            mime = getattr(file_obj, "mime_type", None) or getattr(file_obj, "mimeType", None)
                            safe_uri = self._shorten_uri(uri)
                            file_previews.append(f"- {mime or 'unknown'} | {safe_uri}")
                            continue

            previews_str = "\n".join(text_previews) if text_previews else "(no text parts)"
            files_str = "\n".join(file_previews) if file_previews else "(no file parts)"

            return {
                "total_parts": len(a2a_parts),
                "text_parts_count": text_parts_count,
                "file_parts_count": file_parts_count,
                "total_text_chars": total_text_chars,
                "text_previews_str": previews_str,
                "file_previews_str": files_str,
            }
    

    def _shorten_uri(self, uri: str, keep_tail: int = 36) -> str:
        """
        Shorten potentially sensitive URIs for logging:
        - drop query string
        - show only the tail of the path
        """
        try:
            u = urlparse(uri)
            path = u.path or ""
            tail = path[-keep_tail:] if len(path) > keep_tail else path
            base = f"{u.scheme}://{u.netloc}" if (u.scheme and u.netloc) else ""
            return f"{base}/…{tail}"
        except Exception:
            return (uri[:keep_tail] + "…") if len(uri) > keep_tail else uri

    def _estimate_tokens(self, char_count: int) -> int:
        """
        Rough heuristic: ~4 chars/token. Good for spotting regressions in DEBUG logs.
        """
        return max(1, char_count // 4)