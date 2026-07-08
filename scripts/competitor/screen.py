# -*- coding: utf-8 -*-
"""竞品筛选模块（v2 - 多信号打分）

staging → latest 筛选脚本
读取 staging.json，按多维度规则筛选频道，展示结果给用户确认
用户确认后才写入 latest.json

用法：
  python -m competitor.screen              # 展示筛选结果
  python -m competitor.screen --apply      # 确认后写入 latest.json
  python -m competitor.screen --dry-run    # 只展示，不询问
  python -m competitor.screen --scan-latest # 扫描 latest.json 中的可疑频道
"""
import json
import re
from pathlib import Path
from collections import Counter

from core.config import STAGING_FILE, LATEST_FILE

# 待审核区文件路径
STAGING_REVIEW_FILE = Path(__file__).parent.parent.parent / "data" / "competitor_data" / "staging_review.json"

# ═══════════════════════════════════════════════════════════════
#  多信号筛选配置
# ═══════════════════════════════════════════════════════════════

# 短剧标题关键词（多语言）
DRAMA_TITLE_KEYWORDS = {
    # 英文
    "ceo", "billionaire", "reborn", "revenge", "secret", "pregnant", "mafia",
    "husband", "wife", "divorce", "wedding", "betray", "rich", "poor",
    "forced marriage", "arranged", "contract marriage", "fake marriage",
    "kicked out", "disowned", "abandoned", "substitute", "stand-in",
    "twin", "look-alike", "identical", "hidden identity", "secret identity",
    "back from the dead", "second chance", "enemies to lovers",
    # 中文
    "总裁", "重生", "复仇", "闪婚", "替身", "豪门", "甜宠", "虐恋",
    "逆袭", "打脸", "装穷", "隐藏身份", "退婚", "穿越", "系统",
    "龙王", "战神", "至尊", "绝世", "神医", "高手", "废物",
    "短剧", "微短剧", "爽剧", "短片",
    # 韩文
    "사장", "회장", "재벌", "복수", "계약", "이혼", "재혼",
    "임신", "숨겨진", "진짜", "가짜",
    # 西语
    "embarazada", "millonario", "venganza", "esposo", "esposa",
    "falso", "casamiento", "abandonada", "heredero",
    "CEO", "triángulo", "engañada",
    # 葡萄牙
    "milionário", "vingança", "grávida", "esposo", "esposa",
    "falso", "casamento", "abandonada", "herdeiro", "triângulo",
    "traição", "enganada", "segredo", "herdeira", "casar",
    # 印尼
    "hamil", "nikah", "pura-pura", "kaya", "miskin",
    "CEO", "cinta", "dendam", "pewaris", "suami", "istri",
    "cerai", "kawin", "janda", "duda", "selingkuh", "ditipu",
    "terungkap", "balas dendam", "anak", "ibu", "ayah",
    # 土耳其
    "milyarder", "CEO", "gizli", "varis", "mirasçı", "zengin", "fakir",
    "evlilik", "evlen", "boşan", "ihanet", "intikam", "aşk", "tutku",
    "kurtar", "kaçır", "hamile", "nikah", "sözleşme", "sahte",
    "kız", "oğlan", "baba", "anne", "gelin", "damat",
    "dizi", "bölüm", "kısa dizi", "mini dizi",
    # 德语
    "CEO", "Milliardär", "Erbin", "Erbe", "Geheimnis", "Rache",
    "Heirat", "Scheident", "Betrug", "Braut", "Bräutigam",
    "verstoßen", "verlassen", "verraten", "verliebt", "schwanger",
    "Mafia", "Prinz", "Prinzessin", "König", "Lykan",
    "Ganze Folge", "Kurzfilm", "Kurzdrama", "Mini Drama",
    # 日语
    "CEO", "社長", "会長", "社長令嬢", "大富豪", "令嬢",
    "神医", "戦神", "至尊", "龍王", "絶世",
    "偽装結婚", "政略結婚", "契約結婚", "復讐", "再会",
    "転生", "重生", "溺愛", "寵愛", "愛人",
    "短編ドラマ", "ミニドラマ", "ショートドラマ", "吹き替え",
}

# 非短剧特征关键词
NON_DRAMA_KEYWORDS = [
    "turkish series", "série turca", "novela turca", "turkish drama",
    "full movie", "complete movie", "pelicula completa", "filme completo",
    "documentary", "documental", "documentário",
    "vlog", "challenge", "reaction", "tutorial", "unboxing",
    "top 10", "top 17", "best turkish", "melhores séries",
    "official music video", "official live", "behind the scene",
    "makeup", "grwm", "get ready with me", "day in my life",
    "haul", "review", "tips", "how to", "guide",
    # 土耳其
    "türk dizisi", "full dizi", "belgesel", "müzik videosu",
    # 德语
    "dokumentation", "musikvideo", "vollfilm",
    # 日语
    "ドキュメンタリー", "MV", "ライブ", "フル映画",
]

