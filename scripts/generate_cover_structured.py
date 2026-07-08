#!/usr/bin/env python3
"""
generate_cover_structured.py — 基于 operations-director 生成 AI 封面指令

输入：
  data/materials_structured/{剧名}.json
  distill/outputs/operations-director/rules.json
  distill/outputs/operations-director/evidence.json
输出：
  output/covers_structured/{剧名}_{region}.json

每条方案包含10要素：
  主体、冲突、道具、场景、构图、色彩、标题区、必须保留、可牺牲、禁止
"""

import argparse
import json
import sys
from pathlib import Path
from datetime import datetime

BASE = Path(__file__).parent.parent
sys.path.insert(0, str(BASE / "scripts"))
from nuwa_api import nuwa_chat

def load_json(p: Path, default=None):
    if not p.exists():
        return default
    return json.loads(p.read_text(encoding="utf-8"))

def select_conflicts(material: dict, rules: dict, n: int = 3) -> list:
    """从素材冲突中选最符合题材的"""
    conflicts = material.get("main_conflict", [])
    genre = material.get("target_audience", "女频")
    mapping = {cm["conflict"]: cm for cm in rules.get("conflict_mapping", [])}
    scored = []
    for c in conflicts:
        ctype = c.get("type", "")
        score = 0
        if ctype in mapping:
            score = 5
        elif any(g in genre for g in ["豪门", "总裁"]):
            if ctype in ["真假千金身份反转", "重生复仇", "契约婚姻"]:
                score = 4
        scored.append((score, c))
    scored.sort(key=lambda x: -x[0])
    return [c for _, c in scored[:n]]

# ═══════════════════════════════════════════════════════════════════════
# 旧版 prompt（保留向后兼容，供 panel_v3 原有 action="cover" 使用）
# ═══════════════════════════════════════════════════════════════════════
def build_cover_prompt_legacy(material: dict, rules: dict, evidence: dict) -> str:
    """原版 prompt（含像素坐标/HEX，用于历史兼容）"""
    # 这里可以放回原来的逻辑，但为节省篇幅暂时留空占位
    # 实际使用中 panel_v3 的 cover action 会走这里
    return build_cover_prompt_v2(material, rules, evidence)["jimeng"]

