import asyncio
import logging
import os
import uuid
from typing import Any

import vertexai
from fastapi import BackgroundTasks, FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from google.adk.agents.run_config import RunConfig, StreamingMode
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.adk.sessions.vertex_ai_session_service import VertexAiSessionService
from google.cloud.aiplatform_v1beta1 import types as aip_types
from google.genai import types
from pydantic import BaseModel
from vertexai.preview import reasoning_engines
from vertexai.reasoning_engines import _utils

from app.agent import root_agent

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Agent Management Dashboard")

# Setup templates
templates = Jinja2Templates(directory="templates")

# Read environment variables
PROJECT_ID = os.getenv("GOOGLE_CLOUD_PROJECT")
LOCATION = os.getenv("GOOGLE_CLOUD_LOCATION", "us-east1")
AGENT_RUNTIME_ID = os.getenv("AGENT_RUNTIME_ID")

# Ensure clean format of IDs
engine_numeric_id = AGENT_RUNTIME_ID
engine_full_id = AGENT_RUNTIME_ID

if AGENT_RUNTIME_ID:
    if AGENT_RUNTIME_ID.startswith("projects/"):
        engine_numeric_id = AGENT_RUNTIME_ID.split("/")[-1]
    else:
        if PROJECT_ID and LOCATION:
            engine_full_id = f"projects/{PROJECT_ID}/locations/{LOCATION}/reasoningEngines/{AGENT_RUNTIME_ID}"

# Initialize Vertex AI
if PROJECT_ID:
    vertexai.init(project=PROJECT_ID, location=LOCATION)

# Initialize Session Service
session_service = None
if PROJECT_ID and engine_numeric_id:
    try:
        session_service = VertexAiSessionService(
            project=PROJECT_ID, location=LOCATION, agent_engine_id=engine_numeric_id
        )
        logger.info(
            f"Initialized VertexAiSessionService for engine {engine_numeric_id}"
        )
    except Exception:
        logger.exception("Failed to initialize VertexAiSessionService")


class ActionRequest(BaseModel):
    interrupt_id: str
    approved: bool | None = None
    value: str | None = None


class ScanRequest(BaseModel):
    url: str


# In-memory session state tracking
# session_id -> { "status", "output", "error", "current_node", "is_interrupted", "interrupt_id", "interrupt_message" }
active_sessions = {}

local_session_service = InMemorySessionService()
local_runner = Runner(
    agent=root_agent, session_service=local_session_service, app_name="app"
)


