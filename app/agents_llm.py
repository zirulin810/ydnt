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

Design: Defines the four structured LLM agents. Tools are directly imported as native Python
functions to avoid process startup overhead and connection timeouts on Windows.
"""

from __future__ import annotations

from google.adk.agents import LlmAgent
from google.adk.models import Gemini
from google.genai import types

from app.mcp_server import (
    get_channel_stats,
    get_youtube_transcript,
    search_youtube,
    verify_github_user,
    web_search,
)
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
        "passed directly to you and extract a structured profile of the course.\n"
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
    tools=[],
    output_schema=CourseProfile,
    output_key="course_profile",
)

# ---------------------------------------------------------------------------
# 2. instructor_verify
# ---------------------------------------------------------------------------
instructor_verify = LlmAgent(
    name="instructor_verify",
    model=Gemini(
        model=MODEL_JUDGMENT,
        retry_options=_RETRY_OPTIONS,
    ),
    instruction=(
        "You are a due diligence investigator. Your task is to verify the online presence, background, "
        "and achievements of the course instructor.\n"
        "Use the provided search tools to investigate:\n"
        "1. Their GitHub footprint using verify_github_user.\n"
        "2. Verifiable employment or company history using web_search.\n"
        "3. Their stats using get_channel_stats or transcripts using get_youtube_transcript.\n"
        "Synthesize your findings and output a structured InstructorEvidence report."
    ),
    tools=[verify_github_user, get_channel_stats, get_youtube_transcript, web_search],
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
        "Use YouTube search tools (search_youtube) to find matching content, evaluate their transcripts/captions "
        "using get_youtube_transcript, and determine:\n"
        "- The coverage percentage of the syllabus\n"
        "- The extraction cost (how structured and high-density the free alternative is. Low cost means structured/well-paced, "
        "high cost means unstructured content farm/bloated noise)\n"
        "- Whether the alternative shows signs of low-quality content farming (AI voiceovers, no real hands-on demo, low value)\n"
        "Compile this into a structured FreeAlternatives list."
    ),
    tools=[search_youtube, get_youtube_transcript],
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
        "You will receive the deterministic rubric scoring result containing 'mode', 'red_flags', and 'green_flags'.\n"
        "Translate this data directly into the final Verdict output. Do not make up flags. Provide a detailed, "
        "professional evidence-based conclusion summarizing the due diligence findings."
    ),
    output_schema=Verdict,
    output_key="verdict",
)
