#!/usr/bin/env python3
"""Regression tests for yt account cache behavior.

Run with:
  python3 tests/test_yt_accounts_cache.py
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import panel_v3  # noqa: E402


def test_api_yt_accounts_uses_cache_without_network_or_token_refresh():
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        cache = tmp / "yt_accounts_cache.json"
        cache.write_text(json.dumps({
            "updated_at": "2026-07-01T09:35:00Z",
            "accounts": [{
                "slug": "hk",
                "channel_id": "UC_CACHE",
                "channel_title": "Cached Channel",
                "thumbnail": "https://example.com/avatar.jpg",
                "status": "已授权",
                "source": "cache",
            }]
        }, ensure_ascii=False))

        with patch.dict(panel_v3.DATA_PATHS, {"yt_accounts_cache": cache}, clear=False):
            with patch.object(panel_v3.kc, "load_youtube_token", side_effect=AssertionError("should not read token")):
                with patch("urllib.request.urlopen", side_effect=AssertionError("should not call network")):
                    handler = SimpleNamespace()
                    captured = {}

                    def fake_json(_handler, data, status=200, cache_max_age=0):
                        captured["data"] = data
                        captured["status"] = status

                    with patch.object(panel_v3, "_json", fake_json):
                        panel_v3.Handler._api_yt_accounts(handler)

        assert captured["status"] == 200
        assert captured["data"]["accounts"][0]["channel_id"] == "UC_CACHE"
        assert captured["data"]["accounts"][0]["thumbnail"] == "https://example.com/avatar.jpg"


if __name__ == "__main__":
    test_api_yt_accounts_uses_cache_without_network_or_token_refresh()
    print("ok")
