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

from app.nodes import triage_course
from app.scoring import score_pricing
from app.schemas import CourseProfile


class MockContext:
    def __init__(self, state: dict[str, Any] | None = None) -> None:
        self.state = state or {}


def test_triage_course_non_course() -> None:
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
    event = triage_course._func(ctx, profile)
    assert event.actions.route == "insufficient"
    assert "course due diligence does not apply" in ctx.state.get("insufficient_reason", "")


def test_triage_course_is_course() -> None:
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
    event = triage_course._func(ctx, profile)
    assert event.actions.route == "ok"
    assert event.output == profile


def test_score_pricing_none() -> None:
    score, reasons = score_pricing({"price_usd": None})
    assert score == 3
    assert reasons == []


def test_course_profile_validation() -> None:
    # 1. is_course_page is required
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
            # missing is_course_page
        )

    # 2. missing_critical_info defaults to [] and price_usd can be None
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
