import json
import re

META_TOKEN_PREFIX = "[META:TOKEN_USAGE] "
META_TOKEN_RE = re.compile(r"^\[META:TOKEN_USAGE\]\s*(\{.*\})\s*$")

class YourClientClass(...):
    async def _handle_a2a_response(self, a2a_response, ctx):
        """
        Uses base conversion, then:
          - Extracts file parts to event.custom_metadata["ui_files"] for UI use.
          - Keeps only text parts in event.content (drops images/tools/etc.).
          - NEW: Parses token usage meta from TextPart(s) that start with [META:TOKEN_USAGE],
                 and stores it into event.custom_metadata["token_usage"].
          - NEW (optional): If a token_usage.json artifact appears, store that too.
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

        # Local variable to capture token usage, if present
        token_usage_meta = None

        for p in parts:
            # --- 1) FILE PARTS -> ui_files ---
            fd = getattr(p, "file_data", None)
            if fd and getattr(fd, "file_uri", None):
                file_uri = fd.file_uri
                mime_type = getattr(fd, "mime_type", None)

                # Optional: detect token_usage.json artifacts later if you adopt Option C
                # If you do, capture it separately (not displayed in chat).
                parsed_usage_from_artifact = None
                try:
                    # Only sniff by filename if present in URL; your URL includes filename at the end
                    # e.g., .../files/<session>/token_usage.json?exp=...&sig=...
                    # We won't fetch here (no network); we just route it to metadata.
                    if file_uri.lower().endswith("token_usage.json") or "token_usage.json?" in file_uri.lower():
                        # Just store as a reference; your UI can fetch/download if needed
                        parsed_usage_from_artifact = {
                            "type": "token_usage",
                            "source": "artifact",
                            "uri": file_uri,
                            "mime_type": mime_type or "application/json",
                        }
                except Exception:
                    pass

                ui_files.append(
                    {
                        "url": file_uri,
                        "mime_type": mime_type,
                    }
                )

                # If you want to capture the artifact reference
                if parsed_usage_from_artifact:
                    token_usage_meta = token_usage_meta or {}
                    token_usage_meta["artifact"] = parsed_usage_from_artifact

                continue  # skip to next part

            # --- 2) TEXT PARTS -> human chat; also detect token meta prefix ---
            text_val = getattr(p, "text", None)
            if text_val is None:
                # Drop everything else (function_call, function_response, images, etc.)
                
                continue

            # Detect token usage meta line and parse JSON payload
            # Format we emit from server:
            #   [META:TOKEN_USAGE] {"type":"token_usage","input":637,"output":132,"total":769}
            m = META_TOKEN_RE.match(text_val.strip())
            if m:
                try:
                    payload = json.loads(m.group(1))
                    if isinstance(payload, dict) and payload.get("type") == "token_usage":
                        # Merge with any existing token_usage_meta
                        token_usage_meta = (token_usage_meta or {}) | payload
                    else:
                        # If type isn't token_usage, ignore silently
                        pass
                except Exception:
                    # If parsing fails, ignore this line (don't render)
                    pass

                # IMPORTANT: Do NOT include this meta line in visible message parts
                # (keep text clean for chat UI)
                continue

            # Regular human-visible text -> keep
            keep_text_parts.append(p)

        # --- 3) Save extracted files for UI consumption ---
        if ui_files:
            event.custom_metadata = getattr(event, "custom_metadata", None) or {}
            event.custom_metadata["ui_files"] = ui_files

        # --- 4) Save token usage metadata for analytics/plots ---
        if token_usage_meta:
            event.custom_metadata = getattr(event, "custom_metadata", None) or {}
            # One easy place: stash per-message usage here; your client aggregator can
            # persist per task/context ID for charting later
            event.custom_metadata["token_usage"] = token_usage_meta

        # --- 5) Keep only text parts we want to display in the chat ---
        if content is not None:
            content.parts = keep_text_parts

        return event