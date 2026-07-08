#!/usr/bin/env python3
"""
封面自由分析模块 — 不预设规则，发现封面规律

功能：
- 自由分析封面特征（人物、道具、色彩、构图、文字）
- 只分析爆款视频的封面
- 根据数据发现规律，优化封面规范

注意：
- 不预设评分标准
- 让MiMo自由描述封面特征
- 根据数据发现规律
"""

import json
import base64
import urllib.request
from pathlib import Path
from typing import Optional

# MiMo v2.5 API配置
MIMO_API_KEY = ""


def load_config():
    """从Hermes配置中加载API key"""
    global MIMO_API_KEY
    import os
    
    # 优先从环境变量读取
    MIMO_API_KEY = os.environ.get("XIAOMI_API_KEY", "")
    
    # 如果环境变量没有，从.env文件读取
    if not MIMO_API_KEY:
        env_path = Path.home() / ".hermes" / ".env"
        if env_path.exists():
            content = env_path.read_text()
            import re
            match = re.search(r"XIAOMI_API_KEY=(.+)", content)
            if match:
                MIMO_API_KEY = match.group(1).strip()


def encode_image_from_url(url: str) -> Optional[str]:
    """从URL下载图片并编码为base64"""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=30) as response:
            image_data = response.read()
            return base64.b64encode(image_data).decode()
    except Exception as e:
        print(f"  ⚠️ 下载封面失败: {e}")
        return None


def analyze_cover_freely(image_url: str, title: str = "", views: int = 0) -> dict:
    """
    自由分析封面，不预设规则
    
    Args:
        image_url: 封面图片URL
        title: 视频标题
        views: 播放量（用于判断是否爆款）
    
    Returns:
        分析结果字典
    """
    if not MIMO_API_KEY:
        load_config()
    
    if not MIMO_API_KEY:
        return {"error": "未配置MiMo API key"}
    
    # 下载图片
    image_base64 = encode_image_from_url(image_url)
    if not image_base64:
        return {"error": "下载封面失败"}
    
    # 构建提示词 — 简洁版，避免输出过长被截断
    prompt = f"""分析这个YouTube短剧封面。返回JSON，每个字段1-2句话，总输出不超过200字。

标题：{title[:60]}
播放量：{views:,}

{{
  "人物": "数量、表情、服装、关系暗示",
  "色彩": "主色调、光影、情绪氛围",
  "构图": "布局类型、视线引导",
  "文字": "有无文字、内容、位置",
  "整体风格": "一句话描述风格和情绪",
  "爆款因素": {{"评分": "0-10", "原因": "为什么吸引点击"}}
}}"""

    # 调用MiMo v2.5 API
    try:
        url = f"https://token-plan-cn.xiaomimimo.com/v1/chat/completions"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {MIMO_API_KEY}"
        }
        data = {
            "model": "mimo-v2.5",
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{image_base64}"
                            }
                        }
                    ]
                }
            ],
            "max_tokens": 3000,
            "temperature": 0.3
        }
        
        req = urllib.request.Request(
            url,
            data=json.dumps(data).encode(),
            headers=headers,
            method="POST"
        )
        
        with urllib.request.urlopen(req, timeout=120) as response:
            result = json.loads(response.read().decode())
            
        # 解析响应 — MiMo返回markdown包装的JSON，可能截断
        content = result["choices"][0]["message"]["content"]
        import re

        # 1. 去掉代码块标记
        clean = re.sub(r'```(?:json)?\s*', '', content)
        clean = re.sub(r'\s*```', '', clean).strip()

        # 2. 提取最外层大括号内容
        start = clean.find('{')
        if start == -1:
            return {"error": "无JSON", "raw": content[:300]}

        # 3. 从前往后数括号，找到正确的闭合位置
        depth = 0
        end = -1
        for i in range(start, len(clean)):
            if clean[i] == '{':
                depth += 1
            elif clean[i] == '}':
                depth -= 1
                if depth == 0:
                    end = i
                    break

        if end == -1:
            # JSON被截断，尝试补全
            partial = clean[start:]
            # 尝试逐步补全闭合括号
            for closes in range(10):
                try:
                    analysis = json.loads(partial + '}' * (closes + 1))
                    break
                except json.JSONDecodeError:
                    continue
            else:
                return {"error": "JSON截断无法修复", "raw": content[:300]}
        else:
            raw_json = clean[start:end + 1]
            try:
                analysis = json.loads(raw_json)
            except json.JSONDecodeError:
                return {"error": "JSON解析失败", "raw": content[:300]}
        
        analysis["image_url"] = image_url
        analysis["title"] = title[:50]
        analysis["views"] = views
        return analysis
            
    except Exception as e:
        return {"error": f"API调用失败: {str(e)}"}


