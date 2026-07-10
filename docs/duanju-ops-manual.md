---
title: duanju 系统运维手册
type: concept
tags:
  - 运维
  - duanju
  - 面板
  - hermes
  - telegram
created: '2026-06-27T00:00:00.000Z'
updated: '2026-07-10T00:00:00.000Z'
---
# duanju 系统运维手册

## 系统架构

```
┌─────────────────────────────────────────────┐
│  duanju Hermes (duanju profile)             │
│  - Telegram: ✅ bot 已连接                   │
│  - 飞书: ✅ WebSocket 已连接                 │
│  - API Server: 8642 (key: <API_KEY>)        │
│  - 模型: ark-code-latest (doubao)           │
│  - systemd: hermes-gateway-duanju.service   │
└─────────────────────────────────────────────┘
                    │
                    │ API 调用 (http://127.0.0.1:8642)
                    ▼
┌─────────────────────────────────────────────┐
│  面板 (panel_v3.py)                         │
│  - 端口: 8009                               │
│  - 外网: duanju.opspilot.me (Caddy 反代)    │
│  - 守护: keep_alive.sh (60秒巡检)           │
└─────────────────────────────────────────────┘
```

## 端口分配

| 端口 | 服务 | 说明 |
|------|------|------|
| 8642 | duanju agent API | 面板 AI 功能调用 |
| 8009 | 面板 | Web 控制台 |

## 关键配置文件

### Profile config (`~/.hermes/profiles/duanju/config.yaml`)
```yaml
model:
  provider: custom:doubao
  default: ark-code-latest
custom_providers:
- name: doubao
  base_url: https://ark.cn-beijing.volces.com/api/plan/v3
  api_key: <YOUR_DOUBAO_API_KEY>
gateway:
  api_server:
    enabled: true
    port: 8642
    host: 127.0.0.1
    key: <YOUR_API_SERVER_KEY>
platforms:
  telegram:
    enabled: true
```

### Profile .env (`~/.hermes/profiles/duanju/.env`)
```
TELEGRAM_BOT_TOKEN=<YOUR_BOT_TOKEN>
GATEWAY_ALLOW_ALL_USERS=true
```

### 面板连接 duanju agent
```python
HERMES_API_URL = "http://127.0.0.1:8642/v1/chat/completions"
HERMES_API_KEY = "<YOUR_API_SERVER_KEY>"
```

## 启动/重启命令

### duanju agent (Hermes Gateway)
```bash
# systemd 管理
systemctl --user restart hermes-gateway-duanju
systemctl --user status hermes-gateway-duanju

# 查看日志
journalctl --user -u hermes-gateway-duanju -n 50 --no-pager
tail -50 ~/.hermes/profiles/duanju/logs/gateway.log
```

### 面板
```bash
# 重启
pkill -f panel_v3.py
cd ~/duanju && nohup venv/bin/python3 scripts/panel_v3.py --port 8009 > panel_v3.log 2>&1 &

# 查看日志
tail -50 ~/duanju/panel_v3.log
```

## 故障排查

### Telegram bot 没反应
1. 检查 gateway 日志: `tail -20 ~/.hermes/profiles/duanju/logs/gateway.log`
2. 确认 `✓ telegram connected` 在日志中
3. 确认 `.env` 有 `GATEWAY_ALLOW_ALL_USERS=true`（不是 `TELEGRAM_ALLOW_ALL_USERS`）
4. 新用户发 `/start` 后需要 pairing approve: `hermes --profile duanju pairing list`

### 面板 AI 功能 500
- duanju agent (8642) 没在线。检查: `curl http://127.0.0.1:8642/health`
- 重启: `systemctl --user restart hermes-gateway-duanju`

### 面板数据为空
- 竞品频道: 检查 `data/competitors_channels_all.json` 是否存在
- YouTube Analytics: 需先运行 `scripts/collect_yt_analytics.py`
- 频道分析: 检查 `data/own/channel_analysis_latest.json`

### 外网访问 502/522
- Caddy 反代问题。检查: `systemctl status caddy`
- 面板进程是否在跑: `lsof -ti:8009`

### Gateway 僵尸进程占 CPU
```bash
ps aux | grep hermes | grep -v grep
# 如果某个进程 CPU > 50% 且运行时间异常长
kill <PID>
systemctl --user restart hermes-gateway-duanju
```

## 数据采集脚本

| 脚本 | 用途 | 频率 |
|------|------|------|
| `scripts/collect_yt_analytics.py` | YouTube 频道数据采集 | 每周 |
| `scripts/daily_pipeline.py` | 每日数据管线 | 每天 |
| `scripts/diagnose_channel.py` | 频道诊断 | 按需 |
| `scripts/distill_skill_v2.py` | 蒸馏分析 | 每周 |
| `scripts/channel_weekly_snapshot.py` | 频道周快照 | 每周 |
| `scripts/drama_db_builder.py` | 剧本数据库构建 | 按需 |
