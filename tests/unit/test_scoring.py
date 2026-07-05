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
    Reason,
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
    score, reasons = score_pricing({"price_usd": 0.0})
    assert score == 5
    assert reasons == []

    score, reasons = score_pricing({"price_usd": -10.0})
    assert score == 5
    assert reasons == []

    # Low prices (< 50)
    score, reasons = score_pricing({"price_usd": 29.0})
    assert score == 5
    assert reasons == []

    # Medium-low prices (< 150)
    score, reasons = score_pricing({"price_usd": 99.0})
    assert score == 4
    assert reasons == []

    # Medium prices (< 500)
    score, reasons = score_pricing({"price_usd": 299.0})
    assert score == 3
    assert reasons == []

    # High prices (< 1000)
    score, reasons = score_pricing({"price_usd": 799.0})
    assert score == 2
    assert reasons == []

    # Extremely high prices (>= 1000)
    score, reasons = score_pricing({"price_usd": 1500.0})
    assert score == 1
    assert reasons == []


def test_score_content() -> None:
    """Tests score_content veto conditions (returning 1) and quality levels (2-5)."""
    # 1. Veto condition: manipulation_attempt is True
    score, reasons = score_content({"promised_outcome": "skill", "manipulation_attempt": True})
    assert score == 1

    # 2. Veto condition: recruitment_signal is True
    score, reasons = score_content({"recruitment_signal": True, "promised_outcome": "skill"})
    assert score == 1

    # 3. Veto condition: Recursive Theme (income outcome + monetization syllabus)
    recursive_profile = {
        "promised_outcome": "income",
        "syllabus": ["Audience monetization strategies", "How to sell courses"],
    }
    score, reasons = score_content(recursive_profile)
    assert score == 1

    # 4. Veto condition: Income Promises + Scarcity Manipulation
    income_scarcity_profile = {
        "promised_outcome": "income",
        "scarcity_signals": ["only 2 spots left"],
    }
    score, reasons = score_content(income_scarcity_profile)
    assert score == 1

    # Non-veto quality checks: must return 2-5, never 1
    # Skill course with syllabus
    skill_profile = {
        "promised_outcome": "skill",
        "syllabus": ["Intro", "Setup"],
    }
    score, reasons = score_content(skill_profile)
    assert score >= 2

    # Income course without scarcity or recursive topics
    income_clean_profile = {
        "promised_outcome": "income",
        "syllabus": ["Financial Literacy Basics"],
        "scarcity_signals": [],
    }
    score, reasons = score_content(income_clean_profile)
    assert score >= 2

    # High quality skill course
    high_quality_profile = {
        "promised_outcome": "skill",
        "syllabus": ["Intro", "Setup", "Coding", "Testing", "Deployment"],
        "scarcity_signals": [],
    }
    score, reasons = score_content(high_quality_profile)
    assert score == 5


def test_score_content_reasons_ground_truth() -> None:
    """Tests that score_content reasons contain correct ground-truth assertions."""
    # score_content(manipulation_attempt) → 回傳含一條 red 且 message 含 "Manipulation"; score==1 時無 green。
    score, reasons = score_content({"promised_outcome": "skill", "manipulation_attempt": True})
    assert score == 1
    red_reasons = [r for r in reasons if r.severity == "red"]
    green_reasons = [r for r in reasons if r.severity == "green"]
    assert len(red_reasons) == 1
    assert "Manipulation" in red_reasons[0].message
    assert len(green_reasons) == 0

    # score_content(recruitment) → 含 "MLM" red、無 green。
    score, reasons = score_content({"recruitment_signal": True, "promised_outcome": "skill"})
    assert score == 1
    red_reasons = [r for r in reasons if r.severity == "red"]
    green_reasons = [r for r in reasons if r.severity == "green"]
    assert any("MLM" in r.message for r in red_reasons)
    assert len(green_reasons) == 0


def test_score_instructor() -> None:
    """Tests score_instructor with footprint, GitHub, employment, and course-selling flags."""
    # No footprint or credentials (analogous to exists = False)
    score, reasons = score_instructor(
        {
            "footprint": "weak",
            "github_real_work": False,
            "verifiable_employment": False,
        }
    )
    assert score == 1

    # Verifiable professional work or employment
    score, reasons = score_instructor({"github_real_work": True, "verifiable_employment": False})
    assert score >= 4
    score, reasons = score_instructor({"github_real_work": False, "verifiable_employment": True})
    assert score >= 4

    # Weak footprint and only sells courses
    score, reasons = score_instructor(
        {
            "footprint": "weak",
            "github_real_work": False,
            "verifiable_employment": False,
            "only_sells_courses": True,
        }
    )
    assert score == 2


def test_score_instructor_reasons_ground_truth() -> None:
    """Tests that score_instructor reasons contain correct ground-truth assertions."""
    # score_instructor(github/employment) → 含 "Credible" green。
    score, reasons = score_instructor({"github_real_work": True, "verifiable_employment": False})
    assert any("Credible" in r.message and r.severity == "green" for r in reasons)

    score, reasons = score_instructor({"github_real_work": False, "verifiable_employment": True})
    assert any("Credible" in r.message and r.severity == "green" for r in reasons)


