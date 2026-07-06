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

"""Ground-truth unit tests for rubric_scoring_node.

Design:
This test suite verifies that the rubric scoring node makes the correct/expected
decisions based on ground-truth rules across 8 distinct scenarios. The assertions
focus on behavior (final mode, critical red/green flags) rather than internal scores.
If the current code behaves incorrectly, these tests are designed to fail to reveal bugs.
"""

from __future__ import annotations

from typing import Any

from app.nodes import rubric_scoring_node
from app.schemas import (
    CourseProfile,
    CreatorEvidence,
    FreeAlternative,
    FreeAlternatives,
)


class MockContext:
    """Mock context object to simulate workflow execution environment."""

    def __init__(self, state: dict[str, Any] | None = None) -> None:
        self.state = state or {}


def run_node(
    profile: CourseProfile,
    creator: CreatorEvidence,
    free_alt: FreeAlternatives,
) -> dict[str, Any]:
    """Helper function to execute rubric_scoring_node with given state components."""
    ctx = MockContext(
        state={
            "course_profile": profile,
            "creator_evidence": creator,
            "free_alternatives": free_alt,
        }
    )
    event = rubric_scoring_node._func(ctx, None)
    return event.output


# ===========================================================================
# Helper Defaults
# ===========================================================================
def default_course_profile(**kwargs) -> CourseProfile:
    """Creates a CourseProfile with standard defaults."""
    defaults = {
        "title": "Default Course",
        "creator": "Jane Doe",
        "platform": "skool",
        "price_usd": 100.0,
        "promised_outcome": "skill",
        "syllabus": [],
        "scarcity_signals": [],
        "is_pyramid_scheme": False,
        "is_course_page": True,
    }
    defaults.update(kwargs)
    return CourseProfile(**defaults)


def default_creator_evidence(**kwargs) -> CreatorEvidence:
    """Creates a CreatorEvidence with standard defaults."""
    defaults = {
        "footprint": "weak",
        "verifiable_track_record": False,
        "only_sells_courses": False,
        "evidence_links": [],
    }
    defaults.update(kwargs)
    return CreatorEvidence(**defaults)


def default_free_alternatives(**kwargs) -> FreeAlternatives:
    """Creates a FreeAlternatives with standard defaults."""
    defaults = {
        "items": [],
        "best_coverage_pct": 0,
    }
    defaults.update(kwargs)
    return FreeAlternatives(**defaults)


# ===========================================================================
# Ground-Truth Test Cases
# ===========================================================================
def test_scenario_1_pyramid_scheme() -> None:
    """Scenario 1: Pyramid Scheme.

    A course classified as a pyramid scheme must lead to 'should_not' mode
    and have the pyramid scheme red flag.
    """
    profile = default_course_profile(is_pyramid_scheme=True)
    creator = default_creator_evidence()
    free_alt = default_free_alternatives()

    result = run_node(profile, creator, free_alt)

    assert result["mode"] == "should_not"
    assert any("Pyramid" in flag for flag in result["red_flags"])


def test_scenario_2_recursive_monetization_no_veto() -> None:
    """Scenario 2: Recursive Monetization (No Veto).

    An income course with monetization syllabus terms is NOT a veto
    if is_pyramid_scheme is False. It leads to 'need_not' mode.
    """
    profile = default_course_profile(
        promised_outcome="income",
        syllabus=["Audience growth", "How to sell your course", "Monetize"],
        is_pyramid_scheme=False,
    )
    creator = default_creator_evidence()
    free_alt = default_free_alternatives()

    result = run_node(profile, creator, free_alt)

    assert result["mode"] == "need_not"


