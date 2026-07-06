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

from typing import Any

from google.adk import Context, Event
from google.adk.workflow import node


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
        "recommendation": "insufficient",
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
    creator_raw = ctx.state.get("creator_evidence", {})
    free_alt_raw = ctx.state.get("free_alternatives", {})

    def to_dict(obj: Any) -> dict:
        if hasattr(obj, "model_dump"):
            return obj.model_dump()
        if hasattr(obj, "dict"):
            return obj.dict()
        if isinstance(obj, dict):
            return obj
        return {}

    profile = to_dict(profile_raw)
    creator = to_dict(creator_raw)
    free_alt = to_dict(free_alt_raw)

    from app.scoring import (
        decide_recommendation,
        score_alt_content,
        score_alt_creator,
        score_content,
        score_creator,
        score_pricing,
    )

    price_score, price_reasons = score_pricing(profile)
    content_score, content_reasons = score_content(profile)
    creator_score, creator_reasons = score_creator(creator)
    alt_content_score, alt_content_reasons = score_alt_content(free_alt)
    alt_creator_score, alt_creator_reasons = score_alt_creator(free_alt)

    scores = {
        "price_score": price_score,
        "content_score": content_score,
        "creator_score": creator_score,
        "alt_content_score": alt_content_score,
        "alt_creator_score": alt_creator_score,
    }

    reasons = {
        "content": content_reasons,
        "creator": creator_reasons,
        "alt": alt_content_reasons + alt_creator_reasons,
        "pricing": price_reasons,
    }

    best_coverage_pct = free_alt.get("best_coverage_pct", 0)
    recommendation, red_flags, green_flags = decide_recommendation(
        scores, reasons, profile.get("price_usd"), best_coverage_pct
    )

    free_items = free_alt.get("items", [])
    high_extraction_cost = any(
        item.get("extraction_cost") == "high" for item in free_items
    )

    rubric_result = {
        "recommendation": recommendation,
        "red_flags": red_flags,
        "green_flags": green_flags,
        "best_coverage_pct": best_coverage_pct,
        "high_extraction_cost": high_extraction_cost,
        "price_score": price_score,
        "content_score": content_score,
        "creator_score": creator_score,
        "alt_content_score": alt_content_score,
        "alt_creator_score": alt_creator_score,
    }

    ctx.state["rubric_result"] = rubric_result
    return Event(output=rubric_result)


@node
def finalize_verdict(ctx: Context, node_input: Any) -> Event:
    """Deterministically populates the free alternative resource list in the final verdict.

    Design: Ensures URLs are populated directly from verified tool findings to prevent hallucination.
    """
    verdict_raw = ctx.state.get("verdict", {})
    free_alt_raw = ctx.state.get("free_alternatives", {})

    def to_dict(obj: Any) -> dict:
        if hasattr(obj, "model_dump"):
            return obj.model_dump()
        if hasattr(obj, "dict"):
            return obj.dict()
        if isinstance(obj, dict):
            return obj
        return {}

    verdict = to_dict(verdict_raw)
    free_alt = to_dict(free_alt_raw)

    items = free_alt.get("items", [])
    formatted_items = []
    for item in items:
        formatted_items.append(to_dict(item))

    verdict["free_alternatives"] = formatted_items
    ctx.state["verdict"] = verdict

    return Event(output=verdict)


@node(rerun_on_resume=True)
async def triage_course(ctx: Context, node_input: Any):
    """Triage course profile to route non-course pages or resolve missing info via HITL.

    Design: Rejects non-course pages, and queries the user via RequestInput for missing
    critical info (price/creator). Routes to insufficient if user cannot provide them.
    """
    from google.adk.events import RequestInput

    def to_dict(obj: Any) -> dict:
        if hasattr(obj, "model_dump"):
            return obj.model_dump()
        if hasattr(obj, "dict"):
            return obj.dict()
        if isinstance(obj, dict):
            return obj
        return {}

    profile = ctx.state.get("course_profile") or to_dict(node_input)
    profile = to_dict(profile)

    is_course = profile.get("is_course_page", True)
    if not is_course:
        reason = (
            "The page does not appear to be an online course/product page; "
            "course due diligence does not apply."
        )
        ctx.state["insufficient_reason"] = reason
        yield Event(route="insufficient", state={"insufficient_reason": reason})
        return

    missing = profile.get("missing_critical_info", [])
    resolved = {}

    ordered_items = [item for item in ["price", "creator"] if item in missing]

    for item in ordered_items:
        if item not in ctx.resume_inputs:
            if item == "price":
                msg = (
                    "The course price could not be found on the page. Please provide the price in USD "
                    "(a number, or 'free' if it is free; reply 'unknown' if you cannot)."
                )
            else:
                msg = (
                    "The responsible creator/organization could not be found on the page. Please provide "
                    "the creator's name (reply 'unknown' if you cannot)."
                )
            yield RequestInput(interrupt_id=item, message=msg)
            return

        answer = (ctx.resume_inputs.get(item) or {}).get("value", "")
        norm_answer = str(answer).strip().lower()

        cannot_provide = norm_answer in ["", "unknown", "n/a", "none"]
        if item == "creator" and norm_answer == "anonymous":
            cannot_provide = True

        if cannot_provide:
            reason = f"User could not provide the {item}; due diligence cannot proceed without it."
            ctx.state["insufficient_reason"] = reason
            yield Event(route="insufficient", state={"insufficient_reason": reason})
            return

        if item == "price":
            if norm_answer in ["free", "0", "$0"]:
                resolved["price"] = 0.0
            else:
                clean_price = norm_answer.replace("$", "").replace(",", "").strip()
                try:
                    resolved["price"] = float(clean_price)
                except ValueError:
                    reason = "User could not provide the price; due diligence cannot proceed without it."
                    ctx.state["insufficient_reason"] = reason
                    yield Event(route="insufficient", state={"insufficient_reason": reason})
                    return
        elif item == "creator":
            resolved["creator"] = str(answer).strip()

    merged = dict(profile)
    if "price" in resolved:
        merged["price_usd"] = resolved["price"]
    if "creator" in resolved:
        merged["creator"] = resolved["creator"]

    resolved_keys = set(resolved.keys())
    merged["missing_critical_info"] = [m for m in missing if m not in resolved_keys]

    ctx.state["course_profile"] = merged
    yield Event(output=merged, state={"course_profile": merged}, route="ok")
