---
title: VPS 短剧基础设施
type: architecture
tags:
  - vps
  - duanju
  - infrastructure
  - caddy
  - panel
  - telegram
date: '2026-06-30T00:00:00.000Z'
---
# VPS 短剧基础设施

## 服务器信息
- Host: 43.134.81.206
- User: ubuntu (非 root)
- System: Ubuntu 24.04, 1核, 1.9GB RAM, 50GB
- SSH: `ssh vps` (config alias, id_ed25519)

## 运行服务

### Caddy — 反代
- `duanju.opspilot.me → localhost:8009`
- systemd 管理: `systemctl status caddy`

### panel_v3.py — 短剧运营面板
- 端口: 8009
- 启动: `cd ~/duanju && venv/bin/python3 scripts/panel_v3.py --port 8009`
- 守护: `scripts/keep_alive.sh`（60秒巡检）
- 功能: 仪表盘、上架助手、账号分析、规则库、AI助手

### Hermes Gateway — duanju profile
- 命令: `hermes_cli.main --profile duanju gateway run`
- systemd 服务: `hermes-gateway-duanju.service`
- API Server: 端口 8642，key: `duanju-panel-2026`
- 模型: ark-code-latest (doubao)
- Telegram: ✅ 已配置（bot token 在 profile .env）
- 飞书: ✅ 已连接

## 项目结构 (`/home/ubuntu/duanju/`)
- `scripts/` — 80+ 脚本（panel_v3.py, daily_pipeline, diagnose_channel, distill_skill_v2 等）
- `config/` — 频道配置、模型路由、pipeline 配置
- `data/` — 核心数据（competitor_tiers, drama_db, yt_analytics 等）
- `distill/` — 蒸馏输出
- `output/` — 产出（titles, covers, videos）
- `knowledge/` — 多语种知识库（en/es/id/jp/pt/tr/繁中）
- `references/` — 专家规则（short-drama-expert, distribution-expert 等）
- `panel/frontend/dist/` — Vue 前端构建产物
- `panel/web/index_v3.html` — 备用单文件前端

## Profile 配置 (`~/.hermes/profiles/duanju/`)
- `config.yaml` — 模型、toolsets、gateway API server
- `.env` — TELEGRAM_BOT_TOKEN, GATEWAY_ALLOW_ALL_USERS=true
- `skills/duanju-youtube-expert/` — 短剧 YouTube 运营专家 Skill

## API Keys (VPS duanju/.env)
- MIMO_API_KEY, DEEPSEEK_API_KEY, ARK_API_KEY, ZYLOO_API_KEY
- WHISPER_MODEL=medium

## 自有频道 (data/own/our_channels.json)
| slug | name | market | operator |
|------|------|--------|----------|
| hk | 追劇姐妹 | hk | 张阳铸(点众) |
| en_global | Apocalyptic Films | en_global | 刘志龙(自运营) |
| en_moonlit | Moonlit Drama Studio | en_global | 张阳铸(点众) |
| es_latam | Luna Drama Estudio | es_latam | 张阳铸(点众) |
| br | DramaVerve | br | 刘志龙(自运营) |
| id | DramaCipher | id | 刘志龙(自运营) |

## YouTube OAuth (accounts.json)
- 已授权: hk (追劇姐妹), en_global (Apocalyptic Films)
- 未授权: en_moonlit, es_latam, br, id

## 面板 API 端点
| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/dashboard` | GET | 仪表盘概览 |
| `/api/outputs` | GET | 产出列表 |
| `/api/rules` | GET | 规则库 |
| `/api/analytics` | GET | 竞品频道分析 |
| `/api/generate` | POST | 上架助手（标题+封面） |
| `/api/generate-titles` | POST | 标题生成 |
| `/api/proposal` | POST | 提案 |
| `/api/proposal-history` | GET | 提案历史 |
| `/api/nuwa_chat` | POST | AI 助手对话 |
| `/api/yt-accounts` | GET | YouTube 账号列表 |
| `/api/yt-analytics` | GET | YouTube 数据分析 |
| `/api/channel-analysis` | GET | 频道分析 |
| `/api/competitor-channels` | GET | 竞品频道 |
| `/api/competitor-detail` | GET | 竞品详情 |
| `/api/distill` | GET | 蒸馏数据 |
| `/api/market-insights` | GET | 市场洞察 |

## 已知问题
- VPS 内存小(1.9GB)，不要跑重型任务
- nuwa_chat 需要 duanju agent (8642) 在线，否则 500
- 竞品频道分析数据依赖 `data/competitors_channels_all.json`（2.8MB）
- YouTube Analytics 需要先运行 `scripts/collect_yt_analytics.py` 采集
