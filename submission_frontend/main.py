import os
import logging
import uuid
import asyncio
from typing import Any, Optional
from fastapi import FastAPI, Request, HTTPException, BackgroundTasks
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

import vertexai
from vertexai.preview import reasoning_engines
from google.adk.sessions.vertex_ai_session_service import VertexAiSessionService
from google.cloud.aiplatform_v1beta1 import types as aip_types
from vertexai.reasoning_engines import _utils

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

# Initialize Vertex AI
if PROJECT_ID:
    vertexai.init(project=PROJECT_ID, location=LOCATION)

# Initialize Session Service
session_service = None
if PROJECT_ID and AGENT_RUNTIME_ID:
    try:
        session_service = VertexAiSessionService(
            project=PROJECT_ID,
            location=LOCATION,
            agent_engine_id=AGENT_RUNTIME_ID
        )
        logger.info(f"Initialized VertexAiSessionService for engine {AGENT_RUNTIME_ID}")
    except Exception as e:
        logger.exception("Failed to initialize VertexAiSessionService")

class ActionRequest(BaseModel):
    interrupt_id: str
    approved: Optional[bool] = None
    value: Optional[str] = None

class ScanRequest(BaseModel):
    url: str

# In-memory session state tracking
# session_id -> { "status", "output", "error", "current_node", "is_interrupted", "interrupt_id", "interrupt_message" }
active_sessions = {}

