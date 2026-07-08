#!/usr/bin/env python3
"""Refresh cached YouTube account list for the panel.

This script is intentionally lightweight:
- reads non-secret account/registry metadata from local JSON files
- checks/refreshes OAuth access tokens only when expired or near expiry
- refreshes channel avatars with YouTube Data API only when avatar cache is stale
- writes display-only cache to data/own/yt_accounts_cache.json

No access_token, refresh_token, client_secret, or API key is written to cache.
"""
from __future__ import annotations

import json
import sys
import time
import urllib.parse as up
import urllib.request as ur
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import keychain_helper as kc  # noqa: E402
from core.config import get_own_channel_api_key  # noqa: E402

REGISTRY_FILE = ROOT / "data" / "own" / "our_channels.json"
ACCOUNTS_FILE = Path.home() / ".hermes" / "duanju" / "accounts.json"
CACHE_FILE = ROOT / "data" / "own" / "yt_accounts_cache.json"

TOKEN_REFRESH_MARGIN_SECONDS = 600  # 10 minutes
AVATAR_TTL_SECONDS = 7 * 24 * 3600


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def save_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def refresh_token(slug: str, token_data: dict) -> dict | None:
    client = kc.load_google_client()
    if not client:
        return None
    refresh = token_data.get("refresh_token")
    if not refresh:
        return None

    payload = up.urlencode({
        "client_id": client["client_id"],
        "client_secret": client["client_secret"],
        "refresh_token": refresh,
        "grant_type": "refresh_token",
    }).encode()
    req = ur.Request("https://oauth2.googleapis.com/token", data=payload, method="POST")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")

    with ur.urlopen(req, timeout=30) as resp:
        new_token = json.loads(resp.read().decode("utf-8"))
    if "refresh_token" not in new_token:
        new_token["refresh_token"] = refresh
    new_token["expires_at"] = time.time() + new_token.get("expires_in", 3600)
    new_token["refreshed_at"] = utc_now()
    kc.save_youtube_token(slug, new_token)
    return new_token


def token_status(slug: str) -> tuple[str, float | None, bool]:
    """Return (status, expires_at, refreshed)."""
    token = kc.load_youtube_token(slug)
    if not token:
        return "未授权", None, False

    expires_at = float(token.get("expires_at", 0) or 0)
    if expires_at < time.time() + TOKEN_REFRESH_MARGIN_SECONDS:
        try:
            refreshed = refresh_token(slug, token)
            if refreshed:
                return "已授权", float(refreshed.get("expires_at", 0) or 0), True
            return "token过期", expires_at, False
        except Exception:
            return "token过期", expires_at, False
    return "已授权", expires_at, False


def existing_avatar_cache() -> tuple[dict[str, str], float]:
    data = read_json(CACHE_FILE, {})
    if not isinstance(data, dict):
        return {}, 0
    avatar_updated_at = float(data.get("avatar_updated_at_ts", 0) or 0)
    avatars = {}
    for acct in data.get("accounts", []) or []:
        cid = acct.get("channel_id")
        thumb = acct.get("thumbnail")
        if cid and thumb:
            avatars[cid] = thumb
    return avatars, avatar_updated_at


def fetch_avatars(channel_ids: list[str]) -> tuple[dict[str, str], int]:
    api_key = get_own_channel_api_key()
    if not api_key or not channel_ids:
        return {}, 0

    avatars: dict[str, str] = {}
    calls = 0
    for i in range(0, len(channel_ids), 50):
        batch = channel_ids[i:i + 50]
        url = "https://www.googleapis.com/youtube/v3/channels?" + up.urlencode({
            "part": "snippet",
            "id": ",".join(batch),
            "key": api_key,
        })
        with ur.urlopen(ur.Request(url), timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        calls += 1
        for item in data.get("items", []) or []:
            thumbnails = item.get("snippet", {}).get("thumbnails", {})
            thumb = (thumbnails.get("default") or thumbnails.get("medium") or thumbnails.get("high") or {}).get("url", "")
            if thumb:
                avatars[item.get("id", "")] = thumb
    return avatars, calls


def build_accounts() -> tuple[list[dict], dict]:
    registry_data = read_json(REGISTRY_FILE, {})
    accounts = read_json(ACCOUNTS_FILE, {})
    if not isinstance(accounts, dict):
        accounts = {}

    registry_by_id = {}
    for ch in registry_data.get("channels", []) if isinstance(registry_data, dict) else []:
        cid = ch.get("channel_id")
        if cid:
            registry_by_id[cid] = ch

    slug_by_id = {info.get("channel_id", ""): slug for slug, info in accounts.items() if info.get("channel_id")}
    previous_avatars, avatar_updated_at = existing_avatar_cache()
    refresh_avatars = time.time() - avatar_updated_at > AVATAR_TTL_SECONDS

    all_ids = list(registry_by_id.keys())
    for info in accounts.values():
        cid = info.get("channel_id")
        if cid and cid not in all_ids:
            all_ids.append(cid)

    avatar_calls = 0
    avatars = previous_avatars
    if refresh_avatars:
        try:
            fresh, avatar_calls = fetch_avatars(all_ids)
            if fresh:
                avatars = {**previous_avatars, **fresh}
                avatar_updated_at = time.time()
        except Exception as exc:
            print(f"WARN avatar refresh failed: {exc}", file=sys.stderr)

    result: list[dict] = []
    seen_ids = set()
    token_refreshed = 0

    for cid, ch_info in registry_by_id.items():
        slug = slug_by_id.get(cid) or ch_info.get("slug", ch_info.get("market", ""))
        acct = accounts.get(slug, {}) if slug else {}
        status = "未授权"
        expires_at = None
        refreshed = False
        if slug in accounts:
            status, expires_at, refreshed = token_status(slug)
            token_refreshed += 1 if refreshed else 0

        result.append({
            "slug": slug,
            "channel_title": ch_info.get("name", acct.get("channel_title", "")),
            "channel_id": cid,
            "google_email": acct.get("google_email", ""),
            "market": ch_info.get("market", acct.get("market", "")),
            "language": ch_info.get("language_cn", ch_info.get("language", "")),
            "operator": ch_info.get("operator", ""),
            "operator_type": ch_info.get("operator_type", ""),
            "niche": ch_info.get("niche", ""),
            "status": status,
            "token_expires_at": expires_at,
            "thumbnail": avatars.get(cid, ""),
            "source": "registry",
        })
        seen_ids.add(cid)

    for slug, info in accounts.items():
        cid = info.get("channel_id", "")
        if cid in seen_ids:
            continue
        status, expires_at, refreshed = token_status(slug)
        token_refreshed += 1 if refreshed else 0
        result.append({
            "slug": slug,
            "channel_title": info.get("channel_title", ""),
            "channel_id": cid,
            "google_email": info.get("google_email", ""),
            "market": info.get("market", ""),
            "status": status,
            "token_expires_at": expires_at,
            "thumbnail": avatars.get(cid, ""),
            "source": "legacy",
        })

    meta = {
        "token_refreshed": token_refreshed,
        "avatar_calls": avatar_calls,
        "avatar_updated_at_ts": avatar_updated_at,
        "avatar_refreshed": avatar_calls > 0,
    }
    return result, meta


def main() -> None:
    accounts, meta = build_accounts()
    payload = {
        "updated_at": utc_now(),
        "avatar_updated_at_ts": meta["avatar_updated_at_ts"],
        "accounts": accounts,
    }
    save_json(CACHE_FILE, payload)
    print(json.dumps({
        "ok": True,
        "cache": str(CACHE_FILE),
        "accounts": len(accounts),
        **meta,
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