# 短剧频道名关键词
DRAMA_NAME_KEYWORDS = [
    "drama", "series", "episode", "短剧", "劇場", "劇社", "短片",
    "drama pendek", "drama corto", "drama curto", "kurzdrama",
    "mini drama", "short drama", "micro drama", "reel",
    "dorama", "novela", "telenovela",
    # 土耳其
    "dizi", "mini dizi", "kısa dizi", "kiss",
    # 德语
    "kurzdrama", "mini drama", "drama",
    # 日语
    "ドラマ", "ショートドラマ", "ミニドラマ", "劇場",
]

# 非短剧频道名关键词
NON_DRAMA_NAME_KEYWORDS = [
    "entertainment", "music", "vlog", "review", "news",
    "tv", "channel", "official", "studio",
    "entertainment", "musik", "música",
    # 土耳其
    "showbiz", "haber", "müzik",
    # 德语
    "nachrichten", "musik", "unterhaltung",
    # 日语
    "ニュース", "音楽", "エンタメ",
]

# 短剧描述标签关键词
DRAMA_TAG_KEYWORDS = [
    "drama", "romance", "love", "ceo", "billionaire", "revenge",
    "reborn", "short drama", "mini drama", "微短剧", "甜宠",
    "drama pendek", "drama corto", "dorama",
    # 土耳其
    "dizi", "aşk", "intikam", "milyarder", "CEO", "kısa dizi",
    # 德语
    "drama", "liebe", "rache", "CEO", "kurzdrama",
    # 日语
    "ドラマ", "恋愛", "復讐", "CEO", "社長", "ミニドラマ",
]


def score_channel(ch: dict) -> dict:
    """对单个频道进行多信号打分
    
    Returns:
        {
            "name": str,
            "lang": str,
            "total_score": int,  # 总分，越高越可能是短剧
            "signals": dict,     # 各信号得分
            "verdict": str,      # "pass" | "reject" | "review"
            "reasons": list,     # 拒绝/审查原因
        }
    """
    name = ch.get("channel_name", ch.get("name", ""))
    lang = ch.get("language", "")
    videos = ch.get("videos", [])
    
    signals = {
        "name_score": 0,      # 频道名得分
        "title_score": 0,     # 标题关键词得分
        "tag_score": 0,       # 描述标签得分
        "duration_score": 0,  # 时长得分
        "non_drama_penalty": 0,  # 非短剧惩罚分
    }
    reasons = []
    
    # ── 信号1: 频道名 ──
    name_lower = name.lower()
    if any(kw in name_lower for kw in DRAMA_NAME_KEYWORDS):
        signals["name_score"] = 5
    elif any(kw in name_lower for kw in NON_DRAMA_NAME_KEYWORDS):
        signals["name_score"] = -3
        reasons.append(f"频道名含非短剧关键词")
    
    # ── 信号2: 视频标题 ──
    if videos:
        sample = videos[:20]
        drama_hit = 0
        non_drama_hit = 0
        
        for v in sample:
            title = v.get("title", "").lower()
            if any(kw.lower() in title for kw in DRAMA_TITLE_KEYWORDS):
                drama_hit += 1
            if any(kw in title for kw in NON_DRAMA_KEYWORDS):
                non_drama_hit += 1
        
        total = len(sample)
        drama_ratio = drama_hit / total if total > 0 else 0
        non_drama_ratio = non_drama_hit / total if total > 0 else 0
        
        # 标题得分：按命中率阶梯
        if drama_ratio >= 0.5:
            signals["title_score"] = 5
        elif drama_ratio >= 0.3:
            signals["title_score"] = 3
        elif drama_ratio >= 0.15:
            signals["title_score"] = 1
        else:
            signals["title_score"] = -2
            reasons.append(f"标题短剧关键词命中率过低 ({drama_ratio:.0%})")
        
        # 非短剧惩罚
        if non_drama_ratio >= 0.3:
            signals["non_drama_penalty"] = -5
            reasons.append(f"标题含非短剧关键词 ({non_drama_ratio:.0%})")
        elif non_drama_ratio >= 0.15:
            signals["non_drama_penalty"] = -3
    
    # ── 信号3: 描述标签 ──
    if videos:
        tag_hit = 0
        for v in videos[:10]:
            desc_tags = v.get("description_tags", [])
            desc = v.get("description", "").lower()
            all_text = " ".join(desc_tags) + " " + desc
            if any(kw.lower() in all_text for kw in DRAMA_TAG_KEYWORDS):
                tag_hit += 1
        
        tag_ratio = tag_hit / min(10, len(videos)) if videos else 0
        if tag_ratio >= 0.5:
            signals["tag_score"] = 3
        elif tag_ratio >= 0.3:
            signals["tag_score"] = 1
        else:
            signals["tag_score"] = -1
    
    # ── 信号4: 时长模式 ──
    if videos:
        durations = [v.get("duration", 0) for v in videos[:20] if v.get("duration", 0) > 0]
        if durations:
            avg_dur = sum(durations) / len(durations)
            avg_min = avg_dur / 60
            
            # 短剧频道发的都是合集（60分钟以上）
            # 低于60分钟的：音乐、vlog、单集短剧平台，都过滤掉
            under_60_count = sum(1 for d in durations if d < 3600)  # <60分钟
            over_60_count = sum(1 for d in durations if d >= 3600)  # >=60分钟
            
            total_dur = len(durations)
            under_60_ratio = under_60_count / total_dur
            over_60_ratio = over_60_count / total_dur
            
            if over_60_ratio >= 0.5:
                # 大部分视频>=60分钟，短剧合集频道
                signals["duration_score"] = 3
            elif under_60_ratio >= 0.5:
                # 大部分视频<60分钟，不是短剧合集频道
                signals["duration_score"] = -5
                reasons.append(f"短视频占比过高 ({under_60_ratio:.0%})，不是短剧合集频道")
            else:
                signals["duration_score"] = 0
    
    # ── 计算总分 ──
    total_score = sum(signals.values())
    
    # ── 判断结果 ──
    if total_score >= 5:
        verdict = "pass"
    elif total_score <= -3:
        verdict = "reject"
        if not reasons:
            reasons.append(f"总分过低 ({total_score})")
    else:
        verdict = "review"
        if not reasons:
            reasons.append(f"总分在灰色地带 ({total_score})")
    
    return {
        "name": name,
        "lang": lang,
        "total_score": total_score,
        "signals": signals,
        "verdict": verdict,
        "reasons": reasons,
    }


