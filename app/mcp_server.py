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

"""FastMCP server for YDNT due diligence tools.

Design: Implements the 6 core investigative tools. Supports both live API mode
and a robust cached mock mode. Bifurcates logic into clear mock and live paths.
"""

from __future__ import annotations

import json
import os
import re
from typing import Any

import httpx
from mcp.server.fastmcp import FastMCP

from config import CACHE_DIR, JINA_API_KEY, USE_MOCK, YOUTUBE_API_KEY

mcp = FastMCP("ydnt-tools")


class MockDataMissing(Exception):
    """Raised when mock data or fixture is missing in mock mode."""

    pass


MAX_TRANSCRIPT_CHARS: int = 3000


# ---------------------------------------------------------------------------
# Mock / Cache Helpers
# ---------------------------------------------------------------------------
def get_case_name(query_or_url: str) -> str:
    """Detects the demo case name from a search query or URL keyword.

    Behavior: Under mock mode, this will raise MockDataMissing if the query
    does not match any of the known cases.
    """
    normalized = query_or_url.lower()
    if "andrew" in normalized or "ng" in normalized:
        return "andrew_ng_ml"
    if "fast.ai" in normalized or "fastai" in normalized:
        return "fastai"
    if "automation" in normalized or "agency" in normalized:
        return "ai_automation_agency"
    if "injection" in normalized:
        return "injection_case"
    if "skool" in normalized or "games" in normalized:
        return "skool_games"

    if USE_MOCK:
        raise MockDataMissing(f"No mock case found for query or URL: {query_or_url}")
    return "skool_games"


def load_mock_cache(case_name: str) -> dict:
    """Loads the mock JSON file for a given case name.

    Behavior: Raises MockDataMissing if the mock data file does not exist.
    """
    path = os.path.join(CACHE_DIR, f"{case_name}.json")
    if not os.path.exists(path):
        raise MockDataMissing(f"Mock file not found for case: {case_name}")
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        raise MockDataMissing(
            f"Failed to load mock file for case {case_name}: {e}"
        ) from e


# ---------------------------------------------------------------------------
# Mock Implementations
# ---------------------------------------------------------------------------
def _mock_fetch_sales_page(url_or_case: str) -> str:
    case_name = get_case_name(url_or_case)
    cache = load_mock_cache(case_name)
    val = cache.get("sales_page_raw")
    if not val:
        raise MockDataMissing(
            f"sales_page_raw not found in mock data for case: {case_name}"
        )
    return val


def _mock_search_youtube(query: str) -> list[dict[str, Any]]:
    case_name = get_case_name(query)
    cache = load_mock_cache(case_name)
    val = cache.get("youtube_search")
    if val is None:
        raise MockDataMissing(
            f"youtube_search not found in mock data for case: {case_name}"
        )
    return val


def _mock_get_youtube_transcript(video_id: str) -> str:
    for filename in os.listdir(CACHE_DIR):
        if filename.endswith(".json"):
            path = os.path.join(CACHE_DIR, filename)
            try:
                with open(path, encoding="utf-8") as f:
                    cache = json.load(f)
            except Exception:
                continue
            transcripts = cache.get("transcripts", {})
            if transcripts and video_id in transcripts:
                return transcripts[video_id]
    raise MockDataMissing(
        f"Mock transcript not found in cache for video ID: {video_id}"
    )


def _mock_get_channel_stats(channel_id: str) -> dict[str, Any]:
    for filename in os.listdir(CACHE_DIR):
        if filename.endswith(".json"):
            path = os.path.join(CACHE_DIR, filename)
            try:
                with open(path, encoding="utf-8") as f:
                    cache = json.load(f)
            except Exception:
                continue
            stats = cache.get("channel_stats", {})
            if stats and stats.get("channel_id") == channel_id:
                return stats
    raise MockDataMissing(
        f"Channel stats not found in mock cache for channel ID: {channel_id}"
    )



