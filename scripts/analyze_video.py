#!/usr/bin/env python3
"""视频分析三模式：manual / subtitle-first / frame-first。"""

from __future__ import annotations

import argparse
import json
import subprocess
import shutil
from datetime import datetime
from pathlib import Path


DEFAULT_META = {"duration_sec": 600.0, "width": 1280, "height": 720, "fps": 25.0}


def _run(cmd: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, check=False)


def probe_video(video_path: str) -> dict:
    if not shutil.which("ffprobe"):
        return DEFAULT_META.copy()
    out = _run([
        "ffprobe", "-v", "error", "-show_entries", "stream=width,height,r_frame_rate:format=duration", "-of", "json", video_path
    ])
    if out.returncode != 0:
        return DEFAULT_META.copy()
    data = json.loads(out.stdout or "{}")
    v = (data.get("streams") or [{}])[0]
    fps_raw = v.get("r_frame_rate", "0/1")
    a, b = fps_raw.split("/")
    fps = (float(a) / float(b)) if float(b) else 0
    return {
        "duration_sec": float(data.get("format", {}).get("duration", 0) or 0),
        "width": int(v.get("width", 0) or 0),
        "height": int(v.get("height", 0) or 0),
        "fps": fps,
    }


def parse_srt_text(srt_path: Path) -> str:
    if not srt_path.exists():
        return ""
    lines = []
    for line in srt_path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if not line or line.isdigit() or "-->" in line:
            continue
        lines.append(line)
    return " ".join(lines)


def extract_frames(video_path: str, output_dir: Path, num_frames: int, limit_sec: float | None) -> list[dict]:
    output_dir.mkdir(parents=True, exist_ok=True)
    meta = probe_video(video_path)
    horizon = min(meta["duration_sec"], limit_sec) if limit_sec else meta["duration_sec"]
    frames = []
    if horizon <= 0:
        return frames
    for i in range(1, num_frames + 1):
        ts = horizon * i / (num_frames + 1)
        p = output_dir / f"frame_{i:02d}_{int(ts)}s.jpg"
        if shutil.which("ffmpeg"):
            _run(["ffmpeg", "-y", "-ss", f"{ts:.2f}", "-i", video_path, "-frames:v", "1", "-q:v", "2", str(p)])
        else:
            p.write_text("ffmpeg_not_available", encoding="utf-8")
        if p.exists():
            frames.append({"timestamp_sec": round(ts, 2), "path": str(p)})
    return frames


def infer_from_text(text: str) -> dict:
    chars = [x for x in ["男主", "女主", "总裁", "妹妹", "丈夫", "前夫"] if x in text] or ["男主", "女主"]
    props = [x for x in ["戒指", "合同", "DNA", "遗嘱", "房产证"] if x in text] or ["合同", "戒指"]
    scenes = [x for x in ["婚礼", "豪宅", "法庭", "医院", "公司"] if x in text] or ["豪宅", "公司"]
    hooks = []
    if any(k in text for k in ["身份", "真相", "曝光"]):
        hooks.append("身份曝光")
    if any(k in text for k in ["复仇", "反击", "打脸"]):
        hooks.append("复仇反转")
    if any(k in text for k in ["离婚", "结婚", "替嫁", "闪婚"]):
        hooks.append("婚恋冲突")
    if not hooks:
        hooks = ["关系反转", "利益冲突"]
    return {"characters": chars, "key_props": props, "key_scenes": scenes, "hooks_and_twists": hooks}


def build_highlights(duration_sec: float, preset: str) -> list[dict]:
    if duration_sec <= 0:
        return []
    max_window = 8 * 60 if preset == "fast_validation" else 15 * 60
    window = min(duration_sec, max_window)
    points = [0.2, 0.5, 0.8]
    reasons = ["冲突", "反转", "高潮"]
    out = []
    for i, p in enumerate(points):
        mid = window * p
        out.append({"id": f"H{i+1}", "start_sec": round(max(0, mid - 40), 2), "end_sec": round(min(duration_sec, mid + 40), 2), "reason": reasons[i]})
    return out