def screen_staging() -> tuple:
    """筛选staging.json里的频道
    
    Returns:
        (通过的频道列表, 需审查的频道列表, 拒绝的频道列表)
    """
    staging_path = Path(STAGING_FILE)
    if not staging_path.exists():
        return [], [], []
    
    staging = json.loads(staging_path.read_text(encoding="utf-8"))
    
    # 加载唯一数据库，排除已收录频道
    latest_path = Path(LATEST_FILE)
    if latest_path.exists():
        latest = json.loads(latest_path.read_text(encoding="utf-8"))
        latest_ids = {ch["channel_id"] for ch in latest}
    else:
        latest_ids = set()
    
    # 加载待审核区，排除已存在的频道
    if STAGING_REVIEW_FILE.exists():
        review_existing = json.loads(STAGING_REVIEW_FILE.read_text(encoding="utf-8"))
        review_ids = {ch.get("channel_id") for ch in review_existing}
    else:
        review_ids = set()
    
    passed = []
    review = []
    rejected = []
    
    for ch in staging:
        cid = ch.get("channel_id", "")
        
        # 第一层：排除已收录/已审核的频道
        if cid in latest_ids:
            rejected.append((ch, "已在唯一数据库"))
            continue
        if cid in review_ids:
            rejected.append((ch, "已在待审核区"))
            continue
        
        # 基础过滤
        if ch.get("video_count", 0) < 5:
            rejected.append((ch, "视频数不足"))
            continue
        
        # 第一层过滤：订阅>150万 + 平均时长<60分钟 → 直接删
        subs = ch.get("subscribers", 0)
        videos = ch.get("videos", [])
        if videos:
            avg_dur = sum(v.get("duration", 0) for v in videos[:20]) / len(videos[:20])
            avg_min = avg_dur / 60
        else:
            avg_min = 0
        
        if subs >= 1000000 and avg_min < 60:
            rejected.append((ch, f"订阅{subs/10000:.0f}万+时长{avg_min:.0f}分，非短剧合集"))
            continue
        
        # 多信号打分
        result = score_channel(ch)
        
        if result["verdict"] == "pass":
            passed.append(ch)
        elif result["verdict"] == "reject":
            rejected.append((ch, "; ".join(result["reasons"])))
        else:
            review.append((ch, result))
    
    return passed, review, rejected


