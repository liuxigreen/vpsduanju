#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from datetime import datetime
from pathlib import Path


def _convert_text(text: str, target: str) -> str:
    if target not in {"zh-hk", "zh-tw"}:
        return text
    try:
        import opencc  # type: ignore

        cfg = "s2hk" if target == "zh-hk" else "s2twp"
        return opencc.OpenCC(cfg).convert(text)
    except Exception:
        mapping = {
            "视频": "影片", "后": "後", "里": "裡", "这": "這", "没": "沒", "总": "總", "复": "復", "剧": "劇", "爱": "愛", "云": "雲",
        }
        out = text
        for k, v in mapping.items():
            out = out.replace(k, v)
        if target == "zh-hk":
            out = out.replace("厉害", "犀利").replace("很好看", "好睇")
        return out


def _translate_srt_content(content: str, target: str) -> str:
    lines = content.splitlines()
    out = []
    for line in lines:
        if not line.strip() or line.strip().isdigit() or "-->" in line:
            out.append(line)
        else:
            out.append(_convert_text(line, target))
    return "\n".join(out)


def run_from_manifest(manifest_path: str) -> Path:
    manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    srt_file = None
    files = manifest.get("files", []) if isinstance(manifest.get("files"), list) else []
    for f in files:
        if str(f).lower().endswith(".srt") and Path(f).exists():
            srt_file = Path(f)
            break
    if not srt_file:
        raise FileNotFoundError("manifest files 中未找到可用 srt")

    content = srt_file.read_text(encoding="utf-8", errors="ignore")
    output_dir = Path("output/subtitles")
    output_dir.mkdir(parents=True, exist_ok=True)

    generated = {}
    for target in ["zh-hk", "zh-tw"]:
        converted = _translate_srt_content(content, target)
        out = output_dir / f"{manifest['task_name']}_{manifest['target_region']}_{target}.srt"
        out.write_text(converted, encoding="utf-8")
        generated[target] = str(out)

    result = {
        "manifest": manifest_path,
        "source_subtitle": str(srt_file),
        "generated_subtitles": generated,
        "multi_language_reserved": ["en", "id", "pt", "es", "th", "vi"],
        "voice_api_reserved": True,
        "generated_at": datetime.utcnow().isoformat() + "Z",
    }
    out_meta = output_dir / f"{manifest['task_name']}_{manifest['target_region']}.json"
    out_meta.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return out_meta


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--manifest", required=True)
    args = p.parse_args()
    print(run_from_manifest(args.manifest))


if __name__ == "__main__":
    main()
