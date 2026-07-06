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

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Reason:
    severity: str   # "red" 或 "green"
    message: str


def score_pricing(profile: dict[str, Any]) -> tuple[int, list[Reason]]:
    """Scores course pricing from 1 (very high risk/cost) to 5 (low risk/cost).

    Design: Assesses total price risk. Low pricing receives a high score.
    """
    price = profile.get("price_usd")
    if price is None:
        return 3, []
    if price <= 0:
        return 5, []
    elif price < 50:
        return 4, []
    elif price < 150:
        return 3, []
    elif price < 500:
        return 2, []
    else:
        return 1, []


def score_content(profile: dict[str, Any]) -> tuple[int, list[Reason]]:
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
    manipulation_attempt = profile.get("manipulation_attempt", False)

    # Toxicity check: force return 1 if any veto condition matches
    if (
        manipulation_attempt
        or recruitment_signal
        or is_recursive
        or (promised_outcome == "income" and scarcity_signals)
    ):
        score = 1
    else:
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
        score = max(2, min(5, score))

    reasons = []
    if score == 1:
        if manipulation_attempt:
            reasons.append(Reason("red", "Manipulation Attempt: Sales page tries to manipulate the AI reviewer."))
        if recruitment_signal:
            reasons.append(Reason("red", "Recruitment MLM: Promotes students to become resellers/coaches."))
        if is_recursive:
            reasons.append(Reason("red", "Recursive Theme: Course syllabus focuses on audience monetization/selling courses."))
        if promised_outcome == "income":
            reasons.append(Reason("red", "Income Promises: Marketing promises financial earnings."))
        if scarcity_signals:
            reasons.append(Reason("red", f"Scarcity Manipulation: Marketing uses: {', '.join(scarcity_signals)}."))
    else:
        if is_recursive:
            reasons.append(Reason("red", "Recursive Theme: Course syllabus focuses on audience monetization/selling courses."))
        else:
            reasons.append(Reason("green", "Teaches concrete technical or business skills."))

        if promised_outcome == "income":
            reasons.append(Reason("red", "Income Promises: Marketing promises financial earnings."))
        elif promised_outcome == "skill":
            reasons.append(Reason("green", "Skill acquisition promise."))

        if scarcity_signals:
            reasons.append(Reason("red", f"Scarcity Manipulation: Marketing uses: {', '.join(scarcity_signals)}."))

        if recruitment_signal:
            reasons.append(Reason("red", "Recruitment MLM: Promotes students to become resellers/coaches."))

    return score, reasons


def score_creator(evidence: dict[str, Any]) -> tuple[int, list[Reason]]:
    """Scores creator credibility and footprint from 1 to 5.

    Design: Relies on verifiable hard facts (GitHub real work or employment)
    rather than subjective footprint tags.
    """
    footprint = evidence.get("footprint", "weak")
    github = evidence.get("github_real_work", False)
    employment = evidence.get("verifiable_employment", False)
    only_sells = evidence.get("only_sells_courses", False)

    if github or employment:
        if footprint == "strong":
            score = 5
        else:
            score = 4
    elif footprint == "weak" and only_sells:
        score = 2
    elif footprint == "strong":
        score = 4
    elif footprint == "medium":
        score = 3
    else:
        score = 1

    reasons = []
    if footprint == "weak" and only_sells:
        reasons.append(Reason("red", "Weak Footprint: Creator has no notable independent professional achievements."))
    elif github or employment:
        reasons.append(Reason("green", "Credible Creator: Active GitHub or professional employment."))

    return score, reasons


def score_alt_content(free_alt: dict[str, Any]) -> tuple[int, list[Reason]]:
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

    score = max(1, min(5, score))

    return score, []


def score_alt_creator(free_alt: dict[str, Any]) -> tuple[int, list[Reason]]:
    """Scores alternative creators' credibility from 1 to 5.

    Design: Rates alternative sources based on structural quality.
    """
    items = free_alt.get("items", [])
    if not items:
        return 1, []

    any_content_farm = any(item.get("content_farm_flag", False) for item in items)
    high_extraction_cost = any(item.get("extraction_cost") == "high" for item in items)

    if any_content_farm:
        return 2, []
    if high_extraction_cost:
        return 3, []
    return 5, []


def decide_mode(
    scores: dict[str, int],
    reasons: dict[str, list[Reason]],
) -> tuple[str, list[str], list[str]]:
    """Determines final due diligence mode, red flags, and green flags based on scores and reasons."""
    content_score = scores.get("content_score", 3)
    creator_score = scores.get("creator_score", 1)
    alt_content_score = scores.get("alt_content_score", 1)

    # mode:與現在完全相同的分數判定(不變)
    if content_score == 1:
        mode = "should_not"
    elif content_score >= 3 and creator_score >= 4 and alt_content_score <= content_score:
        mode = "worthy"
    else:
        mode = "need_not"

    # flags:veto 時只取 content 的 red 理由;否則匯集所有理由
    if content_score == 1:
        selected = [r for r in reasons.get("content", []) if r.severity == "red"]
    else:
        selected = [r for rs in reasons.values() for r in rs]

    red_flags = [r.message for r in selected if r.severity == "red"]
    green_flags = [r.message for r in selected if r.severity == "green"]

    return mode, red_flags, green_flags
