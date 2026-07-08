#!/usr/bin/env python3
"""语言检测模块 — 基于视频标题重新分类频道语言

策略: Lingua (专为短文本优化，~95%准确率)
用于修正 search.py 按搜索词硬绑定导致的语言错标问题

用法:
    python3 scripts/classify_languages.py                         # 修正 staging_review.json
    python3 scripts/classify_languages.py --file competitors_channels_all.json
    python3 scripts/classify_languages.py --dry-run               # 只展示不写入
    python3 scripts/classify_languages.py --batch                 # 批量跑两个文件
"""
from __future__ import annotations
import json
import sys
import argparse
from pathlib import Path
from collections import Counter

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

# ── Lingua 配置 ────────────────────────────────────────────────
from lingua import Language, LanguageDetectorBuilder

# 只加载目标语种，减少内存、提高准确率
_TARGET_LANGUAGES = [
    Language.ENGLISH, Language.PORTUGUESE, Language.SPANISH,
    Language.ITALIAN, Language.GERMAN, Language.INDONESIAN,
    Language.TURKISH, Language.JAPANESE, Language.CHINESE,
    Language.KOREAN, Language.THAI, Language.VIETNAMESE,
    Language.FRENCH, Language.ARABIC, Language.RUSSIAN,
    Language.HINDI, Language.MALAY,
]

_detector = None

def get_detector():
    global _detector
    if _detector is None:
        _detector = LanguageDetectorBuilder.from_languages(
            *_TARGET_LANGUAGES
        ).with_preloaded_language_models().build()
    return _detector


# Language enum → 中文名
LANG_MAP = {
    Language.PORTUGUESE: '葡萄牙', Language.ENGLISH: '英文',
    Language.SPANISH: '西语', Language.ITALIAN: '意大利语',
    Language.CHINESE: '繁中', Language.JAPANESE: '日语',
    Language.GERMAN: '德语', Language.INDONESIAN: '印尼',
    Language.TURKISH: '土耳其', Language.KOREAN: '韩语',
    Language.THAI: '泰语', Language.VIETNAMESE: '越南语',
    Language.FRENCH: '法语', Language.ARABIC: '阿拉伯语',
    Language.RUSSIAN: '俄语', Language.HINDI: '印地语',
    Language.MALAY: '马来语',
}

# 我们关注的语种
TARGET_LANGS = {'印尼', '土耳其', '德语', '日语', '繁中', '英文', '葡萄牙', '西语', '意大利语'}


def detect_from_titles(titles: list[str], channel_name: str = '', confidence_threshold: float = 0.55, country: str = '') -> tuple[str, float]:
    """检测频道语言 — 频道名优先，地区其次，标题辅助

    Args:
        titles: 视频标题列表
        channel_name: 频道名（强信号）
        confidence_threshold: 置信度阈值
        country: 国家/地区代码（如 ID、BR、TR）

    Returns:
        (lang_cn, confidence) — 中文语言名、置信度
    """
    # ── 第一优先：频道名 ──
    if channel_name:
        # 频道名含中文 → 繁中（排除纯英文+数字的情况）
        cjk_in_name = sum(1 for c in channel_name if '\u4e00' <= c <= '\u9fff' or '\u3400' <= c <= '\u4dbf')
        if cjk_in_name >= 2:
            # 检查是否有日文假名
            jp_in_name = sum(1 for c in channel_name if '\u3040' <= c <= '\u30ff')
            if jp_in_name >= 2:
                return ('日语', 1.0)
            return ('繁中', 1.0)

        # 频道名含日文假名 → 日语
        jp_in_name = sum(1 for c in channel_name if '\u3040' <= c <= '\u30ff')
        if jp_in_name >= 2:
            return ('日语', 1.0)

        # 频道名含韩文 → 韩语
        kr_in_name = sum(1 for c in channel_name if '\uac00' <= c <= '\ud7af')
        if kr_in_name >= 2:
            return ('韩语', 1.0)

        # 频道名含拉丁语系关键词
        name_lower = channel_name.lower()
        NAME_KEYWORDS = {
            '印尼': ['indonesia', 'indonesian', 'bahasa', 'drama indo', 'nusantara'],
            '葡萄牙': ['português', 'portugues', 'portugal', 'portuguese', 'brasil', 'brazilian'],
            '西语': ['español', 'espanol', 'latino', 'latina', 'hispano'],
            '土耳其': ['türkçe', 'turkce', 'turkiye', 'türk', 'turkish', 'turk'],
            '德语': ['deutsch', 'german', 'kurz', 'kurzdramen'],
            '泰语': ['thai', 'thailand', 'ไทย'],
            '越南语': ['việt', 'vietnam', 'vietnamese'],
            '俄语': ['рус', 'russian'],
        }
        for lang, keywords in NAME_KEYWORDS.items():
            if any(kw in name_lower for kw in keywords):
                return (lang, 1.0)

    # ── 第三优先：标题投票 ──
    if not titles:
        # 没有标题，用地区兜底
        COUNTRY_LANG = {
            'ID': '印尼', 'MY': '马来语', 'TH': '泰语', 'VN': '越南语',
            'TR': '土耳其', 'DE': '德语', 'KR': '韩语', 'JP': '日语',
            'BR': '葡萄牙', 'PT': '葡萄牙', 'MX': '西语', 'ES': '西语',
            'CO': '西语', 'AR': '西语', 'PE': '西语', 'CL': '西语',
            'RU': '俄语', 'PH': '印尼',
        }
        if country:
            lang_from_country = COUNTRY_LANG.get(country.upper(), '')
            if lang_from_country:
                return (lang_from_country, 0.9)
        return ('未知', 0.0)

    sample = [t for t in titles[:8] if t and len(t) > 3]
    if not sample:
        return ('未知', 0.0)

    detector = get_detector()
    votes: Counter = Counter()
    for title in sample:
        try:
            lang = detector.detect_language_of(title)
            if lang is None:
                continue
            conf = detector.compute_language_confidence(title, lang)
            mapped = LANG_MAP.get(lang, '')
            if mapped:
                votes[mapped] += conf
        except Exception:
            continue

    if not votes:
        return ('未知', 0.0)

    top_lang = votes.most_common(1)[0][0]
    total_weight = sum(votes.values())
    confidence = votes[top_lang] / total_weight if total_weight > 0 else 0

    return (top_lang, confidence)


