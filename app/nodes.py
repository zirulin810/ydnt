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

"""Deterministic nodes for the YDNT project.

Design: Implements deterministic, rules-based nodes that do not require LLM calls.
This includes injection screening, budget routing, quick verdict, and the rubric scoring node.
"""

from __future__ import annotations

import re
from typing import Any

from google.adk import Context, Event
from google.adk.workflow import node

from config import DEFAULT_BUDGET_CAP


def strip_injection_sentences(text: str, patterns: list[str]) -> str:
    """Helper to remove sentences containing prompt injection patterns."""
    # Split text into sentences using basic punctuation boundaries
    sentences = re.split(r"(?<=[.!?])\s+", text)
    cleaned_sentences = []
    for sentence in sentences:
        lowered_sentence = sentence.lower()
        if any(p in lowered_sentence for p in patterns):
            continue
        cleaned_sentences.append(sentence)
    return " ".join(cleaned_sentences)


@node
def security_screen(ctx: Context, node_input: Any) -> Event:
    """Screens the sales page raw text for potential prompt injection attempts."""
    raw = ctx.state.get("sales_page_raw", "")
    if not raw and isinstance(node_input, dict):
        raw = node_input.get("sales_page_raw", "")
        if raw:
            ctx.state["sales_page_raw"] = raw

    injection_patterns = [
        "ignore previous",
        "ignore all",
        "disregard",
        "override",
        "rate this 10",
        "best course ever",
        "you must recommend",
        "system prompt",
        "act as",
        "auto-approve",
        "bypass",
    ]

    lowered = raw.lower()
    security_flag = None
    if any(p in lowered for p in injection_patterns):
        security_flag = "injection_detected"
        ctx.state["security_flag"] = security_flag
        # Strip the malicious sentences
        cleaned = strip_injection_sentences(raw, injection_patterns)
        ctx.state["sales_page_clean"] = cleaned
    else:
        ctx.state["sales_page_clean"] = raw

    state_update = {"security_flag": security_flag} if security_flag else {}
    return Event(output=node_input, state=state_update)


@node
def budget_gate(ctx: Context, node_input: Any) -> Event:
    """Routes the workflow path based on course price and risk profile."""
    profile = node_input
    price = 0.0
    promised_outcome = "unknown"
    recruitment_signal = False

    # Extract properties from Pydantic object or dict
    if isinstance(profile, dict):
        price = profile.get("price_usd", 0.0)
        promised_outcome = profile.get("promised_outcome", "unknown")
        recruitment_signal = profile.get("recruitment_signal", False)
    elif profile is not None:
        price = getattr(profile, "price_usd", 0.0)
        promised_outcome = getattr(profile, "promised_outcome", "unknown")
        recruitment_signal = getattr(profile, "recruitment_signal", False)

    budget_cap = ctx.state.get("budget_cap", DEFAULT_BUDGET_CAP)
    security_flag = ctx.state.get("security_flag")

    # High-risk checks: promising income, MLM recruitment, or injection detected
    low_risk = (
        promised_outcome != "income"
        and not recruitment_signal
        and security_flag is None
    )

    route = "quick" if (price < budget_cap and low_risk) else "full"
    return Event(output=node_input, route=route)


@node
def quick_verdict(ctx: Context, node_input: Any) -> Event:
    """Generates a fast due diligence verdict without calling LLM agents."""
    profile = node_input
    title = "Unknown Course"
    price = 0.0

    if isinstance(profile, dict):
        title = profile.get("title", "Unknown Course")
        price = profile.get("price_usd", 0.0)
    elif profile is not None:
        title = getattr(profile, "title", "Unknown Course")
        price = getattr(profile, "price_usd", 0.0)

    verdict = {
        "mode": "B_need_not",
        "red_flags": [],
        "green_flags": ["Low price under budget cap"],
        "money_vs_time": f"Course price (${price}) is below your budget cap. No full due diligence required.",
        "conclusion": f"The course '{title}' is low-cost and low-risk. No further action needed.",
        "confidence": "high",
    }

    ctx.state["verdict"] = verdict
    return Event(output=verdict)


