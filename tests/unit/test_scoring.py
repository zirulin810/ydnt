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

"""Unit tests for the pure scoring functions in app/scoring.py."""

from __future__ import annotations

from app.scoring import (
    decide_mode,
    score_alt_content,
    score_alt_instructor,
    score_content,
    score_instructor,
    score_pricing,
)


def test_score_pricing() -> None:
    """Tests score_pricing with various price levels and boundary conditions."""
    # Free/Zero/Negative prices
    assert score_pricing({"price_usd": 0.0}) == 5
    assert score_pricing({"price_usd": -10.0}) == 5

    # Low prices (< 50)
    assert score_pricing({"price_usd": 29.0}) == 5

    # Medium-low prices (< 150)
    assert score_pricing({"price_usd": 99.0}) == 4

    # Medium prices (< 500)
    assert score_pricing({"price_usd": 299.0}) == 3

    # High prices (< 1000)
    assert score_pricing({"price_usd": 799.0}) == 2

    # Extremely high prices (>= 1000)
    assert score_pricing({"price_usd": 1500.0}) == 1


def test_score_content() -> None:
    """Tests score_content veto conditions (returning 1) and quality levels (2-5)."""
    # 1. Veto condition: security flag injection_detected
    assert score_content({"promised_outcome": "skill"}, "injection_detected") == 1

    # 2. Veto condition: recruitment_signal is True
    assert (
        score_content({"recruitment_signal": True, "promised_outcome": "skill"}, None)
        == 1
    )

    # 3. Veto condition: Recursive Theme (income outcome + monetization syllabus)
    recursive_profile = {
        "promised_outcome": "income",
        "syllabus": ["Audience monetization strategies", "How to sell courses"],
    }
    assert score_content(recursive_profile, None) == 1

    # 4. Veto condition: Income Promises + Scarcity Manipulation
    income_scarcity_profile = {
        "promised_outcome": "income",
        "scarcity_signals": ["only 2 spots left"],
    }
    assert score_content(income_scarcity_profile, None) == 1

    # Non-veto quality checks: must return 2-5, never 1
    # Skill course with syllabus
    skill_profile = {
        "promised_outcome": "skill",
        "syllabus": ["Intro", "Setup"],
    }
    assert score_content(skill_profile, None) >= 2

    # Income course without scarcity or recursive topics
    income_clean_profile = {
        "promised_outcome": "income",
        "syllabus": ["Financial Literacy Basics"],
        "scarcity_signals": [],
    }
    assert score_content(income_clean_profile, None) >= 2

    # High quality skill course
    high_quality_profile = {
        "promised_outcome": "skill",
        "syllabus": ["Intro", "Setup", "Coding", "Testing", "Deployment"],
        "scarcity_signals": [],
    }
    assert score_content(high_quality_profile, None) == 5


def test_score_instructor() -> None:
    """Tests score_instructor with footprint, GitHub, employment, and course-selling flags."""
    # No footprint or credentials (analogous to exists = False)
    assert (
        score_instructor(
            {
                "footprint": "weak",
                "github_real_work": False,
                "verifiable_employment": False,
            }
        )
        == 1
    )

    # Verifiable professional work or employment
    assert (
        score_instructor({"github_real_work": True, "verifiable_employment": False})
        >= 4
    )
    assert (
        score_instructor({"github_real_work": False, "verifiable_employment": True})
        >= 4
    )

    # Weak footprint and only sells courses
    assert (
        score_instructor(
            {
                "footprint": "weak",
                "github_real_work": False,
                "verifiable_employment": False,
                "only_sells_courses": True,
            }
        )
        == 2
    )


def test_score_alt_content() -> None:
    """Tests score_alt_content with coverage, content farm flag, and extraction cost."""
    # Ideal high coverage and low extraction cost
    good_alt = {
        "best_coverage_pct": 90,
        "items": [{"extraction_cost": "low", "content_farm_flag": False}],
    }
    assert score_alt_content(good_alt) == 5

    # Low coverage
    poor_alt = {
        "best_coverage_pct": 10,
        "items": [],
    }
    assert score_alt_content(poor_alt) == 1

    # Content farm flag penalty
    farm_alt = {
        "best_coverage_pct": 80,
        "items": [{"content_farm_flag": True}],
    }
    assert score_alt_content(farm_alt) <= 3


def test_score_alt_instructor() -> None:
    """Tests score_alt_instructor boundary conditions."""
    # No alternatives found
    assert score_alt_instructor({"items": []}) == 1

    # Alternative is a content farm
    assert score_alt_instructor({"items": [{"content_farm_flag": True}]}) == 2

    # High extraction cost
    assert score_alt_instructor({"items": [{"extraction_cost": "high"}]}) == 3

    # Clean alternative source
    assert (
        score_alt_instructor(
            {"items": [{"extraction_cost": "low", "content_farm_flag": False}]}
        )
        == 5
    )


def test_decide_mode_scores_only() -> None:
    """Tests decide_mode to ensure decision branches are derived solely from scores."""
    # 1. content_score == 1 -> should_not
    scores = {"content_score": 1, "instructor_score": 5, "alt_content_score": 2}
    mode, _, _ = decide_mode(scores, {}, {}, {})
    assert mode == "A_should_not"

    # 2. worth_buying (content_score >= 3, instructor_score >= 4, alt_content_score <= content_score)
    scores = {"content_score": 3, "instructor_score": 4, "alt_content_score": 2}
    mode, _, _ = decide_mode(scores, {}, {}, {})
    assert mode == "worth_buying"

    # 3. B_need_not (otherwise)
    # E.g. content_score too low (< 3)
    scores = {"content_score": 2, "instructor_score": 5, "alt_content_score": 2}
    mode, _, _ = decide_mode(scores, {}, {}, {})
    assert mode == "B_need_not"

    # E.g. instructor_score too low (< 4)
    scores = {"content_score": 4, "instructor_score": 3, "alt_content_score": 2}
    mode, _, _ = decide_mode(scores, {}, {}, {})
    assert mode == "B_need_not"

    # E.g. alt_content_score > content_score (free alternatives coverage outweighs course quality)
    scores = {"content_score": 3, "instructor_score": 5, "alt_content_score": 4}
    mode, _, _ = decide_mode(scores, {}, {}, {})
    assert mode == "B_need_not"


def test_decide_mode_veto_flags() -> None:
    """Tests that decide_mode generates correct flags for veto situations."""
    # 1. Prompt Injection veto
    scores = {"content_score": 1}
    profile = {}
    instructor = {}
    free_alt = {}
    mode, red_flags, green_flags = decide_mode(
        scores, profile, instructor, free_alt, security_flag="injection_detected"
    )
    assert mode == "A_should_not"
    assert any("Injection" in flag for flag in red_flags)
    assert green_flags == []

    # 2. Recruitment MLM veto
    scores = {"content_score": 1}
    profile = {"recruitment_signal": True}
    mode, red_flags, green_flags = decide_mode(
        scores, profile, instructor, free_alt
    )
    assert mode == "A_should_not"
    assert any("MLM" in flag for flag in red_flags)
    assert green_flags == []

