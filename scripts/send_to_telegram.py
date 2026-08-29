#!/usr/bin/env python3
"""发送文件到Telegram"""

import os
import sys
from pathlib import Path
import requests

# 读取token
env_file = Path.home() / '.hermes' / '.env'
token = None
if env_file.exists():
    for line in env_file.read_text().split('\n'):
        if line.startswith('TELEGRAM_BOT_TOKEN='):
            token = line.split('=', 1)[1].strip()
            break

if not token:
    print("❌ 未找到TELEGRAM_BOT_TOKEN")
    sys.exit(1)

# 读取chat_id
chat_id = os.environ.get('TELEGRAM_HOME_CHANNEL', '6305628029')

# 发送文件
file_path = Path(__file__).resolve().parent.parent / 'output' / 'dream_drama_analysis.html'
if not file_path.exists():
    print(f"❌ 文件不存在: {file_path}")
    sys.exit(1)

url = f"https://api.telegram.org/bot{token}/sendDocument"
with open(file_path, 'rb') as f:
    files = {'document': f}
    data = {
        'chat_id': chat_id,
        'caption': '📊 Dream Drama 竞品分析报告\n\n请用浏览器打开HTML文件，然后Ctrl+P打印为PDF'
    }
    resp = requests.post(url, files=files, data=data)

if resp.status_code == 200 and resp.json().get('ok'):
    print("✅ 已发送到Telegram")
else:
    print(f"❌ 发送失败: {resp.text[:200]}")
