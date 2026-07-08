#!/usr/bin/env python3
"""
快速配音合成测试：把配音音频叠加到视频上
用法：python3 scripts/quick_dub_test.py --ep 1
"""
import json, subprocess, sys, os, argparse
from pathlib import Path

DUB_DIR = Path("/Users/liuxi/Desktop/youtube/末日倒计时_en/dub_en")
VIDEO = Path("/Users/liuxi/Desktop/youtube/末日倒计时_en/merged_compressed.mp4")
OUTPUT = Path("/tmp/dub_test_ep01.mp4")

def get_ep01_range(dub_files):
    """找到EP01的时间范围（前N条，直到时间跳变）"""
    ep01 = []
    for i, item in enumerate(dub_files):
        ep01.append(item)
        # EP01大约2分钟，看前120秒
        end_s = sum(int(x) * m for x, m in zip(item["end"].replace(",", ":").split(":"), [3600, 60, 1, 0.001]))
        if end_s > 120:
            break
    return ep01

def build_filter(ep01_items):
    """构建ffmpeg filter_complex：把配音wav按时间码叠加"""
    # 先把所有配音文件按时间码拼成一个长音频
    inputs = []
    filter_parts = []
    
    for i, item in enumerate(ep01_items):
        fpath = item["file"]
        if not os.path.exists(fpath):
            continue
        inputs.extend(["-i", fpath])
        start_ms = sum(int(x) * m for x, m in zip(item["start"].replace(",", ":").split(":"), [3600, 60, 1, 0.001]))
        # adelay: 延迟start_ms毫秒
        filter_parts.append(f"[{i}]adelay={int(start_ms*1000)}|{int(start_ms*1000)}[d{i}]")
    
    # 混合所有配音轨
    mix_inputs = "".join(f"[d{i}]" for i in range(len(filter_parts)))
    filter_parts.append(f"{mix_inputs}amix=inputs={len(filter_parts)}:duration=first:dropout_transition=0[dubbed]")
    
    return inputs, ";".join(filter_parts)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--ep", type=int, default=1, help="Episode number")
    parser.add_argument("--duration", type=int, default=130, help="Duration in seconds")
    args = parser.parse_args()
    
    # 加载配音文件列表
    with open(DUB_DIR / "dub_files.json") as f:
        all_items = json.load(f)
    
    ep01 = get_ep01_range(all_items)
    print(f"📝 EP01 配音条目: {len(ep01)}")
    print(f"⏱️ 时间范围: {ep01[0]['start']} → {ep01[-1]['end']}")
    
    # 构建ffmpeg命令
    inputs, filter_str = build_filter(ep01)
    
    cmd = [
        "ffmpeg", "-y",
        "-i", str(VIDEO),  # 视频输入
        *inputs,            # 配音文件输入
        "-filter_complex", filter_str,
        "-map", "0:v",      # 用原视频画面
        "-map", "[dubbed]", # 用混合后的配音
        "-t", str(args.duration),
        "-c:v", "copy",
        "-c:a", "aac", "-b:a", "128k",
        str(OUTPUT)
    ]
    
    print(f"\n🎬 合成中...")
    print(f"命令: {' '.join(cmd[:10])}...")
    
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    if result.returncode == 0:
        size_mb = OUTPUT.stat().st_size / 1024 / 1024
        print(f"\n✅ 完成: {OUTPUT} ({size_mb:.1f}MB)")
    else:
        print(f"\n❌ 失败: {result.stderr[-500:]}")

if __name__ == "__main__":
    main()
