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

"""Unit tests for the Phase 1 pipeline nodes: fetch_page_node and insufficient_verdict."""

from __future__ import annotations

from app.nodes import fetch_page_node, insufficient_verdict


class MockContext:
    """Mock context object to simulate workflow execution environment."""

    def __init__(self, state: dict | None = None) -> None:
        self.state = state or {}


def test_fetch_page_node_mock(monkeypatch) -> None:
    """Tests fetch_page_node in mock mode with a known case."""
    monkeypatch.setattr("app.mcp_server.USE_MOCK", True)
    ctx = MockContext()

    event = fetch_page_node._func(ctx, "andrew")

    assert ctx.state["sales_page_raw"]
    assert isinstance(ctx.state["sales_page_raw"], str)
    assert event.output == ctx.state["sales_page_raw"]
    assert event.actions.route == "ok"


def test_fetch_page_node_failure(monkeypatch) -> None:
    """Tests fetch_page_node in mock mode with an unknown case, triggering failure routing."""
    monkeypatch.setattr("app.mcp_server.USE_MOCK", True)
    ctx = MockContext()

    event = fetch_page_node._func(ctx, "non_existent_case_keyword_12345")

    assert event.actions.route == "insufficient"
    assert ctx.state["insufficient_reason"]
    assert "No mock case found" in ctx.state["insufficient_reason"]


def test_insufficient_verdict_node() -> None:
    """Tests insufficient_verdict node outputs correct schema structures without fabricated scores."""
    ctx = MockContext(state={"insufficient_reason": "Mock fetch error details"})

    event = insufficient_verdict._func(ctx, None)
    output = event.output

    assert output["mode"] == "insufficient"
    assert output["red_flags"] == []
    assert output["green_flags"] == []
    assert "Mock fetch error details" in output["conclusion"]
    assert "Mock fetch error details" in output["money_vs_time"]
    assert output["confidence"] == "low"
    assert ctx.state["verdict"] == output


def test_prepare_free_alt_input_success() -> None:
    """Tests prepare_free_alt_input node with valid title and syllabus."""
    from app.nodes import prepare_free_alt_input

    ctx = MockContext(
        state={
            "course_profile": {
                "title": "Machine Learning Spec",
                "syllabus": ["linear regression", "neural networks"],
            }
        }
    )

    event = prepare_free_alt_input._func(ctx, None)
    output = event.output

    assert "Machine Learning Spec" in output
    assert "linear regression" in output
    assert "neural networks" in output


def test_prepare_free_alt_input_empty() -> None:
    """Tests prepare_free_alt_input node with missing/empty profile info."""
    from app.nodes import prepare_free_alt_input

    ctx = MockContext(state={})

    event = prepare_free_alt_input._func(ctx, None)
    output = event.output

    assert "Unknown Course" in output
    assert "[]" in output