def scan_latest() -> list:
    """扫描latest.json中的可疑频道"""
    latest_path = Path(LATEST_FILE)
    if not latest_path.exists():
        return []
    
    latest = json.loads(latest_path.read_text(encoding="utf-8"))
    suspicious = []
    
    for ch in latest:
        # 第一层过滤：订阅>150万 + 平均时长<60分钟
        subs = ch.get("subscribers", 0)
        videos = ch.get("videos", [])
        if videos:
            avg_dur = sum(v.get("duration", 0) for v in videos[:20]) / len(videos[:20])
            avg_min = avg_dur / 60
        else:
            avg_min = 0
        
        if subs >= 1000000 and avg_min < 60:
            suspicious.append((ch, {
                "name": ch.get("channel_name", ch.get("name", "")),
                "lang": ch.get("language", ""),
                "total_score": -99,
                "signals": {},
                "verdict": "reject",
                "reasons": [f"订阅{subs/10000:.0f}万+时长{avg_min:.0f}分，非短剧合集"],
            }))
            continue
        
        result = score_channel(ch)
        if result["verdict"] in ("reject", "review"):
            suspicious.append((ch, result))
    
    return suspicious


def show_result(passed: list, review: list, rejected: list):
    """展示筛选结果"""
    total = len(passed) + len(review) + len(rejected)
    
    print(f"\n📊 筛选结果报告")
    print(f"━━━━━━━━━━━━━━━━━━")
    print(f"待筛选: {total} 个频道")
    print(f"✅ 通过: {len(passed)} 个频道")
    print(f"⚠️  需审查: {len(review)} 个频道")
    print(f"❌ 拒绝: {len(rejected)} 个频道")
    
    if passed:
        print(f"\n✅ 通过频道:")
        for ch in passed[:15]:
            print(f"  - {ch['name']} ({ch.get('language', '?')})")
        if len(passed) > 15:
            print(f"  ... +{len(passed) - 15} more")
    
    if review:
        print(f"\n⚠️  需审查频道:")
        for ch, result in review:
            signals = result["signals"]
            print(f"  - [{result['lang']}] {result['name']}")
            print(f"    总分: {result['total_score']} | "
                  f"频道名:{signals['name_score']} 标题:{signals['title_score']} "
                  f"标签:{signals['tag_score']} 时长:{signals['duration_score']} "
                  f"惩罚:{signals['non_drama_penalty']}")
            if result["reasons"]:
                print(f"    原因: {'; '.join(result['reasons'])}")
    
    if rejected:
        print(f"\n❌ 拒绝频道:")
        for ch, reason in rejected[:15]:
            print(f"  - {ch.get('name', '?')} ({ch.get('language', '?')}) - {reason}")
        if len(rejected) > 15:
            print(f"  ... +{len(rejected) - 15} more")


def show_scan_result(suspicious: list):
    """展示扫描结果"""
    if not suspicious:
        print("✅ latest.json 中没有可疑频道")
        return
    
    print(f"\n⚠️  latest.json 中发现 {len(suspicious)} 个可疑频道:\n")
    
    for ch, result in suspicious:
        signals = result["signals"]
        print(f"[{result['lang']}] {result['name']}")
        print(f"  总分: {result['total_score']} | "
              f"频道名:{signals['name_score']} 标题:{signals['title_score']} "
              f"标签:{signals['tag_score']} 时长:{signals['duration_score']} "
              f"惩罚:{signals['non_drama_penalty']}")
        if result["reasons"]:
            print(f"  原因: {'; '.join(result['reasons'])}")
        print()


def promote_to_latest(passed: list) -> int:
    """写入latest.json（只追加新频道，不覆盖已有）"""
    latest_path = Path(LATEST_FILE)
    if latest_path.exists():
        latest = json.loads(latest_path.read_text(encoding="utf-8"))
    else:
        latest = []
    
    existing_ids = {ch["channel_id"] for ch in latest}
    new_channels = [ch for ch in passed if ch["channel_id"] not in existing_ids]
    
    if not new_channels:
        print(f"\n⚠️ 没有新频道需要写入（所有通过的频道已在 latest.json 中）")
        return 0
    
    latest.extend(new_channels)
    latest_path.write_text(json.dumps(latest, ensure_ascii=False, indent=2), encoding="utf-8")
    
    print(f"\n✅ 已写入 {len(new_channels)} 个新频道到 latest.json")
    print(f"   latest.json 现有 {len(latest)} 个频道")
    return len(new_channels)


