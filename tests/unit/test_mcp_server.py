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


# ===========================================================================
# Live Mode Tests
# ===========================================================================
def test_live_mode_fetch_sales_page_invalid_url(monkeypatch) -> None:
    """Verifies that live fetch_sales_page raises ValueError if input is not a URL."""
    monkeypatch.setattr("app.mcp_server.USE_MOCK", False)
    with pytest.raises(ValueError):
        fetch_sales_page("andrew")


def test_live_mode_fetch_sales_page_http_error(monkeypatch) -> None:
    """Verifies that live fetch_sales_page raises RuntimeError on HTTP failure (500) from both attempts."""
    monkeypatch.setattr("app.mcp_server.USE_MOCK", False)

    def mock_get(*args, **kwargs):
        return httpx.Response(500, request=httpx.Request("GET", args[0]))

    monkeypatch.setattr(httpx, "get", mock_get)

    with pytest.raises(RuntimeError) as exc_info:
        fetch_sales_page("https://example.com/course")
    assert "failed" in str(exc_info.value).lower()


def test_live_mode_fetch_sales_page_network_exception(monkeypatch) -> None:
    """Verifies that live fetch_sales_page raises RuntimeError on network/request exceptions from both attempts."""
    monkeypatch.setattr("app.mcp_server.USE_MOCK", False)

    def mock_get(*args, **kwargs):
        raise httpx.RequestError("Network connection lost")

    monkeypatch.setattr(httpx, "get", mock_get)

    with pytest.raises(RuntimeError):
        fetch_sales_page("https://example.com/course")


def test_live_mode_fetch_sales_page_fallback_longer(monkeypatch) -> None:
    """Verifies that live fetch_sales_page falls back to Attempt 2 when Attempt 1 result is too short,

    and returns the longer of the two results.
    """
    monkeypatch.setattr("app.mcp_server.USE_MOCK", False)

    call_count = 0

    def mock_get(url, *args, **kwargs):
        nonlocal call_count
        call_count += 1
        headers = kwargs.get("headers", {})
        if "X-Return-Format" not in headers:
            # First attempt: short content
            return httpx.Response(
                200, text="Short content " * 5, request=httpx.Request("GET", url)
            )
        else:
            # Second attempt: longer content
            return httpx.Response(
                200,
                text="Longer content markdown format " * 40,
                request=httpx.Request("GET", url),
            )

    monkeypatch.setattr(httpx, "get", mock_get)

    result = fetch_sales_page("https://example.com/course")
    assert call_count == 2
    assert "Longer content markdown format" in result
    assert len(result) > 800


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
    """Verifies that live get_channel_stats returns fallback sentinel dictionary on YouTube API error."""
    monkeypatch.setattr("app.mcp_server.USE_MOCK", False)
    monkeypatch.setattr("app.mcp_server.YOUTUBE_API_KEY", "fake_key")

    def mock_get(*args, **kwargs):
        return httpx.Response(500, request=httpx.Request("GET", args[0]))

    monkeypatch.setattr(httpx, "get", mock_get)

    res = get_channel_stats("UCqUTefVVx0hEzyVdj6bTxAX")
    assert isinstance(res, dict)
    assert res["found"] is False
    assert "error" in res


def test_live_mode_get_channel_stats_malformed_id(monkeypatch) -> None:
    """Verifies that live get_channel_stats validates channel_id format and short-circuits without calling API."""
    monkeypatch.setattr("app.mcp_server.USE_MOCK", False)
    monkeypatch.setattr("app.mcp_server.YOUTUBE_API_KEY", "fake_key")

    def fail_if_called(*args, **kwargs):
        raise AssertionError("httpx.get should not be called for malformed channel_id")

    monkeypatch.setattr(httpx, "get", fail_if_called)

    res = get_channel_stats("UCqUTefVVx0hEzyVdj6bTxA")
    assert isinstance(res, dict)
    assert res["found"] is False
    assert "invalid channel_id format" in res["error"]


def test_live_mode_get_channel_stats_empty_response(monkeypatch) -> None:
    """Verifies that live get_channel_stats handles empty items response gracefully."""
    monkeypatch.setattr("app.mcp_server.USE_MOCK", False)
    monkeypatch.setattr("app.mcp_server.YOUTUBE_API_KEY", "fake_key")

    def mock_get(*args, **kwargs):
        return httpx.Response(
            200, json={"items": []}, request=httpx.Request("GET", args[0])
        )

    monkeypatch.setattr(httpx, "get", mock_get)

    res = get_channel_stats("UCqUTefVVx0hEzyVdj6bTxAX")
    assert isinstance(res, dict)
    assert res["found"] is False
    assert "channel not found" in res["error"]