def format_verdict_to_markdown(v: dict) -> str:
    """Formats a structured Verdict dictionary into a beautiful, rich Markdown report."""
    rec_raw = v.get("recommendation", "Unknown")
    if isinstance(rec_raw, str):
        rec_raw = rec_raw.lower()
    else:
        rec_raw = "unknown"

    rec_map = {
        "should_not": "❌ SHOULD NOT BUY",
        "need_not": "⚠️ NEED NOT BUY",
        "situational": "⚖️ SITUATIONAL (Marginal Cost-Benefit)",
        "worthy": "✅ WORTHY",
        "insufficient": "❓ INSUFFICIENT INFO",
    }
    rec_display = rec_map.get(rec_raw, rec_raw.upper())

    conf_raw = v.get("confidence", "Unknown")
    if isinstance(conf_raw, str):
        conf_raw = conf_raw.lower()
    else:
        conf_raw = "unknown"

    conf_map = {
        "high": "🟢 HIGH",
        "medium": "🟡 MEDIUM",
        "low": "🔴 LOW",
    }
    conf_display = conf_map.get(conf_raw, conf_raw.upper())

    lines = []
    lines.append("# YDNT Due Diligence Report\n")
    lines.append(f"### **Recommendation**: `{rec_display}`")
    lines.append(f"### **Confidence Level**: `{conf_display}`\n")

    # Conclusion section
    concl = v.get("conclusion", "No conclusion provided.")
    lines.append("## 📝 Conclusion")
    lines.append(f"{concl}\n")

    # Rational Balance Sheet comparison (Money vs Time)
    mvt = v.get("money_vs_time")
    if mvt:
        lines.append("## ⚖️ Value Gap & Rational Balance Sheet")
        lines.append(f"{mvt}\n")

    # Green Flags & Positive Indicators
    green_flags = v.get("green_flags", [])
    if isinstance(green_flags, list) and green_flags:
        lines.append("## ✅ Green Flags & Positive Indicators")
        for flag in green_flags:
            lines.append(f"- {flag}")
        lines.append("")

    # Red Flags & Warnings
    red_flags = v.get("red_flags", [])
    if isinstance(red_flags, list) and red_flags:
        lines.append("## ⚠️ Red Flags & Risk Warnings")
        for flag in red_flags:
            lines.append(f"- {flag}")
        lines.append("")

    # Free Alternatives
    free_alts = v.get("free_alternatives", [])
    if isinstance(free_alts, list) and free_alts:
        lines.append("## 🔍 YouTube Free Alternatives")
        for idx, alt in enumerate(free_alts, 1):
            if not isinstance(alt, dict):
                continue
            title = alt.get("title", f"Alternative {idx}")
            url = alt.get("url", "#")
            coverage = alt.get("coverage_pct", 0)

            cost_raw = alt.get("extraction_cost", "unknown")
            if isinstance(cost_raw, str):
                cost_raw = cost_raw.lower()
            else:
                cost_raw = "unknown"
            cost_map = {
                "low": "🟢 Low (Easy digestion / Low time cost)",
                "medium": "🟡 Medium (Needs curation / Medium time cost)",
                "high": "🔴 High (Scattered / High time cost)",
            }
            cost = cost_map.get(cost_raw, cost_raw.upper())

            flagged = alt.get("content_farm_flag", False)
            flagged_str = (
                "⚠️ Content Farm (Low quality channel)"
                if flagged
                else "✅ Verified Channel / High Quality"
            )

            lines.append(f"### **{idx}. {title}**")
            lines.append(f"- **YouTube Link**: [{url}]({url})")
            lines.append(f"- **Knowledge Coverage**: `{coverage}%`")
            lines.append(f"- **Extraction Cost**: `{cost}`")
            lines.append(f"- **Content Farm Check**: `{flagged_str}`\n")

    return "\n".join(lines)


def execute_agent_query(engine, message: Any, user_id: str, session_id: str):
    """Executes a query by calling the underlying streaming API directly,
    working around the SDK's dynamic registration ValueError bug.
    """
    logger.info(
        f"Executing direct stream_query on {engine.resource_name} (session: {session_id})"
    )
    response = engine.execution_api_client.stream_query_reasoning_engine(
        request=aip_types.StreamQueryReasoningEngineRequest(
            name=engine.resource_name,
            input={"message": message, "user_id": user_id, "session_id": session_id},
            class_method="stream_query",
        ),
    )
    events = []
    for chunk in response:
        for parsed in _utils.yield_parsed_json(chunk):
            if parsed is not None:
                events.append(parsed)
    return events


