#!/usr/bin/env python3
"""
封面蒸馏第一步：从214条竞品封面分析中提取结构化字段
输出：data/cover_distill_stats.json
"""
import json, re, os
from pathlib import Path
from collections import Counter, defaultdict

ROOT = Path(__file__).resolve().parent.parent
EVIDENCE_DIR = ROOT / "distill" / "evidence"
OUTPUT_FILE = ROOT / "data" / "cover_distill_stats.json"

LANGUAGES = ["英文", "印尼", "西语", "日语", "葡萄牙", "土耳其", "繁中"]

def extract_all():
    all_records = []
    for lang in LANGUAGES:
        covers_file = EVIDENCE_DIR / lang / "covers.json"
        if not covers_file.exists():
            print(f"⚠️ {covers_file} 不存在，跳过")
            continue
        with open(covers_file) as f:
            data = json.load(f)
        for item in data:
            item["_lang"] = lang
            all_records.append(item)
    return all_records

def extract_text_info(item):
    """从'文字'字段提取文字信息"""
    text_field = item.get("文字", "")
    if not text_field:
        return {"has_text": False}
    
    has_text = True
    # 判断是否有实质文字（排除"没有文字"等情况）
    no_text_patterns = ["没有文字", "无文字", "未添加文字", "不含文字", "没有添加", "no text", "no title"]
    for p in no_text_patterns:
        if p in text_field.lower():
            has_text = False
            break
    
    if not has_text:
        return {"has_text": False}
    
    # 提取位置
    positions = []
    for pos in ["左上", "右上", "左下", "右下", "底部", "顶部", "中央", "中间", "上方", "下方", "正上", "正下"]:
        if pos in text_field:
            positions.append(pos)
    
    # 提取颜色
    colors = []
    for color in ["白色", "红色", "黄色", "粉色", "蓝色", "黑色", "金色", "橙色", "紫色", "绿色"]:
        if color in text_field:
            colors.append(color)
    
    # 提取字体风格
    font_styles = []
    for style in ["粗体", "无衬线", "手写", "艺术", "衬线", "斜体", "serif", "sans-serif", "handwritten"]:
        if style in text_field.lower():
            font_styles.append(style)
    
    return {
        "has_text": True,
        "positions": positions,
        "colors": colors,
        "font_styles": font_styles,
        "raw": text_field[:200]
    }

def extract_composition_info(item):
    """从'构图'字段提取构图信息"""
    comp_field = item.get("构图", "")
    structured = item.get("结构化", {})
    
    comp_type = structured.get("composition", "") if isinstance(structured, dict) else ""
    
    # 从文本提取构图类型
    comp_types = []
    for ct in ["对角线", "左右", "中心", "三角", "对称", "放射", "纵深", "S形", "黄金分割"]:
        if ct in comp_field:
            comp_types.append(ct)
    
    # 提取景别
    shot_types = []
    for st in ["特写", "近景", "中景", "全景", "远景", "中近景"]:
        if st in comp_field:
            shot_types.append(st)
    
    # 提取视角
    perspectives = []
    for pv in ["平视", "俯视", "仰视", "斜视"]:
        if pv in comp_field:
            perspectives.append(pv)
    
    return {
        "structured_type": comp_type,
        "text_types": comp_types,
        "shot_types": shot_types,
        "perspectives": perspectives,
        "raw": comp_field[:200]
    }

def extract_color_info(item):
    """从'色彩'字段提取色彩信息"""
    color_field = item.get("色彩", "")
    structured = item.get("结构化", {})
    
    color_type = structured.get("color_type", "") if isinstance(structured, dict) else ""
    
    # 提取主色调
    main_colors = []
    for c in ["金色", "暖金", "冷蓝", "红色", "黑色", "白色", "粉色", "紫色", "绿色", "灰色", "棕色", "橙色", "深蓝", "暗红"]:
        if c in color_field:
            main_colors.append(c)
    
    # 提取情绪
    emotions = []
    for e in ["暖", "冷", "明亮", "暗", "柔和", "高对比", "低调", "高级感", "温馨", "紧张", "浪漫"]:
        if e in color_field:
            emotions.append(e)
    
    # 提取光影
    lighting = []
    for l in ["逆光", "侧光", "顺光", "自然光", "人工光", "bokeh", "光斑", "阴影", "柔光", "硬光"]:
        if l in color_field.lower():
            lighting.append(l)
    
    return {
        "structured_type": color_type,
        "main_colors": main_colors,
        "emotions": emotions,
        "lighting": lighting,
        "raw": color_field[:200]
    }

