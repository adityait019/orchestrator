# # agents/hitl_handler.py
# from google.adk.models.llm_response import LlmResponse
# from google.genai import types
# import uuid
# import logging

# logger = logging.getLogger(__name__)


# # =====================================================
# # ✅ UTILITY: SIMPLE INTENT CHECK
# # =====================================================
# def is_followup(user_msg: str):
#     short_replies = ["yes", "y", "ok", "yes please", "continue", "go ahead"]
#     return user_msg.lower().strip() in short_replies


# # =====================================================
# # ✅ CORE FIX: SAFE TOOL CALL CREATOR
# # =====================================================
# def make_tool_call(name: str, args: dict):
#     """Always create function_call WITH ID (CRITICAL FIX)"""
#     part = types.Part.from_function_call(
#         name=name,
#         args=args,
#     )
#     assert part.function_call is not None  # ✅ tells type checker it's safe
#     part.function_call.id = str(f"call_{uuid.uuid4().hex}")  # ✅ REQUIRED
#     return part


# # =====================================================
# # ✅ SAFETY: PATCH ANY MISSING IDS
# # =====================================================
# def ensure_tool_ids(llm_request):
#     """Global safety net (prevents Azure 400 crash)"""
#     for content in llm_request.contents or []:
#         for part in content.parts or []:

#             if getattr(part, "function_call", None):
#                 if not part.function_call.id:
#                     part.function_call.id = f"call_{uuid.uuid4().hex}"
#                     logger.warning("[PATCHED function_call.id]")

#             if getattr(part, "function_response", None):
#                 if not part.function_response.id:
#                     part.function_response.id = f"call_{uuid.uuid4().hex}"
#                     logger.warning("[PATCHED function_response.id]")


# # =====================================================
# # ✅ AFTER MODEL: Intercept transfer
# # =====================================================
# async def hitl_after_model_callback(callback_context, llm_response):

#     ctx = callback_context
#     response = llm_response

#     transfer_call = None

#     if response.content and response.content.parts:
#         for part in response.content.parts:
#             if part.function_call and part.function_call.name == "transfer_to_agent":
#                 transfer_call = part.function_call
#                 break

#     if not transfer_call:
#         return None

#     # ✅ CRITICAL: Ensure ID exists
#     if not transfer_call.id:
#         transfer_call.id = f"call_{uuid.uuid4().hex}"
#         logger.warning("[PATCHED AFTER_MODEL function_call.id]")

#     ctx.state["pending_transfer"] = transfer_call.args

#     target_agent = transfer_call.args.get("agent_name")

#     # ✅ If already same agent → skip HITL
#     if ctx.state.get("active_agent") == target_agent:
#         return None

#     return LlmResponse(
#         content=types.Content(
#             role="model",
#             parts=[
#                 types.Part(
#                     text=f"I suggest delegating this task to {target_agent}. "
#                          f"Do you want me to proceed? (yes/no)"
#                 )
#             ]
#         )
#     )


# # =====================================================
# # ✅ BEFORE MODEL: Routing + HITL
# # =====================================================
# async def hitl_before_model_callback(callback_context, llm_request):

#     ctx = callback_context

#     # ✅ SAFETY PATCH (RUN ALWAYS)
#     ensure_tool_ids(llm_request)

#     # ✅ Extract user input
#     user_msg = ""
#     if llm_request.contents and llm_request.contents[-1].parts:
#         user_msg = llm_request.contents[-1].parts[0].text.strip().lower()

#     # =====================================================
#     # ✅ 1. HANDLE HITL APPROVAL
#     # =====================================================
#     if ctx.state.get("pending_transfer"):

#         if user_msg in ["yes", "y"]:

#             args = ctx.state["pending_transfer"]
#             target_agent = args.get("agent_name")

#             ctx.state["active_agent"] = target_agent
#             ctx.state["pending_transfer"] = None

#             return LlmResponse(
#                 content=types.Content(
#                     role="model",
#                     parts=[
#                         make_tool_call("transfer_to_agent", args)  # ✅ FIXED
#                     ]
#                 )
#             )

#         elif user_msg in ["no", "n"]:

#             ctx.state["pending_transfer"] = None