# ---------------------------------------------------------------------------
# Background Agent Runners (Real Vertex AI)
# ---------------------------------------------------------------------------
async def run_real_agent_workflow(session_id: str, url: str):
    active_sessions[session_id] = {
        "status": "running",
        "output": None,
        "error": None,
        "current_node": "START",
        "is_interrupted": False,
        "interrupt_id": "",
        "interrupt_message": "",
    }
    try:
        if session_service:
            try:
                await session_service.create_session(
                    app_name="app", user_id="default-user", session_id=session_id
                )
                logger.info(f"Pre-created session {session_id} on Vertex AI.")
            except Exception as s_err:
                logger.error(f"Failed to pre-create session {session_id}: {s_err}")

        engine = reasoning_engines.ReasoningEngine(engine_full_id)
        loop = asyncio.get_running_loop()
        events = await loop.run_in_executor(
            None, execute_agent_query, engine, url, "default-user", session_id
        )

        is_interrupted = False
        interrupt_id = ""
        interrupt_message = ""

        if session_service:
            try:
                session = await session_service.get_session(
                    app_name="app", user_id="default-user", session_id=session_id
                )
                if session and session.events:
                    calls = {}
                    responses = set()
                    for event in session.events:
                        if event.content and event.content.parts:
                            for part in event.content.parts:
                                if (
                                    part.function_call
                                    and part.function_call.name == "adk_request_input"
                                ):
                                    calls[part.function_call.id] = (
                                        part.function_call.args
                                    )
                                elif (
                                    part.function_response
                                    and part.function_response.name
                                    == "adk_request_input"
                                ):
                                    responses.add(part.function_response.id)
                    for i_id, args in calls.items():
                        if i_id not in responses:
                            is_interrupted = True
                            interrupt_id = i_id
                            interrupt_message = args.get("message", "Input required")
                            break
            except Exception as s_err:
                logger.error(f"Error checking session status: {s_err}")

        if is_interrupted:
            active_sessions[session_id].update(
                {
                    "status": "interrupted",
                    "is_interrupted": True,
                    "interrupt_id": interrupt_id,
                    "interrupt_message": interrupt_message,
                }
            )
            return

        output_text = None
        for event in reversed(events):
            if "content" in event and event["content"] and "parts" in event["content"]:
                parts = event["content"]["parts"]
                if parts and isinstance(parts, list) and "text" in parts[0]:
                    text = parts[0]["text"]
                    if "# YDNT Due Diligence Report" in text:
                        output_text = text
                        break

        if not output_text:
            for event in reversed(events):
                if (
                    "output" in event
                    and isinstance(event["output"], dict)
                    and "recommendation" in event["output"]
                ):
                    output_text = format_verdict_to_markdown(event["output"])
                    break

        if not output_text:
            output_text = (
                "**Due Diligence has started successfully!**\n\n"
                "Agent is crawling the sales page and verifying the creator in the background."
            )

        active_sessions[session_id].update(
            {"status": "completed", "output": output_text}
        )
    except Exception as e:
        logger.exception(f"Error in background workflow for session {session_id}")
        active_sessions[session_id].update({"status": "failed", "error": str(e)})


async def resume_real_agent_workflow(session_id: str, message: Any):
    active_sessions[session_id].update(
        {
            "status": "running",
            "is_interrupted": False,
            "interrupt_id": "",
            "interrupt_message": "",
        }
    )
    try:
        engine = reasoning_engines.ReasoningEngine(engine_full_id)
        loop = asyncio.get_running_loop()
        events = await loop.run_in_executor(
            None, execute_agent_query, engine, message, "default-user", session_id
        )

        is_interrupted = False
        interrupt_id = ""
        interrupt_message = ""

        if session_service:
            try:
                session = await session_service.get_session(
                    app_name="app", user_id="default-user", session_id=session_id
                )
                if session and session.events:
                    calls = {}
                    responses = set()
                    for event in session.events:
                        if event.content and event.content.parts:
                            for part in event.content.parts:
                                if (
                                    part.function_call
                                    and part.function_call.name == "adk_request_input"
                                ):
                                    calls[part.function_call.id] = (
                                        part.function_call.args
                                    )
                                elif (
                                    part.function_response
                                    and part.function_response.name
                                    == "adk_request_input"
                                ):
                                    responses.add(part.function_response.id)
                    for i_id, args in calls.items():
                        if i_id not in responses:
                            is_interrupted = True
                            interrupt_id = i_id
                            interrupt_message = args.get("message", "Input required")
                            break
            except Exception as s_err:
                logger.error(f"Error checking session status: {s_err}")

        if is_interrupted:
            active_sessions[session_id].update(
                {
                    "status": "interrupted",
                    "is_interrupted": True,
                    "interrupt_id": interrupt_id,
                    "interrupt_message": interrupt_message,
                }
            )
            return

        output_text = None
        for event in reversed(events):
            if "content" in event and event["content"] and "parts" in event["content"]:
                parts = event["content"]["parts"]
                if parts and isinstance(parts, list) and "text" in parts[0]:
                    text = parts[0]["text"]
                    if "# YDNT Due Diligence Report" in text:
                        output_text = text
                        break

        if not output_text:
            for event in reversed(events):
                if (
                    "output" in event
                    and isinstance(event["output"], dict)
                    and "recommendation" in event["output"]
                ):
                    output_text = format_verdict_to_markdown(event["output"])
                    break

        if not output_text:
            output_text = (
                "**Execution resumed successfully!**\n\n"
                "Agent is analyzing the syllabus and searching for YouTube alternatives in the background."
            )

        active_sessions[session_id].update(
            {"status": "completed", "output": output_text}
        )
    except Exception as e:
        logger.exception(
            f"Error in background workflow resume for session {session_id}"
        )
        active_sessions[session_id].update({"status": "failed", "error": str(e)})