def extract_props(item):
    """从'道具'字段提取道具信息"""
    prop_field = item.get("道具", "")
    
    # 常见短剧道具关键词
    prop_keywords = [
        "西装", "婚纱", "婚戒", "戒指", "豪车", "跑车", "手机", "文件",
        "酒杯", "红酒", "枪", "花", "鲜花", "眼镜", "项链", "耳环",
        "裙子", "制服", "护士服", "校服", "雨伞", "破碎", "蛋糕",
        "行李箱", "电脑", "钥匙", "名片", "合同", "护照", "钞票",
        "金条", "钻石", "皇冠", "权杖", "龙纹", "战甲", "武器",
        "听诊器", "手术刀", "书", "笔记本", "照片", "镜子"
    ]
    
    found_props = []
    for p in prop_keywords:
        if p in prop_field:
            found_props.append(p)
    
    return {
        "props": found_props,
        "raw": prop_field[:200]
    }

def extract_person_info(item):
    """从'人物'字段提取人物信息"""
    person_field = item.get("人物", "")
    structured = item.get("结构化", {})
    
    person_count = structured.get("person_count", 0) if isinstance(structured, dict) else 0
    
    # 从文本推断人数
    if not person_count:
        count_match = re.search(r'(\d+)\s*名|(\d+)\s*人|两人|三人|四人|多人|单人|一名|两名|三名', person_field)
        if count_match:
            if "两人" in person_field or "两名" in person_field: person_count = 2
            elif "三人" in person_field or "三名" in person_field: person_count = 3
            elif "四人" in person_field: person_count = 4
            elif "多人" in person_field: person_count = 5
            elif "单人" in person_field or "一名" in person_field: person_count = 1
            elif count_match.group(1): person_count = int(count_match.group(1))
            elif count_match.group(2): person_count = int(count_match.group(2))
    
    # 提取表情关键词
    emotions = []
    for e in ["震惊", "愤怒", "冷漠", "得意", "含泪", "微笑", "绝望", "自信", "心碎", "甜蜜", "决绝", "委屈", "高傲", "恳求", "哭泣"]:
        if e in person_field:
            emotions.append(e)
    
    # 提取服装
    clothing = []
    for c in ["西装", "婚纱", "裙", "制服", "便装", "休闲", "正装", "礼服", "古装", "校服"]:
        if c in person_field:
            clothing.append(c)
    
    return {
        "person_count": person_count,
        "emotions": emotions,
        "clothing": clothing,
        "raw": person_field[:200]
    }

def extract_visual_hierarchy(item):
    """从'视觉层级'字段提取"""
    vh_field = item.get("视觉层级", "")
    if not vh_field:
        return {"first_focus": "", "raw": ""}
    
    # 提取第一眼焦点
    first_focus = ""
    first_match = re.search(r'第一眼[^：:]*[：:]?\s*(.{5,50})', vh_field)
    if first_match:
        first_focus = first_match.group(1).strip()
    
    return {
        "first_focus": first_focus,
        "raw": vh_field[:200]
    }

def extract_genre_elements(item):
    """从'题材元素'字段提取"""
    genre_field = item.get("题材元素", "")
    if not genre_field:
        return {"elements": [], "raw": ""}
    
    elements = []
    for e in ["霸总", "豪门", "甜宠", "宠爱", "复仇", "逆袭", "重生", "穿越", "古装", "宫斗",
              "背叛", "离婚", "契约", "闪婚", "替身", "虐恋", "校园", "职场", "末世", "丧尸",
              "系统", "异能", "战神", "神医", "千金", "女仆", "CEO", "总裁", "黑帮", "悬疑"]:
        if e.lower() in genre_field.lower():
            elements.append(e)
    
    return {
        "elements": elements,
        "raw": genre_field[:300]
    }

def extract_synergy(item):
    """从'封面标题配合'字段提取"""
    syn_field = item.get("封面标题配合", "")
    if not syn_field:
        return {"pattern": "", "raw": ""}
    
    pattern = ""
    for p in ["情绪呼应", "信息互补", "悬念叠加", "完全一致", "互相补充", "视觉化", "对比", "反差"]:
        if p in syn_field:
            pattern = p
            break
    
    return {
        "pattern": pattern,
        "raw": syn_field[:200]
    }

