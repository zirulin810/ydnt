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

from config import CACHE_DIR, GITHUB_TOKEN, USE_MOCK, YOUTUBE_API_KEY

mcp = FastMCP("ydnt-tools")


class MockDataMissing(Exception):
    """Raised when mock data or fixture is missing in mock mode."""

    pass


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


def _mock_verify_github_user(handle: str) -> dict[str, Any]:
    for filename in os.listdir(CACHE_DIR):
        if filename.endswith(".json"):
            path = os.path.join(CACHE_DIR, filename)
            try:
                with open(path, encoding="utf-8") as f:
                    cache = json.load(f)
            except Exception:
                continue
            github_data = cache.get("github_user", {})
            if github_data and github_data.get("handle", "").lower() == handle.lower():
                return github_data
    raise MockDataMissing(f"GitHub user not found in mock cache for handle: {handle}")


def _mock_web_search(query: str) -> list[dict[str, Any]]:
    case_name = get_case_name(query)
    cache = load_mock_cache(case_name)
    val = cache.get("web_search")
    if val is None:
        raise MockDataMissing(
            f"web_search not found in mock data for case: {case_name}"
        )
    return val


# ---------------------------------------------------------------------------
# Live Implementations
# ---------------------------------------------------------------------------
def _live_fetch_sales_page(url_or_case: str) -> str:
    if not (url_or_case.startswith("http://") or url_or_case.startswith("https://")):
        raise ValueError(
            f"fetch_sales_page requires a valid HTTP/HTTPS URL in live mode: {url_or_case}"
        )
    try:
        response = httpx.get(url_or_case, timeout=4.0, follow_redirects=True)
        response.raise_for_status()
        text = response.text
        if not text:
            raise ValueError(f"Empty sales page response from {url_or_case}")
        text = re.sub(r"<[^>]+>", " ", text)
        text = re.sub(r"\s+", " ", text).strip()
        if not text:
            raise ValueError(
                f"Empty text content after parsing HTML from {url_or_case}"
            )
        return text
    except Exception as e:
        raise RuntimeError(
            f"Live sales page fetch failed for {url_or_case}: {e}"
        ) from e


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
    except Exception as e:
        raise RuntimeError(
            f"Live YouTube search failed for query '{query}': {e}"
        ) from e


def _live_get_youtube_transcript(video_id: str) -> str:
    raise NotImplementedError("live mode not implemented yet")


def _live_get_channel_stats(channel_id: str) -> dict[str, Any]:
    if not YOUTUBE_API_KEY:
        raise ValueError("YOUTUBE_API_KEY is not configured for live mode")
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
            raise ValueError(
                f"Channel not found or empty response for channel ID: {channel_id}"
            )
        item = items[0]
        snippet = item.get("snippet", {})
        statistics = item.get("statistics", {})

        subscriber_count = statistics.get("subscriberCount")
        video_count = statistics.get("videoCount")
        view_count = statistics.get("viewCount")

        if not subscriber_count or not video_count or not view_count:
            raise ValueError(
                f"Missing statistical values in YouTube response for channel ID: {channel_id}"
            )

        return {
            "channel_id": channel_id,
            "title": snippet.get("title", ""),
            "subscriber_count": subscriber_count,
            "video_count": video_count,
            "view_count": view_count,
        }
    except Exception as e:
        raise RuntimeError(
            f"Live YouTube channel stats fetch failed for channel ID {channel_id}: {e}"
        ) from e


def _live_verify_github_user(handle: str) -> dict[str, Any]:
    headers = {}
    if GITHUB_TOKEN:
        headers["Authorization"] = f"token {GITHUB_TOKEN}"
    user_url = f"https://api.github.com/users/{handle}"
    try:
        user_resp = httpx.get(user_url, headers=headers, timeout=4.0)
        if user_resp.status_code == 404:
            return {"handle": handle, "exists": False}
        user_resp.raise_for_status()
        user_data = user_resp.json()
        if not user_data:
            raise ValueError(f"Empty user data returned for GitHub handle: {handle}")

        repos_url = (
            f"https://api.github.com/users/{handle}/repos?sort=updated&per_page=5"
        )
        repos_resp = httpx.get(repos_url, headers=headers, timeout=4.0)
        repos_resp.raise_for_status()
        repos = repos_resp.json()
        if not isinstance(repos, list):
            raise ValueError(f"Expected a repository list for GitHub handle: {handle}")

        has_real_work = len(repos) > 0 and any(
            not repo.get("fork", False) and repo.get("stargazers_count", 0) > 2
            for repo in repos
        )
        return {
            "handle": handle,
            "exists": True,
            "public_repos": user_data.get("public_repos", 0),
            "followers": user_data.get("followers", 0),
            "has_real_work": has_real_work,
            "repos": [
                {
                    "name": r.get("name"),
                    "stars": r.get("stargazers_count"),
                    "fork": r.get("fork"),
                }
                for r in repos
            ],
        }
    except Exception as e:
        raise RuntimeError(
            f"Live GitHub user verification failed for handle {handle}: {e}"
        ) from e


def _live_web_search(query: str) -> list[dict[str, Any]]:
    raise NotImplementedError("live mode not implemented yet")


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
        return _mock_get_youtube_transcript(video_id)
    return _live_get_youtube_transcript(video_id)


@mcp.tool()
def get_channel_stats(channel_id: str) -> dict[str, Any]:
    """Retrieves subscriber count and video upload statistics for a channel."""
    if USE_MOCK:
        return _mock_get_channel_stats(channel_id)
    return _live_get_channel_stats(channel_id)


@mcp.tool()
def verify_github_user(handle: str) -> dict[str, Any]:
    """Verifies a user's GitHub activity, repositories, and real work."""
    if USE_MOCK:
        return _mock_verify_github_user(handle)
    return _live_verify_github_user(handle)


@mcp.tool()
def web_search(query: str) -> list[dict[str, Any]]:
    """Performs a web search for credentials, company affiliations, and reviews."""
    if USE_MOCK:
        return _mock_web_search(query)
    return _live_web_search(query)


if __name__ == "__main__":
    mcp.run()
