"""
video_editor 的验证模块
每步完成后调用对应 verify，不合格则报错重做
"""

import os, re, subprocess, json
from pathlib import Path

FFMPEG = str(Path.home() / "bin" / "ffmpeg")


def ffprobe_info(path):
    r = subprocess.run([FFMPEG, "-i", str(path)], capture_output=True, text=True)
    out = r.stderr
    info = {"width": 0, "height": 0, "duration": 0}
    m = re.search(r"Duration:\s*(\d+):(\d+):(\d+\.\d+)", out)
    if m: info["duration"] = int(m.group(1))*3600 + int(m.group(2))*60 + float(m.group(3))
    m = re.search(r"(\d{3,4})x(\d{3,4})", out)
    if m: info["width"], info["height"] = int(m.group(1)), int(m.group(2))
    return info


def verify_merge(merged_path, episodes_dir):
    """验证合并结果"""
    checks = []
    if not merged_path.exists():
        return False, "文件不存在"

    info = ffprobe_info(merged_path)
    mb = merged_path.stat().st_size / (1024*1024)

    # 检查分辨率
    if info["width"] == 0 or info["height"] == 0:
        checks.append("⚠️ 无法读取分辨率")
    else:
        checks.append(f"✅ 分辨率 {info['width']}x{info['height']}")

    # 检查时长（应 > 30分钟）
    if info["duration"] < 1800:
        checks.append(f"⚠️ 时长仅 {info['duration']/60:.1f}分钟，可能漏集")
    else:
        checks.append(f"✅ 时长 {info['duration']/60:.1f}分钟")

    # 检查大小（应 > 1GB）
    if mb < 500:
        checks.append(f"⚠️ 文件仅 {mb:.0f}MB，可能损坏")
    else:
        checks.append(f"✅ 大小 {mb:.0f}MB")

    ok = not any("⚠️" in c for c in checks)
    return ok, "\n    ".join(checks)


def verify_subtitles(srt_path, min_segments=50):
    """验证字幕文件"""
    checks = []
    if not srt_path.exists():
        return False, "字幕文件不存在"

    with open(srt_path) as f:
        content = f.read()

    # 检查格式
    segments = content.count("-->")
    if segments < min_segments:
        checks.append(f"⚠️ 仅 {segments} 段（期望 >{min_segments}）")
    else:
        checks.append(f"✅ {segments} 个字幕段")

    # 检查时间戳格式
    timestamps = re.findall(r"(\d{2}:\d{2}:\d{2},\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2},\d{3})", content)
    if not timestamps:
        checks.append("⚠️ 无有效时间戳")
    else:
        checks.append(f"✅ {len(timestamps)} 个有效时间戳")

    # 检查最大时间戳（应接近视频时长）
    if timestamps:
        last_ts = timestamps[-1][1]
        h, m, s = last_ts.split(":")
        last_sec = int(h)*3600 + int(m)*60 + float(s.replace(",","."))
        if last_sec < 60:
            checks.append(f"⚠️ 最后时间戳仅 {last_sec:.0f}s，可能不完整")
        else:
            checks.append(f"✅ 覆盖到 {last_sec/60:.1f}分钟")

    # 抽样检查内容非空
    lines = [l.strip() for l in content.split("\n") if l.strip() and "-->" not in l and not l.strip().isdigit()]
    non_empty = sum(1 for l in lines if len(l) > 1)
    empty_ratio = 1 - non_empty / max(len(lines), 1)
    if empty_ratio > 0.3:
        checks.append(f"⚠️ {empty_ratio*100:.0f}% 空行")
    else:
        checks.append(f"✅ 内容充实（{non_empty}/{len(lines)} 行有内容）")

    ok = not any("⚠️" in c for c in checks)
    return ok, "\n    ".join(checks)


def verify_translation(analysis_json, min_translated_ratio=0.8):
    """验证翻译+角色分析结果"""
    checks = []
    if not analysis_json.exists():
        return False, "分析文件不存在"

    with open(analysis_json) as f:
        data = json.load(f)

    chars = data.get("characters", {})
    subs = data.get("subtitles", [])

    # 检查角色
    if len(chars) < 2:
        checks.append(f"⚠️ 仅 {len(chars)} 个角色，可能遗漏")
    else:
        checks.append(f"✅ {len(chars)} 个角色: {', '.join(chars.keys())}")

    # 检查翻译覆盖率
    translated = sum(1 for s in subs if s.get("tr","").strip())
    ratio = translated / max(len(subs), 1)
    if ratio < min_translated_ratio:
        checks.append(f"⚠️ 翻译率 {ratio*100:.0f}%（期望 >{min_translated_ratio*100}%）")
    else:
        checks.append(f"✅ 翻译率 {ratio*100:.0f}%")

    # 检查角色标注
    char_assigned = sum(1 for s in subs if s.get("char","") and s["char"] != "旁白")
    char_ratio = char_assigned / max(len(subs), 1)
    if char_ratio < 0.3:
        checks.append(f"⚠️ 角色标注率仅 {char_ratio*100:.0f}%")
    else:
        checks.append(f"✅ 角色标注率 {char_ratio*100:.0f}%")

    # 检查情绪标注
    emotions = set(s.get("emotion","normal") for s in subs)
    checks.append(f"✅ {len(emotions)} 种情绪: {', '.join(sorted(emotions))}")

    # 抽样翻译质量（检查是否包含中文 = 翻译失败）
    chinese_in_trans = sum(1 for s in subs if re.search(r"[\u4e00-\u9fff]", s.get("tr","")))
    if chinese_in_trans > len(subs) * 0.1:
        checks.append(f"⚠️ {chinese_in_trans} 条翻译含中文，可能未翻译")
    else:
        checks.append(f"✅ 翻译质量OK（{chinese_in_trans} 条含中文）")

    ok = not any("⚠️" in c for c in checks)
    return ok, "\n    ".join(checks)


