#!/usr/bin/env python3
"""
配音音频混合脚本 v2：先预混合所有配音到单个WAV，再叠加到视频
用法：python3 scripts/mix_dub_audio.py --video merged.mp4 --dub-files dub_files.json --output dubbed.mp4
"""
import json, subprocess, sys, os, argparse, tempfile, wave, struct
from pathlib import Path

# imageio-ffmpeg路径
import imageio_ffmpeg
FFMPEG_EXE = imageio_ffmpeg.get_ffmpeg_exe()

def srt_time_to_seconds(t):
    """SRT时间码 → 秒"""
    t = t.replace(",", ".")
    parts = t.split(":")
    return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])

def get_video_duration(video_path):
    """获取视频时长"""
    cmd = [FFMPEG_EXE, "-i", str(video_path), "-f", "null", "-"]
    result = subprocess.run(cmd, capture_output=True, text=True)
    for line in result.stderr.split('\n'):
        if 'Duration:' in line:
            duration_str = line.split('Duration:')[1].split(',')[0].strip()
            parts = duration_str.split(':')
            return float(parts[0]) * 3600 + float(parts[1]) * 60 + float(parts[2])
    return 1800.0  # 默认30分钟

def pre_mix_dub_audio(dub_items, output_wav, sample_rate=24000):
    """
    把所有配音文件按时间码混合成单个WAV文件
    这样避免ffmpeg打开太多文件
    """
    # 计算总时长
    max_end = 0
    for item in dub_items:
        end_s = srt_time_to_seconds(item["end"])
        if end_s > max_end:
            max_end = end_s
    
    total_samples = int(max_end * sample_rate) + sample_rate  # 多1秒缓冲
    print(f"  📊 总时长: {max_end:.1f}s, 采样数: {total_samples}")
    
    # 创建静音缓冲区
    mix_buffer = [0] * total_samples
    
    valid_count = 0
    for item in dub_items:
        fpath = item["file"]
        if not os.path.exists(fpath):
            continue
        
        try:
            with wave.open(fpath, 'rb') as w:
                if w.getframerate() != sample_rate:
                    continue  # 跳过采样率不匹配的
                frames = w.getnframes()
                raw = w.readframes(frames)
                samples = struct.unpack(f'<{frames}h', raw)
                
                start_s = srt_time_to_seconds(item["start"])
                start_idx = int(start_s * sample_rate)
                
                # 混合到缓冲区
                for i, s in enumerate(samples):
                    idx = start_idx + i
                    if idx < total_samples:
                        mix_buffer[idx] += s
                        # 防止削波
                        if mix_buffer[idx] > 32767:
                            mix_buffer[idx] = 32767
                        elif mix_buffer[idx] < -32768:
                            mix_buffer[idx] = -32768
                valid_count += 1
        except Exception as e:
            continue
    
    print(f"  📝 混合了 {valid_count} 个配音文件")
    
    # 写入WAV文件
    with wave.open(output_wav, 'wb') as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(sample_rate)
        out.writeframes(struct.pack(f'<{total_samples}h', *mix_buffer))
    
    size_mb = Path(output_wav).stat().st_size / 1024 / 1024
    print(f"  ✅ 预混合完成: {output_wav} ({size_mb:.1f}MB)")
    return output_wav

def mix_with_video(video_path, dub_wav, output_path, original_vol=0.15, dub_vol=1.2):
    """把预混合的配音WAV叠加到视频上"""
    cmd = [
        FFMPEG_EXE, "-y",
        "-i", str(video_path),
        "-i", str(dub_wav),
        "-filter_complex",
        f"[0:a]volume={original_vol}[orig];"
        f"[1:a]volume={dub_vol}[dub];"
        f"[orig][dub]amix=inputs=2:duration=longest:dropout_transition=0[aout]",
        "-map", "0:v",
        "-map", "[aout]",
        "-c:v", "copy",
        "-c:a", "aac", "-b:a", "192k",
        "-shortest",
        str(output_path)
    ]
    
    print(f"  🎬 混合到视频...")
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    if result.returncode == 0:
        size_mb = Path(output_path).stat().st_size / 1024 / 1024
        print(f"  ✅ 完成: {output_path} ({size_mb:.1f}MB)")
        return True
    else:
        print(f"  ❌ 失败: {result.stderr[-300:]}")
        return False

def main():
    parser = argparse.ArgumentParser(description="配音音频混合 v2")
    parser.add_argument("--video", required=True, help="输入视频路径")
    parser.add_argument("--dub-files", required=True, help="配音文件列表JSON")
    parser.add_argument("--output", required=True, help="输出视频路径")
    parser.add_argument("--original-vol", type=float, default=0.15, help="原声音量 (0.0-1.0)")
    parser.add_argument("--dub-vol", type=float, default=1.0, help="配音音量 (0.0-1.0)")
    parser.add_argument("--max-items", type=int, default=0, help="最大配音条数 (0=全部)")
    parser.add_argument("--keep-wav", action="store_true", help="保留预混合WAV文件")
    args = parser.parse_args()
    
    # 加载配音文件列表
    with open(args.dub_files) as f:
        dub_items = json.load(f)
    
    if args.max_items > 0:
        dub_items = dub_items[:args.max_items]
    
    print(f"📹 视频: {args.video}")
    print(f"🎙️ 配音: {len(dub_items)} 条")
    print(f"🔊 原声音量: {args.original_vol}")
    print(f"🔊 配音音量: {args.dub_vol}")
    
    # 1. 预混合配音音频
    dub_wav = Path(args.output).with_suffix('.dub.wav')
    print(f"\n📦 步骤1: 预混合配音音频...")
    pre_mix_dub_audio(dub_items, str(dub_wav))
    
    # 2. 混合到视频
    print(f"\n📦 步骤2: 混合到视频...")
    success = mix_with_video(args.video, dub_wav, args.output, args.original_vol, args.dub_vol)
    
    # 清理
    if not args.keep_wav and dub_wav.exists():
        dub_wav.unlink()
        print(f"  🗑️ 清理临时文件")
    
    if not success:
        sys.exit(1)

if __name__ == "__main__":
    main()