#             return LlmResponse(
#                 content=types.Content(
#                     role="model",
#                     parts=[
#                         types.Part(text="Okay, I will not proceed.")
#                     ]
#                 )
#             )

#         return LlmResponse(
#             content=types.Content(
#                 role="model",
#                 parts=[types.Part(text="Please reply with 'yes' or 'no'.")]
#             )
#         )

#     # =====================================================
#     # ✅ 2. A2A TASK ROUTING
#     # =====================================================
#     task = ctx.state.get("task")

#     if task:

#         # ✅ Agent requests input
#         if task.get("interaction") == "request_input":

#             return LlmResponse(
#                 content=types.Content(
#                     role="model",
#                     parts=[
#                         make_tool_call("transfer_to_agent", {
#                             "agent_name": task["owner"],
#                             "task_id": task["task_id"],
#                             "user_input": user_msg
#                         })  # ✅ FIXED
#                     ]
#                 )
#             )

#         # ✅ Agent still working
#         if task.get("state") == "working":

#             return LlmResponse(
#                 content=types.Content(
#                     role="model",
#                     parts=[
#                         make_tool_call("transfer_to_agent", {
#                             "agent_name": task["owner"],
#                             "task_id": task["task_id"],
#                             "continued": True
#                         })  # ✅ FIXED
#                     ]
#                 )
#             )

#     # =====================================================
#     # ✅ 3. DEFAULT → LET MODEL RUN
#     # =====================================================
#     return None


# agents/hitl_handler.py

from google.adk.models.llm_response import LlmResponse
from google.genai import types
import uuid
import logging

logger = logging.getLogger(__name__)


INPUT_REQUIRED_STATES = {
    "input-required",
    "input_required",
    "inputrequired",
}

BREAK_WORDS = {
    "thanks",
    "thank you",
    "ok",
    "okay",
    "cool",
    "great",
    "fine",
    "bye",
}


def make_tool_call(name: str, args: dict):
    """
    Always create function_call WITH ID.
    """
    part = types.Part.from_function_call(
        name=name,
        args=args,
    )

    assert part.function_call is not None
    part.function_call.id = f"call_{uuid.uuid4().hex}"

    return part


def ensure_tool_ids(llm_request):
    """
    Global safety net.
    """
    for content in llm_request.contents or []:
        for part in content.parts or []:

            if getattr(part, "function_call", None):
                if not part.function_call.id:
                    part.function_call.id = f"call_{uuid.uuid4().hex}"
                    logger.warning("[PATCHED function_call.id]")

            if getattr(part, "function_response", None):
                if not part.function_response.id:
                    part.function_response.id = f"call_{uuid.uuid4().hex}"
                    logger.warning("[PATCHED function_response.id]")


def extract_latest_user_text(llm_request) -> str:
    """
    Extract latest real user text from llm_request.
    Skips META token parts.
    """
    if not llm_request.contents:
        return ""

    latest = llm_request.contents[-1]

    if not latest.parts:
        return ""

    chunks: list[str] = []

    for part in latest.parts:
        text = getattr(part, "text", None)

        if not isinstance(text, str):
            continue

        text = text.strip()

        if not text:
            continue

        if text.startswith("[META:"):
            continue

        chunks.append(text)

    return "\n".join(chunks).strip()


def get_orchestrator_state(ctx) -> dict:
    """
    ADK session state namespace used by your StateManager.
    """
    orch = ctx.state.get("orchestrator")

    if isinstance(orch, dict):
        return orch

    return {}


def is_active_a2a_input_required_task(ctx) -> tuple[bool, dict]:
    """
    Check if orchestrator state says a remote A2A agent is waiting for user input.
    """
    orch = get_orchestrator_state(ctx)
    task = orch.get("task")

    if not isinstance(task, dict):
        return False, {}

    owner = task.get("owner")
    state = str(task.get("state") or "").lower().strip()
    interaction = str(task.get("interaction") or "").lower().strip()

    input_required = (
        interaction == "request_input"
        or state in INPUT_REQUIRED_STATES
    )

    if owner and input_required:
        return True, task

    return False, task