def verify_delogo(original_path, delogo_path):
    """验证字幕隐藏效果"""
    checks = []
    if not delogo_path.exists():
        return False, "文件不存在"

    orig_size = original_path.stat().st_size / (1024*1024)
    new_size = delogo_path.stat().st_size / (1024*1024)

    # 大小不应差太多（±30%）
    ratio = new_size / max(orig_size, 1)
    if ratio < 0.3 or ratio > 2.0:
        checks.append(f"⚠️ 大小异常: {new_size:.0f}MB vs 原始 {orig_size:.0f}MB")
    else:
        checks.append(f"✅ 大小合理: {new_size:.0f}MB")

    info = ffprobe_info(delogo_path)
    if info["duration"] < 100:
        checks.append(f"⚠️ 时长仅 {info['duration']:.0f}s")
    else:
        checks.append(f"✅ 时长 {info['duration']/60:.1f}分钟")

    ok = not any("⚠️" in c for c in checks)
    return ok, "\n    ".join(checks)


def verify_dubbing(audio_files, min_files=10):
    """验证配音结果"""
    checks = []
    if len(audio_files) < min_files:
        checks.append(f"⚠️ 仅 {len(audio_files)} 段配音（期望 >{min_files}）")
    else:
        checks.append(f"✅ {len(audio_files)} 段配音")

    # 检查文件大小
    total_size = 0
    empty = 0
    for af in audio_files:
        p = af["file"] if isinstance(af, dict) else af
        if os.path.exists(p):
            sz = os.path.getsize(p)
            total_size += sz
            if sz < 100: empty += 1
    if empty > len(audio_files) * 0.1:
        checks.append(f"⚠️ {empty} 个空文件")
    else:
        checks.append(f"✅ 总大小 {total_size/(1024*1024):.1f}MB")

    # 检查角色分布
    chars = {}
    for af in audio_files:
        c = af.get("char", "unknown") if isinstance(af, dict) else "unknown"
        chars[c] = chars.get(c, 0) + 1
    checks.append(f"✅ 角色分布: {json.dumps(chars, ensure_ascii=False)}")

    ok = not any("⚠️" in c for c in checks)
    return ok, "\n    ".join(checks)


def verify_final(video_path):
    """验证最终输出"""
    checks = []
    if not video_path.exists():
        return False, "文件不存在"

    info = ffprobe_info(video_path)
    mb = video_path.stat().st_size / (1024*1024)

    # 检查分辨率
    if info["width"] != 1080 or info["height"] != 1920:
        checks.append(f"⚠️ 分辨率 {info['width']}x{info['height']}（期望 1080x1920）")
    else:
        checks.append(f"✅ 分辨率 1080x1920")

    # 检查大小（YouTube 推荐 < 2GB for 10 min, < 10GB for 1hr）
    if mb > 5000:
        checks.append(f"⚠️ {mb:.0f}MB 过大，上传会很慢")
    else:
        checks.append(f"✅ 大小 {mb:.0f}MB")

    # 检查时长
    checks.append(f"✅ 时长 {info['duration']/60:.1f}分钟")

    # 检查编码
    r = subprocess.run([FFMPEG, "-i", str(video_path)], capture_output=True, text=True)
    if "h264" in r.stderr.lower() or "avc" in r.stderr.lower():
        checks.append("✅ H.264 编码")
    else:
        checks.append("⚠️ 非 H.264 编码，YouTube 处理会更慢")

    if "aac" in r.stderr.lower():
        checks.append("✅ AAC 音频")
    else:
        checks.append("⚠️ 非 AAC 音频")

    ok = not any("⚠️" in c for c in checks)
    return ok, "\n    ".join(checks)


# ─── 综合验证入口 ─────────────────────────────────────
def run_verify(step, **kwargs):
    """运行指定步骤的验证"""
    verifiers = {
        "merge": lambda: verify_merge(kwargs["merged"], kwargs["episodes_dir"]),
        "subtitles": lambda: verify_subtitles(kwargs["srt"]),
        "translation": lambda: verify_translation(kwargs["analysis_json"]),
        "delogo": lambda: verify_delogo(kwargs["original"], kwargs["delogo"]),
        "dubbing": lambda: verify_dubbing(kwargs["audio_files"]),
        "final": lambda: verify_final(kwargs["video"]),
    }

    if step not in verifiers:
        return True, "无验证器"

    ok, msg = verifiers[step]()
    status = "✅ PASS" if ok else "❌ FAIL"
    print(f"\n  [{step.upper()} 验证] {status}")
    print(f"    {msg}")
    return ok, msg