# ---------------------------------------------------------------------------
# Background Agent Runners (Simulated Local Mode)
# ---------------------------------------------------------------------------
async def simulate_mock_agent_workflow(session_id: str, url: str):
    active_sessions[session_id] = {
        "status": "running",
        "output": None,
        "error": None,
        "current_node": "START",
        "is_interrupted": False,
        "interrupt_id": "",
        "interrupt_message": "",
    }
    try:
        # Create session in local InMemorySessionService
        local_session_service.create_session_sync(
            user_id="default-user", app_name="app", session_id=session_id
        )

        # Build the initial message with the user's input URL
        message = types.Content(role="user", parts=[types.Part.from_text(text=url)])

        loop = asyncio.get_running_loop()

        def execute_run():
            return list(
                local_runner.run(
                    new_message=message,
                    user_id="default-user",
                    session_id=session_id,
                    run_config=RunConfig(streaming_mode=StreamingMode.SSE),
                )
            )

        events = await loop.run_in_executor(None, execute_run)

        # Check if paused on interrupt
        is_interrupted = False
        interrupt_id = ""
        interrupt_message = ""

        session_data = local_session_service.get_session_sync(
            user_id="default-user", app_name="app", session_id=session_id
        )

        if session_data and session_data.events:
            calls = {}
            responses = set()
            for event in session_data.events:
                if event.content and event.content.parts:
                    for part in event.content.parts:
                        if (
                            part.function_call
                            and part.function_call.name == "adk_request_input"
                        ):
                            calls[part.function_call.id] = part.function_call.args
                        elif (
                            part.function_response
                            and part.function_response.name == "adk_request_input"
                        ):
                            responses.add(part.function_response.id)
            for i_id, args in calls.items():
                if i_id not in responses:
                    is_interrupted = True
                    interrupt_id = i_id
                    interrupt_message = args.get("message", "Input required")
                    break

        if is_interrupted:
            active_sessions[session_id].update(
                {
                    "status": "interrupted",
                    "is_interrupted": True,
                    "interrupt_id": interrupt_id,
                    "interrupt_message": interrupt_message,
                }
            )
            return

        output_text = None
        for event in reversed(events):
            if event.content and event.content.parts:
                text = event.content.parts[0].text
                if text and "# YDNT Due Diligence Report" in text:
                    output_text = text
                    break

        if not output_text:
            verdict = session_data.state.get("final_verdict", {})
            if not verdict:
                verdict = session_data.state.get("verdict", {})
            if verdict:
                output_text = format_verdict_to_markdown(verdict)

        if not output_text:
            output_text = "Analysis completed, but no report was produced."

        active_sessions[session_id].update(
            {"status": "completed", "output": output_text}
        )
    except Exception as e:
        logger.exception(f"Error in local background workflow for session {session_id}")
        active_sessions[session_id].update({"status": "failed", "error": str(e)})


