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

"""Pydantic data contracts for the YDNT project.

Design: Defines structural data contracts for all inputs, outputs, and intermediate states
used within the agentic workflow. No business logic or dependency on other modules.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class CourseProfile(BaseModel):
    """Profile of the online course extracted from the sales page."""

    title: str = Field(description="The title of the online course.")
    creator: str = Field(
        description="The individual or organization responsible for the course (e.g. instructor, producer, or company/institution owning the course). This is distinct from the hosting platform or marketplace (which goes in platform). For official/institutional courses, the organization is the creator, even if it shares the name with the hosting platform."
    )
    platform: str = Field(
        description="The host platform, e.g., skool, whop, gumroad, udemy, youtube."
    )
    price_usd: float | None = Field(
        default=None,
        description="The price of the course in USD, or null if not found.",
    )
    promised_outcome: Literal["income", "skill", "unknown"] = Field(
        description="The type of outcome promised: making income/money or learning a skill."
    )
    syllabus: list[str] = Field(
        default_factory=list,
        description="The syllabus or list of topics covered in the course.",
    )
    scarcity_signals: list[str] = Field(
        default_factory=list,
        description="Marketing scarcity signals detected, e.g., countdown, limited seats, price-increase.",
    )
    is_pyramid_scheme: bool = Field(
        default=False,
        description="Whether the core value proposition of the course is based on recruiting others, reselling the same course, or building an audience/following just to sell them the exact same money-making program (self-replicating pyramid scheme). Explicitly exclude legitimate skill-based, professional, or certification courses (e.g. yoga teacher training, coding bootcamps, certified professional paths) even if students will teach, consult, or earn money after completing them.",
    )
    is_course_page: bool = Field(
        description="Whether this page is the detail, sales, or enrollment page of a single, specific online course or paid product. Course catalogs, course lists, search results, category pages, platform homepages, 'browse all courses' indices, and other 'non-single-course' pages, as well as news, blogs, login walls, or 404 pages, are False."
    )
    missing_critical_info: list[Literal["creator", "price"]] = Field(
        default_factory=list,
        description="List of missing critical info like 'creator' or 'price' that cannot be found on the page.",
    )


class CreatorEvidence(BaseModel):
    """Evidence about the creator's background and footprint."""

    footprint: Literal["strong", "medium", "weak"] = Field(
        description="The strength of the creator's independent online presence."
    )
    verifiable_track_record: bool = Field(
        description="Whether the creator (individual or organization) has a verifiable real-world professional track record or standing, such as verifiable employment, company ownership, notable work, or reputable institutional status, rather than just selling courses."
    )
    only_sells_courses: bool = Field(
        description="Whether the creator's only verifiable achievement is selling courses."
    )
    evidence_links: list[str] = Field(
        default_factory=list,
        description="Verifiable links proving the creator's footprint/evidence.",
    )


class FreeAlternative(BaseModel):
    """A free alternative source (e.g. YouTube video or playlist)."""

    title: str = Field(description="The title of the free alternative.")
    url: str = Field(description="The URL of the free alternative.")
    coverage_pct: int = Field(
        description="The percentage of the course syllabus covered by this alternative."
    )
    extraction_cost: Literal["low", "medium", "high"] = Field(
        description="The time/effort cost to extract structured knowledge from this alternative."
    )
    content_farm_flag: bool = Field(
        description="Whether this source is flaggeed as a low-quality content farm."
    )


class FreeAlternatives(BaseModel):
    """Collection of free alternatives and aggregate coverage stats."""

    items: list[FreeAlternative] = Field(
        default_factory=list, description="List of free alternative resources."
    )
    best_coverage_pct: int = Field(
        description="The highest coverage percentage among all alternatives."
    )


class Verdict(BaseModel):
    """The final verdict and due diligence report for the course."""

    recommendation: Literal[
        "should_not", "need_not", "situational", "worthy", "insufficient"
    ] = Field(
        description="The final evaluation recommendation: should not buy (should_not), need not buy (need_not), situational (the course has content and is credible, but cost-benefit ratio adjusted by coverage is marginal, so purchase is up to the user to weigh), worthy, or insufficient info."
    )
    red_flags: list[str] = Field(
        default_factory=list,
        description="List of red flags found with associated evidence.",
    )
    green_flags: list[str] = Field(
        default_factory=list,
        description="List of positive indicators found with associated evidence.",
    )
    money_vs_time: str = Field(
        description="Comparison of total cost between buying the course vs compiling free alternatives."
    )
    conclusion: str = Field(
        description="Evidence-based conclusion report summarizing the due diligence."
    )
    confidence: Literal["high", "medium", "low"] = Field(
        description="Confidence level of the verdict."
    )
    free_alternatives: list[FreeAlternative] = Field(
        default_factory=list,
        description="The free alternative resources (with links) surfaced during due diligence.",
    )
