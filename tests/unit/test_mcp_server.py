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

"""Unit tests for the MCP server tools, focusing on mock/live boundary isolation."""

from __future__ import annotations

import httpx
import pytest

from app.mcp_server import (
    MockDataMissing,
    fetch_sales_page,
    get_channel_stats,
    get_youtube_transcript,
    search_youtube,
    verify_github_user,
    web_search,
)


# ===========================================================================
# Mock Mode Tests
# ===========================================================================
def test_mock_mode_known_case(monkeypatch) -> None:
    """Verifies that in mock mode, known cases successfully load non-empty sales page content."""
    monkeypatch.setattr("app.mcp_server.USE_MOCK", True)
    sales_page = fetch_sales_page("andrew")
    assert sales_page
    assert isinstance(sales_page, str)
    assert len(sales_page) > 0


def test_mock_mode_unknown_case_raises(monkeypatch) -> None:
    """Verifies that in mock mode, unknown or missing fixture cases raise MockDataMissing."""
    monkeypatch.setattr("app.mcp_server.USE_MOCK", True)
    with pytest.raises(MockDataMissing):
        fetch_sales_page("non_existent_case_keyword_12345")


def test_mock_mode_get_youtube_transcript_missing(monkeypatch) -> None:
    """Verifies that get_youtube_transcript raises MockDataMissing if not found in mock cache."""
    monkeypatch.setattr("app.mcp_server.USE_MOCK", True)
    with pytest.raises(MockDataMissing):
        get_youtube_transcript("non_existent_video_id_9999")


def test_mock_mode_get_channel_stats_missing(monkeypatch) -> None:
    """Verifies that get_channel_stats raises MockDataMissing if not found in mock cache."""
    monkeypatch.setattr("app.mcp_server.USE_MOCK", True)
    with pytest.raises(MockDataMissing):
        get_channel_stats("non_existent_channel_id_9999")


def test_mock_mode_verify_github_user_missing(monkeypatch) -> None:
    """Verifies that verify_github_user raises MockDataMissing if not found in mock cache."""
    monkeypatch.setattr("app.mcp_server.USE_MOCK", True)
    with pytest.raises(MockDataMissing):
        verify_github_user("non_existent_github_handle_9999")


# ===========================================================================
# Live Mode Tests
# ===========================================================================
def test_live_mode_fetch_sales_page_invalid_url(monkeypatch) -> None:
    """Verifies that live fetch_sales_page raises ValueError if input is not a URL."""
    monkeypatch.setattr("app.mcp_server.USE_MOCK", False)
    with pytest.raises(ValueError):
        fetch_sales_page("andrew")


def test_live_mode_fetch_sales_page_http_error(monkeypatch) -> None:
    """Verifies that live fetch_sales_page raises RuntimeError on HTTP failure (500)."""
    monkeypatch.setattr("app.mcp_server.USE_MOCK", False)

    def mock_get(*args, **kwargs):
        return httpx.Response(500, request=httpx.Request("GET", args[0]))

    monkeypatch.setattr(httpx, "get", mock_get)

    with pytest.raises(RuntimeError) as exc_info:
        fetch_sales_page("https://example.com/course")
    assert "failed" in str(exc_info.value).lower()


def test_live_mode_fetch_sales_page_network_exception(monkeypatch) -> None:
    """Verifies that live fetch_sales_page raises RuntimeError on network/request exception."""
    monkeypatch.setattr("app.mcp_server.USE_MOCK", False)

    def mock_get(*args, **kwargs):
        raise httpx.RequestError("Network connection lost")

    monkeypatch.setattr(httpx, "get", mock_get)

    with pytest.raises(RuntimeError):
        fetch_sales_page("https://example.com/course")


def test_live_mode_search_youtube_api_error(monkeypatch) -> None:
    """Verifies that live search_youtube raises RuntimeError on YouTube API error."""
    monkeypatch.setattr("app.mcp_server.USE_MOCK", False)
    monkeypatch.setattr("app.mcp_server.YOUTUBE_API_KEY", "fake_key")

    def mock_get(*args, **kwargs):
        return httpx.Response(500, request=httpx.Request("GET", args[0]))

    monkeypatch.setattr(httpx, "get", mock_get)

    with pytest.raises(RuntimeError):
        search_youtube("andrew")


def test_live_mode_search_youtube_no_api_key(monkeypatch) -> None:
    """Verifies that live search_youtube raises ValueError when API key is missing."""
    monkeypatch.setattr("app.mcp_server.USE_MOCK", False)
    monkeypatch.setattr("app.mcp_server.YOUTUBE_API_KEY", None)
    with pytest.raises(ValueError):
        search_youtube("andrew")


def test_live_mode_get_channel_stats_api_error(monkeypatch) -> None:
    """Verifies that live get_channel_stats raises RuntimeError on YouTube API error."""
    monkeypatch.setattr("app.mcp_server.USE_MOCK", False)
    monkeypatch.setattr("app.mcp_server.YOUTUBE_API_KEY", "fake_key")

    def mock_get(*args, **kwargs):
        return httpx.Response(500, request=httpx.Request("GET", args[0]))

    monkeypatch.setattr(httpx, "get", mock_get)

    with pytest.raises(RuntimeError):
        get_channel_stats("channel_123")


def test_live_mode_get_channel_stats_no_api_key(monkeypatch) -> None:
    """Verifies that live get_channel_stats raises ValueError when API key is missing."""
    monkeypatch.setattr("app.mcp_server.USE_MOCK", False)
    monkeypatch.setattr("app.mcp_server.YOUTUBE_API_KEY", None)
    with pytest.raises(ValueError):
        get_channel_stats("channel_123")


def test_live_mode_verify_github_user_api_error(monkeypatch) -> None:
    """Verifies that live verify_github_user raises RuntimeError on GitHub API error."""
    monkeypatch.setattr("app.mcp_server.USE_MOCK", False)

    def mock_get(*args, **kwargs):
        return httpx.Response(500, request=httpx.Request("GET", args[0]))

    monkeypatch.setattr(httpx, "get", mock_get)

    with pytest.raises(RuntimeError):
        verify_github_user("some_github_handle")


def test_live_mode_not_implemented(monkeypatch) -> None:
    """Verifies that live get_youtube_transcript and web_search raise NotImplementedError."""
    monkeypatch.setattr("app.mcp_server.USE_MOCK", False)

    with pytest.raises(NotImplementedError):
        get_youtube_transcript("video_123")

    with pytest.raises(NotImplementedError):
        web_search("query")
