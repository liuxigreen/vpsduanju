#!/usr/bin/env python3
"""Regression tests for channel-analysis video window and diagnosis merge."""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import panel_v3  # noqa: E402


def test_recent_videos_returns_latest_15_by_published_at_desc():
    videos = [
        {"video_id": f"v{i:02d}", "published_at": f"2026-06-{i:02d}T00:00:00Z"}
        for i in range(1, 13)
    ] + [
        {"video_id": "missing-date", "published_at": ""},
        {"video_id": "bad-date", "published_at": "not-a-date"},
    ]

    result = panel_v3._recent_videos(videos, limit=15)

    assert [v["video_id"] for v in result] == [
        "v12", "v11", "v10", "v09", "v08", "v07", "v06", "v05", "v04", "v03", "v02", "v01"
    ]


def test_load_diagnosis_entry_merges_latest_archives_and_legacy_by_video_id():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        own = root / "own"
        legacy = root / "legacy"
        own.mkdir()
        legacy.mkdir()

        def write(path: Path, scores: list[dict], avg: float = 0):
            path.write_text(json.dumps({
                "summary": {"avg_score": avg, "needs_optimization": 1, "top_issues": []},
                "channel_llm": {"summary": "latest channel llm"},
                "video_scores": scores,
                "retention_data": {"has_data": True},
            }, ensure_ascii=False), encoding="utf-8")

        write(legacy / "Apocalyptic_Films_latest.json", [
            {"video_id": "legacy-only", "score": 4.0, "scores": {"llm": 4.0}},
            {"video_id": "same", "score": 3.0, "scores": {"llm": 3.0}},
        ], avg=4.0)
        write(own / "Apocalyptic_Films_20260618.json", [
            {"video_id": "archive-only", "score": 5.0, "scores": {"llm": 5.0}},
            {"video_id": "same", "score": 6.0, "scores": {"llm": 6.0}},
        ], avg=5.0)
        write(own / "Apocalyptic_Films_latest.json", [
            {"video_id": "latest-only", "score": 7.0, "scores": {"llm": 7.0}},
            {"video_id": "same", "score": 8.0, "scores": {"llm": 8.0}},
        ], avg=7.0)

        entry = panel_v3._load_diagnosis_entry("Apocalyptic Films", own, legacy)

    scores = {v["video_id"]: v["score"] for v in entry["video_scores"]}
    assert scores == {
        "latest-only": 7.0,
        "same": 8.0,
        "archive-only": 5.0,
        "legacy-only": 4.0,
    }
    assert entry["avg_score"] == 7.0
    assert entry["total_videos"] == 4


if __name__ == "__main__":
    test_recent_videos_returns_latest_15_by_published_at_desc()
    test_load_diagnosis_entry_merges_latest_archives_and_legacy_by_video_id()
    print("ok")