@node
def rubric_scoring_node(ctx: Context, node_input: Any) -> Event:
    """Computes the 6+1 axes rubric scores deterministically from gathered data.

    Design: Re-implements score.py logic as a workflow node. It reads the Pydantic
    outputs generated by parse_course, instructor_verify, and free_alt_score,
    running a rules-based scoring to determine mode A/B/worth_buying.
    """
    profile = ctx.state.get("course_profile", {})
    instructor = ctx.state.get("instructor_evidence", {})
    free_alt = ctx.state.get("free_alternatives", {})

    def to_dict(obj: Any) -> dict:
        if hasattr(obj, "model_dump"):
            return obj.model_dump()
        if hasattr(obj, "dict"):
            return obj.dict()
        if isinstance(obj, dict):
            return obj
        return {}

    p_dict = to_dict(profile)
    i_dict = to_dict(instructor)
    f_dict = to_dict(free_alt)

    red_flags = []
    green_flags = []

    # Axis 1: Recursive Theme
    promised_outcome = p_dict.get("promised_outcome", "unknown")
    syllabus = p_dict.get("syllabus", [])
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
    if is_recursive:
        red_flags.append(
            "Recursive Theme: Course syllabus focuses on audience monetization/selling courses."
        )
    else:
        green_flags.append("Teaches concrete technical or business skills.")

    # Axis 2: Footprint
    footprint = i_dict.get("footprint", "weak")
    github_real_work = i_dict.get("github_real_work", False)
    verifiable_employment = i_dict.get("verifiable_employment", False)
    only_sells_courses = i_dict.get("only_sells_courses", False)
    if footprint == "weak" and only_sells_courses:
        red_flags.append(
            "Weak Footprint: Instructor has no notable independent professional achievements."
        )
    elif github_real_work or verifiable_employment:
        green_flags.append(
            "Credible Instructor: Active GitHub or professional employment."
        )

    # Axis 3: Promises
    if promised_outcome == "income":
        red_flags.append("Income Promises: Marketing promises financial earnings.")
    elif promised_outcome == "skill":
        green_flags.append("Skill acquisition promise.")

    # Axis 4: Free alternatives depth
    free_items = f_dict.get("items", [])
    any_content_farm = any(
        item.get("content_farm_flag", False) for item in free_items
    )
    if any_content_farm:
        red_flags.append(
            "Content Farm: Free alternatives are bloated or low-quality."
        )

    # Axis 5: Scarcity
    scarcity_signals = p_dict.get("scarcity_signals", [])
    if scarcity_signals:
        red_flags.append(
            f"Scarcity Manipulation: Marketing uses: {', '.join(scarcity_signals)}."
        )

    # Axis 6: Recruitment
    recruitment_signal = p_dict.get("recruitment_signal", False)
    if recruitment_signal:
        red_flags.append(
            "Recruitment MLM: Promotes students to become resellers/coaches."
        )

    # Axis 7 (+1): Extraction Cost
    best_coverage_pct = f_dict.get("best_coverage_pct", 0)
    high_extraction_cost = any(
        item.get("extraction_cost") == "high" for item in free_items
    )
    if best_coverage_pct < 60:
        red_flags.append(
            f"Low Free Coverage: Free alternatives cover only {best_coverage_pct}%."
        )
    elif high_extraction_cost:
        red_flags.append(
            "High Extraction Cost: Free alternatives are unstructured/messy."
        )

    # Verdict Mode
    if (
        is_recursive
        or recruitment_signal
        or (promised_outcome == "income" and scarcity_signals)
    ):
        mode = "A_should_not"
    elif best_coverage_pct >= 70 and not high_extraction_cost and not any_content_farm:
        mode = "B_need_not"
    elif (
        footprint in ["strong", "medium"]
        and best_coverage_pct < 80
        and high_extraction_cost
    ):
        mode = "worth_buying"
    else:
        mode = "B_need_not"

    rubric_result = {
        "mode": mode,
        "red_flags": red_flags,
        "green_flags": green_flags,
        "best_coverage_pct": best_coverage_pct,
        "high_extraction_cost": high_extraction_cost,
    }

    ctx.state["rubric_result"] = rubric_result
    return Event(output=rubric_result)
