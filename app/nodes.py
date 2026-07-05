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
    If fetching fails or is missing, routes to insufficient verdict.
    """
    url_or_case = ""
    if isinstance(node_input, dict):
        url_or_case = (
            node_input.get("url_or_case")
            or node_input.get("url")
            or node_input.get("text")
            or ""
        )
    elif isinstance(node_input, str):
        url_or_case = node_input
    elif hasattr(node_input, "parts") and node_input.parts:
        parts_text = []
        for part in node_input.parts:
            if hasattr(part, "text") and part.text:
                parts_text.append(part.text)
        url_or_case = " ".join(parts_text).strip()
    elif hasattr(node_input, "text") and node_input.text:
        url_or_case = str(node_input.text).strip()

    if not url_or_case:
        url_or_case = ctx.state.get("url_or_case") or ctx.state.get("url") or ""

    if not url_or_case:
        ctx.state["insufficient_reason"] = (
            "fetch_page_node requires a valid URL or case name as input."
        )
        return Event(route="insufficient")

    from app.mcp_server import fetch_sales_page

    try:
        raw_text = fetch_sales_page(url_or_case)
        if not raw_text:
            raise ValueError("Sales page content is empty.")
    except Exception as e:
        ctx.state["insufficient_reason"] = str(e)
        return Event(route="insufficient")

    ctx.state["sales_page_raw"] = raw_text
    return Event(output=raw_text, route="ok")


@node
def insufficient_verdict(ctx: Context, node_input: Any) -> Event:
    """Generates an honest 'insufficient' due diligence verdict when the page is unreachable.

    Design: Complies with fail-loud and code integrity rules. Does not invent any scores.
    """
    reason = ctx.state.get("insufficient_reason", "Unknown reason")
    conclusion_text = f"Due diligence could not be performed because the sales page was unreachable: {reason}"
    verdict = {
        "mode": "insufficient",
        "red_flags": [],
        "green_flags": [],
        "money_vs_time": f"Cannot compare time/money since the sales page was unreachable ({reason}).",
        "conclusion": conclusion_text,
        "confidence": "low",
    }
    ctx.state["verdict"] = verdict

    from google.genai import types

    content = types.Content(
        role="model", parts=[types.Part.from_text(text=conclusion_text)]
    )
    return Event(output=verdict, content=content)


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
def prepare_free_alt_input(ctx: Context, node_input: Any) -> Event:
    """Prepares the text prompt input for free_alt_score using course profile details.

    Design: Deterministic node to merge title and syllabus into a unified query string.
    """
    profile_raw = ctx.state.get("course_profile", {})

    def to_dict(obj: Any) -> dict:
        if hasattr(obj, "model_dump"):
            return obj.model_dump()
        if hasattr(obj, "dict"):
            return obj.dict()
        if isinstance(obj, dict):
            return obj
        return {}

    profile = to_dict(profile_raw)
    title = profile.get("title") or "Unknown Course"
    syllabus = profile.get("syllabus") or []

    prompt = (
        f"Find free alternatives for the course '{title}'. The syllabus is: {syllabus}."
    )
    return Event(output=prompt)


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

    price_score, price_reasons = score_pricing(profile)
    content_score, content_reasons = score_content(profile, security_flag)
    instructor_score, instructor_reasons = score_instructor(instructor)
    alt_content_score, alt_content_reasons = score_alt_content(free_alt)
    alt_instructor_score, alt_instructor_reasons = score_alt_instructor(free_alt)

    scores = {
        "price_score": price_score,
        "content_score": content_score,
        "instructor_score": instructor_score,
        "alt_content_score": alt_content_score,
        "alt_instructor_score": alt_instructor_score,
    }

    reasons = {
        "content": content_reasons,
        "instructor": instructor_reasons,
        "alt": alt_content_reasons + alt_instructor_reasons,
        "pricing": price_reasons,
    }

    mode, red_flags, green_flags = decide_mode(scores, reasons)


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
