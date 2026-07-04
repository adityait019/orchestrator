# agents/hitl_handler.py
from google.adk.models.llm_response import LlmResponse
from google.genai import types
import uuid
import logging

logger = logging.getLogger(__name__)


# =====================================================
# ✅ UTILITY: SIMPLE INTENT CHECK
# =====================================================
def is_followup(user_msg: str):
    short_replies = ["yes", "y", "ok", "yes please", "continue", "go ahead"]
    return user_msg.lower().strip() in short_replies


# =====================================================
# ✅ CORE FIX: SAFE TOOL CALL CREATOR
# =====================================================
def make_tool_call(name: str, args: dict):
    """Always create function_call WITH ID (CRITICAL FIX)"""
    part = types.Part.from_function_call(
        name=name,
        args=args,
    )
    assert part.function_call is not None  # ✅ tells type checker it's safe
    part.function_call.id = str(f"call_{uuid.uuid4().hex}")  # ✅ REQUIRED
    return part


# =====================================================
# ✅ SAFETY: PATCH ANY MISSING IDS
# =====================================================
def ensure_tool_ids(llm_request):
    """Global safety net (prevents Azure 400 crash)"""
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


# =====================================================
# ✅ AFTER MODEL: Intercept transfer
# =====================================================
async def hitl_after_model_callback(callback_context, llm_response):

    ctx = callback_context
    response = llm_response

    transfer_call = None

    if response.content and response.content.parts:
        for part in response.content.parts:
            if part.function_call and part.function_call.name == "transfer_to_agent":
                transfer_call = part.function_call
                break

    if not transfer_call:
        return None

    # ✅ CRITICAL: Ensure ID exists
    if not transfer_call.id:
        transfer_call.id = f"call_{uuid.uuid4().hex}"
        logger.warning("[PATCHED AFTER_MODEL function_call.id]")

    ctx.state["pending_transfer"] = transfer_call.args

    target_agent = transfer_call.args.get("agent_name")

    # ✅ If already same agent → skip HITL
    if ctx.state.get("active_agent") == target_agent:
        return None

    return LlmResponse(
        content=types.Content(
            role="model",
            parts=[
                types.Part(
                    text=f"I suggest delegating this task to {target_agent}. "
                         f"Do you want me to proceed? (yes/no)"
                )
            ]
        )
    )


# =====================================================
# ✅ BEFORE MODEL: Routing + HITL
# =====================================================
async def hitl_before_model_callback(callback_context, llm_request):

    ctx = callback_context

    # ✅ SAFETY PATCH (RUN ALWAYS)
    ensure_tool_ids(llm_request)

    # ✅ Extract user input
    user_msg = ""
    if llm_request.contents and llm_request.contents[-1].parts:
        user_msg = llm_request.contents[-1].parts[0].text.strip().lower()

    # =====================================================
    # ✅ 1. HANDLE HITL APPROVAL
    # =====================================================
    if ctx.state.get("pending_transfer"):

        if user_msg in ["yes", "y"]:

            args = ctx.state["pending_transfer"]
            target_agent = args.get("agent_name")

            ctx.state["active_agent"] = target_agent
            ctx.state["pending_transfer"] = None

            return LlmResponse(
                content=types.Content(
                    role="model",
                    parts=[
                        make_tool_call("transfer_to_agent", args)  # ✅ FIXED
                    ]
                )
            )

        elif user_msg in ["no", "n"]:

            ctx.state["pending_transfer"] = None

            return LlmResponse(
                content=types.Content(
                    role="model",
                    parts=[
                        types.Part(text="Okay, I will not proceed.")
                    ]
                )
            )

        return LlmResponse(
            content=types.Content(
                role="model",
                parts=[types.Part(text="Please reply with 'yes' or 'no'.")]
            )
        )

    # =====================================================
    # ✅ 2. A2A TASK ROUTING
    # =====================================================
    task = ctx.state.get("task")

    if task:

        # ✅ Agent requests input
        if task.get("interaction") == "request_input":

            return LlmResponse(
                content=types.Content(
                    role="model",
                    parts=[
                        make_tool_call("transfer_to_agent", {
                            "agent_name": task["owner"],
                            "task_id": task["task_id"],
                            "user_input": user_msg
                        })  # ✅ FIXED
                    ]
                )
            )

        # ✅ Agent still working
        if task.get("state") == "working":

            return LlmResponse(
                content=types.Content(
                    role="model",
                    parts=[
                        make_tool_call("transfer_to_agent", {
                            "agent_name": task["owner"],
                            "task_id": task["task_id"],
                            "continued": True
                        })  # ✅ FIXED
                    ]
                )
            )

    # =====================================================
    # ✅ 3. DEFAULT → LET MODEL RUN
    # =====================================================
    return None
