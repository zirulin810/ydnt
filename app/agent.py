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

"""Workflow definition for the YDNT due diligence agent.

Design: Assembles the ADK 2.0 Workflow DAG using deterministic nodes and LLM agents.
Tracks the complete execution flow from sales page ingestion to the final verdict.
"""

from __future__ import annotations

import os

import google.auth

# Initialize Google Cloud / Vertex AI environment variables
try:
    _, project_id = google.auth.default()
    os.environ["GOOGLE_CLOUD_PROJECT"] = project_id
    os.environ["GOOGLE_CLOUD_LOCATION"] = "global"
    os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "True"
except Exception:
    pass

from google.adk.apps import App
from google.adk.workflow import START, Edge, Workflow

from app.agents_llm import (
    free_alt_score,
    instructor_verify,
    parse_course,
    verdict_agent,
)
from app.nodes import (
    fetch_page_node,
    finalize_verdict,
    insufficient_verdict,
    prepare_free_alt_input,
    rubric_scoring_node,
)

# ---------------------------------------------------------------------------
# Workflow DAG Definition
# ---------------------------------------------------------------------------
root_agent = Workflow(
    name="ydnt_due_diligence",
    edges=[
        # Phase 1: Input ingestion, cleaning, and gate routing
        Edge(from_node=START, to_node=fetch_page_node),
        Edge(from_node=fetch_page_node, to_node=parse_course, route="ok"),
        Edge(
            from_node=fetch_page_node,
            to_node=insufficient_verdict,
            route="insufficient",
        ),
        # Full linear analysis path
        Edge(from_node=parse_course, to_node=instructor_verify),
        Edge(from_node=instructor_verify, to_node=prepare_free_alt_input),
        Edge(from_node=prepare_free_alt_input, to_node=free_alt_score),
        Edge(from_node=free_alt_score, to_node=rubric_scoring_node),
        Edge(from_node=rubric_scoring_node, to_node=verdict_agent),
        Edge(from_node=verdict_agent, to_node=finalize_verdict),
    ],
)

# App instance exposed for agents-cli CLI tools
app = App(
    root_agent=root_agent,
    name="app",
)
