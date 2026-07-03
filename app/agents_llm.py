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

Design: Defines the four structured LLM agents. Connects tools programmatically using
McpToolset stdio subprocesses to ensure portability across execution environments.
"""

from __future__ import annotations

import json
import os
import sys

from google.adk.agents import LlmAgent
from google.adk.models import Gemini
from google.adk.tools.mcp_tool import McpToolset
from google.adk.tools.mcp_tool.mcp_session_manager import StdioConnectionParams
from google.genai import types
from mcp import StdioServerParameters

from app.schemas import CourseProfile, FreeAlternatives, InstructorEvidence, Verdict
from config import MODEL_JUDGMENT, MODEL_ROUTING

# Centralized retry options for model requests
_RETRY_OPTIONS = types.HttpRetryOptions(attempts=3)

# ---------------------------------------------------------------------------
# MCP Toolset Helper
# ---------------------------------------------------------------------------
_PYTHON_PATH = sys.executable
_SERVER_PATH = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "mcp_server.py")
)


def _create_mcp_toolset(tool_filter: list[str]) -> McpToolset:
    """Helper to instantiate a programmatic McpToolset for the local server.

    Args:
        tool_filter: List of tool names to expose to the LLM.

    Returns:
        An instantiated McpToolset.
    """
    return McpToolset(
        connection_params=StdioConnectionParams(
            server_params=StdioServerParameters(
                command=_PYTHON_PATH,
                args=[_SERVER_PATH],
            )
        ),
        tool_filter=tool_filter,
    )


# ---------------------------------------------------------------------------
# Python Function Tools
# ---------------------------------------------------------------------------
def run_rubric_scoring(
    course_profile_json: str,
    instructor_evidence_json: str,
    free_alternatives_json: str,
) -> dict:
    """Runs the deterministic rubric scoring engine.

    Design: Executes the Level 4 skill script via subprocess to compute score flags.

    Args:
        course_profile_json: JSON string of CourseProfile.
        instructor_evidence_json: JSON string of InstructorEvidence.
        free_alternatives_json: JSON string of FreeAlternatives.

    Returns:
        The verdict JSON output from score.py.
    """
    try:
        import subprocess

        script_path = os.path.abspath(
            os.path.join(
                os.path.dirname(__file__),
                "../.agents/skills/course-rubric/scripts/score.py",
            )
        )
        result = subprocess.run(
            [
                sys.executable,
                script_path,
                course_profile_json,
                instructor_evidence_json,
                free_alternatives_json,
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        return json.loads(result.stdout.strip())
    except Exception as e:
        return {"error": f"Failed to run rubric scoring: {e}"}


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
        "Use the fetch_sales_page tool to get the course page content.\n"
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
    tools=[_create_mcp_toolset(tool_filter=["fetch_sales_page"])],
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
    tools=[
        _create_mcp_toolset(
            tool_filter=[
                "verify_github_user",
                "get_channel_stats",
                "get_youtube_transcript",
                "web_search",
            ]
        )
    ],
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
    tools=[
        _create_mcp_toolset(
            tool_filter=["search_youtube", "get_youtube_transcript"]
        )
    ],
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
        "You MUST call the run_rubric_scoring tool to compute the deterministic rubric results.\n"
        "Provide a structured Verdict recommendation:\n"
        "- A_should_not: Don't buy because seller is deceptive, course is recruitment MLM, or uses fake scarcity.\n"
        "- B_need_not: Don't buy because high-quality free alternatives cover most of it and extraction cost is low.\n"
        "- worth_buying: The free alternatives are messy/high extraction cost, the instructor is highly credible, "
        "and the course offers high value under budget cap.\n"
        "- insufficient: Not enough data to make a recommendation.\n"
        "Support your flags (red/green) with concrete evidence links and details. Contrast money vs. time costs."
    ),
    tools=[run_rubric_scoring],
    output_schema=Verdict,
    output_key="verdict",
)
