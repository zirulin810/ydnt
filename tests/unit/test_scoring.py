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
    decide_recommendation,
    score_alt_content,
    score_alt_creator,
    score_content,
    score_creator,
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
    assert score == 4
    assert reasons == []

    # Medium-low prices (< 150)
    score, reasons = score_pricing({"price_usd": 99.0})
    assert score == 3
    assert reasons == []

    # Medium prices (< 500)
    score, reasons = score_pricing({"price_usd": 299.0})
    assert score == 2
    assert reasons == []

    # High prices (>= 500)
    score, reasons = score_pricing({"price_usd": 799.0})
    assert score == 1
    assert reasons == []

    # Extremely high prices
    score, reasons = score_pricing({"price_usd": 1500.0})
    assert score == 1
    assert reasons == []


def test_score_content() -> None:
    """Tests score_content veto conditions (returning 1) and quality levels (2-5)."""
    # 1. Sole Veto condition: is_pyramid_scheme is True
    score, _ = score_content({"promised_outcome": "skill", "is_pyramid_scheme": True})
    assert score == 1

    # 2. Non-veto: income + scarcity does NOT veto (score is not 1)
    income_scarcity_profile = {
        "promised_outcome": "income",
        "scarcity_signals": ["only 2 spots left"],
        "syllabus": ["Intro", "Setup"],
    }
    score, _ = score_content(income_scarcity_profile)
    # base 2 (income) + 1 (len(syllabus)=2) - 1 (scarcity) = 2
    assert score == 2

    # 3. Non-veto: income + monetization keyword in syllabus does NOT veto
    monetization_profile = {
        "promised_outcome": "income",
        "syllabus": ["Audience monetization strategies", "How to sell courses"],
        "is_pyramid_scheme": False,
    }
    score, _ = score_content(monetization_profile)
    # base 2 + 1 (len=2) = 3
    assert score == 3

    # Non-veto quality checks: must return 2-5, never 1
    # Skill course with syllabus
    skill_profile = {
        "promised_outcome": "skill",
        "syllabus": ["Intro", "Setup"],
    }
    score, _ = score_content(skill_profile)
    assert score >= 2

    # High quality skill course
    high_quality_profile = {
        "promised_outcome": "skill",
        "syllabus": ["Intro", "Setup", "Coding", "Testing", "Deployment"],
        "scarcity_signals": [],
    }
    score, _reasons = score_content(high_quality_profile)
    assert score == 5


def test_score_content_reasons_ground_truth() -> None:
    """Tests that score_content reasons contain correct ground-truth assertions."""
    # score_content(is_pyramid_scheme) -> returns red reason with "Pyramid Scheme"
    score, reasons = score_content({"promised_outcome": "skill", "is_pyramid_scheme": True})
    assert score == 1
    red_reasons = [r for r in reasons if r.severity == "red"]
    green_reasons = [r for r in reasons if r.severity == "green"]
    assert len(red_reasons) == 1
    assert "Pyramid" in red_reasons[0].message
    assert len(green_reasons) == 0


def test_score_creator() -> None:
    """Tests score_creator with footprint, track record, and course-selling flags."""
    # No footprint or credentials (analogous to exists = False)
    score, _ = score_creator(
        {
            "footprint": "weak",
            "verifiable_track_record": False,
        }
    )
    assert score == 1

    # Verifiable professional work or employment
    score, _ = score_creator({"verifiable_track_record": True})
    assert score >= 4

    # Weak footprint and only sells courses
    score, _reasons = score_creator(
        {
            "footprint": "weak",
            "verifiable_track_record": False,
            "only_sells_courses": True,
        }
    )
    assert score == 2


def test_score_creator_reasons_ground_truth() -> None:
    """Tests that score_creator reasons contain correct ground-truth assertions."""
    # score_creator(track record) → 含 "Credible" green。
    _, reasons = score_creator({"verifiable_track_record": True})
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
    assert reasons == []

    # Low coverage
    poor_alt = {
        "best_coverage_pct": 10,
        "items": [],
    }
    score, reasons = score_alt_content(poor_alt)
    assert score == 1
    assert reasons == []

    # Content farm flag penalty
    farm_alt = {
        "best_coverage_pct": 80,
        "items": [{"content_farm_flag": True}],
    }
    score, reasons = score_alt_content(farm_alt)
    assert score <= 3
    assert reasons == []


