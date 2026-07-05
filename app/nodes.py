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
def fetch_page_node(ctx: Context, node_input: Any) -> Event:
    """Fetches the course sales page raw text and stores it in context.

    Design: Deterministic node that calls fetch_sales_page to fetch page content.
    """
    url_or_case = ""
    if isinstance(node_input, dict):
        url_or_case = node_input.get("url_or_case") or node_input.get("url") or ""
    elif isinstance(node_input, str):
        url_or_case = node_input
    elif hasattr(node_input, "parts") and node_input.parts:
        parts_text = []
        for part in node_input.parts:
            if hasattr(part, "text") and part.text:
                parts_text.append(part.text)
        url_or_case = " ".join(parts_text).strip()
    elif hasattr(node_input, "text") and getattr(node_input, "text"):
        url_or_case = str(node_input.text).strip()

    if not url_or_case:
        url_or_case = ctx.state.get("url_or_case") or ctx.state.get("url") or ""

    if not url_or_case:
        raise ValueError("fetch_page_node requires a valid URL or case name as input.")

    from app.mcp_server import fetch_sales_page

    raw_text = fetch_sales_page(url_or_case)
    ctx.state["sales_page_raw"] = raw_text
    return Event(output=raw_text)


@node
def security_screen(ctx: Context, node_input: Any) -> Event:
    """Screens the sales page raw text for potential prompt injection attempts."""
    raw = ctx.state.get("sales_page_raw", "")
    if not raw:
        if isinstance(node_input, str):
            raw = node_input
        elif isinstance(node_input, dict):
            raw = node_input.get("sales_page_raw", "")

    if not raw:
        raw = ""

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
    return Event(output=ctx.state["sales_page_clean"], state=state_update)


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

    Design: Reconstructed as a thin shell delegating to app/scoring.py.
    """
    profile_raw = ctx.state.get("course_profile", {})
    instructor_raw = ctx.state.get("instructor_evidence", {})
    free_alt_raw = ctx.state.get("free_alternatives", {})
    security_flag = ctx.state.get("security_flag")

    def to_dict(obj: Any) -> dict:
        if hasattr(obj, "model_dump"):
            return obj.model_dump()
        if hasattr(obj, "dict"):
            return obj.dict()
        if isinstance(obj, dict):
            return obj
        return {}

    profile = to_dict(profile_raw)
    instructor = to_dict(instructor_raw)
    free_alt = to_dict(free_alt_raw)

    from app.scoring import (
        decide_mode,
        score_alt_content,
        score_alt_instructor,
        score_content,
        score_instructor,
        score_pricing,
    )

    price_score = score_pricing(profile)
    content_score = score_content(profile, security_flag)
    instructor_score = score_instructor(instructor)
    alt_content_score = score_alt_content(free_alt)
    alt_instructor_score = score_alt_instructor(free_alt)

    scores = {
        "price_score": price_score,
        "content_score": content_score,
        "instructor_score": instructor_score,
        "alt_content_score": alt_content_score,
        "alt_instructor_score": alt_instructor_score,
    }

    mode, red_flags, green_flags = decide_mode(
        scores, profile, instructor, free_alt, security_flag
    )

    best_coverage_pct = free_alt.get("best_coverage_pct", 0)
    free_items = free_alt.get("items", [])
    high_extraction_cost = any(
        item.get("extraction_cost") == "high" for item in free_items
    )

    rubric_result = {
        "mode": mode,
        "red_flags": red_flags,
        "green_flags": green_flags,
        "best_coverage_pct": best_coverage_pct,
        "high_extraction_cost": high_extraction_cost,
        "price_score": price_score,
        "content_score": content_score,
        "instructor_score": instructor_score,
        "alt_content_score": alt_content_score,
        "alt_instructor_score": alt_instructor_score,
    }

    ctx.state["rubric_result"] = rubric_result
    return Event(output=rubric_result)