# =====================================================
# AFTER MODEL: Intercept transfer
# =====================================================
async def hitl_after_model_callback(callback_context, llm_response):
    """
    Cortex decided to transfer.

    We intercept and ask HITL approval.

    Critical:
    Store the original meaningful user request in pending_transfer["_remote_message"].
    """

    ctx = callback_context
    response = llm_response

    transfer_call = None

    if response.content and response.content.parts:
        for part in response.content.parts:
            if (
                getattr(part, "function_call", None)
                and part.function_call.name == "transfer_to_agent"
            ):
                transfer_call = part.function_call
                break

    if not transfer_call:
        return None

    if not transfer_call.id:
        transfer_call.id = f"call_{uuid.uuid4().hex}"
        logger.warning("[PATCHED AFTER_MODEL function_call.id]")

    target_agent = transfer_call.args.get("agent_name")

    # If already same active agent, no HITL needed.
    if ctx.state.get("active_agent") == target_agent:
        return None

    args = dict(transfer_call.args or {})

    original_user_message = ctx.state.get("_last_meaningful_user_message")

    if original_user_message:
        args["_remote_message"] = original_user_message

    ctx.state["pending_transfer"] = args

    logger.info(
        "[HITL PENDING TRANSFER] target=%s remote_message=%s",
        target_agent,
        str(args.get("_remote_message", ""))[:250],
    )

    return LlmResponse(
        content=types.Content(
            role="model",
            parts=[
                types.Part(
                    text=(
                        f"I suggest delegating this task to {target_agent}. "
                        f"Do you want me to proceed? (yes/no)"
                    )
                )
            ],
        )
    )


# =====================================================
# BEFORE MODEL: Routing + HITL
# =====================================================
async def hitl_before_model_callback(callback_context, llm_request):
    """
    Responsibilities:
    1. Patch function call IDs.
    2. Handle HITL approval.
    3. Route A2A continuation by reading ctx.state["orchestrator"]["task"].
    4. Store last meaningful user message for future HITL delegation.
    """

    ctx = callback_context

    ensure_tool_ids(llm_request)

    user_msg_raw = extract_latest_user_text(llm_request)
    user_msg = user_msg_raw.lower().strip()

    # =====================================================
    # 1. HANDLE HITL APPROVAL
    # =====================================================
    if ctx.state.get("pending_transfer"):

        if user_msg in ["yes", "y"]:

            args = dict(ctx.state["pending_transfer"] or {})
            target_agent = args.get("agent_name")

            ctx.state["active_agent"] = target_agent
            ctx.state["pending_transfer"] = None

            logger.info(
                "[HITL APPROVED] target=%s remote_message=%s",
                target_agent,
                str(args.get("_remote_message", ""))[:250],
            )

            return LlmResponse(
                content=types.Content(
                    role="model",
                    parts=[
                        make_tool_call("transfer_to_agent", args)
                    ],
                )
            )

        if user_msg in ["no", "n"]:

            ctx.state["pending_transfer"] = None

            return LlmResponse(
                content=types.Content(
                    role="model",
                    parts=[
                        types.Part(text="Okay, I will not proceed.")
                    ],
                )
            )

        return LlmResponse(
            content=types.Content(
                role="model",
                parts=[
                    types.Part(text="Please reply with 'yes' or 'no'.")
                ],
            )
        )

    # =====================================================
    # 2. HANDLE A2A CONTINUATION
    # =====================================================
    has_active_task, task = is_active_a2a_input_required_task(ctx)

    if has_active_task and user_msg not in BREAK_WORDS:
        target_agent = task.get("owner")

        args = {
            "agent_name": target_agent,
            "task_id": task.get("task_id"),
            "context_id": task.get("context_id"),
            "_remote_message": user_msg_raw,
            "_continuation": True,
        }

        logger.info(
            "[A2A CONTINUATION TRANSFER] target=%s task_id=%s context_id=%s remote_message=%s",
            target_agent,
            args.get("task_id"),
            args.get("context_id"),
            user_msg_raw[:250],
        )

        return LlmResponse(
            content=types.Content(
                role="model",
                parts=[
                    make_tool_call("transfer_to_agent", args)
                ],
            )
        )

    # =====================================================
    # 3. STORE LAST MEANINGFUL USER MESSAGE
    # =====================================================
    if user_msg_raw and not user_msg_raw.startswith("[META:"):
        ctx.state["_last_meaningful_user_message"] = user_msg_raw

    return None