def write_to_review(passed: list, review: list) -> dict:
    """写入待审核区（staging_review.json）
    
    Args:
        passed: 通过筛选的频道列表
        review: 需审查的频道列表，格式为 [(channel, result), ...]
    
    Returns:
        {"passed": int, "review": int, "total": int}
    """
    # 读取现有待审核数据
    if STAGING_REVIEW_FILE.exists():
        existing = json.loads(STAGING_REVIEW_FILE.read_text(encoding="utf-8"))
    else:
        existing = []
    
    existing_ids = {ch.get("channel_id") for ch in existing}
    
    # 排除已在 latest.json 中的频道
    latest_path = Path(LATEST_FILE)
    if latest_path.exists():
        latest = json.loads(latest_path.read_text(encoding="utf-8"))
        latest_ids = {ch["channel_id"] for ch in latest}
    else:
        latest_ids = set()
    
    # 添加通过的频道（排除已有）
    new_passed = []
    for ch in passed:
        cid = ch["channel_id"]
        if cid not in existing_ids and cid not in latest_ids:
            ch["_review_status"] = "passed"
            ch["_review_score"] = None
            new_passed.append(ch)
            existing_ids.add(cid)
    
    # 添加需审查的频道（排除已有）
    new_review = []
    for ch, result in review:
        cid = ch["channel_id"]
        if cid not in existing_ids and cid not in latest_ids:
            ch["_review_status"] = "review"
            ch["_review_score"] = result["total_score"]
            ch["_review_signals"] = result["signals"]
            ch["_review_reasons"] = result["reasons"]
            new_review.append(ch)
            existing_ids.add(cid)
    
    # 合并并写入
    all_channels = existing + new_passed + new_review
    STAGING_REVIEW_FILE.write_text(
        json.dumps(all_channels, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )
    
    return {
        "passed": len(new_passed),
        "review": len(new_review),
        "total": len(all_channels)
    }


def approve_review(channel_ids: list) -> int:
    """从待审核区确认收录到latest.json
    
    Args:
        channel_ids: 要确认的频道ID列表
    
    Returns:
        成功收录的频道数量
    """
    if not STAGING_REVIEW_FILE.exists():
        return 0
    
    review_data = json.loads(STAGING_REVIEW_FILE.read_text(encoding="utf-8"))
    latest_path = Path(LATEST_FILE)
    
    if latest_path.exists():
        latest = json.loads(latest_path.read_text(encoding="utf-8"))
    else:
        latest = []
    
    existing_ids = {ch["channel_id"] for ch in latest}
    
    # 找出要确认的频道
    to_approve = []
    remaining = []
    for ch in review_data:
        if ch["channel_id"] in channel_ids and ch["channel_id"] not in existing_ids:
            # 清理审核字段
            clean_ch = {k: v for k, v in ch.items() if not k.startswith("_review_")}
            to_approve.append(clean_ch)
        else:
            remaining.append(ch)
    
    # 写入latest.json
    if to_approve:
        latest.extend(to_approve)
        latest_path.write_text(
            json.dumps(latest, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )
    
    # 更新待审核区
    STAGING_REVIEW_FILE.write_text(
        json.dumps(remaining, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )
    
    return len(to_approve)


def reject_review(channel_ids: list) -> int:
    """从待审核区拒绝（删除）
    
    Args:
        channel_ids: 要拒绝的频道ID列表
    
    Returns:
        拒绝的频道数量
    """
    if not STAGING_REVIEW_FILE.exists():
        return 0
    
    review_data = json.loads(STAGING_REVIEW_FILE.read_text(encoding="utf-8"))
    
    # 找出要拒绝的频道
    to_reject = []
    remaining = []
    for ch in review_data:
        if ch["channel_id"] in channel_ids:
            to_reject.append(ch)
        else:
            remaining.append(ch)
    
    # 更新待审核区
    STAGING_REVIEW_FILE.write_text(
        json.dumps(remaining, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )
    
    return len(to_reject)


def main():
    """主函数"""
    import argparse
    parser = argparse.ArgumentParser(description="staging → latest 筛选")
    parser.add_argument("--apply", action="store_true", help="确认后写入 latest.json")
    parser.add_argument("--dry-run", action="store_true", help="只展示，不询问")
    parser.add_argument("--scan-latest", action="store_true", help="扫描 latest.json 中的可疑频道")
    args = parser.parse_args()
    
    if args.scan_latest:
        suspicious = scan_latest()
        show_scan_result(suspicious)
        return
    
    # 运行筛选
    passed, review, rejected = screen_staging()
    show_result(passed, review, rejected)
    
    if not passed and not review:
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
