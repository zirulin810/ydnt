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

"""LlmAgents definitions for the YDNT project.

Design: Defines the four structured LLM agents used in the due diligence pipeline.
All agents use central configurations for models and emit structured Pydantic outputs.
"""

from __future__ import annotations

from google.adk.agents import LlmAgent
from google.adk.models import Gemini
from google.genai import types

from app.schemas import CourseProfile, FreeAlternatives, InstructorEvidence, Verdict
from config import MODEL_JUDGMENT, MODEL_ROUTING

# Centralized retry options for model requests
_RETRY_OPTIONS = types.HttpRetryOptions(attempts=3)

# ---------------------------------------------------------------------------
# 1. parse_course
# ---------------------------------------------------------------------------
parse_course = LlmAgent(
    name="parse_course",
    model=Gemini(
        model=MODEL_ROUTING,
        retry_options=_RETRY_OPTIONS,
    ),
    instruction=(
        "You are an online course analyzer. Your task is to analyze the cleaned text of a course's sales page "
        "and extract a structured profile of the course.\n"
        "Identify:\n"
        "- Title of the course\n"
        "- Instructor/speaker name\n"
        "- Platform it is hosted on (e.g. skool, whop, gumroad, udemy, youtube)\n"
        "- Price in USD (if not explicitly mentioned, estimate or set to 0.0)\n"
        "- Promised outcome (Literal 'income' for promises of making money, 'skill' for learning a skill, or 'unknown')\n"
        "- Syllabus/topics covered\n"
        "- Scarcity signals (e.g. limited seats, countdown timers, price increases)\n"
        "- Recruitment signals (MLM elements, students becoming resellers/coaches for the course itself)\n"
        "Do not invent facts. If information is missing, use default empty lists or values."
    ),
    output_schema=CourseProfile,
    output_key="course_profile",
)

# ---------------------------------------------------------------------------
# 2. instructor_verify
# ---------------------------------------------------------------------------
# Tools will be added in app/agent.py when instantiating/running, or defined here
instructor_verify = LlmAgent(
    name="instructor_verify",
    model=Gemini(
        model=MODEL_JUDGMENT,
        retry_options=_RETRY_OPTIONS,
    ),
    instruction=(
        "You are a due diligence investigator. Your task is to verify the online presence, background, "
        "and achievements of the course instructor.\n"
        "Use search tools to investigate:\n"
        "1. Their GitHub footprint (look for active code repositories, commits, and real developer work).\n"
        "2. Verifiable employment or company history on LinkedIn or news.\n"
        "3. Whether their only notable online presence/achievement is selling online courses.\n"
        "Synthesize your findings and output a structured InstructorEvidence report."
    ),
    output_schema=InstructorEvidence,
    output_key="instructor_evidence",
)

# ---------------------------------------------------------------------------
# 3. free_alt_score
# ---------------------------------------------------------------------------
free_alt_score = LlmAgent(
    name="free_alt_score",
    model=Gemini(
        model=MODEL_JUDGMENT,
        retry_options=_RETRY_OPTIONS,
    ),
    instruction=(
        "You are a resource cataloger. Your task is to find free alternative learning materials (specifically YouTube "
        "videos, channels, or playlists) that cover the course's syllabus.\n"
        "Use YouTube search tools to find matching content, evaluate their transcripts/captions, and determine:\n"
        "- The coverage percentage of the syllabus\n"
        "- The extraction cost (how structured and high-density the free alternative is. Low cost means structured/well-paced, "
        "high cost means unstructured content farm/bloated noise)\n"
        "- Whether the alternative shows signs of low-quality content farming (AI voiceovers, no real hands-on demo, low value)\n"
        "Compile this into a structured FreeAlternatives list."
    ),
    output_schema=FreeAlternatives,
    output_key="free_alternatives",
)

# ---------------------------------------------------------------------------
# 4. verdict_agent
# ---------------------------------------------------------------------------
verdict_agent = LlmAgent(
    name="verdict_agent",
    model=Gemini(
        model=MODEL_JUDGMENT,
        retry_options=_RETRY_OPTIONS,
    ),
    instruction=(
        "You are the final judge of YDNT (You Don't Need This). Your task is to produce the final, evidence-based "
        "due diligence verdict and buying recommendation.\n"
        "Synthesize all evidence gathered so far (CourseProfile, InstructorEvidence, FreeAlternatives) and "
        "the deterministic scoring results from the rubric tool.\n"
        "Provide a structured Verdict recommendation:\n"
        "- A_should_not: Don't buy because seller is deceptive, course is recruitment MLM, or uses fake scarcity.\n"
        "- B_need_not: Don't buy because high-quality free alternatives cover most of it and extraction cost is low.\n"
        "- worth_buying: The free alternatives are messy/high extraction cost, the instructor is highly credible, "
        "and the course offers high value under budget cap.\n"
        "- insufficient: Not enough data to make a recommendation.\n"
        "Support your flags (red/green) with concrete evidence links and details. Contrast money vs. time costs."
    ),
    output_schema=Verdict,
    output_key="verdict",
)