# ---------------------------------------------------------------------------
# Live Implementations
# ---------------------------------------------------------------------------
def _live_fetch_sales_page(url_or_case: str) -> str:
    if not (url_or_case.startswith("http://") or url_or_case.startswith("https://")):
        raise ValueError(
            f"fetch_sales_page requires a valid HTTP/HTTPS URL in live mode: {url_or_case}"
        )

    jina_api_key = JINA_API_KEY

    def fetch_from_jina(url: str, return_markdown: bool = False) -> str:
        jina_url = f"https://r.jina.ai/{url}"
        headers = {"X-Timeout": "15"}
        if return_markdown:
            headers["X-Return-Format"] = "markdown"
        if jina_api_key:
            headers["Authorization"] = f"Bearer {jina_api_key}"
        response = httpx.get(jina_url, headers=headers, timeout=25.0, follow_redirects=True)
        response.raise_for_status()
        return response.text.strip()

    errors = []
    results = []

    # Attempt 1: Default headers (no format specified)
    try:
        text = fetch_from_jina(url_or_case, return_markdown=False)
        if text:
            results.append(text)
    except Exception as e:
        errors.append(f"Attempt 1 failed: {e}")

    # Fallback condition: Attempt 1 failed or returned result is too short (< 800 characters)
    needs_attempt_2 = (not results) or (len(results[0]) < 800)

    if needs_attempt_2:
        # Attempt 2: X-Return-Format: markdown
        try:
            text = fetch_from_jina(url_or_case, return_markdown=True)
            if text:
                results.append(text)
        except Exception as e:
            errors.append(f"Attempt 2 failed: {e}")

    # Select the best result from the first phase
    best_result = ""
    if results:
        results.sort(key=len, reverse=True)
        best_result = results[0]

    # Detect if the best result is still like a partial page / has loading
    text_lower = best_result.lower() if best_result else ""
    has_loading = any(ind in text_lower for ind in ["loading...", "loading data", "please wait", "citation loading"])
    is_partial = (not best_result) or (len(best_result) < 1200) or has_loading

    if is_partial:
        # Cache-bypass retry attempt
        try:
            import time
            ts = int(time.time())
            sep = "&" if "?" in url_or_case else "?"
            bypass_url = f"{url_or_case}{sep}t={ts}"

            bypass_results = []
            try:
                text_bp = fetch_from_jina(bypass_url, return_markdown=False)
                if text_bp:
                    bypass_results.append(text_bp)
            except Exception as e:
                errors.append(f"Bypass Attempt 1 failed: {e}")

            if (not bypass_results) or (len(bypass_results[0]) < 800):
                try:
                    text_bp_fb = fetch_from_jina(bypass_url, return_markdown=True)
                    if text_bp_fb:
                        bypass_results.append(text_bp_fb)
                except Exception as e:
                    errors.append(f"Bypass Attempt 2 failed: {e}")

            if bypass_results:
                bypass_results.sort(key=len, reverse=True)
                bp_best = bypass_results[0]
                # Compare length to previous best and keep the longer one
                if len(bp_best) > len(best_result):
                    best_result = bp_best
        except Exception as e:
            errors.append(f"Cache-bypass flow failed: {e}")

    if best_result:
        cleaned = re.sub(r"\s+", " ", best_result).strip()
        if cleaned:
            return cleaned

    err_msg = "; ".join(errors) or "Returned empty content from all attempts."
    raise RuntimeError(
        f"Live sales page fetch failed for {url_or_case}: {err_msg}"
    )


def _live_search_youtube(query: str) -> list[dict[str, Any]]:
    if not YOUTUBE_API_KEY:
        raise ValueError("YOUTUBE_API_KEY is not configured for live mode")
    url = "https://www.googleapis.com/youtube/v3/search"
    params = {
        "part": "snippet",
        "q": query,
        "key": YOUTUBE_API_KEY,
        "maxResults": 5,
        "type": "video",
    }
    try:
        resp = httpx.get(url, params=params, timeout=4.0)
        resp.raise_for_status()
        data = resp.json()
        items = data.get("items", [])
        if not items:
            raise ValueError(f"Empty results from YouTube search for query: {query}")
        results = []
        for item in items:
            snippet = item.get("snippet", {})
            video_id = item.get("id", {}).get("videoId")
            if not video_id or not snippet:
                continue
            results.append(
                {
                    "title": snippet.get("title", ""),
                    "video_id": video_id,
                    "channel_title": snippet.get("channelTitle", ""),
                    "channel_id": snippet.get("channelId", ""),
                    "description": snippet.get("description", ""),
                    "url": f"https://www.youtube.com/watch?v={video_id}",
                }
            )
        if not results:
            raise ValueError(
                f"No valid video results parsed from YouTube search for query: {query}"
            )
        return results
    except httpx.HTTPError as e:
        # httpx errors embed the request URL, which carries the API key; never surface it.
        status = getattr(getattr(e, "response", None), "status_code", None)
        detail = f"HTTP {status}" if status else type(e).__name__
        raise RuntimeError(
            f"Live YouTube search failed for query '{query}' ({detail})"
        ) from e
    except Exception as e:
        raise RuntimeError(
            f"Live YouTube search failed for query '{query}': {e}"
        ) from e


