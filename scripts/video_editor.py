#!/usr/bin/env python3
"""
短剧出海 · 剪辑师工作台 v3
==========================
竖屏短剧专用 (1080x1920)
"""

import os, sys, json, glob, re, asyncio, argparse, subprocess, tempfile, base64, time
from pathlib import Path
from datetime import datetime

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

from video_verify import run_verify
import requests

# ─── 配置 ──────────────────────────────────────────────
DEEPSEEK_KEY = os.getenv("DEEPSEEK_API_KEY")
DEEPSEEK_URL = "https://api.edgefn.net/v1/chat/completions"
DEEPSEEK_MODEL = "DeepSeek-V4-Flash"

MIMO_KEY = os.getenv("MIMO_API_KEY")
MIMO_URL = "https://token-plan-cn.xiaomimimo.com/v1/chat/completions"

WHISPER_MODEL = os.getenv("WHISPER_MODEL", "medium")
OUTPUT_DIR = Path.home() / "Desktop" / "youtube"
FFMPEG = str(Path.home() / "bin" / "ffmpeg")

# ─── 语言配置 ──────────────────────────────────────────
LANG_CFG = {
    "en": {"name": "英文", "wl": "en",
           "style": "FontName=Arial,FontSize=22,PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,Outline=2,MarginV=30"},
    "id": {"name": "印尼文", "wl": "id",
           "style": "FontName=Arial,FontSize=22,PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,Outline=2,MarginV=30"},
}

EMOTION_ZH = {
    "angry":"愤怒","sad":"悲伤","happy":"开心","tender":"温柔",
    "scared":"恐惧","surprised":"惊喜","cold":"冷漠","anxious":"紧张","normal":""
}


# ─── 工具 ──────────────────────────────────────────────
def ffprobe_info(path):
    """用 ffmpeg -i 解析视频信息"""
    r = subprocess.run([FFMPEG, "-i", str(path)], capture_output=True, text=True)
    out = r.stderr
    info = {"width": 0, "height": 0, "duration": 0, "video": "", "audio": ""}
    m = re.search(r"Duration:\s*(\d+):(\d+):(\d+\.\d+)", out)
    if m:
        info["duration"] = int(m.group(1))*3600 + int(m.group(2))*60 + float(m.group(3))
    m = re.search(r"Video:\s*(\w+)", out)
    if m: info["video"] = m.group(1)
    m = re.search(r"(\d{3,4})x(\d{3,4})", out)
    if m:
        info["width"] = int(m.group(1))
        info["height"] = int(m.group(2))
    m = re.search(r"Audio:\s*(\w+)", out)
    if m: info["audio"] = m.group(1)
    return info


def log(msg):
    print(msg, flush=True)


# ─── Step 1: 合并 ─────────────────────────────────────
def merge(ep_dir, out):
    log("\n📹 Step 1: 合并分集...")
    files = []
    for p in ["*.mp4","*.MP4","*.mov"]:
        files = sorted(glob.glob(os.path.join(ep_dir, p)))
        if files: break
    if not files:
        log(f"❌ 未找到视频: {ep_dir}"); return None
    log(f"  {len(files)} 个分集")

    concat = tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False)
    for f in files:
        concat.write(f"file '{f}'\n")
    concat.close()

    subprocess.run([FFMPEG, "-y", "-f", "concat", "-safe", "0",
                    "-i", concat.name, "-c", "copy", str(out)],
                   capture_output=True)
    os.unlink(concat.name)

    if out.exists():
        mb = out.stat().st_size / (1024*1024)
        dur = ffprobe_info(str(out))["duration"]
        log(f"  ✅ {mb:.0f}MB, {dur/60:.1f}分钟")
        return out
    log("  ❌ 合并失败"); return None


