#!/usr/bin/env python3
"""
分桶v2：用标题skeleton体系（蒸馏已有）分桶，不用新关键词

标题skeleton → 模板卡映射：
  身份落差型 → identity
  关系背叛补偿型 → relationship
  情绪爆点型 → emotion
  重生改命型 → time
  系统开挂型 → system
  reversal = 标题含反转词但不属于以上5类
  compensation = 背叛+代价/报复结果

每桶选3条：题材多样性优先，其次播放量
"""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INPUT = ROOT / "data" / "reverse_engineered_covers" / "from_distill.json"
OUTPUT = ROOT / "data" / "reverse_engineered_covers" / "buckets"
OUTPUT.mkdir(parents=True, exist_ok=True)

# ============================================================
# Hook匹配规则（从蒸馏skeleton定义派生，按优先级排序）
# 具体hook先匹配，reversal/compensation兜底
# ============================================================

HOOK_RULES = [
    # 1. 系统/能力（最具体，先匹配）
    ("system", [
        "system", "sistem", "系统", "觉醒", "awaken", "ability", "kemampuan",
        "超能力", "异能", "读心", "穿越", "cross", "viaja", "travel",
        "levelling", "level up", "upgrade", "vip",
        "雷击", "petir", "lightning", "listrik",
    ]),
    # 2. 重生/时间（具体）
    ("time", [
        "reborn", "重生", "renací", "renacer", "lahir kembali", "terlahir",
        "past life", "前世", "转生", "doğmuş", "yeniden",
        "after years", "多年", "绝嗣", "那一夜",
        "38岁", "19岁", "45岁", "39岁",
    ]),
    # 3. 身份反差（常见但有明确关键词）
    ("identity", [
        "secret", "billionaire", "heiress", "actually", "real identity",
        "hidden", "true heir", "miliarder", "pewaris", "dewa", "perang",
        "神医", "战神", "至尊", "隐世", "正体", "真千金", "heredero",
        "varis", "gerçek", "trillion", "satpam", "pengemis",
        "useless", "mocked", "poor", "pobre", "fakir", "miskin",
        "kurye", "taksici", "vendedor", "garçon",
        "ridiculizan", "dihina", "diremehkan", "herkes",
    ]),
    # 4. 情绪爆点（有明确场景词）
    ("emotion", [
        "wedding night", "wedding", "birthday", "saved him", "hospital",
        "婚礼", "生日", "病床", "救命",
        "malam pernikahan", "ulang tahun",
        "boda", "cumpleaños", "noche de boda",
    ]),
    # 5. 关系背叛（中等优先级）
    ("relationship", [
        "husband", "wife", "marriage", "married", "divorce", "cheat",
        "betray", "first love", "ex", "affair", "lover",
        "suami", "istri", "cerai", "selingkuh", "cinta pertama",
        "esposo", "esposa", "matrimonio", "traición", "engañ",
        "婚", "妻", "夫", "出轨", "背叛", "离婚", "初恋", "前任",
        "koca", "karı", "boşanma", "ihanet", "marido",
        "forced", "arranged", "contract", "契约", "替嫁", "闪婚",
        "dipaksa", "nikah", "kontrak",
    ]),
    # 6. 补偿/复仇（兜底类）
    ("compensation", [
        "revenge", "pay", "destroy", "ruin", "face-slapping", "slap",
        "make them pay", "regret", "beg", "跪求", "后悔", "付出代价",
        "balas dendam", "hukum", "bayar", "membalas",
        "venganza", "pagar", "arrepentirse",
        "复仇", "打脸", "碾压", "清算",
        "intikam", "öde", "bedel",
        "se vengó", "se vuelve",
    ]),
    # 7. 反转（最后兜底）
    ("reversal", [
        "but", "actually", "turns out", "unexpectedly", "shock",
        "ternyata", "tak disangka", "gila", "siapa sangka",
        "resulta", "inesperadamente", "todos",
        "殊不知", "岂料", "竟然", "全场",
        "ama", "ancak", "meğer",
    ]),
]

