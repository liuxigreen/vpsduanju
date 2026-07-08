#!/usr/bin/env python3
"""Regression tests for channel_weekly_snapshot original recent-14 viewCount behavior."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import channel_weekly_snapshot as cws  # noqa: E402


def test_get_video_stats_defaults_to_recent14_viewcount_15():
    calls = []

    def fake_api_get(path, params):
        calls.append((path, dict(params)))
        if path == "/youtube/v3/search":
            return {"items": [{"id": {"videoId": "popular-recent-id"}}]}
        if path == "/youtube/v3/videos":
            return {"items": [{
                "id": "popular-recent-id",
                "snippet": {
                    "title": "Popular recent video",
                    "publishedAt": "2026-07-01T00:00:00Z",
                    "description": "",
                    "thumbnails": {"high": {"url": "thumb"}},
                },
                "statistics": {"viewCount": "1", "likeCount": "2", "commentCount": "3"},
                "contentDetails": {"duration": "PT1M"},
            }]}
        raise AssertionError(path)

    old = cws.api_get
    cws.api_get = fake_api_get
    try:
        videos = cws.get_video_stats("UC_TEST")
    finally:
        cws.api_get = old

    search_params = calls[0][1]
    assert search_params["order"] == "viewCount"
    assert search_params["maxResults"] == "15"
    assert "publishedAfter" in search_params
    assert videos[0]["video_id"] == "popular-recent-id"


def test_build_panel_json_uses_same_videos_sorted_by_date_limit15():
    videos = [
        {"video_id": f"v{i}", "title": f"Video {i}", "published_at": f"2026-06-{i:02d}T00:00:00Z", "views": 1000 + i, "likes": 10, "comments": 1, "thumbnail": ""}
        for i in range(1, 17)
    ]
    report = {
        "channel_stats": {"name": "Test Channel", "channel_id": "UC_TEST", "published_at": "2026-01-01T00:00:00Z", "subscribers": 1, "total_views": 1, "total_videos": 1},
        "videos": videos,
        "growth": {},
        "weekly_growth": {},
    }

    panel = cws.build_panel_json([report])
    recent_ids = [v["video_id"] for v in panel["channel_details"]["Test Channel"]["recent_videos"]]

    assert recent_ids == ["v16", "v15", "v14", "v13", "v12", "v11", "v10", "v9", "v8", "v7", "v6", "v5", "v4", "v3", "v2"]


if __name__ == "__main__":
    test_get_video_stats_defaults_to_recent14_viewcount_15()
    test_build_panel_json_uses_same_videos_sorted_by_date_limit15()
    print("ok")