# ═══════════════════════════════════════════════════════════════════════
# 新版双版本 prompt 生成器
# ═══════════════════════════════════════════════════════════════════════
def build_cover_prompt_v2(material: dict, rules: dict, evidence: dict, cover_prompt_mode: str = "balanced", aspect_ratio: str = "16:9") -> dict:
    """
    返回两个版本的 prompt 字典：
    {
      "jimeng": "...",   # 即梦5.0专用（697字，去坐标/HEX）
      "gpt":   "...",   # GPT/DALL-E 3专用（1800字，保留艺术术语与HEX）
    }

    cover_prompt_mode: "strict" | "balanced" | "creative"
      - strict  : 严谨港风，规则优先，不冒险
      - balanced: 平衡港风（默认），合规与美感兼顾
      - creative: 创意突破，允许风格化光影和构图实验

    aspect_ratio: "16:9"（桌面横幅）或 "9:16"（手机封面）
    """
    drama = material["drama_name"]
    genre = material.get("target_audience", "女頻")
    emotion = material.get("emotion", "懸疑")

    # ── 根据 aspect_ratio 确定比例描述 ─────────────────────────────────────
    if aspect_ratio == "9:16":
        ratio_desc = "9:16竖版比例，手机封面尺寸"
        ratio_note = "注意：竖版构图，人物垂直居中，上下留出标题区和safe zone"
    else:
        ratio_desc = "16:9横版比例，桌面横幅尺寸"
        ratio_note = "注意：横版构图，左右冷暖分割优先，底部标题区约15%"

    # ── 根据 cover_prompt_mode 确定风格基调 ─────────────────────────────────
    mode_style = {
        "strict":   "严谨港风：严格遵循30+条铁律，-safe zone/FULL标签/标题区/背景虚化每项显式标注，不冒险。",
        "balanced": "平衡港风：先满足硬规则，再提升镜头叙事和情绪张力，适度光影对比。",
        "creative": "创意港风：在满足硬规则前提下允许风格化光影实验，强化三区过渡的视觉冲击，色彩更浓郁。",
    }.get(cover_prompt_mode, "平衡港风：先满足硬规则，再提升镜头叙事和情绪张力。")

    # 构图手法根据 mode 微调
    composition_note = {
        "strict":   "构图采用经典左右分割（左冷右暖），边界清晰不模糊。",
        "balanced": "构图首选左右冷暖分割，交界光晕柔和过渡，可尝试中心放射或纵深引导。",
        "creative": "构图强化三区并置的破碎感，交界处可有轻微光斑溢出，增强时空错位。",
    }.get(cover_prompt_mode, "构图首选左右冷暖分割，交界光晕柔和过渡。")

    # 光影强度描述
    lighting_tones = {
        "strict":   "中等到强对比，光影明确不实验",
        "balanced": "强对比，光影层次丰富",
        "creative": "极高对比，暗金+酒红/金黄+纯白/土褐→琥珀渐变，光影可溢出边界",
    }.get(cover_prompt_mode, "强对比，光影层次丰富")

    # ── 即梦版：去坐标/HEX/px，强化亚洲面容+港风描述 ─────────────────────
    jimeng = f'''即梦5.0封面指令 — 《{drama}》

三幕合一构图。三方案共用骨架，仅色彩权重和光影强度不同。

三幕元素（固定）：
左区（第1幕）：女主半透明 + 生锈铲子 + DNA半露 + 假坟光斑（极度虚化）
中区（第2幕）：女主清晰 + 假千右边缘震惊 + 黑卡反光 + 奢侈品包 + 股权书飘落 + 金黄光斑
右区（第3幕）：男主虚化 + 红酒飞溅 + 西装外套披肩 + 假千左边缘被推倒 + 暗金酒红光斑

构图：{ratio_desc}。三区并置（左约1/4、中约44%、右约31%），{composition_note} 背景极度虚化琥珀金bokeh。

女主面部：水平居中偏上（留标题区），面积≥60%。亚洲面容，港星气质（类似蔡卓妍/周冬雨清冷感，TVB质感）。同一张脸三幕光影分区：左土褐逆光、中金黄主光、右暗金侧逆光。面部清晰，不可遮挡。

道具Z字流：
起点左下→生锈铲子
→邻右→DNA报告
→中央焦点→黑卡
→空中→股权书飘落模糊
→右区高潮→红酒飞溅动态
→披肩→西装外套
→右边缘→假千金（惊恐<15%）
→假千金手→奢侈品包

三方案色彩（根据 mode 微调）：
A（护妻）：暗金+酒红 {lighting_tones}。权重：红酒 > 西装 > DNA
B（打脸）：金黄+纯白闪耀 {lighting_tones}。权重：黑卡 > 股权 > DNA
C（觉醒）：土褐→琥珀渐变 {lighting_tones}。权重：铲子 > DNA > 黑卡

标题区：底部约15%高度（全宽），深色渐变背景，剧名艺术字。左上角"FULL EPISODES"胶囊（半透明）。

必须保留：女主面部≥60%（同一张脸）、七道具全出现、三区柔和过渡、标题区完整。{ratio_note}

禁止：画面坐标/箭头/文字、清晰建筑/家具、假千面>女主30%、竖向比例（仅限16:9时）、标题区内放人脸。

{ratio_desc}，横向构图。'''

    # ── GPT版：碎片化时空错位，艺术术语，保留HEX ─────────────────────

    # ── GPT版：碎片化时空错位，艺术术语，保留HEX ─────────────────────
    # 根据 aspect_ratio 和 mode 调整描述
    gpt_aspect_note = "9:16 vertical mobile cover" if aspect_ratio == "9:16" else "16:9 horizontal widescreen"
    gpt_mode_hint = {
        "strict":   "strict compliance, conservative lighting, no experimental composition",
        "balanced": "balanced compliance and aesthetic, moderate contrast, classic Hong Kong style",
        "creative": "creative flair, experimental lighting, stronger color saturation, shattered glass effect emphasized",
    }.get(cover_prompt_mode, "balanced compliance and aesthetic")

    gpt = f'''AI Cover Prompt — \"{drama}\" (GPT/DALL-E 3)

Shattered glass collage, {gpt_aspect_note}. Fuse Acts 1-3 into temporal-misalignment with transparency overlays. East Asian actress resembling Hong Kong stars (Angela Yuen / Zhou Dongyu), realistic. Style: {gpt_mode_hint}.

Act 1 (Left zone): Teen protagonist semi-transparent + rusty shovel + DNA half-buried + soil bokeh.
Act 2 (Center): Protagonist sharp focus + false heiress (right edge, shocked) + black card raised specular + luxury bag + floating docs + golden bokeh.
Act 3 (Right): Male lead Ke Han soft-focus silhouette + wine splash frozen + suit coat draped + false heiress toppled + dark gold/wine-red lighting.

Composition: Three overlapping glass panes cracked but fused. Light bleed at cracks with feathered edges. Background: abstract circular bokeh (amber, 60-80% opacity).

Face: Centered upper third, min 60% area. East Asian Hong Kong actress natural beauty. Tri-zone Rembrandt: left earthy fill 30%, center golden key 80%, right rim dark gold + wine-red 50%.

Props Z-flow:
1. Shovel bottom-left
2. DNA report right adjacent
3. Black card center-upper specular
4. Floating docs 2-3 sheets
5. Wine splash arc motion blur
6. Suit coat draped right shoulder
7. False heiress right edge (<15% frame)
8. Luxury bag in hand subtle logo

Variants:
A (Protect): Dark Gold (#B8860B) + Wine Red (#722F37) high contrast. Chiaroscuro rim light. Weights: Wine > Suit > DNA.
B (Face-Slap): Pure Gold (#FFD700) + White (#FFFFFF) dazzling. High-key sparkling bokeh. Weights: Black Card > Docs > DNA.
C (Awakening): Earth Brown (#8B7355) -> Amber (#FFBF00) gradient. Diagonal sweep lighting. Weights: Shovel > DNA > Black Card.

Technical: 1280x720 ({aspect_ratio}). Title zone bottom 15% metallic shadow. FULL EPISODES capsule top-left. Abstract bokeh background only. No text/UI except title zone.'''

    return {"jimeng": jimeng, "gpt": gpt}

