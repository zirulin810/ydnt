# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from typing import Any
import pytest
from pydantic import ValidationError

from google.adk import Context
from google.adk.workflow import node, START, Edge, Workflow
from google.adk.apps import App, ResumabilityConfig
from google.genai import types

from app.nodes import triage_course
from app.scoring import score_pricing
from app.schemas import CourseProfile


class MockContext:
    def __init__(self, state: dict[str, Any] | None = None) -> None:
        self.state = state or {}
        self.resume_inputs = {}


@pytest.mark.asyncio
async def test_triage_course_non_course() -> None:
    profile = {
        "title": "Not a Course",
        "creator": "None",
        "platform": "blog",
        "price_usd": None,
        "promised_outcome": "unknown",
        "syllabus": [],
        "scarcity_signals": [],
        "recruitment_signal": False,
        "manipulation_attempt": False,
        "is_course_page": False,
        "missing_critical_info": []
    }
    ctx = MockContext()
    events = []
    async for event in triage_course._func(ctx, profile):
        events.append(event)
    assert len(events) == 1
    event = events[0]
    assert event.actions.route == "insufficient"
    assert "course due diligence does not apply" in ctx.state.get("insufficient_reason", "")


@pytest.mark.asyncio
async def test_triage_course_is_course() -> None:
    profile = {
        "title": "A Real Course",
        "creator": "Jane Doe",
        "platform": "skool",
        "price_usd": 99.0,
        "promised_outcome": "skill",
        "syllabus": ["Intro"],
        "scarcity_signals": [],
        "recruitment_signal": False,
        "manipulation_attempt": False,
        "is_course_page": True,
        "missing_critical_info": []
    }
    ctx = MockContext()
    events = []
    async for event in triage_course._func(ctx, profile):
        events.append(event)
    assert len(events) == 1
    event = events[0]
    assert event.actions.route == "ok"
    assert event.output == profile


@pytest.mark.asyncio
async def test_triage_course_hitl_missing_price_suspend() -> None:
    profile = {
        "title": "Real Course",
        "creator": "Jane Doe",
        "platform": "skool",
        "price_usd": None,
        "promised_outcome": "skill",
        "syllabus": [],
        "scarcity_signals": [],
        "recruitment_signal": False,
        "manipulation_attempt": False,
        "is_course_page": True,
        "missing_critical_info": ["price"]
    }
    ctx = MockContext()
    events = []
    async for event in triage_course._func(ctx, profile):
        events.append(event)
    assert len(events) == 1
    req = events[0]
    assert req.interrupt_id == "price"
    assert "The course price could not be found" in req.message


@pytest.mark.asyncio
async def test_triage_course_hitl_missing_price_resume_ok() -> None:
    profile = {
        "title": "Real Course",
        "creator": "Jane Doe",
        "platform": "skool",
        "price_usd": None,
        "promised_outcome": "skill",
        "syllabus": [],
        "scarcity_signals": [],
        "recruitment_signal": False,
        "manipulation_attempt": False,
        "is_course_page": True,
        "missing_critical_info": ["price"]
    }
    ctx = MockContext(state={"course_profile": profile})
    ctx.resume_inputs = {"price": {"value": "49.99"}}
    events = []
    async for event in triage_course._func(ctx, None):
        events.append(event)
    assert len(events) == 1
    ev = events[0]
    assert ev.actions.route == "ok"
    assert ev.output["price_usd"] == 49.99
    assert "price" not in ev.output["missing_critical_info"]


@pytest.mark.asyncio
async def test_triage_course_hitl_missing_price_resume_free() -> None:
    profile = {
        "title": "Real Course",
        "creator": "Jane Doe",
        "platform": "skool",
        "price_usd": None,
        "promised_outcome": "skill",
        "syllabus": [],
        "scarcity_signals": [],
        "recruitment_signal": False,
        "manipulation_attempt": False,
        "is_course_page": True,
        "missing_critical_info": ["price"]
    }
    ctx = MockContext(state={"course_profile": profile})
    ctx.resume_inputs = {"price": {"value": "free"}}
    events = []
    async for event in triage_course._func(ctx, None):
        events.append(event)
    assert len(events) == 1
    ev = events[0]
    assert ev.actions.route == "ok"
    assert ev.output["price_usd"] == 0.0