def test_scenario_3_income_promise_with_scarcity_no_veto() -> None:
    """Scenario 3: Income Promise + Scarcity (No Veto).

    A course promising income combined with scarcity marketing signals
    does NOT trigger should_not anymore; it leads to 'need_not' mode.
    """
    profile = default_course_profile(
        promised_outcome="income",
        scarcity_signals=["only 2 spots left", "countdown timer"],
    )
    creator = default_creator_evidence()
    free_alt = default_free_alternatives()

    result = run_node(profile, creator, free_alt)

    assert result["mode"] == "need_not"
    assert any("Scarcity" in flag for flag in result["red_flags"])
    assert any("Income" in flag for flag in result["red_flags"])


def test_scenario_4_high_free_coverage() -> None:
    """Scenario 4: High Free Coverage.

    A skill course where high-quality (non content farm) free alternatives cover
    70%+ of the syllabus with low extraction cost must lead to 'need_not' mode.
    """
    profile = default_course_profile(promised_outcome="skill")
    creator = default_creator_evidence(footprint="medium")
    free_alt = default_free_alternatives(
        items=[
            FreeAlternative(
                title="Awesome YouTube Playlist",
                url="https://youtube.com/playlist",
                coverage_pct=75,
                extraction_cost="low",
                content_farm_flag=False,
            )
        ],
        best_coverage_pct=75,
    )

    result = run_node(profile, creator, free_alt)

    assert result["mode"] == "need_not"


def test_scenario_5_strong_footprint_low_coverage_high_extraction() -> None:
    """Scenario 5: Strong/Medium Footprint + Coverage < 80% + High Extraction Cost.

    A course taught by an creator with a strong footprint, where free alternatives
    cover less than 80% and have high extraction cost, must lead to 'worthy' mode.
    """
    profile = default_course_profile(promised_outcome="skill")
    creator = default_creator_evidence(
        footprint="strong",
        verifiable_track_record=True,
    )
    free_alt = default_free_alternatives(
        items=[
            FreeAlternative(
                title="Messy Code Base",
                url="https://github.com/messy",
                coverage_pct=70,
                extraction_cost="high",
                content_farm_flag=False,
            )
        ],
        best_coverage_pct=70,
    )

    result = run_node(profile, creator, free_alt)

    assert result["mode"] == "worthy"


def test_scenario_6_skill_course_credible_creator_no_good_alternative() -> None:
    """Scenario 6: Skill course + Credible Creator + No Good Free Alternatives.

    A skill course where the creator has verifiable professional work / GitHub contributions,
    and there are no good free alternatives (very low coverage or extremely high cost),
    must lead to 'worthy' mode.
    """
    profile = default_course_profile(promised_outcome="skill")
    creator = default_creator_evidence(
        footprint="weak",  # Even with weak public footprint, the creator has real work
        verifiable_track_record=True,
    )
    # The only alternative has extremely low coverage (20%)
    free_alt = default_free_alternatives(
        items=[
            FreeAlternative(
                title="Sparse Post",
                url="https://blog.com/post",
                coverage_pct=20,
                extraction_cost="low",
                content_farm_flag=False,
            )
        ],
        best_coverage_pct=20,
    )

    result = run_node(profile, creator, free_alt)

    assert result["mode"] == "worthy"


def test_scenario_7_weak_footprint_only_sells_courses() -> None:
    """Scenario 7: Weak Footprint + Only Sells Courses.

    An creator with a weak footprint whose only verifiable activity is selling
    courses must trigger a weak footprint red flag.
    """
    profile = default_course_profile(promised_outcome="skill")
    creator = default_creator_evidence(
        footprint="weak",
        only_sells_courses=True,
    )
    free_alt = default_free_alternatives()

    result = run_node(profile, creator, free_alt)

    assert any("Weak Footprint" in flag for flag in result["red_flags"])


def test_scenario_8_boundary_empty_evidences() -> None:
    """Scenario 8: Boundary: All Three Evidences Empty.

    When all input evidences are empty or default, it should evaluate to the
    existing default mode.
    """
    profile = default_course_profile(promised_outcome="unknown")
    creator = default_creator_evidence()
    free_alt = default_free_alternatives()

    result = run_node(profile, creator, free_alt)

    assert result["mode"] == "need_not"