def _live_get_youtube_transcript(video_id: str) -> str:
    from youtube_transcript_api import YouTubeTranscriptApi
    try:
        data = YouTubeTranscriptApi().fetch(video_id, languages=["en", "zh-TW", "zh-CN", "zh"])
        parts = []
        for item in data:
            if isinstance(item, dict):
                parts.append(item.get("text", ""))
            else:
                parts.append(getattr(item, "text", ""))
        return " ".join(parts)
    except Exception as e:
        raise RuntimeError(
            f"Failed to fetch YouTube transcript for video {video_id}: {e}"
        ) from e


def _channel_stats_not_found(channel_id: str, reason: str) -> dict[str, Any]:
    return {
        "channel_id": channel_id,
        "found": False,
        "title": "",
        "subscriber_count": None,
        "video_count": None,
        "view_count": None,
        "error": reason,
    }


def _live_get_channel_stats(channel_id: str) -> dict[str, Any]:
    if not YOUTUBE_API_KEY:
        raise ValueError("YOUTUBE_API_KEY is not configured for live mode")

    if not re.fullmatch(r"UC[0-9A-Za-z_-]{22}", channel_id or ""):
        return _channel_stats_not_found(channel_id, "invalid channel_id format")

    url = "https://www.googleapis.com/youtube/v3/channels"
    params = {
        "part": "statistics,snippet",
        "id": channel_id,
        "key": YOUTUBE_API_KEY,
    }
    try:
        resp = httpx.get(url, params=params, timeout=4.0)
        resp.raise_for_status()
        data = resp.json()
        items = data.get("items", [])
        if not items:
            return _channel_stats_not_found(channel_id, "channel not found / empty response")
        item = items[0]
        snippet = item.get("snippet", {})
        statistics = item.get("statistics", {})

        subscriber_count = statistics.get("subscriberCount")
        video_count = statistics.get("videoCount")
        view_count = statistics.get("viewCount")

        if not subscriber_count or not video_count or not view_count:
            return _channel_stats_not_found(channel_id, "missing statistics")

        return {
            "channel_id": channel_id,
            "title": snippet.get("title", ""),
            "subscriber_count": subscriber_count,
            "video_count": video_count,
            "view_count": view_count,
        }
    except httpx.HTTPError as e:
        # httpx errors embed the request URL, which carries the API key; never surface it.
        status = getattr(getattr(e, "response", None), "status_code", None)
        detail = f"HTTP {status}" if status else type(e).__name__
        return _channel_stats_not_found(channel_id, f"fetch error ({detail})")
    except Exception as e:
        return _channel_stats_not_found(channel_id, f"fetch error: {e}")



# ---------------------------------------------------------------------------
# MCP Tools
# ---------------------------------------------------------------------------
@mcp.tool()
def fetch_sales_page(url_or_case: str) -> str:
    """Fetches the raw text content of a course sales page.

    Design: Implements clean mock/live bifurcation.
    """
    if USE_MOCK:
        return _mock_fetch_sales_page(url_or_case)
    return _live_fetch_sales_page(url_or_case)


@mcp.tool()
def search_youtube(query: str) -> list[dict[str, Any]]:
    """Searches YouTube for tutorials and videos covering a specific query."""
    if USE_MOCK:
        return _mock_search_youtube(query)
    return _live_search_youtube(query)


@mcp.tool()
def get_youtube_transcript(video_id: str) -> str:
    """Retrieves the transcript/captions for a specified YouTube video."""
    if USE_MOCK:
        raw_transcript = _mock_get_youtube_transcript(video_id)
    else:
        raw_transcript = _live_get_youtube_transcript(video_id)

    if len(raw_transcript) > MAX_TRANSCRIPT_CHARS:
        return raw_transcript[:MAX_TRANSCRIPT_CHARS] + " [TRUNCATED]"
    return raw_transcript


@mcp.tool()
def get_channel_stats(channel_id: str) -> dict[str, Any]:
    """Retrieves subscriber count and video upload statistics for a channel."""
    if USE_MOCK:
        return _mock_get_channel_stats(channel_id)
    return _live_get_channel_stats(channel_id)

if __name__ == "__main__":
    mcp.run()
