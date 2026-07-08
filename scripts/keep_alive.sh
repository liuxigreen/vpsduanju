#!/bin/bash
# duanju 面板守护脚本
# 每60秒检查面板，自动重启
# 隧道由 launchd 管理 (com.cloudflare.cloudflared)，不在此脚本中维护

while true; do
  # 检查面板
  if ! lsof -ti:8009 > /dev/null 2>&1; then
    echo "[$(date)] 面板未运行，重启..."
    cd ~/duanju && nohup python3 scripts/panel_v3.py --port 8009 > /dev/null 2>&1 &
  fi

  sleep 60
done