def extract_viral_score(item):
    """从'爆款因素'字段提取评分"""
    viral_field = item.get("爆款因素", "")
    if not viral_field:
        return {"score": 0, "raw": ""}
    
    score = 0
    if isinstance(viral_field, dict):
        score_str = str(viral_field.get("评分", "0"))
        score_match = re.search(r'(\d+)', score_str)
        if score_match:
            score = int(score_match.group(1))
        return {"score": score, "raw": json.dumps(viral_field, ensure_ascii=False)[:300]}
    
    score_match = re.search(r'评分[：:]\s*(\d+)', str(viral_field))
    if score_match:
        score = int(score_match.group(1))
    
    return {
        "score": score,
        "raw": str(viral_field)[:300]
    }

def infer_genre(item):
    """根据多个字段推断题材"""
    genre_elements = item.get("题材元素", "")
    person_field = item.get("人物", "")
    all_text = f"{genre_elements} {person_field} {item.get('道具', '')}"
    
    genre_map = {
        "霸总豪门": ["霸总", "豪门", "CEO", "总裁", "豪车", "黑卡", "保镖"],
        "甜宠宠爱": ["甜宠", "宠爱", "溺爱", "甜蜜", "温馨"],
        "复仇逆袭": ["复仇", "逆袭", "打脸", "清算", "跪求"],
        "重生穿越": ["重生", "穿越", "前世", "改命"],
        "背叛离婚": ["背叛", "离婚", "出轨", "前任", "替身"],
        "契约闪婚": ["契约", "闪婚", "假结婚", "先婚后爱"],
        "虐恋": ["虐恋", "虐心", "误会", "折磨"],
        "古装宫斗": ["古装", "宫斗", "宫廷", "皇帝", "妃子"],
        "职场": ["职场", "商战", "公司", "办公室"],
        "校园": ["校园", "学校", "学生", "青春"],
        "末世求生": ["末世", "丧尸", "求生", "废墟"],
        "系统异能": ["系统", "异能", "超能力", "觉醒"],
        "战神": ["战神", "军人", "部队", "战场"],
        "神医": ["神医", "医生", "医术", "救人"],
    }
    
    scores = {}
    for genre, keywords in genre_map.items():
        score = sum(1 for kw in keywords if kw in all_text)
        if score > 0:
            scores[genre] = score
    
    if scores:
        return max(scores, key=scores.get)
    return "其他"