def test_score_alt_creator() -> None:
    """Tests score_alt_creator boundary conditions."""
    # No alternatives found
    score, reasons = score_alt_creator({"items": []})
    assert score == 1
    assert reasons == []

    # Alternative is a content farm
    score, reasons = score_alt_creator({"items": [{"content_farm_flag": True}]})
    assert score == 2
    assert reasons == []

    # High extraction cost
    score, reasons = score_alt_creator({"items": [{"extraction_cost": "high"}]})
    assert score == 3
    assert reasons == []

    # Clean alternative source
    score, reasons = score_alt_creator(
        {"items": [{"extraction_cost": "low", "content_farm_flag": False}]}
    )
    assert score == 5
    assert reasons == []


def test_decide_recommendation_scores_only() -> None:
    """Tests decide_recommendation to ensure decision branches are derived solely from scores and price/coverage."""
    # 1. content_score == 1 -> should_not
    scores = {"content_score": 1, "creator_score": 5}
    rec, _, _ = decide_recommendation(scores, {}, price_usd=0.0, best_coverage_pct=0.0)
    assert rec == "should_not"

    # 2. content_score < 3 -> need_not
    scores = {"content_score": 2, "creator_score": 5}
    rec, _, _ = decide_recommendation(scores, {}, price_usd=0.0, best_coverage_pct=0.0)
    assert rec == "need_not"

    # 3. creator_score < 4 -> need_not
    scores = {"content_score": 4, "creator_score": 3}
    rec, _, _ = decide_recommendation(scores, {}, price_usd=0.0, best_coverage_pct=0.0)
    assert rec == "need_not"

    # 4. price_usd is None -> situational (eff_score = 3)
    scores = {"content_score": 4, "creator_score": 4}
    rec, _, _ = decide_recommendation(scores, {}, price_usd=None, best_coverage_pct=50.0)
    assert rec == "situational"

    # 5. Free (price_usd <= 0) -> worthy (eff_score = 5)
    scores = {"content_score": 4, "creator_score": 4}
    rec, _, _ = decide_recommendation(scores, {}, price_usd=0.0, best_coverage_pct=80.0)
    assert rec == "worthy"

    # 6. $50 @ 80% coverage -> situational
    scores = {"content_score": 4, "creator_score": 4}
    rec, _, _ = decide_recommendation(scores, {}, price_usd=50.0, best_coverage_pct=80.0)
    assert rec == "situational"

    # 7. $50 @ 90% coverage -> need_not
    scores = {"content_score": 4, "creator_score": 4}
    rec, _, _ = decide_recommendation(scores, {}, price_usd=50.0, best_coverage_pct=90.0)
    assert rec == "need_not"


def test_decide_recommendation_veto_flags() -> None:
    """Tests that decide_recommendation generates correct flags for veto situations."""
    scores = {"content_score": 1}
    reasons = {
        "content": [
            Reason("red", "Pyramid Scheme: Course revolves around recruiting or reselling the course itself."),
            Reason("green", "Teaches concrete technical or business skills.")
        ],
        "creator": [
            Reason("red", "Weak Footprint: Creator has no notable independent professional achievements.")
        ]
    }
    rec, red_flags, green_flags = decide_recommendation(scores, reasons, price_usd=0.0, best_coverage_pct=0.0)
    assert rec == "should_not"
    assert len(red_flags) == 1
    assert "Pyramid" in red_flags[0]
    assert green_flags == []


def test_decide_recommendation_non_veto_flags() -> None:
    """Tests that decide_recommendation collects all reasons and separates them by severity when not vetoed."""
    scores = {"content_score": 3, "creator_score": 4}
    reasons = {
        "content": [
            Reason("green", "Teaches concrete technical or business skills."),
            Reason("red", "Income Promises: Marketing promises financial earnings.")
        ],
        "creator": [
            Reason("green", "Credible Creator: verifiable professional or organizational standing.")
        ],
        "alt": [
            Reason("red", "Content Farm: Free alternatives are bloated or low-quality.")
        ]
    }
    rec, red_flags, green_flags = decide_recommendation(scores, reasons, price_usd=0.0, best_coverage_pct=0.0)
    assert rec == "worthy"
    assert len(red_flags) == 2
    assert any("Income" in flag for flag in red_flags)
    assert any("Content Farm" in flag for flag in red_flags)
    assert len(green_flags) == 2
    assert any("Teaches" in flag for flag in green_flags)
    assert any("Credible" in flag for flag in green_flags)