def _build_result(video_path: str, preset: str, text_blob: str, frames: list[dict], meta: dict, mode: str) -> dict:
    e = infer_from_text(text_blob)
    return {
        "video_path": video_path,
        "mode": mode,
        "preset": preset,
        "analyzed_at": datetime.utcnow().isoformat() + "Z",
        "analysis_scope_sec": min(meta["duration_sec"], 1800) if preset == "full_rebuild" else meta["duration_sec"],
        "video_meta": {"duration_sec": round(meta["duration_sec"], 2), "resolution": f"{meta['width']}x{meta['height']}", "fps": round(meta["fps"], 2)},
        "frames": frames,
        "subtitle_excerpt": text_blob[:2000],
        "characters": e["characters"],
        "key_props": e["key_props"],
        "key_scenes": e["key_scenes"],
        "hooks_and_twists": e["hooks_and_twists"],
        "highlights": build_highlights(meta["duration_sec"], preset),
        "suggested_edit_duration_min": [3, 8] if preset == "fast_validation" else [5, 15],
        "frame_first": mode == "frame-first",
    }


def _validate_manual(manual: dict) -> None:
    required = ["characters", "key_props", "key_scenes", "hooks_and_twists", "highlights", "suggested_edit_duration_min"]
    miss = [k for k in required if k not in manual]
    if miss:
        raise ValueError(f"manual analysis 缺少字段: {miss}")


def analyze_video(video_path: str, output_path: str, preset: str = "fast_validation", subtitle_path: str | None = None,
                  ocr_text_path: str | None = None, mode: str = "frame-first", manual_analysis_path: str | None = None) -> dict:
    meta = probe_video(video_path)
    text_blob = ""
    frames: list[dict] = []

    if mode == "manual":
        if not manual_analysis_path:
            raise ValueError("manual 模式需要 --manual-analysis")
        manual = json.loads(Path(manual_analysis_path).read_text(encoding="utf-8"))
        _validate_manual(manual)
        result = {
            "video_path": video_path,
            "mode": "manual",
            "preset": preset,
            "analyzed_at": datetime.utcnow().isoformat() + "Z",
            "video_meta": {"duration_sec": round(meta["duration_sec"], 2), "resolution": f"{meta['width']}x{meta['height']}", "fps": round(meta["fps"], 2)},
            **manual,
            "frame_first": False,
        }
    else:
        if subtitle_path:
            text_blob = parse_srt_text(Path(subtitle_path))
        elif ocr_text_path and Path(ocr_text_path).exists():
            text_blob = Path(ocr_text_path).read_text(encoding="utf-8", errors="ignore")

        if mode == "frame-first":
            stem = Path(video_path).stem
            limit_sec = 1800 if preset == "full_rebuild" else None
            frames = extract_frames(video_path, Path("data/drama_analysis") / f"{stem}_frames", 12 if preset == "full_rebuild" else 8, limit_sec)

        # subtitle-first 在无视频模型条件下直接使用字幕推理
        result = _build_result(video_path, preset, text_blob, frames, meta, mode)

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--input", required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--preset", default="fast_validation", choices=["fast_validation", "full_rebuild"])
    p.add_argument("--mode", default="frame-first", choices=["manual", "subtitle-first", "frame-first"])
    p.add_argument("--subtitle")
    p.add_argument("--ocr-text")
    p.add_argument("--manual-analysis")
    args = p.parse_args()
    r = analyze_video(args.input, args.output, args.preset, args.subtitle, args.ocr_text, args.mode, args.manual_analysis)
    print(json.dumps({"output": args.output, "mode": args.mode, "highlights": len(r.get("highlights", []))}, ensure_ascii=False))


if __name__ == "__main__":
    main()