async def resume_mock_agent_workflow(
    session_id: str, value: str, interrupt_id: str | None = None
):
    active_sessions[session_id].update(
        {
            "status": "running",
            "is_interrupted": False,
            "interrupt_id": "",
            "interrupt_message": "",
        }
    )
    try:
        # Get the interrupt_id from active_sessions if not provided
        if not interrupt_id:
            session_data = local_session_service.get_session_sync(
                user_id="default-user", app_name="app", session_id=session_id
            )
            if session_data and session_data.events:
                calls = {}
                responses = set()
                for event in session_data.events:
                    if event.content and event.content.parts:
                        for part in event.content.parts:
                            if (
                                part.function_call
                                and part.function_call.name == "adk_request_input"
                            ):
                                calls[part.function_call.id] = part.function_call.args
                            elif (
                                part.function_response
                                and part.function_response.name == "adk_request_input"
                            ):
                                responses.add(part.function_response.id)
                for i_id, _args in calls.items():
                    if i_id not in responses:
                        interrupt_id = i_id
                        break

        # Build the function response message
        res_payload = {}
        if value.lower() in ("true", "false"):
            res_payload = {"approved": value.lower() == "true"}
        else:
            res_payload = {"value": value, "result": value}

        message = types.Content(
            role="user",
            parts=[
                types.Part(
                    function_response=types.FunctionResponse(
                        id=interrupt_id, name="adk_request_input", response=res_payload
                    )
                )
            ],
        )

        loop = asyncio.get_running_loop()

        def execute_run():
            return list(
                local_runner.run(
                    new_message=message,
                    user_id="default-user",
                    session_id=session_id,
                    run_config=RunConfig(streaming_mode=StreamingMode.SSE),
                )
            )

        events = await loop.run_in_executor(None, execute_run)

        is_interrupted = False
        interrupt_id = ""
        interrupt_message = ""

        session_data = local_session_service.get_session_sync(
            user_id="default-user", app_name="app", session_id=session_id
        )

        if session_data and session_data.events:
            calls = {}
            responses = set()
            for event in session_data.events:
                if event.content and event.content.parts:
                    for part in event.content.parts:
                        if (
                            part.function_call
                            and part.function_call.name == "adk_request_input"
                        ):
                            calls[part.function_call.id] = part.function_call.args
                        elif (
                            part.function_response
                            and part.function_response.name == "adk_request_input"
                        ):
                            responses.add(part.function_response.id)
            for i_id, args in calls.items():
                if i_id not in responses:
                    is_interrupted = True
                    interrupt_id = i_id
                    interrupt_message = args.get("message", "Input required")
                    break

        if is_interrupted:
            active_sessions[session_id].update(
                {
                    "status": "interrupted",
                    "is_interrupted": True,
                    "interrupt_id": interrupt_id,
                    "interrupt_message": interrupt_message,
                }
            )
            return

        output_text = None
        for event in reversed(events):
            if event.content and event.content.parts:
                text = event.content.parts[0].text
                if text and "# YDNT Due Diligence Report" in text:
                    output_text = text
                    break

        if not output_text:
            verdict = session_data.state.get("final_verdict", {})
            if not verdict:
                verdict = session_data.state.get("verdict", {})
            if verdict:
                output_text = format_verdict_to_markdown(verdict)

        if not output_text:
            output_text = "Analysis completed, but no report was produced."

        active_sessions[session_id].update(
            {"status": "completed", "output": output_text}
        )
    except Exception as e:
        logger.exception(
            f"Error in local background workflow resume for session {session_id}"
        )
        active_sessions[session_id].update({"status": "failed", "error": str(e)})


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
@app.get("/", response_class=HTMLResponse)
async def get_index(request: Request):
    return templates.TemplateResponse(request=request, name="index.html", context={})


@app.post("/api/scan")
async def post_scan(req: ScanRequest, background_tasks: BackgroundTasks):
    session_id = f"session-{uuid.uuid4().hex[:8]}"
    if os.getenv("LOCAL_TEST") == "1":
        background_tasks.add_task(simulate_mock_agent_workflow, session_id, req.url)
    else:
        if not AGENT_RUNTIME_ID:
            raise HTTPException(
                status_code=500, detail="AGENT_RUNTIME_ID environment variable not set"
            )
        background_tasks.add_task(run_real_agent_workflow, session_id, req.url)
    return {"status": "running", "session_id": session_id}