# ─── Step 2: 提取字幕 ─────────────────────────────────
def find_existing_subtitles(episodes_dir, video_path):
    """检查是否有自带字幕文件或内嵌字幕"""
    log("\n🔍 Step 2a: 检查已有字幕...")

    # 1. 检查外部字幕文件
    sub_exts = ["*.srt", "*.ass", "*.ssa", "*.vtt"]
    for ext in sub_exts:
        subs = sorted(glob.glob(os.path.join(episodes_dir, ext)))
        if subs:
            log(f"  ✅ 找到 {len(subs)} 个外部字幕文件: {ext}")
            # 合并所有字幕文件
            merged = []
            for srt_file in subs:
                with open(srt_file, encoding="utf-8", errors="ignore") as f:
                    merged.append(f.read())
            return "\n\n".join(merged), "external"

    # 2. 检查视频内嵌字幕
    r = subprocess.run([FFMPEG, "-i", str(video_path)], capture_output=True, text=True)
    sub_streams = []
    for line in r.stderr.split("\n"):
        if "Subtitle:" in line or ("Stream #" in line and "sub" in line.lower()):
            sub_streams.append(line.strip())

    if sub_streams:
        log(f"  ✅ 找到内嵌字幕: {len(sub_streams)} 条流")
        # 提取第一条字幕流
        extracted_srt = str(video_path).replace(".mp4", "_embedded.srt")
        subprocess.run([
            FFMPEG, "-y", "-i", str(video_path),
            "-map", "0:s:0", extracted_srt
        ], capture_output=True)
        if os.path.exists(extracted_srt):
            with open(extracted_srt) as f:
                return f.read(), "embedded"

    log("  ℹ️ 无已有字幕，将使用 Whisper 提取")
    return None, None


def extract(video, srt, lang="zh", episodes_dir=None):
    """提取字幕：优先用已有文件，没有才跑 Whisper"""
    # 先检查已有字幕
    if episodes_dir:
        content, source = find_existing_subtitles(episodes_dir, video)
        if content:
            with open(srt, "w") as f:
                f.write(content)
            segs = content.count("-->")
            log(f"  ✅ 使用{source}字幕: {segs} 段 (跳过 Whisper)")
            return srt

    log(f"\n🎤 Step 2b: Whisper 提取字幕 (模型: {WHISPER_MODEL})...")
    subprocess.run([
        sys.executable, "-m", "whisper", str(video),
        "--model", WHISPER_MODEL, "--language", lang,
        "--output_format", "srt",
        "--output_dir", str(srt.parent),
        "--verbose", "False"
    ], capture_output=True)

    whisper_out = srt.parent / (video.stem + ".srt")
    if whisper_out != srt and whisper_out.exists():
        whisper_out.rename(srt)

    if srt.exists():
        with open(srt) as f:
            segs = sum(1 for l in f if "-->" in l)
        log(f"  ✅ {segs} 个字幕段")
        return srt
    log("  ❌ 失败"); return None