GENRE_KW = {
    "ceo": ["ceo", "billionaire", "miliarder", "总裁", "başkan", "bilionário"],
    "martial_arts": ["martial", "warrior", "fighter", "dewa", "beladiri", "战神", "武"],
    "medical": ["doctor", "medical", "surgeon", "dokter", "tabib", "医", "神医"],
    "campus": ["school", "student", "campus", "sekolah", "escuela", "校园"],
    "family": ["family", "mother", "father", "keluarga", "familia", "家庭"],
    "royal": ["prince", "princess", "king", "pangeran", "príncipe", "王子"],
    "historical": ["ancient", "dynasty", "costume", "kuno", "古代", "宫廷"],
    "urban": ["urban", "city", "street", "kota", "urbano", "都市"],
}


def classify(title: str) -> str:
    t = title.lower()
    for hook, keywords in HOOK_RULES:
        if any(kw in t for kw in keywords):
            return hook
    return "reversal"


def classify_genre(title: str) -> str:
    t = title.lower()
    for genre, keywords in GENRE_KW.items():
        if any(kw in t for kw in keywords):
            return genre
    return "general"


def pick_top3(bucket):
    by_genre = {}
    for item in bucket:
        g = item["genre"]
        by_genre.setdefault(g, []).append(item)
    for g in by_genre:
        by_genre[g].sort(key=lambda x: x["views"], reverse=True)

    selected = []
    for g in sorted(by_genre, key=lambda g: max(i["views"] for i in by_genre[g]), reverse=True):
        if len(selected) >= 3:
            break
        selected.append(by_genre[g].pop(0))

    remaining = [i for items in by_genre.values() for i in items]
    remaining.sort(key=lambda x: x["views"], reverse=True)
    for item in remaining:
        if len(selected) >= 3:
            break
        selected.append(item)
    return selected[:3]


def main():
    with open(INPUT) as f:
        data = json.load(f)

    items = [d for d in data if "chatgpt_prompt" in d.get("reverse_engineered", {})]
    print(f"加载: {len(items)} 条\n")

    buckets = {hook: [] for hook, _ in HOOK_RULES}
    for item in items:
        title = item.get("title", "")
        re_data = item.get("reverse_engineered", {})
        hook = classify(title)
        genre = classify_genre(title)
        entry = {
            "video_id": item.get("video_id", ""),
            "title": title,
            "views": item.get("views", 0),
            "language": item.get("language", ""),
            "hook": hook,
            "genre": genre,
            "chatgpt_prompt": re_data.get("chatgpt_prompt", ""),
        }
        buckets[hook].append(entry)

    summary = {}
    for hook, bucket in buckets.items():
        genre_counts = {}
        for item in bucket:
            genre_counts[item["genre"]] = genre_counts.get(item["genre"], 0) + 1

        top3 = pick_top3(bucket)

        with open(OUTPUT / f"{hook}.json", "w", encoding="utf-8") as f:
            json.dump(bucket, f, ensure_ascii=False, indent=2)
        with open(OUTPUT / f"{hook}_top3.json", "w", encoding="utf-8") as f:
            json.dump(top3, f, ensure_ascii=False, indent=2)

        summary[hook] = {
            "total": len(bucket),
            "genres": genre_counts,
            "top3": [{"genre": t["genre"], "views": t["views"], "title": t["title"][:50]} for t in top3],
        }

        print(f"{'='*50}")
        print(f"📁 {hook}: {len(bucket)} 条 | 题材: {genre_counts}")
        for t in top3:
            print(f"   [{t['views']:>8,}] [{t['genre']:>12}] {t['title'][:55]}")

    with open(OUTPUT / "summary.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    print(f"\n{'='*50}")
    print(f"✅ 输出: {OUTPUT}")
    for hook, s in summary.items():
        print(f"  {hook}: {s['total']}条 → top3={[t['genre'] for t in s['top3']]}")


if __name__ == "__main__":
    main()
