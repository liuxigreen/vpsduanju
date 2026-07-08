#!/usr/bin/env python3
"""
封面分析模块 — 使用MiMo v2.5视觉能力分析YouTube视频封面

分析维度（参考运营总监封面规范）：
- 人物特写：面部是否清晰，占比是否≥60%
- 情绪表达：是否有情绪化表情（惊讶/愤怒/甜蜜）
- 关键道具：是否包含与冲突相关的道具
- 色彩搭配：主色调是否与题材情绪匹配
- 文字标签：是否有简洁的题材词标签
- 构图建议：是否符合双人对峙/中心聚焦等构图

注意：这些规范来自distill/outputs/operations-director_v0.md
需要随着数据积累不断验证和优化
"""

import json
import base64
import urllib.request
from pathlib import Path
from typing import Optional

# MiMo v2.5 API配置
MIMO_API_KEY = ""  # 从config.yaml读取
MIMO_BASE_URL = "https://token-plan-cn.xiaomimimo.com/v1"


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
    
    # 如果还是没有，从config.yaml读取
    if not MIMO_API_KEY:
        config_path = Path.home() / ".hermes" / "config.yaml"
        if config_path.exists():
            content = config_path.read_text()
            match = re.search(r"api_key:\s*['\"]?(sk-[^'\"\\s]+)['\"]?", content)
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


def analyze_cover(image_url: str, title: str = "", genre: str = "") -> dict:
    """
    分析单个封面图片
    
    Args:
        image_url: 封面图片URL
        title: 视频标题（用于关联分析）
        genre: 题材类型（用于判断封面规范）
    
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
    
    # 构建提示词（参考运营总监封面规范）
    prompt = f"""分析这个YouTube视频封面，给出以下维度的评分（0-10分）和建议：

1. **人物特写**：面部是否清晰？占比是否≥60%？
2. **情绪表达**：是否有情绪化表情（惊讶/愤怒/甜蜜/坚定）？
3. **关键道具**：是否包含与冲突相关的道具（如DNA报告、婚戒、股权转让书）？
4. **色彩搭配**：主色调是否与题材情绪匹配？（如虐恋用冷色调，甜宠用暖色调）
5. **文字标签**：是否有简洁的题材词标签（如"重生"、"逆袭"、"豪门"）？
6. **构图质量**：是否符合专业构图（双人对峙/中心聚焦/左右分割）？

视频标题：{title[:60]}
题材类型：{genre}