# ─── Step 3: 翻译 + 角色分析 ──────────────────────────
def translate_analyze(srt, lang, out_json):
    lang_name = LANG_CFG[lang]["name"]
    log(f"\n🌐 Step 3: 翻译+角色分析 ({lang_name})...")

    with open(srt) as f:
        content = f.read()
    blocks = [b.strip() for b in content.strip().split("\n\n") if b.strip()]
    total = len(blocks)
    log(f"  {total} 个字幕段")

    # 解析所有字幕
    parsed = []
    for block in blocks:
        lines = block.split("\n")
        if len(lines) >= 3 and "-->" in lines[1]:
            idx = int(lines[0]) if lines[0].isdigit() else 0
            ts = lines[1]
            text = "\n".join(lines[2:])
            parsed.append({"idx": idx, "ts": ts, "zh": text})

    # 先分析前80句识别角色
    sample = "\n".join(f"{i+1}. {p['zh']}" for i, p in enumerate(parsed[:80]))
    char_prompt = f"""分析以下中文短剧字幕，识别所有说话角色。

为每个角色生成英文音色描述（用于AI语音合成TTS），要区分明显：
- 年龄段（20s/30s/40s/50s/teen）
- 性格（温柔/冷酷/阳光/阴沉…）
- 音色特点（磁性/甜美/沙哑/清亮…）

输出纯JSON：
{{
    "角色名": {{"gender": "M/F", "desc": "English voice description for TTS voicing"}}
}}

字幕：
{sample}"""

    resp = requests.post(DEEPSEEK_URL,
        headers={"Authorization": f"Bearer {DEEPSEEK_KEY}", "Content-Type": "application/json"},
        json={"model": DEEPSEEK_MODEL, "messages": [{"role": "user", "content": char_prompt}],
              "max_tokens": 2048, "temperature": 0.3}, timeout=60)

    characters = {}
    if resp.status_code == 200:
        txt = resp.json()["choices"][0]["message"]["content"]
        try:
            js = txt[txt.index("{"):txt.rindex("}")+1]
            characters = json.loads(js)
            log(f"  识别到 {len(characters)} 个角色:")
            for n, v in characters.items():
                log(f"    {n} ({v.get('gender','?')}): {v.get('desc','')[:60]}")
        except: characters = {"旁白": {"gender":"N","desc":"neutral narrator"}}

    # 分批翻译+标注
    char_list = ", ".join(characters.keys())
    batch = 30
    subtitles = []

    for i in range(0, total, batch):
        chunk = parsed[i:i+batch]
        txts = [p["zh"] for p in chunk]
        prompt = f"""翻译中文字幕为{lang_name}，标注角色和情绪。

角色：{char_list}
情绪：angry/sad/happy/tender/scared/surprised/cold/anxious/normal

每行一条：角色|情绪|翻译
保持行数一致（{len(txts)}行）

{chr(10).join(f'{j+1}. {t}' for j,t in enumerate(txts))}"""

        resp = requests.post(DEEPSEEK_URL,
            headers={"Authorization": f"Bearer {DEEPSEEK_KEY}", "Content-Type": "application/json"},
            json={"model": DEEPSEEK_MODEL, "messages": [{"role": "user", "content": prompt}],
                  "max_tokens": 4096, "temperature": 0.3}, timeout=60)

        if resp.status_code == 200:
            lines = resp.json()["choices"][0]["message"]["content"].strip().split("\n")
            for j, p in enumerate(chunk):
                if j < len(lines):
                    parts = lines[j].split("|", 2)
                    if len(parts) == 3:
                        ch, em, tr = parts[0].strip(), parts[1].strip().lower(), parts[2].strip()
                    else:
                        ch, em, tr = "旁白", "normal", lines[j].strip()
                else:
                    ch, em, tr = "旁白", "normal", ""

                # 解析时间戳
                ts_parts = p["ts"].split("-->")
                subtitles.append({
                    "idx": p["idx"],
                    "start": ts_parts[0].strip() if len(ts_parts)>=2 else "",
                    "end": ts_parts[1].strip() if len(ts_parts)>=2 else "",
                    "zh": p["zh"], "tr": tr,
                    "char": ch, "emotion": em
                })
        else:
            for p in chunk:
                ts_parts = p["ts"].split("-->")
                subtitles.append({"idx": p["idx"],
                    "start": ts_parts[0].strip() if len(ts_parts)>=2 else "",
                    "end": ts_parts[1].strip() if len(ts_parts)>=2 else "",
                    "zh": p["zh"], "tr": "", "char": "旁白", "emotion": "normal"})
            log(f"  ⚠️ API错误 {resp.status_code}")

        log(f"  进度: {min(i+batch, total)}/{total}")

    result = {"characters": characters, "subtitles": subtitles}
    with open(out_json, "w") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    log(f"  ✅ 完成: {len(subtitles)} 条, {len(characters)} 角色")
    return result


# ─── Step 4: 隐藏原字幕 ───────────────────────────────
def hide_subs(inp, out, rect=None):
    log("\n🔲 Step 4: 隐藏原字幕...")
    info = ffprobe_info(str(inp))
    w, h = info["width"], info["height"]

    # 竖屏 1080x1920 字幕通常在底部
    if rect:
        p = rect.split(":")
        sx,sy,sw,sh = int(p[0]),int(p[1]),int(p[2]),int(p[3])
    else:
        sh = int(h * 0.10)  # 竖屏字幕区域相对小
        sy = h - sh - int(h * 0.03)
        sx = int(w * 0.10)
        sw = int(w * 0.80)

    log(f"  {w}x{h} → delogo x={sx} y={sy} w={sw} h={sh}")

    subprocess.run([
        FFMPEG, "-y", "-i", str(inp),
        "-vf", f"delogo=x={sx}:y={sy}:w={sw}:h={sh}:show=false",
        "-c:a", "copy", "-c:v", "libx264", "-preset", "fast", "-crf", "20",
        str(out)
    ], capture_output=True)

    if out.exists():
        mb = out.stat().st_size / (1024*1024)
        log(f"  ✅ {mb:.0f}MB")
        return out
    log("  ❌ 失败"); return None