# ═══════════════════════════════════════════════════════════════════════
# 主流程（保持与原脚本接口一致）
# ═══════════════════════════════════════════════════════════════════════
def generate_covers(drama_name: str, region: str = "hk", version: str = "both", cover_prompt_mode: str = "balanced", aspect_ratio: str = "16:9"):
    """
    生成封面方案

    Args:
      version: "legacy" | "optimized" | "both"
      cover_prompt_mode: "strict" | "balanced" | "creative"
      aspect_ratio: "16:9" (desktop banner) | "9:16" (mobile cover)
    """
    material_path = BASE / "data" / "materials_structured" / f"{drama_name}.json"
    rules_path = BASE / "distill" / "outputs" / "operations-director" / "rules.json"
    evidence_path = BASE / "distill" / "outputs" / "operations-director" / "evidence.json"

    if not material_path.exists():
        raise FileNotFoundError(f"请先运行 material_structurer: {material_path}")
    if not rules_path.exists():
        raise FileNotFoundError(f"请先运行 distill_operations_director: {rules_path}")

    material = load_json(material_path)
    rules = load_json(rules_path, {})
    evidence = load_json(evidence_path, {})

    print(f"🎬 生成封面: {drama_name} | mode={cover_prompt_mode} | ratio={aspect_ratio}")

    if version in ("optimized", "both"):
        prompts = build_cover_prompt_v2(material, rules, evidence, cover_prompt_mode=cover_prompt_mode, aspect_ratio=aspect_ratio)
        for key, p in prompts.items():
            print(f"[{key.upper()}] Prompt length: {len(p)} chars")

        # 返回优化版结构（不经过女娲，直接输出 prompt 文本供面板使用）
        out_dir = BASE / "output" / "covers_structured"
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"{drama_name}_{region}_optimized.json"

        output = {
            "drama_name": drama_name,
            "region": region,
            "generated_at": datetime.utcnow().isoformat() + "Z",
            "source": "operations-director + structured v2",
            "prompts": prompts,  # {"jimeng": "...", "gpt": "..."}
            "input_files": {
                "material": str(material_path),
                "rules": str(rules_path),
                "evidence": str(evidence_path),
            },
        }
        out_path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"✅ 优化版 prompt 已保存: {out_path}")
        return out_path

    if version == "legacy":
        prompt = build_cover_prompt_legacy(material, rules, evidence)
        print(f"Prompt length: {len(prompt)} chars")

        resp = nuwa_chat(prompt, max_tokens=8000, rotate=False, json_mode=True, timeout=240)
        print(f"女娲返回: {len(resp)} chars")

        import re
        resp_clean = re.sub(r'```json\s*', '', resp, flags=re.IGNORECASE)
        resp_clean = re.sub(r'\s*```', '', resp_clean).strip()
        start = resp_clean.find('{')
        end = resp_clean.rfind('}') + 1
        json_str = resp_clean[start:end] if start != -1 and end != -1 else resp_clean

        try:
            data = json.loads(json_str)
        except json.JSONDecodeError as e:
            print("JSON解析失败:", e)
            print("--- JSON片段（后500字）---")
            print(json_str[-500:])
            try:
                fixed = json_str + "}]}"
                data = json.loads(fixed)
                print("⚠️  尝试补全结构成功（输出可能不完整）")
            except:
                raise

        out_dir = BASE / "output" / "covers_structured"
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"{drama_name}_{region}.json"

        output = {
            "drama_name": drama_name,
            "region": region,
            "generated_at": datetime.utcnow().isoformat() + "Z",
            "source": "operations-director + nuwa",
            "candidates": data.get("candidates", []),
            "input_files": {
                "material": str(material_path),
                "rules": str(rules_path),
                "evidence": str(evidence_path),
            },
        }
        out_path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"✅ 封面方案已保存: {out_path}")
        print(f"   候选方案: {len(output['candidates'])} 个")
        return out_path

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--drama", required=True, help="剧名")
    parser.add_argument("--region", default="hk", help="地区 (hk/tw/sg/mo)")
    parser.add_argument("--version", default="both", choices=["legacy", "optimized", "both"],
                        help="生成版本：legacy(旧版)/optimized(仅优化prompt)/both(都生成)")
    args = parser.parse_args()

    try:
        out = generate_covers(args.drama, args.region, version=args.version)
        if args.version in ("optimized", "both"):
            # 仅输出 prompt 文件，无需解析 candidates
            print(f"\n提示词已生成，可直接复制使用：")
            data = json.loads(open(out).read())
            for k, v in data["prompts"].items():
                print(f"  [{k.upper()}] {len(v)} 字")
        else:
            data = json.loads(open(out).read())
            for i, c in enumerate(data["candidates"], 1):
                print(f"\n方案{i}: {c.get('style','')} | {c.get('text_overlay','')}")
                print(f"  主体: {c.get('subject','')[:60]}")
                print(f"  构图: {c.get('composition','')} | 色彩: {c.get('color_scheme','')}")
                print(f"  冲突: {', '.join(c.get('conflict',[])[:2])}")
                print(f"  必须保留: {', '.join(c.get('must_keep',[])[:3])}")
    except Exception as e:
        print(f"❌ 失败: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
