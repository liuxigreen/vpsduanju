#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from scripts.skill_router import get_skill_context, build_prompt_with_skill


def _load(path: Path, default=None):
    if default is None:
        default = {}
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def _safe_channel_alias(name: str) -> str:
    return "hk" if "hk" in name.lower() else "us"


def upload_video_real(payload: dict) -> dict:
    from googleapiclient.discovery import build  # type: ignore
    from googleapiclient.http import MediaFileUpload  # type: ignore

    from scripts.auth_youtube import get_credentials

    channel_alias = _safe_channel_alias(payload.get("target_channel", "hk"))
    creds = get_credentials(channel_alias)
    youtube = build("youtube", "v3", credentials=creds)

    body = {
        "snippet": {
            "title": payload["title"],
            "description": payload.get("description", ""),
            "tags": payload.get("tags", []),
            "categoryId": payload.get("category_id", "24"),
        },
        "status": {
            "privacyStatus": payload.get("privacy", "private"),
            "selfDeclaredMadeForKids": False,
        },
    }
    if payload.get("schedule"):
        body["status"]["publishAt"] = payload["schedule"]
        body["status"]["privacyStatus"] = "private"

    req = youtube.videos().insert(
        part="snippet,status",
        body=body,
        media_body=MediaFileUpload(payload["video_file"], resumable=True),
    )

    resp = None
    while resp is None:
        _, resp = req.next_chunk()

    video_id = resp["id"]
    if payload.get("thumbnail") and Path(payload["thumbnail"]).exists():
        youtube.thumbnails().set(videoId=video_id, media_body=MediaFileUpload(payload["thumbnail"])).execute()

    # 字幕上传占位（保留路径）
    subtitle_path = payload.get("subtitle")
    subtitle_status = "reserved"
    if subtitle_path and Path(subtitle_path).exists():
        subtitle_status = "ready_to_upload_manual_or_api"

    return {
        "upload_status": "uploaded",
        "video_id": video_id,
        "url": f"https://www.youtube.com/watch?v={video_id}",
        "subtitle_status": subtitle_status,
    }


def build_payload_from_manifest(manifest: dict) -> dict:
    task = manifest["task_name"]
    region = manifest["target_region"]

    title_json = _load(Path(f"output/titles/{task}_{region}.json"), {})
    cover_json = _load(Path(f"output/covers/{task}_{region}.json"), {})
    edit_json = _load(Path(f"output/edits/{task}_{region}.json"), {})
    sub_json = _load(Path(f"output/subtitles/{task}_{region}.json"), {})

    best_title = (title_json.get("title_candidates") or [{"title": task}])[0]["title"]
    best_cover = (cover_json.get("cover_candidates") or [{}])[0]
    video_file = edit_json.get("output_video")
    subtitle_file = None
    if sub_json.get("generated_subtitles"):
        subtitle_file = sub_json["generated_subtitles"].get("zh-hk") or next(iter(sub_json["generated_subtitles"].values()))

    return {
        "target_channel": manifest.get("target_channel", "hk_main"),
        "video_file": video_file,
        "title": best_title,
        "description": f"{best_title}\n\n短劇,短劇合集,YouTube短劇,微短劇,Full Episodes,#短劇 #港劇",
        "tags": ["短劇", "港劇", "繁體中文字幕", manifest.get("preset", "")],
        "thumbnail": best_cover.get("image_path"),  # 目前为 prompt 结果，预留
        "subtitle": subtitle_file,
        "schedule": manifest.get("schedule"),
        "privacy": manifest.get("privacy", "private"),
    }




def _writeback_manifest(manifest_path: str, result: dict) -> None:
    mpath = Path(manifest_path)
    if not mpath.exists():
        return
    try:
        manifest = json.loads(mpath.read_text(encoding="utf-8"))
    except Exception:
        return
    upload_status = result.get("upload_status", "unknown")
    manifest["upload_status"] = upload_status
    if result.get("video_id"):
        manifest["last_video_id"] = result["video_id"]
        manifest["last_uploaded_at"] = datetime.utcnow().isoformat() + "Z"
    mpath.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
def run_from_manifest(manifest_path: str) -> Path:
    manifest = _load(Path(manifest_path), {})
    payload = build_payload_from_manifest(manifest)

    fallback = None
    result: dict[str, Any]
    try:
        if not payload.get("video_file") or not Path(payload["video_file"]).exists():
            raise FileNotFoundError("edited video not found")
        result = upload_video_real(payload)
    except Exception as e:
        fallback = str(e)
        result = {"upload_status": "stub_pending_manual_auth", "reason": fallback}

    _writeback_manifest(manifest_path, result)
    out = {
        "manifest": manifest_path,
        "payload": payload,
        "result": result,
        "video_id": result.get("video_id"),
        "updated_at": datetime.utcnow().isoformat() + "Z",
    }
    out_path = Path(f"output/upload/{manifest['task_name']}_{manifest['target_region']}.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    return out_path


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--manifest", required=True)
    args = p.parse_args()
    print(run_from_manifest(args.manifest))


if __name__ == "__main__":
    main()