def execute_agent_query(engine, message: Any, user_id: str, session_id: str):
    """Executes a query by calling the underlying streaming API directly,
    working around the SDK's dynamic registration ValueError bug.
    """
    logger.info(f"Executing direct stream_query on {engine.resource_name} (session: {session_id})")
    response = engine.execution_api_client.stream_query_reasoning_engine(
        request=aip_types.StreamQueryReasoningEngineRequest(
            name=engine.resource_name,
            input={
                "message": message,
                "user_id": user_id,
                "session_id": session_id
            },
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
        "interrupt_message": ""
    }
    try:
        if session_service:
            try:
                await session_service.create_session(
                    app_name="app",
                    user_id="default-user",
                    session_id=session_id
                )
                logger.info(f"Pre-created session {session_id} on Vertex AI.")
            except Exception as s_err:
                logger.error(f"Failed to pre-create session {session_id}: {s_err}")

        engine = reasoning_engines.ReasoningEngine(AGENT_RUNTIME_ID)
        loop = asyncio.get_running_loop()
        events = await loop.run_in_executor(
            None,
            execute_agent_query,
            engine,
            url,
            "default-user",
            session_id
        )
        
        is_interrupted = False
        interrupt_id = ""
        interrupt_message = ""
        
        if session_service:
            try:
                session = await session_service.get_session(
                    app_name="app",
                    user_id="default-user",
                    session_id=session_id
                )
                if session and session.events:
                    calls = {}
                    responses = set()
                    for event in session.events:
                        if event.content and event.content.parts:
                            for part in event.content.parts:
                                if part.function_call and part.function_call.name == "adk_request_input":
                                    calls[part.function_call.id] = part.function_call.args
                                elif part.function_response and part.function_response.name == "adk_request_input":
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
            active_sessions[session_id].update({
                "status": "interrupted",
                "is_interrupted": True,
                "interrupt_id": interrupt_id,
                "interrupt_message": interrupt_message
            })
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
                if "output" in event and isinstance(event["output"], dict) and "recommendation" in event["output"]:
                    v = event["output"]
                    rec = v.get("recommendation", "Unknown").upper()
                    conf = v.get("confidence", "Unknown").upper()
                    concl = v.get("conclusion", "No conclusion provided.")
                    output_text = f"# YDNT Due Diligence Report\n\n### **Recommendation**: `{rec}` (Confidence: {conf})\n\n#### **Conclusion**\n{concl}"
                    break

        if not output_text:
            output_text = (
                "**已成功啟動盡職調查！**\n\n"
                "Agent 正在背景抓取銷售頁與驗證創作者。"
            )

        active_sessions[session_id].update({
            "status": "completed",
            "output": output_text
        })
    except Exception as e:
        logger.exception(f"Error in background workflow for session {session_id}")
        active_sessions[session_id].update({
            "status": "failed",
            "error": str(e)
        })

async def resume_real_agent_workflow(session_id: str, message: Any):
    active_sessions[session_id].update({
        "status": "running",
        "is_interrupted": False,
        "interrupt_id": "",
        "interrupt_message": ""
    })
    try:
        engine = reasoning_engines.ReasoningEngine(AGENT_RUNTIME_ID)
        loop = asyncio.get_running_loop()
        events = await loop.run_in_executor(
            None,
            execute_agent_query,
            engine,
            message,
            "default-user",
            session_id
        )
        
        is_interrupted = False
        interrupt_id = ""
        interrupt_message = ""
        
        if session_service:
            try:
                session = await session_service.get_session(
                    app_name="app",
                    user_id="default-user",
                    session_id=session_id
                )
                if session and session.events:
                    calls = {}
                    responses = set()
                    for event in session.events:
                        if event.content and event.content.parts:
                            for part in event.content.parts:
                                if part.function_call and part.function_call.name == "adk_request_input":
                                    calls[part.function_call.id] = part.function_call.args
                                elif part.function_response and part.function_response.name == "adk_request_input":
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
            active_sessions[session_id].update({
                "status": "interrupted",
                "is_interrupted": True,
                "interrupt_id": interrupt_id,
                "interrupt_message": interrupt_message
            })
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
                if "output" in event and isinstance(event["output"], dict) and "recommendation" in event["output"]:
                    v = event["output"]
                    rec = v.get("recommendation", "Unknown").upper()
                    conf = v.get("confidence", "Unknown").upper()
                    concl = v.get("conclusion", "No conclusion provided.")
                    output_text = f"# YDNT Due Diligence Report\n\n### **Recommendation**: `{rec}` (Confidence: {conf})\n\n#### **Conclusion**\n{concl}"
                    break

        if not output_text:
            output_text = (
                "**已成功恢復執行！**\n\n"
                "Agent 正在背景分析大綱與搜尋 YouTube 替代方案。"
            )

        active_sessions[session_id].update({
            "status": "completed",
            "output": output_text
        })
    except Exception as e:
        logger.exception(f"Error in background workflow resume for session {session_id}")
        active_sessions[session_id].update({
            "status": "failed",
            "error": str(e)
        })

# ---------------------------------------------------------------------------
# Background Agent Runners (Simulated Local Mode)
# ---------------------------------------------------------------------------
async def simulate_mock_agent_workflow(session_id: str):
    active_sessions[session_id] = {
        "status": "running",
        "output": None,
        "error": None,
        "current_node": "START",
        "is_interrupted": False,
        "interrupt_id": "",
        "interrupt_message": ""
    }
    
    # Simulate fetch_page_node
    await asyncio.sleep(2)
    active_sessions[session_id]["current_node"] = "fetch_page_node"
    
    # Simulate parse_course
    await asyncio.sleep(2)
    active_sessions[session_id]["current_node"] = "parse_course"
    
    # Simulate triage_course -> suspend on price check!
    await asyncio.sleep(2)
    active_sessions[session_id].update({
        "status": "interrupted",
        "current_node": "triage_course",
        "is_interrupted": True,
        "interrupt_id": "price_verify_input",
        "interrupt_message": "The sales page lists multiple price points. Please enter the correct price in USD for 'The Skool Games'."
    })

async def resume_mock_agent_workflow(session_id: str, value: str):
    active_sessions[session_id].update({
        "status": "running",
        "is_interrupted": False,
        "interrupt_id": "",
        "interrupt_message": ""
    })
    
    # Simulate creator_verify
    await asyncio.sleep(2)
    active_sessions[session_id]["current_node"] = "creator_verify"
    
    # Simulate free_alt_score
    await asyncio.sleep(2)
    active_sessions[session_id]["current_node"] = "free_alt_score"
    
    # Simulate verdict_agent
    await asyncio.sleep(2)
    active_sessions[session_id]["current_node"] = "verdict_agent"
    
    # Simulate completed report
    await asyncio.sleep(1)
    active_sessions[session_id].update({
        "status": "completed",
        "current_node": "finalize_verdict",
        "output": f"# YDNT Due Diligence Report\n\n### **Recommendation**: `APPROVED` (Confidence: HIGH)\n\n#### **Conclusion**\nSuccessfully resumed and verified 'The Skool Games' at ${value} USD!"
    })

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
        background_tasks.add_task(simulate_mock_agent_workflow, session_id)
    else:
        if not AGENT_RUNTIME_ID:
            raise HTTPException(status_code=500, detail="AGENT_RUNTIME_ID environment variable not set")
        background_tasks.add_task(run_real_agent_workflow, session_id, req.url)
    return {"status": "running", "session_id": session_id}

@app.get("/api/pending")
async def get_pending():
    # Return empty list in local dev to ensure TWO BLANK CARDS initially!
    if os.getenv("LOCAL_TEST") == "1":
        return []
        
    if not session_service:
        return []
    try:
        list_resp = await session_service.list_sessions(app_name="app")
        pending_approvals = []
        
        for session_info in list_resp.sessions:
            try:
                session = await session_service.get_session(
                    app_name="app",
                    user_id="default-user",
                    session_id=session_info.id
                )
                if not session or not session.events:
                    continue
                
                calls = {}
                responses = set()
                
                for event in session.events:
                    if event.content and event.content.parts:
                        for part in event.content.parts:
                            if part.function_call and part.function_call.name == "adk_request_input":
                                calls[part.function_call.id] = part.function_call.args
                            elif part.function_response and part.function_response.name == "adk_request_input":
                                responses.add(part.function_response.id)
                
                for interrupt_id, args in calls.items():
                    if interrupt_id not in responses:
                        course_profile = session.state.get("course_profile", {})
                        current_node = "START"
                        for event in session.events:
                            if event.node_name:
                                current_node = event.node_name
                                
                        pending_approvals.append({
                            "session_id": session.id,
                            "interrupt_id": interrupt_id,
                            "message": args.get("message", "Input required"),
                            "course_profile": course_profile,
                            "current_node": current_node
                        })
            except Exception as s_err:
                logger.error(f"Error checking session {session_info.id}: {s_err}")
                continue
                
        return pending_approvals
    except Exception as e:
        logger.exception("Error listing pending approvals")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/session/{session_id}/status")
async def get_session_status(session_id: str):
    state = active_sessions.get(session_id)
    if not state:
        raise HTTPException(status_code=404, detail="Session not found")
        
    current_node = state.get("current_node", "START")
    if os.getenv("LOCAL_TEST") != "1" and session_service:
        try:
            session = await session_service.get_session(
                app_name="app",
                user_id="default-user",
                session_id=session_id
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
        "error": state.get("error")
    }

@app.post("/api/action/{session_id}")
async def post_action(session_id: str, req: ActionRequest, background_tasks: BackgroundTasks):
    if os.getenv("LOCAL_TEST") == "1":
        val = req.value or str(req.approved)
        background_tasks.add_task(resume_mock_agent_workflow, session_id, val)
        return {"status": "resuming"}
        
    if not AGENT_RUNTIME_ID:
        raise HTTPException(status_code=500, detail="AGENT_RUNTIME_ID environment variable not set")
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
                        "response": res_payload
                    }
                }
            ]
        }
        background_tasks.add_task(resume_real_agent_workflow, session_id, message)
        return {"status": "resuming"}
    except Exception as e:
        logger.exception(f"Error resuming session {session_id}")
        raise HTTPException(status_code=500, detail=str(e))