def analyze_breakout_covers(videos: list, max_count: int = 5) -> list:
    """
    分析爆款视频的封面
    
    Args:
        videos: 视频列表
        max_count: 最多分析的封面数量
    
    Returns:
        分析结果列表
    """
    # 筛选爆款视频（播放>均值3倍）
    if not videos:
        return []
    
    avg_views = sum(v.get("views", 0) for v in videos) / len(videos)
    breakout_videos = [v for v in videos if v.get("views", 0) > avg_views * 3]
    
    if not breakout_videos:
        # 如果没有爆款，取播放量最高的
        breakout_videos = sorted(videos, key=lambda x: x.get("views", 0), reverse=True)[:max_count]
    
    # 取前N个
    top_videos = breakout_videos[:max_count]
    
    results = []
    for i, video in enumerate(top_videos):
        thumbnail = video.get("thumbnail", "")
        if not thumbnail:
            continue
        
        print(f"    🖼️ 分析封面 [{i+1}/{len(top_videos)}]: {video.get('title', '')[:30]}...")
        
        analysis = analyze_cover_freely(
            image_url=thumbnail,
            title=video.get("title", ""),
            views=video.get("views", 0)
        )
        
        results.append(analysis)
    
    return results


def _extract_person_count(text: str) -> str:
    """从自由文本中提取人物数量类型"""
    if not isinstance(text, str):
        return "未知"
    import re
    # Check for explicit count mentions
    if re.search(r'(?:单人|一个人|一人|独自|独身)', text):
        return "单人"
    if re.search(r'(?:双人|两位|两人|一对|二位)', text):
        return "双人"
    if re.search(r'(?:多人|三位|三位|一群|数人|众人|人群)', text):
        return "多人"
    # Count pronouns/names as proxy
    names = re.findall(r'(?:一位|两位|三位|两位|男主|女主|男主角|女主角|男子|女子|青年|女子|男人|女人)', text)
    if len(names) >= 3:
        return "多人"
    elif len(names) == 2:
        return "双人"
    elif len(names) == 1:
        return "单人"
    return "未知"


def _extract_emotion(text: str) -> str:
    """从自由文本中提取主要情绪"""
    if not isinstance(text, str):
        return "无"
    import re
    emotions = {
        "冷峻": r"冷峻|冷漠|冷淡|冰冷|傲慢|高冷",
        "惊恐": r"惊恐|惊愕|惊慌|恐惧|害怕|震惊|错愕",
        "深情": r"深情|温柔|甜蜜|恩爱|含情|爱意|温情",
        "愤怒": r"愤怒|怒|激怒|暴怒|嗔怒|不满|怨恨",
        "坚定": r"坚定|决绝|果断|坚毅|刚毅|沉着",
        "无辜": r"无辜|委屈|楚楚|可怜|柔弱|泪眼",
        "对峙": r"对峙|对抗|挑衅|敌意|紧张|张力",
        "自信": r"自信|霸气|霸道|威严|气势|强势|盛气",
    }
    found = []
    for emotion, pattern in emotions.items():
        if re.search(pattern, text):
            found.append(emotion)
    return "/".join(found[:3]) if found else "无"


def _extract_color(text: str) -> str:
    """从自由文本中提取主色调"""
    if not isinstance(text, str):
        return "其他"
    import re
    colors = {
        "暖色调": r"暖色|暖黄|暖橙|橙色|暖光|金色|暖调",
        "冷色调": r"冷色|冷蓝|蓝色|冷调|暗蓝|深蓝",
        "粉紫色": r"粉色|粉紫|紫色|粉红|浪漫",
        "红色系": r"红色|大红|金红|朱红|暗红|红调",
        "暗色调": r"暗色|暗黑|暗调|深色|黑色|阴暗",
        "高对比": r"对比|冷暖|高饱和|鲜明|强烈",
        "自然色": r"自然|真实|朴素|清新|淡雅",
    }
    for color, pattern in colors.items():
        if re.search(pattern, text):
            return color
    return "其他"


def _extract_composition(text: str) -> str:
    """从自由文本中提取构图类型"""
    if not isinstance(text, str):
        return "其他"
    import re
    comps = {
        "中心构图": r"中心|居中|中央|中间|核心",
        "左右分割": r"左右|分割|对称|两侧|对立",
        "特写构图": r"特写|近景|close.?up|面部|脸部|大头",
        "中景构图": r"中景|半身|腰部以上",
        "对比构图": r"对比|反差|高矮|贫富|强弱",
        "引导线": r"引导|视线|路径|纵深|透视",
    }
    for comp, pattern in comps.items():
        if re.search(pattern, text):
            return comp
    return "其他"


