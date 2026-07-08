#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

try:
    import yaml
except ModuleNotFoundError:
    yaml = None

def _load_panel(path: str) -> dict:
    raw = Path(path).read_text(encoding="utf-8")
    if yaml:
        return yaml.safe_load(raw)

    panel = {}
    cur_list_key = None
    for line in raw.splitlines():
        if not line.strip() or line.strip().startswith("#"):
            continue
        if line.lstrip().startswith("-") and cur_list_key:
            panel.setdefault(cur_list_key, []).append(line.split("-", 1)[1].strip())
            continue
        if ":" in line:
            k, v = line.split(":", 1)
            k = k.strip()
            v = v.split("#", 1)[0].strip().strip('"\'')
            if v == "":
                panel[k] = []
                cur_list_key = k
            else:
                panel[k] = v
                cur_list_key = None
    return panel


def cmd_analyze_video(args):
    from scripts.analyze_video import analyze_video
    output = args.output or f"data/drama_analysis/{Path(args.input).stem}.json"
    result = analyze_video(args.input, output, args.preset, args.subtitle, args.ocr_text, args.mode, args.manual_analysis)
    print(json.dumps({"output": output, "highlights": len(result.get("highlights", []))}, ensure_ascii=False))


def cmd_ad_materials(args):
    from scripts.search_ad_materials import collect_ad_materials
    output = args.output or f"data/ad_materials/{args.drama_name}.json"
    result = collect_ad_materials(args.drama_name, output)
    print(json.dumps({"output": output, "title_candidates": len(result.get("title_candidates", []))}, ensure_ascii=False))


def cmd_title(args):
    from scripts.generate_title import run_from_manifest as title_from_manifest
    print(title_from_manifest(args.manifest))


def cmd_cover(args):
    from scripts.generate_cover import run_from_manifest as cover_from_manifest
    print(cover_from_manifest(args.manifest))


def cmd_edit(args):
    from scripts.edit_video import run_from_manifest as edit_from_manifest
    print(edit_from_manifest(args.manifest))


def cmd_subtitle(args):
    from scripts.translate_subtitle import run_from_manifest as subtitle_from_manifest
    print(subtitle_from_manifest(args.manifest))


def cmd_upload(args):
    from scripts.upload_youtube import run_from_manifest as upload_from_manifest
    print(upload_from_manifest(args.manifest))


def cmd_analytics(args):
    from scripts.analyze_analytics import analyze_channel
    print(json.dumps(analyze_channel(args.channel), ensure_ascii=False, indent=2))


def cmd_comments(args):
    from scripts.analyze_comments import analyze_comments
    print(json.dumps(analyze_comments(args.channel, args.video_id), ensure_ascii=False, indent=2))


def cmd_signal(args):
    from scripts.signal_engine import run_signal
    print(json.dumps(run_signal(args.channel), ensure_ascii=False, indent=2))
def cmd_distill(args): print(f"distill scope={args.scope} (keep connected, not executed before first real video)")
def cmd_web_panel(args):
    from scripts.web_panel import serve as serve_web_panel
    serve_web_panel(port=args.port, open_browser=args.open)

def cmd_feishu_bitable(args):
    """飞书多维表格：创建/写入频道日报和视频明细"""
    from scripts.feishu_bitable import run_daily, create_bitable
    if args.create:
        refs = create_bitable()
        print(json.dumps(refs, ensure_ascii=False, indent=2))
    else:
        run_daily()

def cmd_proposal(args):
    """生成完整上架方案（搜索→分析→封面→标题→方案）"""
    from scripts.pre_upload_pipeline import run_pipeline
    proposal_file = run_pipeline(
        drama_name=args.drama,
        region=args.region,
        video_file=args.video,
        skip_search=args.skip_search
    )
    print(proposal_file)

def cmd_search(args):
    """搜索国内素材"""
    from scripts.pre_upload_pipeline import search_drama_materials
    search_drama_materials(args.drama)

def cmd_conflicts(args):
    """分析冲突点"""
    from scripts.pre_upload_pipeline import analyze_with_content_expert
    from scripts.pre_upload_pipeline import DATA_DIR
    import json
    
    raw_file = DATA_DIR / args.drama / "search_raw.json"
    if raw_file.exists():
        search_results = json.loads(raw_file.read_text(encoding="utf-8")).get("results", {})
    else:
        from scripts.pre_upload_pipeline import search_drama_materials
        search_results = search_drama_materials(args.drama)
    
    analysis = analyze_with_content_expert(args.drama, search_results)
    print(f"冲突点: {len(analysis.get('conflicts', []))} 个")
    for cf in analysis.get('conflicts', [])[:5]:
        print(f"  [{cf.get('id')}] EP{cf.get('episode')} {cf.get('type')} 强度{cf.get('hook_intensity')} 爆款{cf.get('viral_score')}")
        print(f"    {cf.get('description')}")



def cmd_panel_v2(args):
    """Panel v2 — 全新控制台（看内容标题 + nvwa规则库）"""
    from scripts.panel_v2 import serve as serve_panel_v2
    serve_panel_v2(port=args.port, open_browser=args.open)


