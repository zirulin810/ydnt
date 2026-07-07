import os
import logging
import uuid
from typing import Any, Optional
from fastapi import FastAPI, Request, HTTPException
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

@app.get("/", response_class=HTMLResponse)
async def get_index(request: Request):
    return templates.TemplateResponse(request=request, name="index.html", context={})

@app.post("/api/scan")
async def post_scan(req: ScanRequest):
    if not AGENT_RUNTIME_ID:
        raise HTTPException(status_code=500, detail="AGENT_RUNTIME_ID environment variable not set")
    try:
        session_id = f"session-{uuid.uuid4().hex[:8]}"
        engine = reasoning_engines.ReasoningEngine(AGENT_RUNTIME_ID)
        
        logger.info(f"Starting scan for URL: {req.url} in session {session_id}")
        
        # Pre-create the session on Google Cloud to prevent SessionNotFoundError on custom workflow runners
        if session_service:
            try:
                await session_service.create_session(
                    app_name="app",
                    user_id="default-user",
                    session_id=session_id
                )
                logger.info(f"Pre-created session {session_id} on Vertex AI successfully.")
            except Exception as s_err:
                logger.error(f"Failed to pre-create session {session_id}: {s_err}")

        # Trigger query using our custom helper
        events = execute_agent_query(
            engine=engine,
            message=req.url,
            user_id="default-user",
            session_id=session_id
        )
        
        logger.info(f"Completed execute_agent_query with {len(events)} events.")
        
        # Check if the session is currently suspended / interrupted
        is_interrupted = False
        interrupt_message = ""
        interrupt_id = ""

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
            return {
                "status": "interrupted",
                "session_id": session_id,
                "interrupt_id": interrupt_id,
                "message": interrupt_message
            }
            
        # Type-safe Event Filtering (Option C) - Extract final YDNT Report
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
                "**已成功啟動盡職調查！**\n\n"  # noqa: RUF001
                "Agent 正在背景抓取銷售頁與驗證創作者。若需要您手動確認價格或創作者資訊，系統會自動列在「待處理事項」中。"  # noqa: RUF001
            )

        return {"status": "completed", "session_id": session_id, "output": output_text}
    except Exception as e:
        logger.exception("Error during scan execution")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/pending")
async def get_pending():
    if os.getenv("LOCAL_TEST") == "1":
        return [
            {
                "session_id": "session-skool-games-01",
                "interrupt_id": "creator_verify_approve",
                "message": "Please confirm if 'Sam Ovens' is the authentic creator of 'The Skool Games' course.",
                "course_profile": {
                    "title": "The Skool Games",
                    "course_title": "The Skool Games",
                    "creator": "Sam Ovens",
                    "price_usd": 99.0,
                    "sales_page_url": "https://www.skool.com/games"
                },
                "current_node": "creator_verify"
            },
            {
                "session_id": "session-ai-agency-02",
                "interrupt_id": "price_verify_input",
                "message": "The sales page lists multiple price points. Please enter the correct price in USD for 'AI Automation Agency'.",
                "course_profile": {
                    "title": "AI Automation Agency",
                    "course_title": "AI Automation Agency",
                    "creator": "Iman Gadzhi",
                    "price_usd": 5000.0,
                    "sales_page_url": "https://www.educate.io/aaa"
                },
                "current_node": "triage_course"
            }
        ]
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
                
                # Scan history for unresolved adk_request_input calls
                calls = {}
                responses = set()
                
                for event in session.events:
                    if event.content and event.content.parts:
                        for part in event.content.parts:
                            if part.function_call and part.function_call.name == "adk_request_input":
                                calls[part.function_call.id] = part.function_call.args
                            elif part.function_response and part.function_response.name == "adk_request_input":
                                responses.add(part.function_response.id)
                
                # Check for unresolved interrupts
                for interrupt_id, args in calls.items():
                    if interrupt_id not in responses:
                        course_profile = session.state.get("course_profile", {})
                        
                        # Get the last non-empty node_name
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

@app.post("/api/action/{session_id}")
async def post_action(session_id: str, req: ActionRequest):
    if os.getenv("LOCAL_TEST") == "1":
        return {"status": "success", "output": "# YDNT Due Diligence Report\n\n### **Recommendation**: `APPROVED` (Confidence: HIGH)\n\n#### **Conclusion**\nSuccessfully resumed and verified mock session!"}
    if not AGENT_RUNTIME_ID:
        raise HTTPException(status_code=500, detail="AGENT_RUNTIME_ID environment variable not set")
    try:
        engine = reasoning_engines.ReasoningEngine(AGENT_RUNTIME_ID)
        
        # Build the response payload
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
        
        logger.info(f"Resuming session {session_id} with payload: {message}")
        
        # Trigger query using our custom helper
        events = execute_agent_query(
            engine=engine,
            message=message,
            user_id="default-user",
            session_id=session_id
        )
        
        logger.info(f"Resume execute_agent_query finished with {len(events)} events.")
        
        # Type-safe Event Filtering (Option C) - Extract final YDNT Report
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
                "**已成功恢復執行！**\n\n"  # noqa: RUF001
                "Agent 正在背景分析大綱與搜尋 YouTube 替代方案，約需 30 到 60 秒。分析完成後，您重新整理首頁即可點擊卡片查看完整報告。"  # noqa: RUF001
            )

        return {"status": "success", "output": output_text}
    except Exception as e:
        logger.exception(f"Error resuming session {session_id}")
        raise HTTPException(status_code=500, detail=str(e))
