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

"""Unit tests for the content-based coverage check and its fallback chain."""

from __future__ import annotations

import httpx
import pytest

from app import coverage
from app.mcp_server import get_video_duration_seconds
from app.nodes import verify_coverage
from app.schemas import CoverageAssessment

PROFILE = {"title": "ML Course", "syllabus": ["regression", "neural networks"]}


def _free_alt() -> dict:
    return {
        "items": [
            {
                "title": "Top video",
                "url": "https://www.youtube.com/watch?v=AAAAAAAAAAA",
                "coverage_pct": 80,
                "extraction_cost": "low",
                "content_farm_flag": False,
            },
            {
                "title": "Farm video",
                "url": "https://youtu.be/BBBBBBBBBBB",
                "coverage_pct": 95,
                "extraction_cost": "low",
                "content_farm_flag": True,
            },
            {
                "title": "Second video",
                "url": "https://www.youtube.com/watch?v=CCCCCCCCCCC",
                "coverage_pct": 50,
                "extraction_cost": "medium",
                "content_farm_flag": False,
            },
        ],
        "best_coverage_pct": 95,
    }


def _fail(*args, **kwargs):
    raise RuntimeError("unavailable")


def _returns(pct: int):
    calls = []

    def assess(video_id, prompt_fields):
        calls.append(video_id)
        return CoverageAssessment(coverage_pct=pct, covered_topics=["regression"])

    assess.calls = calls
    return assess


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://www.youtube.com/watch?v=7iic3Zj427M", "7iic3Zj427M"),
        ("https://www.youtube.com/watch?list=PL1&v=7iic3Zj427M", "7iic3Zj427M"),
        ("https://youtu.be/7iic3Zj427M?t=30", "7iic3Zj427M"),
        ("https://www.youtube.com/shorts/7iic3Zj427M", "7iic3Zj427M"),
        ("https://www.youtube.com/playlist?list=PL123", None),
        ("", None),
    ],
)
def test_extract_video_id(url, expected) -> None:
    assert coverage.extract_video_id(url) == expected


def test_sample_window() -> None:
    """Unknown length samples the first minute; short videos are sent whole;
    long videos are sampled from the middle to skip intros."""
    assert coverage.sample_window(None) == (0, 60)
    assert coverage.sample_window(45) is None
    assert coverage.sample_window(60) is None
    assert coverage.sample_window(600) == (270, 330)


def test_video_check_updates_top_non_farm_candidate(monkeypatch) -> None:
    video = _returns(30)
    monkeypatch.setattr(coverage, "assess_from_video", video)
    monkeypatch.setattr(coverage, "assess_from_transcript", _fail)

    updated, record = coverage.check_top_alternative(PROFILE, _free_alt())

    assert video.calls == ["AAAAAAAAAAA"]
    top, farm, second = updated["items"]
    assert (top["coverage_pct"], top["coverage_basis"]) == (30, "video")
    assert (farm["coverage_pct"], farm["coverage_basis"]) == (95, "metadata")
    assert second["coverage_basis"] == "metadata"
    assert updated["best_coverage_pct"] == 95
    assert record["basis"] == "video"
    assert record["metadata_coverage_pct"] == 80


def test_falls_back_to_transcript_when_video_fails(monkeypatch) -> None:
    monkeypatch.setattr(coverage, "assess_from_video", _fail)
    monkeypatch.setattr(coverage, "assess_from_transcript", _returns(40))

    free_alt = _free_alt()
    free_alt["items"].pop(1)
    updated, record = coverage.check_top_alternative(PROFILE, free_alt)

    assert updated["items"][0]["coverage_basis"] == "transcript"
    assert updated["best_coverage_pct"] == 50
    assert record["basis"] == "transcript"
    assert record["errors"] == ["video: RuntimeError"]


def test_keeps_metadata_estimate_when_all_checks_fail(monkeypatch) -> None:
    monkeypatch.setattr(coverage, "assess_from_video", _fail)
    monkeypatch.setattr(coverage, "assess_from_transcript", _fail)

    updated, record = coverage.check_top_alternative(PROFILE, _free_alt())

    assert [i["coverage_pct"] for i in updated["items"]] == [80, 95, 50]
    assert {i["coverage_basis"] for i in updated["items"]} == {"metadata"}
    assert updated["best_coverage_pct"] == 95
    assert record["basis"] == "metadata"
    assert len(record["errors"]) == 2


def test_no_video_candidate(monkeypatch) -> None:
    monkeypatch.setattr(coverage, "assess_from_video", _fail)
    free_alt = {
        "items": [
            {
                "title": "Playlist",
                "url": "https://www.youtube.com/playlist?list=PL1",
                "coverage_pct": 60,
                "extraction_cost": "low",
                "content_farm_flag": False,
            }
        ],
        "best_coverage_pct": 60,
    }
    updated, record = coverage.check_top_alternative(PROFILE, free_alt)
    assert record["basis"] == "metadata"
    assert updated["items"][0]["coverage_basis"] == "metadata"


def test_get_video_duration_seconds(monkeypatch) -> None:
    monkeypatch.setattr("app.mcp_server.YOUTUBE_API_KEY", "test-key")

    def mock_get(url, *args, **kwargs):
        return httpx.Response(
            200,
            json={"items": [{"contentDetails": {"duration": "PT1H2M3S"}}]},
            request=httpx.Request("GET", url),
        )

    monkeypatch.setattr(httpx, "get", mock_get)
    assert get_video_duration_seconds("AAAAAAAAAAA") == 3723


def test_get_video_duration_seconds_error(monkeypatch) -> None:
    monkeypatch.setattr("app.mcp_server.YOUTUBE_API_KEY", "test-key")
    monkeypatch.setattr(httpx, "get", _fail)
    assert get_video_duration_seconds("AAAAAAAAAAA") is None


class MockContext:
    def __init__(self, state: dict | None = None) -> None:
        self.state = state or {}


def test_verify_coverage_node(monkeypatch) -> None:
    monkeypatch.setattr(coverage, "assess_from_video", _returns(20))
    ctx = MockContext(
        state={"course_profile": PROFILE, "free_alternatives": _free_alt()}
    )

    event = verify_coverage._func(ctx, None)

    assert ctx.state["coverage_check"]["basis"] == "video"
    assert ctx.state["free_alternatives"]["items"][0]["coverage_pct"] == 20
    assert event.output == ctx.state["coverage_check"]