def classify_channel(ch: dict) -> dict:
    """对单个频道重新检测语言

    Returns: {"old_lang", "new_lang", "confidence", "changed"}
    """
    old_lang = ch.get('language', '未知')
    titles = [v.get('title', '') for v in ch.get('videos', [])]
    channel_name = ch.get('name', '')
    country = ch.get('country', '')
    new_lang, confidence = detect_from_titles(titles, channel_name=channel_name, country=country)
    # 没有足够数据时保留原语言
    if new_lang == '未知' and old_lang != '未知':
        new_lang = old_lang
    changed = new_lang != old_lang and new_lang != '未知'

    return {
        'name': ch.get('name', '?'),
        'old_lang': old_lang,
        'new_lang': new_lang,
        'confidence': confidence,
        'changed': changed,
    }


def run_on_file(filepath: Path, dry_run: bool = False):
    """对指定文件全量跑语言检测"""
    print(f"📂 文件: {filepath.name}")
    with open(filepath) as f:
        data = json.load(f)

    channels = data if isinstance(data, list) else data.get('channels', [])
    print(f"📊 共 {len(channels)} 个频道\n")

    changes = []
    stats = {'total': 0, 'changed': 0, 'low_conf': 0}

    for ch in channels:
        stats['total'] += 1
        result = classify_channel(ch)

        if result['confidence'] < 0.55:
            stats['low_conf'] += 1

        if result['changed']:
            stats['changed'] += 1
            changes.append(result)
            symbol = '🔄'
        else:
            symbol = '  '

        conf_str = f"{result['confidence']:.2f}"
        print(f"  {symbol} {conf_str} | {result['old_lang']:>4} → {result['new_lang']:>4} | {result['name'][:35]}")

    print(f"\n{'='*60}")
    print(f"📊 统计: {stats['total']}个频道, {stats['changed']}个需修正, {stats['low_conf']}个低置信度")

    if changes:
        print(f"\n🔄 需修正:")
        for c in changes:
            print(f"  {c['name']}: {c['old_lang']} → {c['new_lang']} ({c['confidence']:.2f})")

    if not dry_run and changes:
        for ch in channels:
            for c in changes:
                if ch.get('name') == c['name']:
                    ch['language'] = c['new_lang']
                    ch['_lang_confidence'] = round(c['confidence'], 3)
                    ch['_lang_method'] = 'lingua'
                    break

        with open(filepath, 'w') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"\n✅ 已写入 {filepath.name} ({stats['changed']} 个修正)")
        return stats['changed']
    elif dry_run:
        print(f"\n🔍 dry-run 模式，未写入")
        return 0

    return 0


def main():
    parser = argparse.ArgumentParser(description='Lingua 语言检测修正')
    parser.add_argument('--file', default='staging_review.json', help='目标文件名')
    parser.add_argument('--dry-run', action='store_true', help='只展示不写入')
    parser.add_argument('--batch', action='store_true', help='批量跑 staging_review + competitors_channels_all')
    args = parser.parse_args()

    data_dir = ROOT / 'data' / 'competitor_data'

    if args.batch:
        total_fixed = 0
        for fp in [data_dir / 'staging_review.json', ROOT / 'data' / 'competitors_channels_all.json', data_dir / 'latest.json']:
            if fp.exists():
                total_fixed += run_on_file(fp, args.dry_run)
                print()
        print(f"🏁 批量完成: 共修正 {total_fixed} 个频道")
    else:
        target = data_dir / args.file
        if not target.exists():
            print(f"❌ 文件不存在: {target}")
            return
        run_on_file(target, args.dry_run)


if __name__ == '__main__':
    main()