@app.get("/api/pending")
async def get_pending():
    if os.getenv("LOCAL_TEST") == "1":
        pending_approvals = []
        try:
            for s_id, state in active_sessions.items():
                if state.get("status") == "interrupted":
                    try:
                        session = local_session_service.get_session_sync(
                            user_id="default-user", app_name="app", session_id=s_id
                        )
                        if not session or not session.events:
                            continue

                        calls = {}
                        responses = set()

                        for event in session.events:
                            if event.content and event.content.parts:
                                for part in event.content.parts:
                                    if (
                                        part.function_call
                                        and part.function_call.name
                                        == "adk_request_input"
                                    ):
                                        calls[part.function_call.id] = (
                                            part.function_call.args
                                        )
                                    elif (
                                        part.function_response
                                        and part.function_response.name
                                        == "adk_request_input"
                                    ):
                                        responses.add(part.function_response.id)

                        for interrupt_id, args in calls.items():
                            if interrupt_id not in responses:
                                course_profile = session.state.get("course_profile", {})
                                current_node = "START"
                                for event in session.events:
                                    if event.node_name:
                                        current_node = event.node_name

                                pending_approvals.append(
                                    {
                                        "session_id": session.id,
                                        "interrupt_id": interrupt_id,
                                        "message": args.get(
                                            "message", "Input required"
                                        ),
                                        "course_profile": course_profile,
                                        "current_node": current_node,
                                    }
                                )
                    except Exception as s_err:
                        logger.error(f"Error checking local session {s_id}: {s_err}")
            return pending_approvals
        except Exception:
            logger.exception("Error listing local pending approvals")
            return []

    if not session_service:
        return []
    try:
        list_resp = await session_service.list_sessions(app_name="app")
        pending_approvals = []

        for session_info in list_resp.sessions:
            try:
                session = await session_service.get_session(
                    app_name="app", user_id="default-user", session_id=session_info.id
                )
                if not session or not session.events:
                    continue

                calls = {}
                responses = set()

                for event in session.events:
                    if event.content and event.content.parts:
                        for part in event.content.parts:
                            if (
                                part.function_call
                                and part.function_call.name == "adk_request_input"
                            ):
                                calls[part.function_call.id] = part.function_call.args
                            elif (
                                part.function_response
                                and part.function_response.name == "adk_request_input"
                            ):
                                responses.add(part.function_response.id)

                for interrupt_id, args in calls.items():
                    if interrupt_id not in responses:
                        course_profile = session.state.get("course_profile", {})
                        current_node = "START"
                        for event in session.events:
                            if event.node_name:
                                current_node = event.node_name

                        pending_approvals.append(
                            {
                                "session_id": session.id,
                                "interrupt_id": interrupt_id,
                                "message": args.get("message", "Input required"),
                                "course_profile": course_profile,
                                "current_node": current_node,
                            }
                        )
            except Exception as s_err:
                logger.error(f"Error checking session {session_info.id}: {s_err}")
                continue

        return pending_approvals
    except Exception as e:
        logger.exception("Error listing pending approvals")
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.get("/api/session/{session_id}/status")
async def get_session_status(session_id: str):
    state = active_sessions.get(session_id)
    if not state:
        raise HTTPException(status_code=404, detail="Session not found")

    current_node = state.get("current_node", "START")
    if os.getenv("LOCAL_TEST") == "1":
        try:
            session = local_session_service.get_session_sync(
                user_id="default-user", app_name="app", session_id=session_id
            )
            if session and session.events:
                for event in session.events:
                    if event.node_name:
                        current_node = event.node_name
                state["current_node"] = current_node
        except Exception as e:
            logger.error(f"Error checking local session progress: {e}")
    elif session_service:
        try:
            session = await session_service.get_session(
                app_name="app", user_id="default-user", session_id=session_id
            )
            if session and session.events:
                for event in session.events:
                    if event.node_name:
                        current_node = event.node_name
                state["current_node"] = current_node
        except Exception as e:
            logger.error(f"Error checking real-time session progress: {e}")

    return {
        "status": state["status"],
        "current_node": current_node,
        "is_interrupted": state.get("is_interrupted", False),
        "interrupt_id": state.get("interrupt_id", ""),
        "message": state.get("interrupt_message", ""),
        "output": state.get("output"),
        "error": state.get("error"),
    }


@app.post("/api/action/{session_id}")
async def post_action(
    session_id: str, req: ActionRequest, background_tasks: BackgroundTasks
):
    if os.getenv("LOCAL_TEST") == "1":
        val = req.value or str(req.approved)
        background_tasks.add_task(
            resume_mock_agent_workflow, session_id, val, req.interrupt_id
        )
        return {"status": "resuming"}

    if not AGENT_RUNTIME_ID:
        raise HTTPException(
            status_code=500, detail="AGENT_RUNTIME_ID environment variable not set"
        )
    try:
        res_payload = {}
        if req.value is not None:
            res_payload = {"value": req.value, "result": req.value}
        else:
            res_payload = {"approved": req.approved}

        message = {
            "role": "user",
            "parts": [
                {
                    "function_response": {
                        "id": req.interrupt_id,
                        "name": "adk_request_input",
                        "response": res_payload,
                    }
                }
            ],
        }
        background_tasks.add_task(resume_real_agent_workflow, session_id, message)
        return {"status": "resuming"}
    except Exception as e:
        logger.exception(f"Error resuming session {session_id}")
        raise HTTPException(status_code=500, detail=str(e)) from e
