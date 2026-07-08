#!/usr/bin/env python3
"""
staging → latest 筛选脚本
读取 staging.json，按规则筛选频道，展示结果给用户确认
用户确认后才写入 latest.json

用法：
  python scripts/screen_staging.py              # 展示筛选结果
  python scripts/screen_staging.py --apply      # 确认后写入 latest.json
  python scripts/screen_staging.py --dry-run    # 只展示，不询问
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
DATA_DIR = ROOT / "data" / "competitor_data"
STAGING_FILE = DATA_DIR / "staging.json"
LATEST_FILE = DATA_DIR / "latest.json"

# ═══════════════════════════════════════════════════════════════
#  筛选规则配置（随时可调，不会污染下游数据）
# ═══════════════════════════════════════════════════════════════

SCREENING_RULES = {
    # 基础条件
    "min_videos": 10,                    # 最少视频数
    "min_avg_views": 5000,               # 最低平均播放量
    "min_subscribers": 1000,             # 最低订阅数
    
    # 短剧判断
    "require_drama_tag": True,           # 必须有is_drama标记
    "min_drama_ratio": 0.5,             # 短剧视频占比 ≥ 50%
    
    # 语言地区
    "allowed_languages": ["英文", "西语", "印尼", "葡萄牙", "繁中"],
    "allowed_countries": ["US", "ES", "ID", "PT", "BR", "TW", "MY", "PH", "TH", "VN"],
    
    # 频道名关键词（可选，用于辅助判断）
    "name_keywords": ["drama", "series", "episode", "短剧", "劇場", "劇社", "短片", 
                      "drama pendek", "drama corto", "drama curto", "kurzdrama"],
}

# ═══════════════════════════════════════════════════════════════
#  筛选逻辑
# ═══════════════════════════════════════════════════════════════

def load_json(path: Path) -> list:
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(path: Path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def screen_staging() -> tuple[list, list]:
    """筛选staging.json里的频道，返回 (通过, 不通过)"""
    staging = load_json(STAGING_FILE)
    rules = SCREENING_RULES
    
    passed = []
    rejected = []
    
    for ch in staging:
        reject_reason = None
        
        # 检查基础条件
        if ch.get("video_count", 0) < rules["min_videos"]:
            reject_reason = f"视频数不足 ({ch.get('video_count', 0)} < {rules['min_videos']})"
        
        elif ch.get("avg_views", 0) < rules["min_avg_views"]:
            reject_reason = f"平均播放量不足 ({ch.get('avg_views', 0)} < {rules['min_avg_views']})"
        
        elif ch.get("subscribers", 0) < rules["min_subscribers"]:
            reject_reason = f"订阅数不足 ({ch.get('subscribers', 0)} < {rules['min_subscribers']})"
        
        # 检查短剧标记
        elif rules["require_drama_tag"] and not ch.get("is_drama"):
            reject_reason = "无短剧标记"
        
        # 检查语言地区
        elif ch.get("language") not in rules["allowed_languages"]:
            reject_reason = f"语言不在允许列表: {ch.get('language')}"
        
        elif ch.get("country") not in rules["allowed_countries"]:
            reject_reason = f"地区不在允许列表: {ch.get('country')}"
        
        if reject_reason:
            rejected.append((ch, reject_reason))
        else:
            passed.append(ch)
    
    return passed, rejected


def show_result(passed: list, rejected: list):
    """展示筛选结果"""
    total = len(passed) + len(rejected)
    
    print(f"\n📊 筛选结果报告")
    print(f"━━━━━━━━━━━━━━━━━━")
    print(f"待筛选: {total} 个频道")
    print(f"✅ 通过: {len(passed)} 个频道")
    print(f"❌ 不通过: {len(rejected)} 个频道")
    
    if passed:
        print(f"\n✅ 通过频道:")
        for ch in passed[:15]:
            print(f"  - {ch['name']} ({ch.get('language', '?')}) - 视频:{ch.get('video_count', 0)} - 平均播放:{ch.get('avg_views', 0):,}")
        if len(passed) > 15:
            print(f"  ... +{len(passed) - 15} more")
    
    if rejected:
        print(f"\n❌ 不通过频道:")
        for ch, reason in rejected[:15]:
            print(f"  - {ch['name']} ({ch.get('language', '?')}) - {reason}")
        if len(rejected) > 15:
            print(f"  ... +{len(rejected) - 15} more")


def promote_to_latest(passed: list):
    """写入latest.json（只追加新频道，不覆盖已有）"""
    latest = load_json(LATEST_FILE)
    existing_ids = {ch["channel_id"] for ch in latest}
    
    new_channels = [ch for ch in passed if ch["channel_id"] not in existing_ids]
    
    if not new_channels:
        print(f"\n⚠️ 没有新频道需要写入（所有通过的频道已在 latest.json 中）")
        return 0
    
    latest.extend(new_channels)
    save_json(LATEST_FILE, latest)
    
    print(f"\n✅ 已写入 {len(new_channels)} 个新频道到 latest.json")
    print(f"   latest.json 现有 {len(latest)} 个频道")
    return len(new_channels)


def main():
    import argparse
    parser = argparse.ArgumentParser(description="staging → latest 筛选")
    parser.add_argument("--apply", action="store_true", help="确认后写入 latest.json")
    parser.add_argument("--dry-run", action="store_true", help="只展示，不询问")
    args = parser.parse_args()
    
    # 运行筛选
    passed, rejected = screen_staging()
    show_result(passed, rejected)
    
    if not passed:
        print(f"\n⚠️ 没有频道通过筛选")
        return
    
    # 确认写入
    if args.dry_run:
        print(f"\n（dry-run 模式，不写入）")
        return
    
    if args.apply:
        promote_to_latest(passed)
        return
    
    confirm = input(f"\n确认写入 latest.json? (y/n): ")
    if confirm.lower() == "y":
        promote_to_latest(passed)
    else:
        print("❌ 已取消")


if __name__ == "__main__":
    main()
