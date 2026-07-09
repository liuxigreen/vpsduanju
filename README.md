# duanju：短剧出海内容操作系统

一句话定位：
**duanju 不是批量上传脚本，而是“2 个稳定 Nuwa 专家脑 + 1 个动态信号层 + 抽帧视频理解 + 可手动可自动执行面板 + 可切换模型路由”的操作系统。**

## 核心架构

- **Nuwa #1 内容策略脑**：`references/short-drama-expert/`
- **Nuwa #2 分发运营脑**：`references/distribution-expert/`
- **地区专家（繁体市场）**：`references/hk-traditional-market-expert/`
- **动态信号层（非 Nuwa）**：`scripts/signal_engine.py`
- **模型统一路由**：`scripts/model_router.py` + `config/model_registry.example.yaml`
- **Skill 路由**：`scripts/skill_router.py`

## 目录结构（重构后）

```text
duanju/
├── main.py
├── AGENTS.md
├── config/
│   ├── model_registry.example.yaml
│   ├── pipeline.example.yaml
│   └── distill_settings.example.yaml
├── panel/
│   └── panel_config.example.yaml
├── scripts/
│   ├── model_router.py
│   ├── skill_router.py
│   ├── build_manifest.py
│   ├── signal_engine.py
│   ├── update_channel_brain.py
│   ├── report_builder.py
│   ├── check_cover.py
│   ├── generate_title.py
│   ├── generate_cover.py
│   ├── edit_video.py
│   ├── translate_subtitle.py
│   ├── upload_youtube.py
│   ├── analyze_analytics.py
│   ├── analyze_comments.py
│   └── search_ad_materials.py
├── references/
│   ├── short-drama-expert/{SKILL.md,META.md}
│   ├── distribution-expert/{SKILL.md,META.md}
│   └── hk-traditional-market-expert/{SKILL.md,META.md}
├── distill/
│   ├── README.md
│   ├── prompts/
│   ├── sources/
│   ├── outputs/
│   ├── versions/
│   └── logs/
└── data/
    ├── drama_analysis/
    ├── ad_materials/
    ├── analytics/
    ├── comments/
    ├── channel_brain/
    └── manifests/
```

## 双 preset

- `fast_validation`：3~8 分钟快测，优先 CTR/30秒留存/评论反应。
- `full_rebuild`：5~15 分钟重构，默认看前30分钟，强调剧情一致性。

见：`config/pipeline.example.yaml`

## 默认视频理解路径

默认不整段喂大模型：

`视频 -> ffmpeg 抽帧 -> OCR/字幕 -> 帧理解 -> 汇总 -> 必要时再升重型视频模型`

见：`config/model_registry.example.yaml` policy

## 统一入口命令

```bash
python main.py analyze-video --input raw.mp4 --output data/drama_analysis/demo.json
python main.py ad-materials --drama-name "demo" --output data/ad_materials/demo.json
python main.py title --manifest data/manifests/demo_drama_hk.json
python main.py cover --manifest data/manifests/demo_drama_hk.json
python main.py edit --manifest data/manifests/demo_drama_hk.json
python main.py subtitle --manifest data/manifests/demo_drama_hk.json
python main.py upload --manifest data/manifests/demo_drama_hk.json
python main.py analytics --channel hk_main
python main.py comments --channel hk_main --video-id abc123
python main.py signal --channel hk_main
python main.py distill --scope weekly
python main.py run --panel panel/panel_config.example.yaml --preset fast_validation
python main.py run --panel panel/panel_config.example.yaml --preset full_rebuild
```

## 最小可跑通链路（本地离线骨架）

```bash
python main.py run --panel panel/panel_config.example.yaml --preset fast_validation
python main.py analytics --channel hk_main
python main.py comments --channel hk_main --video-id demo001
python main.py signal --channel hk_main
```

执行后可看到：
- `data/manifests/*.json`
- `output/titles/*.json`
- `output/covers/*.json`
- `data/analytics/*`
- `data/comments/*`
- `data/channel_brain/hk_main.json` 更新

## 封面提示词模式（Nuwa fallback）

在 `manifest` 增加 `cover_prompt_mode` 可调封面提示词策略（仅影响 Nuwa fallback 路径）：

- `strict`：合规优先（safe zone/FULL/标题区/虚化强约束）
- `balanced`：默认，合规与美感平衡
- `creative`：在不破坏硬规则前提下强调风格创意

示例：

```json
{
  "task_name": "demo_drama",
  "target_region": "hk",
  "preset": "full_rebuild",
  "cover_prompt_mode": "creative"
}
```

## distill 频率策略

- analytics/comments：daily 或 every 2 days
- weekly signal digest：每周
- mini-distill：每周
- full-distill：每月
- 事件触发：爆款 / 连续扑街 / CTR 突降 / 新地区 / 新题材