def summarize_cover_patterns(cover_analyses: list) -> dict:
    """
    汇总封面分析结果，发现规律
    支持 str 和 dict 两种输入格式
    """
    if not cover_analyses:
        return {}
    
    person_counts = {"单人": 0, "双人": 0, "多人": 0, "无人": 0, "未知": 0}
    emotion_counts = {}
    prop_counts = {}
    color_counts = {}
    composition_counts = {}
    
    for analysis in cover_analyses:
        if "error" in analysis:
            continue
        
        # 人物 — 兼容 str 和 dict
        person = analysis.get("人物", "")
        if isinstance(person, dict):
            comp_type = person.get("数量", 0)
            try:
                comp_type = int(comp_type)
            except (ValueError, TypeError):
                comp_type = 0
            if comp_type == 1: person_counts["单人"] += 1
            elif comp_type == 2: person_counts["双人"] += 1
            elif comp_type > 2: person_counts["多人"] += 1
            else: person_counts["无人"] += 1
            emotion = person.get("表情", "无")
        else:
            person_str = str(person)
            category = _extract_person_count(person_str)
            person_counts[category] = person_counts.get(category, 0) + 1
            emotion = _extract_emotion(person_str)
        
        # 表情
        if isinstance(emotion, dict):
            emotion = "/".join(str(v) for v in emotion.values())
        elif isinstance(emotion, list):
            emotion = "/".join(str(v) for v in emotion)
        emotion = str(emotion)
        if emotion and emotion != "无":
            emotion_counts[emotion] = emotion_counts.get(emotion, 0) + 1
        
        # 道具 — 兼容 str 和 dict
        prop = analysis.get("道具", "")
        if isinstance(prop, dict):
            if prop.get("有无"):
                prop_type = str(prop.get("类型", "其他"))
                prop_counts[prop_type] = prop_counts.get(prop_type, 0) + 1
        else:
            prop_str = str(prop)
            if len(prop_str) > 10:  # has meaningful content
                import re
                prop_keywords = re.findall(r'(?:婚纱|西装|礼服|囚服|军装|古装|华服|手术刀|剑|刀|花|戒指|项链|王冠|权杖)', prop_str)
                if prop_keywords:
                    for pk in prop_keywords:
                        prop_counts[pk] = prop_counts.get(pk, 0) + 1
                else:
                    prop_counts["有道具"] = prop_counts.get("有道具", 0) + 1
        
        # 色彩 — 兼容 str 和 dict
        color = analysis.get("色彩", "")
        if isinstance(color, dict):
            main_color = str(color.get("主色调", "其他"))
        else:
            main_color = _extract_color(str(color))
        color_counts[main_color] = color_counts.get(main_color, 0) + 1
        
        # 构图 — 兼容 str 和 dict
        comp = analysis.get("构图", "")
        if isinstance(comp, dict):
            comp_layout = str(comp.get("布局", "其他"))
        else:
            comp_layout = _extract_composition(str(comp))
        composition_counts[comp_layout] = composition_counts.get(comp_layout, 0) + 1
    
    def _top(d):
        if not d: return "未知"
        return max(d.items(), key=lambda x: x[1])[0]
    
    return {
        "样本数": len(cover_analyses),
        "人物分布": person_counts,
        "最常见人物": _top(person_counts),
        "表情分布": emotion_counts,
        "最常见表情": _top(emotion_counts),
        "道具分布": prop_counts,
        "色彩分布": color_counts,
        "最常见色彩": _top(color_counts),
        "构图分布": composition_counts,
        "最常见构图": _top(composition_counts),
    }



# 测试代码
if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("用法: python cover_analyzer_free.py <image_url> [title] [views]")
        print("示例: python cover_analyzer_free.py 'https://i.ytimg.com/vi/xxx/hqdefault.jpg' 'CEO离婚' 10000")
        sys.exit(1)
    
    image_url = sys.argv[1]
    title = sys.argv[2] if len(sys.argv) > 2 else ""
    views = int(sys.argv[3]) if len(sys.argv) > 3 else 0
    
    print(f"🔍 自由分析封面: {image_url}")
    result = analyze_cover_freely(image_url, title, views)
    print(json.dumps(result, indent=2, ensure_ascii=False))