def cmd_run(args):
    from scripts.build_manifest import build_manifest
    from scripts.edit_video import run_from_manifest as edit_from_manifest
    from scripts.generate_cover import run_from_manifest as cover_from_manifest
    from scripts.generate_title import run_from_manifest as title_from_manifest
    from scripts.translate_subtitle import run_from_manifest as subtitle_from_manifest
    from scripts.upload_youtube import run_from_manifest as upload_from_manifest
    panel = _load_panel(args.panel)
    task_name = panel.get("task_name", "demo_drama")
    target_region = panel.get("target_region", "hk")
    manifest_path = Path(panel.get("manifest_output", f"data/manifests/{task_name}_{target_region}.json"))

    files = panel.get("files", [])
    manifest = build_manifest(task_name, args.preset, panel.get("target_channel", "hk_main"), target_region, files)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    mode = panel.get("mode", "semi-auto")
    if mode in ("auto", "semi-auto"):
        title_from_manifest(str(manifest_path))
        cover_from_manifest(str(manifest_path))
        edit_from_manifest(str(manifest_path))
        subtitle_from_manifest(str(manifest_path))

    upload_result = None
    if args.with_upload:
        upload_path = upload_from_manifest(str(manifest_path))
        try:
            upload_result = json.loads(Path(upload_path).read_text(encoding="utf-8"))
        except Exception:
            upload_result = None

    print(manifest_path)
    if args.with_post_analysis:
        video_id = args.video_id
        if not video_id and upload_result:
            video_id = upload_result.get("result", {}).get("video_id")
        print("\n# post-analysis")
        print(f"python main.py analytics --channel {manifest.get('target_channel', 'hk_main')}")
        if video_id:
            print(f"python main.py comments --channel {manifest.get('target_channel', 'hk_main')} --video-id {video_id}")
        else:
            print("# upload 未返回 video_id，请手动填写")
            print(f"python main.py comments --channel {manifest.get('target_channel', 'hk_main')} --video-id <video_id>")
        print(f"python main.py signal --channel {manifest.get('target_channel', 'hk_main')}")
    else:
        print("\n# next steps")
        print(f"python main.py upload --manifest {manifest_path}")
        print(f"python main.py analytics --channel {manifest.get('target_channel', 'hk_main')}")
        print(f"python main.py comments --channel {manifest.get('target_channel', 'hk_main')} --video-id <video_id>")
        print(f"python main.py signal --channel {manifest.get('target_channel', 'hk_main')}")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="duanju content operating system")
    sp = p.add_subparsers(dest="command", required=True)

    a = sp.add_parser("analyze-video")
    a.add_argument("--input", required=True)
    a.add_argument("--output")
    a.add_argument("--preset", default="fast_validation", choices=["fast_validation", "full_rebuild"])
    a.add_argument("--mode", default="frame-first", choices=["manual", "subtitle-first", "frame-first"])
    a.add_argument("--subtitle")
    a.add_argument("--ocr-text")
    a.add_argument("--manual-analysis")
    a.set_defaults(func=cmd_analyze_video)

    a = sp.add_parser("ad-materials")
    a.add_argument("--drama-name", required=True)
    a.add_argument("--output")
    a.set_defaults(func=cmd_ad_materials)

    for name, func in [("title", cmd_title), ("cover", cmd_cover), ("edit", cmd_edit), ("subtitle", cmd_subtitle), ("upload", cmd_upload)]:
        x = sp.add_parser(name)
        x.add_argument("--manifest", required=True)
        x.set_defaults(func=func)

    a = sp.add_parser("analytics")
    a.add_argument("--channel", required=True)
    a.set_defaults(func=cmd_analytics)

    a = sp.add_parser("comments")
    a.add_argument("--channel", required=True)
    a.add_argument("--video-id", required=True)
    a.set_defaults(func=cmd_comments)

    a = sp.add_parser("signal")
    a.add_argument("--channel", required=True)
    a.set_defaults(func=cmd_signal)

    a = sp.add_parser("distill")
    a.add_argument("--scope", choices=["weekly", "monthly", "event"], required=True)
    a.set_defaults(func=cmd_distill)

    a = sp.add_parser("web-panel")
    a.add_argument("--port", type=int, default=8008)
    a.add_argument("--open", action="store_true")
    a.set_defaults(func=cmd_web_panel)

    a = sp.add_parser("panel-v2")
    a.add_argument("--port", type=int, default=8008)
    a.add_argument("--open", action="store_true")
    a.set_defaults(func=cmd_panel_v2)

    a = sp.add_parser("proposal")
    a.add_argument("--drama", required=True, help="短剧名称")
    a.add_argument("--region", default="hk", choices=["hk", "tw", "sg", "en", "mo", "my"])
    a.add_argument("--video", help="原始视频文件路径")
    a.add_argument("--skip-search", action="store_true", help="跳过搜索，使用已有素材")
    a.set_defaults(func=cmd_proposal)

    a = sp.add_parser("search")
    a.add_argument("--drama", required=True, help="短剧名称")
    a.set_defaults(func=cmd_search)

    a = sp.add_parser("conflicts")
    a.add_argument("--drama", required=True, help="短剧名称")
    a.set_defaults(func=cmd_conflicts)

    a = sp.add_parser("run")
    a.add_argument("--panel", required=True)
    a.add_argument("--preset", choices=["fast_validation", "full_rebuild"], required=True)
    a.add_argument("--with-upload", action="store_true", help="pipeline后串联upload")
    a.add_argument("--with-post-analysis", action="store_true", help="pipeline后输出/执行post-analysis命令")
    a.add_argument("--video-id", help="post-analysis时显式指定video_id")
    a.set_defaults(func=cmd_run)

    a = sp.add_parser("feishu-bitable")
    a.add_argument("--create", action="store_true", help="创建新多维表格")
    a.set_defaults(func=cmd_feishu_bitable)

    return p


def main() -> None:
    args = build_parser().parse_args()
    try:
        args.func(args)
    except ModuleNotFoundError as exc:
        missing = getattr(exc, "name", None) or "unknown"
        print(
            f"❌ 缺少依赖模块: {missing}\n"
            f"请先安装依赖后重试（例如: pip install {missing}）。",
            file=sys.stderr,
        )
        raise SystemExit(2) from exc


if __name__ == "__main__":
    main()