def test_score_alt_content() -> None:
    """Tests score_alt_content with coverage, content farm flag, and extraction cost."""
    # Ideal high coverage and low extraction cost
    good_alt = {
        "best_coverage_pct": 90,
        "items": [{"extraction_cost": "low", "content_farm_flag": False}],
    }
    score, reasons = score_alt_content(good_alt)
    assert score == 5

    # Low coverage
    poor_alt = {
        "best_coverage_pct": 10,
        "items": [],
    }
    score, reasons = score_alt_content(poor_alt)
    assert score == 1

    # Content farm flag penalty
    farm_alt = {
        "best_coverage_pct": 80,
        "items": [{"content_farm_flag": True}],
    }
    score, reasons = score_alt_content(farm_alt)
    assert score <= 3


def test_score_alt_instructor() -> None:
    """Tests score_alt_instructor boundary conditions."""
    # No alternatives found
    score, reasons = score_alt_instructor({"items": []})
    assert score == 1
    assert reasons == []

    # Alternative is a content farm
    score, reasons = score_alt_instructor({"items": [{"content_farm_flag": True}]})
    assert score == 2
    assert reasons == []

    # High extraction cost
    score, reasons = score_alt_instructor({"items": [{"extraction_cost": "high"}]})
    assert score == 3
    assert reasons == []

    # Clean alternative source
    score, reasons = score_alt_instructor(
        {"items": [{"extraction_cost": "low", "content_farm_flag": False}]}
    )
    assert score == 5
    assert reasons == []


def test_decide_mode_scores_only() -> None:
    """Tests decide_mode to ensure decision branches are derived solely from scores."""
    # 1. content_score == 1 -> should_not
    scores = {"content_score": 1, "instructor_score": 5, "alt_content_score": 2}
    mode, red_flags, green_flags = decide_mode(scores, {})
    assert mode == "should_not"

    # 2. worth_buying (content_score >= 3, instructor_score >= 4, alt_content_score <= content_score)
    scores = {"content_score": 3, "instructor_score": 4, "alt_content_score": 2}
    mode, red_flags, green_flags = decide_mode(scores, {})
    assert mode == "worth_buying"

    # 3. need_not (otherwise)
    # E.g. content_score too low (< 3)
    scores = {"content_score": 2, "instructor_score": 5, "alt_content_score": 2}
    mode, red_flags, green_flags = decide_mode(scores, {})
    assert mode == "need_not"

    # E.g. instructor_score too low (< 4)
    scores = {"content_score": 4, "instructor_score": 3, "alt_content_score": 2}
    mode, red_flags, green_flags = decide_mode(scores, {})
    assert mode == "need_not"

    # E.g. alt_content_score > content_score (free alternatives coverage outweighs course quality)
    scores = {"content_score": 3, "instructor_score": 5, "alt_content_score": 4}
    mode, red_flags, green_flags = decide_mode(scores, {})
    assert mode == "need_not"


def test_decide_mode_veto_flags() -> None:
    """Tests that decide_mode generates correct flags for veto situations."""
    # content_score==1 → 只取 content 的 red、green 為空;
    scores = {"content_score": 1}
    reasons = {
        "content": [
            Reason("red", "Manipulation Attempt: Sales page tries to manipulate the AI reviewer."),
            Reason("green", "Teaches concrete technical or business skills.")
        ],
        "instructor": [
            Reason("red", "Weak Footprint: Instructor has no notable independent professional achievements.")
        ]
    }
    mode, red_flags, green_flags = decide_mode(scores, reasons)
    assert mode == "should_not"
    assert len(red_flags) == 1
    assert "Manipulation" in red_flags[0]
    assert green_flags == []


def test_decide_mode_non_veto_flags() -> None:
    """Tests that decide_mode collects all reasons and separates them by severity when not vetoed."""
    # 非 veto → 匯集所有理由並依 severity 拆分。
    scores = {"content_score": 3, "instructor_score": 4, "alt_content_score": 2}
    reasons = {
        "content": [
            Reason("green", "Teaches concrete technical or business skills."),
            Reason("red", "Income Promises: Marketing promises financial earnings.")
        ],
        "instructor": [
            Reason("green", "Credible Instructor: Active GitHub or professional employment.")
        ],
        "alt": [
            Reason("red", "Content Farm: Free alternatives are bloated or low-quality.")
        ]
    }
    mode, red_flags, green_flags = decide_mode(scores, reasons)
    assert mode == "worth_buying"
    assert len(red_flags) == 2
    assert any("Income" in flag for flag in red_flags)
    assert any("Content Farm" in flag for flag in red_flags)
    assert len(green_flags) == 2
    assert any("Teaches" in flag for flag in green_flags)
    assert any("Credible" in flag for flag in green_flags)