def test_live_mode_get_channel_stats_no_api_key(monkeypatch) -> None:
    """Verifies that live get_channel_stats raises ValueError when API key is missing."""
    monkeypatch.setattr("app.mcp_server.USE_MOCK", False)
    monkeypatch.setattr("app.mcp_server.YOUTUBE_API_KEY", None)
    with pytest.raises(ValueError):
        get_channel_stats("channel_123")


def test_live_mode_get_youtube_transcript_success(monkeypatch) -> None:
    """Verifies that live get_youtube_transcript fetches and concatenates transcript snippets."""
    monkeypatch.setattr("app.mcp_server.USE_MOCK", False)

    class MockYouTubeTranscriptApi:
        def fetch(self, video_id, languages=None, preserve_formatting=False):
            return [
                {"text": "Hello world", "start": 0.0, "duration": 1.0},
                {"text": "This is a transcript", "start": 1.0, "duration": 2.0},
            ]

    import youtube_transcript_api

    monkeypatch.setattr(
        youtube_transcript_api, "YouTubeTranscriptApi", MockYouTubeTranscriptApi
    )

    text = get_youtube_transcript("video_123")
    assert text == "Hello world This is a transcript"


def test_live_mode_get_youtube_transcript_failure(monkeypatch) -> None:
    """Verifies that live get_youtube_transcript raises RuntimeError on fetch exception."""
    monkeypatch.setattr("app.mcp_server.USE_MOCK", False)

    class MockYouTubeTranscriptApi:
        def fetch(self, video_id, languages=None, preserve_formatting=False):
            raise Exception("Transcript disabled")

    import youtube_transcript_api

    monkeypatch.setattr(
        youtube_transcript_api, "YouTubeTranscriptApi", MockYouTubeTranscriptApi
    )

    with pytest.raises(RuntimeError):
        get_youtube_transcript("video_123")


def test_get_youtube_transcript_truncation(monkeypatch) -> None:
    """Verifies that get_youtube_transcript truncates outputs exceeding MAX_TRANSCRIPT_CHARS."""
    monkeypatch.setattr("app.mcp_server.USE_MOCK", True)

    long_str = "A" * 4000
    monkeypatch.setattr(
        "app.mcp_server._mock_get_youtube_transcript", lambda vid: long_str
    )

    from app.mcp_server import MAX_TRANSCRIPT_CHARS

    result = get_youtube_transcript("video_123")
    assert len(result) <= MAX_TRANSCRIPT_CHARS + len(" [TRUNCATED]")
    assert result.endswith("[TRUNCATED]")
    assert result.startswith("A" * MAX_TRANSCRIPT_CHARS)


def test_live_mode_fetch_sales_page_headers_x_timeout(monkeypatch) -> None:
    """Verifies that the GET request to Jina Reader includes the X-Timeout: 15 header."""
    monkeypatch.setattr("app.mcp_server.USE_MOCK", False)

    headers_captured = []

    def mock_get(url, *args, **kwargs):
        headers = kwargs.get("headers", {})
        headers_captured.append(headers)
        return httpx.Response(200, text="A" * 1500, request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx, "get", mock_get)

    _ = fetch_sales_page("https://example.com/course")
    assert len(headers_captured) >= 1
    assert headers_captured[0].get("X-Timeout") == "15"


def test_live_mode_fetch_sales_page_cache_bypass_retry(monkeypatch) -> None:
    """Verifies the safety net: if initial fetches return loading screen/short text,

    it triggers a cache-bypass retry with a timestamp parameter and returns the full result.
    """
    monkeypatch.setattr("app.mcp_server.USE_MOCK", False)

    requests_captured = []

    def mock_get(url, *args, **kwargs):
        requests_captured.append((url, kwargs.get("headers", {})))
        headers = kwargs.get("headers", {})

        # Check if the URL has cache bypass query parameter "t="
        if "t=" in url:
            # Bypass request: returns the full course page
            return httpx.Response(
                200,
                text="Complete course content! " * 80,
                request=httpx.Request("GET", url),
            )

        # Initial request: returns a "loading" / short text
        if "X-Return-Format" not in headers:
            return httpx.Response(
                200, text="Loading... please wait.", request=httpx.Request("GET", url)
            )
        else:
            return httpx.Response(
                200, text="Short fallback text", request=httpx.Request("GET", url)
            )

    monkeypatch.setattr(httpx, "get", mock_get)

    result = fetch_sales_page("https://example.com/course")

    # We expect 3 requests total:
    # 1. Initial default: returns "Loading... please wait."
    # 2. Initial markdown fallback: returns "Short fallback text"
    # 3. Cache-bypassed default (since initial results were < 1200 and had "Loading"): returns full text
    assert len(requests_captured) >= 3

    bypass_url, bypass_headers = requests_captured[-1]
    assert "t=" in bypass_url
    assert bypass_headers.get("X-Timeout") == "15"

    assert "Complete course content!" in result