# ─── Step 5: MiMo 角色音色设计 ─────────────────────────
def design_voices(characters):
    log("\n🎨 Step 5: 角色音色设计...")
    vmap = {}
    for name, info in characters.items():
        desc = info.get("desc", f"A voice for {name}")
        log(f"  {name}: {desc[:50]}...")
        resp = requests.post(MIMO_URL,
            headers={"Authorization": f"Bearer {MIMO_KEY}", "Content-Type": "application/json"},
            json={"model": "mimo-v2.5-tts-voicedesign",
                  "messages": [
                      {"role": "user", "content": desc},
                      {"role": "assistant", "content": "I am ready to perform."}
                  ], "stream": False},
            timeout=30)
        if resp.status_code == 200:
            msg = resp.json()["choices"][0]["message"]
            if "audio" in msg and isinstance(msg["audio"], dict) and "data" in msg["audio"]:
                vmap[name] = msg["audio"]
                log(f"    ✅")
            else: vmap[name] = None
        else:
            vmap[name] = None
            log(f"    ❌ {resp.status_code}")
    return vmap


# ─── Step 6: AI配音 ───────────────────────────────────
def dub(analysis, vmap, out_dir):
    log("\n🎙️ Step 6: AI配音 (MiMo)...")
    subs = analysis["subtitles"]
    files = []
    stats = {}

    for i, s in enumerate(subs):
        text = s["tr"]
        char = s["char"]
        emotion = s["emotion"]
        if not text.strip(): continue

        stats[char] = stats.get(char, 0) + 1

        emo_tag = ""
        if emotion and emotion != "normal":
            zh = EMOTION_ZH.get(emotion, "")
            if zh: emo_tag = f"<style>{zh}</style>"

        content = f"{emo_tag}{text}"
        vd = vmap.get(char)

        if vd and isinstance(vd, dict) and "data" in vd:
            msgs = [
                {"role": "user", "content": f"Say this: {text}"},
                {"role": "assistant", "content": content, "audio": vd}
            ]
        else:
            msgs = [
                {"role": "user", "content": text},
                {"role": "assistant", "content": content, "audio": {"voice": "mimo_default"}}
            ]

        try:
            resp = requests.post(MIMO_URL,
                headers={"Authorization": f"Bearer {MIMO_KEY}", "Content-Type": "application/json"},
                json={"model": "mimo-v2.5-tts", "messages": msgs, "stream": False},
                timeout=30)
            if resp.status_code == 200:
                msg = resp.json()["choices"][0]["message"]
                if "audio" in msg and isinstance(msg["audio"], dict) and "data" in msg["audio"]:
                    audio = base64.b64decode(msg["audio"]["data"])
                    af = os.path.join(out_dir, f"dub_{i:05d}.wav")
                    with open(af, "wb") as f:
                        f.write(audio)
                    files.append({"idx": i, "file": af, "start": s["start"],
                                  "end": s["end"], "char": char, "emotion": emotion})
        except Exception as e:
            log(f"  ⚠️ #{i}: {e}")

        if (i+1) % 50 == 0:
            log(f"  进度: {i+1}/{len(subs)}")

    log(f"  ✅ {len(files)} 段配音")
    for c, n in sorted(stats.items(), key=lambda x: -x[1]):
        log(f"    {c}: {n}句")
    return files


# ─── Step 7: 烧录字幕 ─────────────────────────────────
def burn(video, analysis, out, cfg):
    log("\n🎬 Step 7: 烧录字幕...")
    srt = str(out).replace(".mp4", "_clean.srt")
    with open(srt, "w") as f:
        for i, s in enumerate(analysis["subtitles"]):
            f.write(f"{i+1}\n{s['start']} --> {s['end']}\n{s['tr']}\n\n")

    style = cfg["style"]
    subprocess.run([
        FFMPEG, "-y", "-i", str(video),
        "-vf", f"subtitles={srt}:force_style='{style}'",
        "-c:v", "libx264", "-preset", "fast", "-crf", "20",
        "-c:a", "copy", str(out)
    ], capture_output=True)

    if out.exists():
        mb = out.stat().st_size / (1024*1024)
        dur = ffprobe_info(str(out))["duration"]
        log(f"  ✅ {mb:.0f}MB, {dur/60:.1f}分钟")
        return out
    log("  ❌ 失败"); return None


