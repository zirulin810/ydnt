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

"""Pure scoring functions for YDNT due diligence rubrics.

Design:
Provides pure functions to score different axes of online courses and determine
the final mode, without depending on google.adk or Context objects.
"""

from __future__ import annotations

from typing import Any


def score_pricing(profile: dict[str, Any]) -> int:
    """Scores course pricing from 1 (very high risk/cost) to 5 (low risk/cost).

    Design: Assesses total price risk. Low pricing receives a high score.
    """
    price = profile.get("price_usd", 0.0)
    if price <= 0:
        return 5
    elif price < 50:
        return 5
    elif price < 150:
        return 4
    elif price < 500:
        return 3
    elif price < 1000:
        return 2
    else:
        return 1


def score_content(profile: dict[str, Any], security_flag: str | None) -> int:
    """Scores course content value and safety from 1 to 5.

    Design: Returning 1 if and only if any toxicity/veto signals occur.
    Otherwise, returns a quality score between 2 and 5.
    """
    promised_outcome = profile.get("promised_outcome", "unknown")
    syllabus = profile.get("syllabus", [])
    syllabus_str = " ".join(syllabus).lower()
    recursive_keywords = [
        "audience",
        "sell course",
        "monetize",
        "make money",
        "following",
        "passive income",
    ]
    is_recursive = promised_outcome == "income" and any(
        k in syllabus_str for k in recursive_keywords
    )
    scarcity_signals = profile.get("scarcity_signals", [])
    recruitment_signal = profile.get("recruitment_signal", False)

    # Toxicity check: force return 1 if any veto condition matches
    if (
        security_flag == "injection_detected"
        or recruitment_signal
        or is_recursive
        or (promised_outcome == "income" and scarcity_signals)
    ):
        return 1

    # Quality scoring for non-toxic courses (giving 2..5)
    if promised_outcome == "income":
        score = 2
    elif promised_outcome == "skill":
        score = 3
    else:
        score = 2

    if len(syllabus) >= 5:
        score += 2
    elif len(syllabus) >= 2:
        score += 1

    if scarcity_signals:
        score -= 1

    # Ensure score is within 2..5 range for non-toxic content
    return max(2, min(5, score))


def score_instructor(evidence: dict[str, Any]) -> int:
    """Scores instructor credibility and footprint from 1 to 5.

    Design: Relies on verifiable hard facts (GitHub real work or employment)
    rather than subjective footprint tags.
    """
    footprint = evidence.get("footprint", "weak")
    github = evidence.get("github_real_work", False)
    employment = evidence.get("verifiable_employment", False)
    only_sells = evidence.get("only_sells_courses", False)

    if github or employment:
        if footprint == "strong":
            return 5
        return 4

    if footprint == "weak" and only_sells:
        return 2

    if footprint == "strong":
        return 4
    elif footprint == "medium":
        return 3
    else:
        return 1


def score_alt_content(free_alt: dict[str, Any]) -> int:
    """Scores quality and coverage depth of free alternatives from 1 to 5.

    Design: Values coverage percentage while penalizing low-quality content
    farms and unstructured content (high extraction cost).
    """
    best_coverage = free_alt.get("best_coverage_pct", 0)
    items = free_alt.get("items", [])

    any_content_farm = any(item.get("content_farm_flag", False) for item in items)
    high_extraction_cost = any(item.get("extraction_cost") == "high" for item in items)

    if best_coverage >= 80:
        score = 5
    elif best_coverage >= 60:
        score = 4
    elif best_coverage >= 40:
        score = 3
    elif best_coverage >= 20:
        score = 2
    else:
        score = 1

    if any_content_farm:
        score -= 2
    if high_extraction_cost:
        score -= 1

    return max(1, min(5, score))


def score_alt_instructor(free_alt: dict[str, Any]) -> int:
    """Scores alternative instructors' credibility from 1 to 5.

    Design: Rates alternative sources based on structural quality.
    """
    items = free_alt.get("items", [])
    if not items:
        return 1

    any_content_farm = any(item.get("content_farm_flag", False) for item in items)
    high_extraction_cost = any(item.get("extraction_cost") == "high" for item in items)

    if any_content_farm:
        return 2
    if high_extraction_cost:
        return 3
    return 5


def decide_mode(
    scores: dict[str, int],
    profile: dict[str, Any],
    instructor: dict[str, Any],
    free_alt: dict[str, Any],
    security_flag: str | None = None,
) -> tuple[str, list[str], list[str]]:
    """Determines final due diligence mode, red flags, and green flags.

    Design: Mode determination is solely based on scores. Raw fields are
    used only to generate the flag messages.
    """
    promised_outcome = profile.get("promised_outcome", "unknown")
    syllabus = profile.get("syllabus", [])
    syllabus_str = " ".join(syllabus).lower()
    recursive_keywords = [
        "audience",
        "sell course",
        "monetize",
        "make money",
        "following",
        "passive income",
    ]
    is_recursive = promised_outcome == "income" and any(
        k in syllabus_str for k in recursive_keywords
    )

    scarcity_signals = profile.get("scarcity_signals", [])
    recruitment_signal = profile.get("recruitment_signal", False)

    footprint = instructor.get("footprint", "weak")
    github_real_work = instructor.get("github_real_work", False)
    verifiable_employment = instructor.get("verifiable_employment", False)
    only_sells_courses = instructor.get("only_sells_courses", False)

    free_items = free_alt.get("items", [])
    best_coverage_pct = free_alt.get("best_coverage_pct", 0)
    any_content_farm = any(item.get("content_farm_flag", False) for item in free_items)
    high_extraction_cost = any(
        item.get("extraction_cost") == "high" for item in free_items
    )

    red_flags = []
    green_flags = []

    # Flag calculations matching historical rules
    if is_recursive:
        red_flags.append(
            "Recursive Theme: Course syllabus focuses on audience monetization/selling courses."
        )
    else:
        green_flags.append("Teaches concrete technical or business skills.")

    if footprint == "weak" and only_sells_courses:
        red_flags.append(
            "Weak Footprint: Instructor has no notable independent professional achievements."
        )
    elif github_real_work or verifiable_employment:
        green_flags.append(
            "Credible Instructor: Active GitHub or professional employment."
        )

    if promised_outcome == "income":
        red_flags.append("Income Promises: Marketing promises financial earnings.")
    elif promised_outcome == "skill":
        green_flags.append("Skill acquisition promise.")

    if any_content_farm:
        red_flags.append("Content Farm: Free alternatives are bloated or low-quality.")

    if scarcity_signals:
        red_flags.append(
            f"Scarcity Manipulation: Marketing uses: {', '.join(scarcity_signals)}."
        )

    if recruitment_signal:
        red_flags.append(
            "Recruitment MLM: Promotes students to become resellers/coaches."
        )

    if best_coverage_pct < 60:
        red_flags.append(
            f"Low Free Coverage: Free alternatives cover only {best_coverage_pct}%."
        )
    elif high_extraction_cost:
        red_flags.append(
            "High Extraction Cost: Free alternatives are unstructured/messy."
        )

    # Decision Matrix solely based on scores
    content_score = scores.get("content_score", 3)
    instructor_score = scores.get("instructor_score", 1)
    alt_content_score = scores.get("alt_content_score", 1)

    if content_score == 1:
        mode = "A_should_not"
    elif (
        content_score >= 3
        and instructor_score >= 4
        # coverage <= course content quality (meaning free alternative is not better/easier than buying)
        and alt_content_score <= content_score
    ):
        mode = "worth_buying"
    else:
        mode = "B_need_not"

    return mode, red_flags, green_flags