def run():
    print("📥 加载214条封面分析数据...")
    records = extract_all()
    print(f"   共 {len(records)} 条")
    
    print("🔍 提取结构化字段...")
    extracted = []
    for item in records:
        r = {
            "lang": item["_lang"],
            "person": extract_person_info(item),
            "composition": extract_composition_info(item),
            "color": extract_color_info(item),
            "text": extract_text_info(item),
            "props": extract_props(item),
            "visual_hierarchy": extract_visual_hierarchy(item),
            "genre_elements": extract_genre_elements(item),
            "synergy": extract_synergy(item),
            "viral": extract_viral_score(item),
            "genre_inferred": infer_genre(item),
            "title": item.get("_meta", {}).get("title", "") if isinstance(item.get("_meta"), dict) else "",
            "views": item.get("_meta", {}).get("views", 0) if isinstance(item.get("_meta"), dict) else 0,
        }
        extracted.append(r)
    
    print("📊 统计分析...")
    
    # === 1. 构图统计 ===
    comp_stats = defaultdict(lambda: {"count": 0, "scores": [], "by_lang": defaultdict(int)})
    for r in extracted:
        for ct in r["composition"]["text_types"] or ["未标注"]:
            comp_stats[ct]["count"] += 1
            comp_stats[ct]["by_lang"][r["lang"]] += 1
            if r["viral"]["score"] > 0:
                comp_stats[ct]["scores"].append(r["viral"]["score"])
    
    # === 2. 色彩统计 ===
    color_stats = defaultdict(lambda: {"count": 0, "scores": [], "by_lang": defaultdict(int)})
    for r in extracted:
        for c in r["color"]["main_colors"] or ["未标注"]:
            color_stats[c]["count"] += 1
            color_stats[c]["by_lang"][r["lang"]] += 1
            if r["viral"]["score"] > 0:
                color_stats[c]["scores"].append(r["viral"]["score"])
    
    # === 3. 文字统计 ===
    text_count = {"有文字": 0, "无文字": 0}
    text_positions = Counter()
    text_colors = Counter()
    for r in extracted:
        if r["text"]["has_text"]:
            text_count["有文字"] += 1
            for p in r["text"]["positions"]:
                text_positions[p] += 1
            for c in r["text"]["colors"]:
                text_colors[c] += 1
        else:
            text_count["无文字"] += 1
    
    # === 4. 人物数量统计 ===
    person_count_stats = defaultdict(lambda: {"count": 0, "scores": []})
    for r in extracted:
        pc = r["person"]["person_count"]
        try:
            pc = int(pc) if pc else 0
        except (ValueError, TypeError):
            pc = 0
        label = f"{pc}人" if pc > 0 else "未知"
        person_count_stats[label]["count"] += 1
        if r["viral"]["score"] > 0:
            person_count_stats[label]["scores"].append(r["viral"]["score"])
    
    # === 5. 道具统计 ===
    prop_counter = Counter()
    for r in extracted:
        for p in r["props"]["props"]:
            prop_counter[p] += 1
    
    # === 6. 景别统计 ===
    shot_stats = Counter()
    for r in extracted:
        for st in r["composition"]["shot_types"]:
            shot_stats[st] += 1
    
    # === 7. 题材统计 ===
    genre_stats = defaultdict(lambda: {"count": 0, "scores": [], "by_lang": defaultdict(int)})
    for r in extracted:
        g = r["genre_inferred"]
        genre_stats[g]["count"] += 1
        genre_stats[g]["by_lang"][r["lang"]] += 1
        if r["viral"]["score"] > 0:
            genre_stats[g]["scores"].append(r["viral"]["score"])
    
    # === 8. 视觉层级统计 ===
    hierarchy_counter = Counter()
    for r in extracted:
        fh = r["visual_hierarchy"]["first_focus"]
        if fh:
            # 简化分类
            if any(kw in fh for kw in ["人物", "脸", "表情", "眼神"]):
                hierarchy_counter["人物/表情"] += 1
            elif any(kw in fh for kw in ["道具", "物品", "戒指", "手机", "文件"]):
                hierarchy_counter["道具"] += 1
            elif any(kw in fh for kw in ["文字", "标题", "FULL"]):
                hierarchy_counter["文字"] += 1
            elif any(kw in fh for kw in ["场景", "背景", "环境"]):
                hierarchy_counter["场景"] += 1
            elif any(kw in fh for kw in ["光", "色", "氛围"]):
                hierarchy_counter["光影/氛围"] += 1
            else:
                hierarchy_counter["其他"] += 1
    
    # === 9. 封面标题配合统计 ===
    synergy_counter = Counter()
    for r in extracted:
        if r["synergy"]["pattern"]:
            synergy_counter[r["synergy"]["pattern"]] += 1
    
    # === 10. 语种偏好统计 ===
    lang_preferences = {}
    for lang in LANGUAGES:
        lang_records = [r for r in extracted if r["lang"] == lang]
        if not lang_records:
            continue
        
        lang_pref = {
            "sample_size": len(lang_records),
            "top_compositions": Counter(),
            "top_colors": Counter(),
            "text_rate": 0,
            "avg_person_count": 0,
            "top_genres": Counter(),
        }
        
        person_counts = []
        for r in lang_records:
            for ct in r["composition"]["text_types"]:
                lang_pref["top_compositions"][ct] += 1
            for c in r["color"]["main_colors"]:
                lang_pref["top_colors"][c] += 1
            if r["text"]["has_text"]:
                lang_pref["text_rate"] += 1
            pc = r["person"]["person_count"]
            try:
                pc = int(pc) if pc else 0
            except (ValueError, TypeError):
                pc = 0
            if pc > 0:
                person_counts.append(pc)
            lang_pref["top_genres"][r["genre_inferred"]] += 1
        
        lang_pref["text_rate"] = round(lang_pref["text_rate"] / len(lang_records) * 100, 1)
        lang_pref["avg_person_count"] = round(sum(person_counts) / len(person_counts), 1) if person_counts else 0
        lang_pref["top_compositions"] = dict(lang_pref["top_compositions"].most_common(5))
        lang_pref["top_colors"] = dict(lang_pref["top_colors"].most_common(5))
        lang_pref["top_genres"] = dict(lang_pref["top_genres"].most_common(5))
        
        lang_preferences[lang] = lang_pref
    
    # === 11. 题材×构图交叉 ===
    genre_comp_cross = defaultdict(lambda: defaultdict(int))
    for r in extracted:
        g = r["genre_inferred"]
        for ct in r["composition"]["text_types"]:
            genre_comp_cross[g][ct] += 1
    
    # === 12. 题材×色彩交叉 ===
    genre_color_cross = defaultdict(lambda: defaultdict(int))
    for r in extracted:
        g = r["genre_inferred"]
        for c in r["color"]["main_colors"]:
            genre_color_cross[g][c] += 1
    
    # 计算平均分
    def avg_score(scores):
        return round(sum(scores) / len(scores), 1) if scores else 0
    
    # 组装输出
    output = {
        "version": "1.0.0",
        "generated_at": "2026-07-11",
        "source": f"{len(records)}条竞品封面分析",
        "languages_covered": LANGUAGES,
        
        "composition_stats": {
            ct: {
                "count": info["count"],
                "avg_score": avg_score(info["scores"]),
                "by_lang": dict(info["by_lang"]),
            }
            for ct, info in sorted(comp_stats.items(), key=lambda x: -x[1]["count"])
        },
        
        "color_stats": {
            c: {
                "count": info["count"],
                "avg_score": avg_score(info["scores"]),
                "by_lang": dict(info["by_lang"]),
            }
            for c, info in sorted(color_stats.items(), key=lambda x: -x[1]["count"])
        },
        
        "text_stats": {
            "has_text_distribution": text_count,
            "text_rate": round(text_count["有文字"] / len(records) * 100, 1),
            "top_positions": dict(text_positions.most_common(10)),
            "top_colors": dict(text_colors.most_common(10)),
        },
        
        "person_stats": {
            label: {
                "count": info["count"],
                "avg_score": avg_score(info["scores"]),
            }
            for label, info in sorted(person_count_stats.items(), key=lambda x: -x[1]["count"])
        },
        
        "prop_stats": dict(prop_counter.most_common(20)),
        
        "shot_type_stats": dict(shot_stats.most_common(10)),
        
        "genre_stats": {
            g: {
                "count": info["count"],
                "avg_score": avg_score(info["scores"]),
                "by_lang": dict(info["by_lang"]),
            }
            for g, info in sorted(genre_stats.items(), key=lambda x: -x[1]["count"])
        },
        
        "visual_hierarchy_stats": dict(hierarchy_counter.most_common(10)),
        
        "synergy_stats": dict(synergy_counter.most_common(10)),
        
        "lang_preferences": lang_preferences,
        
        "genre_composition_cross": {
            g: dict(comps) for g, comps in genre_comp_cross.items()
        },
        
        "genre_color_cross": {
            g: dict(colors) for g, colors in genre_color_cross.items()
        },
    }
    
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    
    print(f"\n✅ 输出到 {OUTPUT_FILE}")
    print(f"   文件大小: {os.path.getsize(OUTPUT_FILE) / 1024:.1f} KB")
    
    # 打印摘要
    print(f"\n📊 蒸馏摘要:")
    print(f"   总样本: {len(records)} 条")
    print(f"   构图类型: {len(comp_stats)} 种")
    print(f"   色彩方案: {len(color_stats)} 种")
    print(f"   题材类型: {len(genre_stats)} 种")
    print(f"   有文字比例: {output['text_stats']['text_rate']}%")
    print(f"   道具种类: {len(prop_counter)} 种")
    
    print(f"\n   构图TOP5:")
    for ct, info in list(sorted(comp_stats.items(), key=lambda x: -x[1]["count"]))[:5]:
        avg = avg_score(info["scores"])
        print(f"     {ct}: {info['count']}次, 爆款分{avg}")
    
    print(f"\n   色彩TOP5:")
    for c, info in list(sorted(color_stats.items(), key=lambda x: -x[1]["count"]))[:5]:
        avg = avg_score(info["scores"])
        print(f"     {c}: {info['count']}次, 爆款分{avg}")
    
    print(f"\n   题材TOP5:")
    for g, info in list(sorted(genre_stats.items(), key=lambda x: -x[1]["count"]))[:5]:
        avg = avg_score(info["scores"])
        print(f"     {g}: {info['count']}次, 爆款分{avg}")
    
    print(f"\n   道具TOP10:")
    for prop, count in prop_counter.most_common(10):
        print(f"     {prop}: {count}次")
    
    print(f"\n   语种偏好:")
    for lang, pref in lang_preferences.items():
        print(f"     {lang}({pref['sample_size']}条): 文字率{pref['text_rate']}%, 均{pref['avg_person_count']}人")

if __name__ == "__main__":
    run()