# ─── 主流程 ────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--drama", required=True)
    ap.add_argument("--episodes", required=True)
    ap.add_argument("--lang", default="en")
    ap.add_argument("--dub", action="store_true")
    ap.add_argument("--skip-merge", action="store_true")
    ap.add_argument("--merged")
    ap.add_argument("--delogo-rect")
    args = ap.parse_args()

    if args.lang not in LANG_CFG:
        log(f"❌ 不支持: {args.lang}"); return
    if not DEEPSEEK_KEY: log("❌ 缺 DEEPSEEK_API_KEY"); return
    if args.dub and not MIMO_KEY: log("❌ 缺 MIMO_API_KEY"); return

    cfg = LANG_CFG[args.lang]
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    wd = OUTPUT_DIR / f"{args.drama}_{args.lang}"
    wd.mkdir(parents=True, exist_ok=True)

    log(f"{'='*55}")
    log(f"  剪辑师工作台 v3 | {args.drama} | {cfg['name']}")
    log(f"  配音: {'MiMo角色配音' if args.dub else '纯字幕'}")
    log(f"  输出: {wd}")
    log(f"{'='*55}")
    t0 = time.time()

    # 1 合并
    if args.skip_merge or args.merged:
        merged = Path(args.merged) if args.merged else None
        if not (merged and merged.exists()):
            log("❌ 未找到已合并视频"); return
        log(f"\n⏭️ 跳过合并: {merged}")
    else:
        merged = wd / "merged.mp4"
        if not merge(args.episodes, merged): return
    ok, msg = run_verify("merge", merged=merged, episodes_dir=args.episodes)
    if not ok: log("  ❌ 合并验证失败，请检查"); return

    # 2 提取字幕
    zh_srt = wd / "sub_zh.srt"
    if not zh_srt.exists():
        extract(merged, zh_srt, episodes_dir=args.episodes)
    else: log(f"\n⏭️ 字幕已存在")
    ok, msg = run_verify("subtitles", srt=zh_srt)
    if not ok: log("  ❌ 字幕验证失败"); return

    # 3 翻译+分析
    aj = wd / f"analysis_{args.lang}.json"
    if not aj.exists():
        analysis = translate_analyze(zh_srt, args.lang, aj)
    else:
        with open(aj) as f: analysis = json.load(f)
        log(f"\n⏭️ 分析已存在: {len(analysis['characters'])}角色 {len(analysis['subtitles'])}条")
    ok, msg = run_verify("translation", analysis_json=aj)
    if not ok: log("  ⚠️ 翻译验证有警告，继续执行")

    # 4 隐藏原字幕
    no_sub = wd / "no_subs.mp4"
    if not no_sub.exists():
        hide_subs(merged, no_sub, args.delogo_rect)
    else: log(f"\n⏭️ 已存在")
    ok, msg = run_verify("delogo", original=merged, delogo=no_sub)
    if not ok: log("  ⚠️ 字幕隐藏验证有警告")

    # 5+6 配音
    if args.dub:
        vm = design_voices(analysis["characters"])
        dd = wd / "dub"
        dd.mkdir(exist_ok=True)
        dfs = dub(analysis, vm, str(dd))
        ok, msg = run_verify("dubbing", audio_files=dfs)
        if not ok: log("  ⚠️ 配音验证有警告")

    # 7 烧录
    final = OUTPUT_DIR / f"{args.drama}_{args.lang}.mp4"
    burn(no_sub, analysis, final, cfg)
    ok, msg = run_verify("final", video=final)

    elapsed = time.time() - t0
    log(f"\n{'='*55}")
    log(f"  ✅ 完成！{elapsed/60:.1f}分钟")
    log(f"  {final}")
    log(f"{'='*55}")

if __name__ == "__main__":
    main()
