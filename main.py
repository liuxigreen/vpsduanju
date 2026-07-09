#!/usr/bin/env python3
"""duanju content operating system - CLI 入口

已实现:
  proposal / search / conflicts    上架方案生成流程
  title / cover                    单步生成
  upload                           YouTube 上传（走 auth_youtube OAuth）
  panel-v2                         老 Vue2 面板（v3 用 panel_v3.py）
  feishu-bitable                   飞书多维表格日报
  distill                          蒸馏（占位）

已下线（未实现或被替代）:
  analyze-video / subtitle / edit  视频理解/字幕翻译/剪辑（未实现）
  run                              全流程（依赖未实现模块）
  web-panel / analytics / comments / signal / ad-materials
                                   依赖不存在的脚本
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def cmd_title(args):
    from scripts.generate_title import run_from_manifest as title_from_manifest
    print(title_from_manifest(args.manifest))


def cmd_cover(args):
    from scripts.generate_cover import run_from_manifest as cover_from_manifest
    print(cover_from_manifest(args.manifest))


def cmd_upload(args):
    from scripts.upload_youtube import run_from_manifest as upload_from_manifest
    print(upload_from_manifest(args.manifest))


def cmd_distill(args):
    print(f"distill scope={args.scope} (keep connected, not executed before first real video)")


def cmd_panel_v2(args):
    """Panel v2 — 老版面板（Vue3 v3 用 scripts/panel_v3.py serve）"""
    from scripts.panel_v2 import serve as serve_panel_v2
    serve_panel_v2(port=args.port, open_browser=args.open)


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


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="duanju content operating system")
    sp = p.add_subparsers(dest="command", required=True)

    for name, func in [("title", cmd_title), ("cover", cmd_cover), ("upload", cmd_upload)]:
        x = sp.add_parser(name)
        x.add_argument("--manifest", required=True)
        x.set_defaults(func=func)

    a = sp.add_parser("distill")
    a.add_argument("--scope", choices=["weekly", "monthly", "event"], required=True)
    a.set_defaults(func=cmd_distill)

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
