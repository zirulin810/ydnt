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

Design: Implements the core investigative tools against live APIs
(Jina Reader for sales pages, YouTube Data API, youtube-transcript-api).
"""

from __future__ import annotations

import re
from typing import Any

import httpx
from mcp.server.fastmcp import FastMCP

from app.config import JINA_API_KEY, YOUTUBE_API_KEY

mcp = FastMCP("ydnt-tools")


def _youtube_headers() -> dict[str, str]:
    # Send the key as a header, not a query parameter, so it never appears in
    # request URLs that httpx logs at INFO level or embeds in error messages.
    return {"X-Goog-Api-Key": YOUTUBE_API_KEY or ""}


MAX_TRANSCRIPT_CHARS: int = 3000


# ---------------------------------------------------------------------------
# Implementations
# ---------------------------------------------------------------------------
def _fetch_sales_page(url: str) -> str:
    if not (url.startswith("http://") or url.startswith("https://")):
        raise ValueError(f"fetch_sales_page requires a valid HTTP/HTTPS URL: {url}")

    jina_api_key = JINA_API_KEY

    def fetch_from_jina(url: str, return_markdown: bool = False) -> str:
        jina_url = f"https://r.jina.ai/{url}"
        headers = {"X-Timeout": "15"}
        if return_markdown:
            headers["X-Return-Format"] = "markdown"
        if jina_api_key:
            headers["Authorization"] = f"Bearer {jina_api_key}"
        response = httpx.get(
            jina_url, headers=headers, timeout=25.0, follow_redirects=True
        )
        response.raise_for_status()
        return response.text.strip()

    errors = []
    results = []

    # Attempt 1: Default headers (no format specified)
    try:
        text = fetch_from_jina(url, return_markdown=False)
        if text:
            results.append(text)
    except Exception as e:
        errors.append(f"Attempt 1 failed: {e}")

    # Fallback condition: Attempt 1 failed or returned result is too short (< 800 characters)
    needs_attempt_2 = (not results) or (len(results[0]) < 800)

    if needs_attempt_2:
        # Attempt 2: X-Return-Format: markdown
        try:
            text = fetch_from_jina(url, return_markdown=True)
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
    has_loading = any(
        ind in text_lower
        for ind in ["loading...", "loading data", "please wait", "citation loading"]
    )
    is_partial = (not best_result) or (len(best_result) < 1200) or has_loading

    if is_partial:
        # Cache-bypass retry attempt
        try:
            import time

            ts = int(time.time())
            sep = "&" if "?" in url else "?"
            bypass_url = f"{url}{sep}t={ts}"

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
    raise RuntimeError(f"Sales page fetch failed for {url}: {err_msg}")


def _search_youtube(query: str) -> list[dict[str, Any]]:
    if not YOUTUBE_API_KEY:
        raise ValueError("YOUTUBE_API_KEY is not configured")
    url = "https://www.googleapis.com/youtube/v3/search"
    params = {
        "part": "snippet",
        "q": query,
        "maxResults": 5,
        "type": "video",
    }
    try:
        resp = httpx.get(url, params=params, headers=_youtube_headers(), timeout=4.0)
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
            f"YouTube search failed for query '{query}' ({detail})"
        ) from e
    except Exception as e:
        raise RuntimeError(f"YouTube search failed for query '{query}': {e}") from e


def get_video_duration_seconds(video_id: str) -> int | None:
    """Returns a YouTube video's length in seconds, or None if unavailable."""
    if not YOUTUBE_API_KEY:
        return None
    try:
        resp = httpx.get(
            "https://www.googleapis.com/youtube/v3/videos",
            params={"part": "contentDetails", "id": video_id},
            headers=_youtube_headers(),
            timeout=4.0,
        )
        resp.raise_for_status()
        items = resp.json().get("items", [])
        duration = items[0]["contentDetails"]["duration"] if items else ""
    except Exception:
        # httpx errors embed the request URL, which carries the API key; never surface it.
        return None
    match = re.fullmatch(
        r"P(?:(\d+)D)?T?(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", duration or ""
    )
    if not match or not any(match.groups()):
        return None
    days, hours, minutes, seconds = (int(g or 0) for g in match.groups())
    return ((days * 24 + hours) * 60 + minutes) * 60 + seconds


def _get_youtube_transcript(video_id: str) -> str:
    from youtube_transcript_api import YouTubeTranscriptApi

    try:
        data = YouTubeTranscriptApi().fetch(
            video_id, languages=["en", "zh-TW", "zh-CN", "zh"]
        )
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


def _get_channel_stats(channel_id: str) -> dict[str, Any]:
    if not YOUTUBE_API_KEY:
        raise ValueError("YOUTUBE_API_KEY is not configured")

    if not re.fullmatch(r"UC[0-9A-Za-z_-]{22}", channel_id or ""):
        return _channel_stats_not_found(channel_id, "invalid channel_id format")

    url = "https://www.googleapis.com/youtube/v3/channels"
    params = {
        "part": "statistics,snippet",
        "id": channel_id,
    }
    try:
        resp = httpx.get(url, params=params, headers=_youtube_headers(), timeout=4.0)
        resp.raise_for_status()
        data = resp.json()
        items = data.get("items", [])
        if not items:
            return _channel_stats_not_found(
                channel_id, "channel not found / empty response"
            )
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
def fetch_sales_page(url: str) -> str:
    """Fetches the raw text content of a course sales page."""
    return _fetch_sales_page(url)


@mcp.tool()
def search_youtube(query: str) -> list[dict[str, Any]]:
    """Searches YouTube for tutorials and videos covering a specific query."""
    return _search_youtube(query)


@mcp.tool()
def get_youtube_transcript(video_id: str) -> str:
    """Retrieves the transcript/captions for a specified YouTube video."""
    raw_transcript = _get_youtube_transcript(video_id)

    if len(raw_transcript) > MAX_TRANSCRIPT_CHARS:
        return raw_transcript[:MAX_TRANSCRIPT_CHARS] + " [TRUNCATED]"
    return raw_transcript


@mcp.tool()
def get_channel_stats(channel_id: str) -> dict[str, Any]:
    """Retrieves subscriber count and video upload statistics for a channel."""
    return _get_channel_stats(channel_id)


if __name__ == "__main__":
    mcp.run()
