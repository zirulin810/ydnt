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
    """Tests score_content with safety signals, outcome, syllabus depth, and scarcity."""
    # Safety flag check (injection detected)
    assert score_content({"promised_outcome": "skill"}, "injection_detected") == 1

    # MLM recruitment signal
    assert (
        score_content({"recruitment_signal": True, "promised_outcome": "skill"}, None)
        == 1
    )

    # High quality skill course with many syllabus topics and no scarcity signals
    high_quality_profile = {
        "promised_outcome": "skill",
        "syllabus": ["Intro", "Setup", "Coding", "Testing", "Deployment"],
        "scarcity_signals": [],
    }
    assert score_content(high_quality_profile, None) == 5

    # Skill course with fewer topics and scarcity signals
    lower_quality_profile = {
        "promised_outcome": "skill",
        "syllabus": ["Intro"],
        "scarcity_signals": ["limited seats"],
    }
    assert score_content(lower_quality_profile, None) <= 3


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