@pytest.mark.asyncio
async def test_triage_course_hitl_missing_price_resume_unknown() -> None:
    profile = {
        "title": "Real Course",
        "creator": "Jane Doe",
        "platform": "skool",
        "price_usd": None,
        "promised_outcome": "skill",
        "syllabus": [],
        "scarcity_signals": [],
        "recruitment_signal": False,
        "manipulation_attempt": False,
        "is_course_page": True,
        "missing_critical_info": ["price"]
    }
    ctx = MockContext(state={"course_profile": profile})
    ctx.resume_inputs = {"price": {"value": "unknown"}}
    events = []
    async for event in triage_course._func(ctx, None):
        events.append(event)
    assert len(events) == 1
    ev = events[0]
    assert ev.actions.route == "insufficient"
    assert "User could not provide the price" in ctx.state.get("insufficient_reason", "")


from google.adk.runners import InMemoryRunner

def test_hitl_workflow_runner_pause_resume() -> None:
    @node
    def seed_node(ctx: Context, node_input: Any) -> Any:
        profile = {
            "title": "Runner Course",
            "creator": "John Doe",
            "platform": "skool",
            "price_usd": None,
            "promised_outcome": "skill",
            "syllabus": [],
            "scarcity_signals": [],
            "recruitment_signal": False,
            "manipulation_attempt": False,
            "is_course_page": True,
            "missing_critical_info": ["price"]
        }
        ctx.state["course_profile"] = profile
        return profile

    test_wf = Workflow(
        name="test_wf",
        edges=[
            Edge(from_node=START, to_node=seed_node),
            Edge(from_node=seed_node, to_node=triage_course),
        ]
    )

    test_app = App(
        root_agent=test_wf,
        name="test_hitl_runner_app",
        resumability_config=ResumabilityConfig(is_resumable=True)
    )

    runner = InMemoryRunner(app=test_app)
    runner.session_service.create_session_sync(
        user_id="user_test",
        app_name=runner.app_name,
        session_id="sess_test"
    )

    msg1 = types.Content(role="user", parts=[types.Part.from_text(text="start")])
    events1 = list(runner.run(user_id="user_test", session_id="sess_test", new_message=msg1))
    
    assert len(events1) == 2
    ev_pause = events1[1]
    parts = ev_pause.content.parts
    assert len(parts) == 1
    fc = parts[0].function_call
    assert fc.name == "adk_request_input"
    assert fc.id == "price"
    assert ev_pause.long_running_tool_ids == {"price"}

    resumption_message = types.Content(
        role="user",
        parts=[
            types.Part(
                function_response=types.FunctionResponse(
                    id="price",
                    name="adk_request_input",
                    response={"value": "29.99"}
                )
            )
        ]
    )
    events2 = list(runner.run(user_id="user_test", session_id="sess_test", new_message=resumption_message))
    
    assert len(events2) == 1
    ev_ok = events2[0]
    assert ev_ok.actions.route == "ok"
    assert ev_ok.output["price_usd"] == 29.99


def test_score_pricing_none() -> None:
    score, reasons = score_pricing({"price_usd": None})
    assert score == 3
    assert reasons == []


def test_course_profile_validation() -> None:
    with pytest.raises(ValidationError):
        CourseProfile(
            title="A Course",
            creator="Jane Doe",
            platform="skool",
            price_usd=10.0,
            promised_outcome="skill",
            syllabus=[],
            scarcity_signals=[],
            recruitment_signal=False,
            manipulation_attempt=False,
        )

    profile = CourseProfile(
        title="A Course",
        creator="Jane Doe",
        platform="skool",
        price_usd=None,
        promised_outcome="skill",
        syllabus=[],
        scarcity_signals=[],
        recruitment_signal=False,
        manipulation_attempt=False,
        is_course_page=True,
    )
    assert profile.missing_critical_info == []
    assert profile.price_usd is None
