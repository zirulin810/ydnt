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
    FreeAlternative,
    FreeAlternatives,
    InstructorEvidence,
)


class MockContext:
    """Mock context object to simulate workflow execution environment."""

    def __init__(self, state: dict[str, Any] | None = None) -> None:
        self.state = state or {}


def run_node(
    profile: CourseProfile,
    instructor: InstructorEvidence,
    free_alt: FreeAlternatives,
) -> dict[str, Any]:
    """Helper function to execute rubric_scoring_node with given state components."""
    ctx = MockContext(
        state={
            "course_profile": profile,
            "instructor_evidence": instructor,
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
        "instructor": "Jane Doe",
        "platform": "skool",
        "price_usd": 100.0,
        "promised_outcome": "skill",
        "syllabus": [],
        "scarcity_signals": [],
        "recruitment_signal": False,
    }
    defaults.update(kwargs)
    return CourseProfile(**defaults)


def default_instructor_evidence(**kwargs) -> InstructorEvidence:
    """Creates an InstructorEvidence with standard defaults."""
    defaults = {
        "footprint": "weak",
        "github_real_work": False,
        "verifiable_employment": False,
        "only_sells_courses": False,
        "evidence_links": [],
    }
    defaults.update(kwargs)
    return InstructorEvidence(**defaults)


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
def test_scenario_1_mlm_recruitment() -> None:
    """Scenario 1: MLM Recruitment.

    A course with recruitment signals (recruiting students as resellers/coaches)
    must lead to 'A_should_not' mode and have the MLM recruitment red flag.
    """
    profile = default_course_profile(recruitment_signal=True)
    instructor = default_instructor_evidence()
    free_alt = default_free_alternatives()

    result = run_node(profile, instructor, free_alt)

    assert result["mode"] == "A_should_not"
    assert any("MLM" in flag for flag in result["red_flags"])


def test_scenario_2_recursive_monetization() -> None:
    """Scenario 2: Recursive Monetization.

    A course promising income whose syllabus focuses on audience monetization,
    selling courses, or building followers must lead to 'A_should_not' mode.
    """
    profile = default_course_profile(
        promised_outcome="income",
        syllabus=["Audience growth", "How to sell your course", "Monetize"],
    )
    instructor = default_instructor_evidence()
    free_alt = default_free_alternatives()

    result = run_node(profile, instructor, free_alt)

    assert result["mode"] == "A_should_not"
    assert any("Recursive" in flag for flag in result["red_flags"])


def test_scenario_3_income_promise_with_scarcity() -> None:
    """Scenario 3: Income Promise + Scarcity Manipulation.

    A course promising income combined with scarcity marketing signals
    must lead to 'A_should_not' mode.
    """
    profile = default_course_profile(
        promised_outcome="income",
        scarcity_signals=["only 2 spots left", "countdown timer"],
    )
    instructor = default_instructor_evidence()
    free_alt = default_free_alternatives()

    result = run_node(profile, instructor, free_alt)

    assert result["mode"] == "A_should_not"
    assert any("Scarcity" in flag for flag in result["red_flags"])
    assert any("Income" in flag for flag in result["red_flags"])


def test_scenario_4_high_free_coverage() -> None:
    """Scenario 4: High Free Coverage.

    A skill course where high-quality (non content farm) free alternatives cover
    70%+ of the syllabus with low extraction cost must lead to 'B_need_not' mode.
    """
    profile = default_course_profile(promised_outcome="skill")
    instructor = default_instructor_evidence(footprint="medium")
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

    result = run_node(profile, instructor, free_alt)

    assert result["mode"] == "B_need_not"


def test_scenario_5_strong_footprint_low_coverage_high_extraction() -> None:
    """Scenario 5: Strong/Medium Footprint + Coverage < 80% + High Extraction Cost.

    A course taught by an instructor with a strong footprint, where free alternatives
    cover less than 80% and have high extraction cost, must lead to 'worth_buying' mode.
    """
    profile = default_course_profile(promised_outcome="skill")
    instructor = default_instructor_evidence(
        footprint="strong",
        github_real_work=True,
        verifiable_employment=True,
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

    result = run_node(profile, instructor, free_alt)

    assert result["mode"] == "worth_buying"


def test_scenario_6_skill_course_credible_instructor_no_good_alternative() -> None:
    """Scenario 6: Skill course + Credible Instructor + No Good Free Alternatives.

    A skill course where the instructor has verifiable professional work / GitHub contributions,
    and there are no good free alternatives (very low coverage or extremely high cost),
    must lead to 'worth_buying' mode.
    """
    profile = default_course_profile(promised_outcome="skill")
    instructor = default_instructor_evidence(
        footprint="weak",  # Even with weak public footprint, the instructor has real work
        github_real_work=True,
        verifiable_employment=False,
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

    result = run_node(profile, instructor, free_alt)

    assert result["mode"] == "worth_buying"


def test_scenario_7_weak_footprint_only_sells_courses() -> None:
    """Scenario 7: Weak Footprint + Only Sells Courses.

    An instructor with a weak footprint whose only verifiable activity is selling
    courses must trigger a weak footprint red flag.
    """
    profile = default_course_profile(promised_outcome="skill")
    instructor = default_instructor_evidence(
        footprint="weak",
        only_sells_courses=True,
    )
    free_alt = default_free_alternatives()

    result = run_node(profile, instructor, free_alt)

    assert any("Weak Footprint" in flag for flag in result["red_flags"])


def test_scenario_8_boundary_empty_evidences() -> None:
    """Scenario 8: Boundary: All Three Evidences Empty.

    When all input evidences are empty or default, it should evaluate to the
    existing default mode.
    """
    profile = default_course_profile(promised_outcome="unknown")
    instructor = default_instructor_evidence()
    free_alt = default_free_alternatives()

    result = run_node(profile, instructor, free_alt)

    assert result["mode"] == "B_need_not"