请用JSON格式返回：
{{
    "person_score": 8,
    "person_detail": "面部清晰，占比约70%",
    "emotion_score": 7,
    "emotion_detail": "表情坚定，有冲突感",
    "prop_score": 5,
    "prop_detail": "未见明显道具",
    "color_score": 8,
    "color_detail": "冷色调，符合虐恋题材",
    "text_score": 3,
    "text_detail": "无题材词标签",
    "composition_score": 7,
    "composition_detail": "中心聚焦构图，突出人物",
    "overall_score": 6.3,
    "suggestions": ["添加题材词标签", "增加关键道具元素"]
}}"""

    # 调用MiMo v2.5 API
    try:
        url = f"{MIMO_BASE_URL}/chat/completions"
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
            "max_tokens": 1000,
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
            
        # 解析响应
        content = result["choices"][0]["message"]["content"]
        
        # 尝试提取JSON
        import re
        json_match = re.search(r'\{[\s\S]*\}', content)
        if json_match:
            analysis = json.loads(json_match.group())
            analysis["image_url"] = image_url
            return analysis
        else:
            return {"error": "无法解析响应", "raw": content}
            
    except Exception as e:
        return {"error": f"API调用失败: {str(e)}"}


def analyze_channel_covers(videos: list, genre: str = "", max_count: int = 5) -> dict:
    """
    分析频道的封面质量
    
    Args:
        videos: 视频列表（需要包含thumbnail字段）
        genre: 频道主要题材
        max_count: 最多分析的封面数量
    
    Returns:
        分析结果汇总
    """
    if not videos:
        return {"error": "无视频数据"}
    
    # 筛选有封面的视频
    videos_with_cover = [v for v in videos if v.get("thumbnail")]
    if not videos_with_cover:
        return {"error": "无封面数据"}
    
    # 按播放量排序，取前N个
    sorted_videos = sorted(videos_with_cover, key=lambda x: x.get("views", 0), reverse=True)
    top_videos = sorted_videos[:max_count]
    
    results = []
    for i, video in enumerate(top_videos):
        print(f"  🖼️ 分析封面 {i+1}/{len(top_videos)}: {video.get('title', '')[:30]}...")
        analysis = analyze_cover(
            image_url=video["thumbnail"],
            title=video.get("title", ""),
            genre=genre
        )
        analysis["video_title"] = video.get("title", "")[:50]
        analysis["views"] = video.get("views", 0)
        results.append(analysis)
    
    # 汇总统计
    valid_results = [r for r in results if "error" not in r]
    if not valid_results:
        return {"error": "所有封面分析失败", "details": results}
    
    # 计算平均分
    scores = {
        "person": [r.get("person_score", 0) for r in valid_results],
        "emotion": [r.get("emotion_score", 0) for r in valid_results],
        "prop": [r.get("prop_score", 0) for r in valid_results],
        "color": [r.get("color_score", 0) for r in valid_results],
        "text": [r.get("text_score", 0) for r in valid_results],
        "composition": [r.get("composition_score", 0) for r in valid_results],
        "overall": [r.get("overall_score", 0) for r in valid_results],
    }
    
    avg_scores = {}
    for key, values in scores.items():
        avg_scores[f"avg_{key}_score"] = round(sum(values) / len(values), 1) if values else 0
    
    # 收集所有建议
    all_suggestions = []
    for r in valid_results:
        all_suggestions.extend(r.get("suggestions", []))
    
    # 统计最常见的建议
    from collections import Counter
    suggestion_counter = Counter(all_suggestions)
    top_suggestions = [s for s, _ in suggestion_counter.most_common(3)]
    
    return {
        "analyzed_count": len(valid_results),
        "avg_scores": avg_scores,
        "top_suggestions": top_suggestions,
        "details": results,
    }


def generate_cover_diagnostics(cover_analysis: dict) -> list:
    """
    基于封面分析生成诊断建议
    
    Args:
        cover_analysis: analyze_channel_covers的返回结果
    
    Returns:
        诊断建议列表
    """
    if "error" in cover_analysis:
        return []
    
    issues = []
    avg_scores = cover_analysis.get("avg_scores", {})
    
    # 人物特写评分
    person_score = avg_scores.get("avg_person_score", 0)
    if person_score < 6:
        issues.append({
            "severity": "major",
            "category": "封面",
            "issue": f"人物特写不足（平均{person_score}分）",
            "detail": "面部不清晰或占比<60%，影响观众识别",
            "action": "① 封面人物面部必须清晰，占画面60%以上\n② 使用情绪化面部特写（惊讶/愤怒/甜蜜表情）\n③ 参考爆款视频的封面构图"
        })
    
    # 情绪表达评分
    emotion_score = avg_scores.get("avg_emotion_score", 0)
    if emotion_score < 6:
        issues.append({
            "severity": "major",
            "category": "封面",
            "issue": f"情绪表达不足（平均{emotion_score}分）",
            "detail": "封面缺乏情绪张力，无法吸引点击",
            "action": "① 封面必须有情绪化表情（惊讶/愤怒/甜蜜/坚定）\n② 使用冷暖对比光强化情绪\n③ 参考短剧专家SDE-011：CEO/豪门首选双人对峙型封面"
        })
    
    # 关键道具评分
    prop_score = avg_scores.get("avg_prop_score", 0)
    if prop_score < 5:
        issues.append({
            "severity": "info",
            "category": "封面",
            "issue": f"关键道具缺失（平均{prop_score}分）",
            "detail": "封面缺乏与冲突相关的道具元素",
            "action": "① 添加关键道具（DNA报告、婚戒、股权转让书）\n② 道具置于视觉焦点附近\n③ 参考运营总监封面规范：服装反差 > 关键道具 > 场景暗示"
        })
    
    # 文字标签评分
    text_score = avg_scores.get("avg_text_score", 0)
    if text_score < 5:
        issues.append({
            "severity": "info",
            "category": "封面",
            "issue": f"文字标签缺失（平均{text_score}分）",
            "detail": "封面缺乏题材词标签，不利于算法识别",
            "action": "① 添加简洁的题材词标签（如'重生'、'逆袭'、'豪门'）\n② 字体需小且不喧宾夺主\n③ 参考运营总监封面规范：文字标签为可选元素"
        })
    
    # 整体评分
    overall_score = avg_scores.get("avg_overall_score", 0)
    if overall_score < 6:
        issues.append({
            "severity": "major",
            "category": "封面",
            "issue": f"封面整体质量偏低（平均{overall_score}分）",
            "detail": "封面设计需要优化，影响CTR",
            "action": "① 参考运营总监封面规范\n② 分析爆款视频的封面特征\n③ 使用AI工具生成封面草稿，再人工优化"
        })
    
    return issues


# 测试代码
if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("用法: python cover_analyzer.py <image_url> [title] [genre]")
        print("示例: python cover_analyzer.py 'https://i.ytimg.com/vi/xxx/hqdefault.jpg' 'CEO离婚' '总裁'")
        sys.exit(1)
    
    image_url = sys.argv[1]
    title = sys.argv[2] if len(sys.argv) > 2 else ""
    genre = sys.argv[3] if len(sys.argv) > 3 else ""
    
    print(f"🔍 分析封面: {image_url}")
    result = analyze_cover(image_url, title, genre)
    print(json.dumps(result, indent=2, ensure_ascii=False))
