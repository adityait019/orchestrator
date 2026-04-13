async def handle_a2a_status_message(message, emitter, processor, context):
    """
    Handle A2A status.message payloads.
    These are OUTPUT, not progress.
    """

    # message shape:
    # {
    #   "kind": "message",
    #   "parts": [ ... ],
    #   "metadata": {...}
    # }

    parts = message.get("parts", [])
    if not parts:
        return

    for part in parts:
        # FILE OUTPUT
        if part.get("kind") == "file":
            file_obj = part.get("file", {})
            uri = file_obj.get("uri")
            if uri:
                await emitter.file_processed([uri])
            continue

        # TEXT OUTPUT
        if part.get("kind") == "text":
            text = part.get("text")
            if text:
                await emitter.bot_message(text)
            continue