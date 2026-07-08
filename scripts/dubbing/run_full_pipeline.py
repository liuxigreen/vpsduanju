#!/usr/bin/env python3
"""
本地翻译配音系统 — 完整测试脚本
测试：ASR → 说话人分离 → 翻译 → TTS 配音
"""

import os
import sys
import json
import subprocess
import tempfile
from pathlib import Path
from datetime import datetime

# 测试配置
TEST_DIR = Path(__file__).parent.parent.parent / "data" / "dubbing" / "test_output"
TEST_DIR.mkdir(parents=True, exist_ok=True)

WHISPER_MODEL = "large-v3"
DEVICE = "cpu"  # CPU避免MPS float64兼容问题

def extract_audio(video_path: str, output_path: str = None) -> str:
    """从视频提取音频"""
    print(f"\n[1/5] 提取音频...")
    
    if output_path is None:
        output_path = str(TEST_DIR / "audio.wav")
    
    cmd = [
        "ffmpeg", "-y",
        "-i", video_path,
        "-vn",  # 无视频
        "-acodec", "pcm_s16le",
        "-ar", "16000",  # 16kHz for Whisper
        "-ac", "1",  # 单声道
        output_path
    ]
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    if result.returncode == 0:
        duration_cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", output_path]
        dur_result = subprocess.run(duration_cmd, capture_output=True, text=True)
        duration_str = dur_result.stdout.strip()
        print(f"  ✓ 音频提取完成: {output_path}")
        if duration_str:
            try:
                print(f"  ✓ 时长: {float(duration_str):.1f}秒")
            except ValueError:
                print(f"  ✓ 音频已提取")
        return output_path
    else:
        print(f"  ❌ 提取失败: {result.stderr}")
        return None

def transcribe_with_whisper(audio_path: str, language: str = "zh") -> dict:
    """Whisper语音识别"""
    print(f"\n[2/5] Whisper语音识别 (模型: {WHISPER_MODEL})...")
    
    import whisper
    
    model = whisper.load_model(WHISPER_MODEL, device=DEVICE)
    
    print(f"  识别中...")
    result = model.transcribe(
        audio_path,
        language=language,
        task="transcribe",
        verbose=False,
        word_timestamps=True
    )
    
    print(f"  ✓ 识别完成: {len(result['segments'])}个片段")
    
    # 保存结果
    output_file = TEST_DIR / "transcription.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"  ✓ 保存: {output_file}")
    
    return result

def diarize_speakers(audio_path: str) -> list:
    """说话人分离"""
    print(f"\n[3/5] 说话人分离 (Pyannote)...")
    
    try:
        from pyannote.audio import Pipeline
    except ImportError:
        print("  ⚠️  pyannote未安装，使用简化方案...")
        return simple_diarization(audio_path)
    
    # 需要HuggingFace token
    hf_token = os.environ.get("HF_TOKEN")
    
    if not hf_token:
        print("  ⚠️  无HF_TOKEN，使用简化方案...")
        return simple_diarization(audio_path)
    
    try:
        pipeline = Pipeline.from_pretrained(
            "pyannote/speaker-diarization-3.1",
            use_auth_token=hf_token
        )
        
        print("  分离中...")
        diarization = pipeline(audio_path)
        
        speakers = []
        for turn, _, speaker in diarization.itertracks(yield_label=True):
            speakers.append({
                "start": turn.start,
                "end": turn.end,
                "speaker": speaker
            })
        
        print(f"  ✓ 分离完成: {len(set(s['speaker'] for s in speakers))}个说话人")
        
        # 保存
        output_file = TEST_DIR / "speakers.json"
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(speakers, f, ensure_ascii=False, indent=2)
        
        return speakers
        
    except Exception as e:
        print(f"  ❌ Pyannote失败: {e}")
        return simple_diarization(audio_path)

def simple_diarization(audio_path: str) -> list:
    """简化版说话人分割（基于静音检测）"""
    print("  使用简化方案（基于时间分割）...")
    
    # 获取音频时长
    duration_cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", audio_path]
    dur_result = subprocess.run(duration_cmd, capture_output=True, text=True)
    duration_str = dur_result.stdout.strip()
    
    try:
        duration = float(duration_str) if duration_str else 30.0
    except ValueError:
        duration = 30.0
    
    # 简单按时间分割（实际应该用能量检测）
    speakers = []
    segment_duration = 5.0  # 5秒一段
    
    for i, start in enumerate(range(0, int(duration), int(segment_duration))):
        speakers.append({
            "start": start,
            "end": min(start + segment_duration, duration),
            "speaker": f"SPEAKER_{i % 2}"  # 假设2个说话人
        })
    
    print(f"  ✓ 简化分割: {len(speakers)}个片段")
    return speakers

def translate_segments(segments: list, source_lang: str = "zh", target_lang: str = "en") -> list:
    """翻译文本段落"""
    print(f"\n[4/5] 翻译 ({source_lang} → {target_lang})...")
    
    # 尝试使用本地DeepSeek
    try:
        import requests
        
        api_base = os.environ.get("DEEPSEEK_API_BASE", "https://api.deepseek.com/v1")
        api_key = os.environ.get("DEEPSEEK_API_KEY")
        
        if not api_key:
            # 尝试从配置文件读取
            config_file = Path.home() / ".hermes" / "config.yaml"
            if config_file.exists():
                import yaml
                with open(config_file) as f:
                    config = yaml.safe_load(f)
                    api_key = config.get("providers", {}).get("deepseek", {}).get("api_key")
        
        if api_key:
            print(f"  使用DeepSeek API...")
            return translate_with_deepseek(segments, api_key, api_base, target_lang)
    except Exception as e:
        print(f"  DeepSeek失败: {e}")
    
    # 备选：使用Whisper内置翻译
    print(f"  使用Whisper内置翻译...")
    return translate_with_whisper(segments, target_lang)

def translate_with_deepseek(segments: list, api_key: str, api_base: str, target_lang: str) -> list:
    """使用DeepSeek翻译"""
    import requests
    
    lang_names = {"en": "English", "ja": "Japanese", "ko": "Korean", "es": "Spanish"}
    target_name = lang_names.get(target_lang, target_lang)
    
    translated = []
    
    # 批量翻译（减少API调用）
    batch_size = 10
    for i in range(0, len(segments), batch_size):
        batch = segments[i:i+batch_size]
        
        # 构建批量翻译prompt
        texts = [s["text"] for s in batch]
        prompt = f"""Translate the following Chinese texts to {target_name}. 
Return ONLY the translations, one per line, in the same order.
Keep the same meaning and emotional tone.

Texts:
{chr(10).join(f'{j+1}. {t}' for j, t in enumerate(texts))}"""
        
        try:
            response = requests.post(
                f"{api_base}/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": "deepseek-chat",
                    "messages": [
                        {"role": "system", "content": "You are a professional translator. Translate accurately while preserving the emotional tone."},
                        {"role": "user", "content": prompt}
                    ],
                    "temperature": 0.3,
                    "max_tokens": 1000
                },
                timeout=30
            )
            
            if response.status_code == 200:
                result = response.json()["choices"][0]["message"]["content"]
                translations = [line.strip().split(". ", 1)[-1] if ". " in line else line.strip() 
                              for line in result.strip().split("\n") if line.strip()]
                
                for j, seg in enumerate(batch):
                    seg_copy = seg.copy()
                    seg_copy["translated"] = translations[j] if j < len(translations) else seg["text"]
                    translated.append(seg_copy)
                
                print(f"  ✓ 已翻译 {min(i+batch_size, len(segments))}/{len(segments)}")
            else:
                raise Exception(f"API错误: {response.status_code}")
                
        except Exception as e:
            print(f"  ⚠️  批量翻译失败，使用原文: {e}")
            for seg in batch:
                seg_copy = seg.copy()
                seg_copy["translated"] = seg["text"]
                translated.append(seg_copy)
    
    return translated

def translate_with_whisper(segments: list, target_lang: str) -> list:
    """使用Whisper内置翻译"""
    # Whisper只能翻译成英文
    if target_lang != "en":
        print(f"  ⚠️  Whisper只能翻译成英文，目标语言: {target_lang}")
    
    translated = []
    for seg in segments:
        seg_copy = seg.copy()
        # 简单标记（实际需要用Whisper重新识别翻译）
        seg_copy["translated"] = f"[需要翻译] {seg['text']}"
        translated.append(seg_copy)
    
    return translated

def generate_tts(text: str, output_path: str, voice_description: str = None, reference_audio: str = None) -> bool:
    """生成TTS音频"""
    
    # 尝试VoxCPM2
    try:
        from voxcpm import VoxCPM
        import soundfile as sf
        
        model = VoxCPM.from_pretrained("openbmb/VoxCPM2", load_denoiser=False)
        
        wav = model.generate(
            text=text,
            cfg_value=2.0,
            inference_timesteps=10
        )
        
        sf.write(output_path, wav, model.tts_model.sample_rate)
        return True
        
    except Exception as e:
        print(f"    VoxCPM2失败: {e}")
    
    # 备选：edge-tts（微软免费TTS）
    try:
        import edge_tts
        import asyncio
        
        async def generate():
            voice = "en-US-GuyNeural" if all(c.isascii() for c in text) else "zh-CN-YunxiNeural"
            communicate = edge_tts.Communicate(text, voice)
            await communicate.save(output_path)
        
        asyncio.run(generate())
        return True
        
    except Exception as e:
        print(f"    edge-tts失败: {e}")
    
    return False

def assemble_dubbed_audio(segments: list, audio_duration: float, output_path: str) -> str:
    """拼接配音音频"""
    print(f"\n[5/5] 拼接配音音频...")
    
    # 创建静音底板
    silent_cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", f"anullsrc=r=16000:cl=mono:d={audio_duration}",
        "-acodec", "pcm_s16le",
        str(TEST_DIR / "silent_base.wav")
    ]
    subprocess.run(silent_cmd, capture_output=True)
    
    # 为每个片段生成TTS
    tts_files = []
    for i, seg in enumerate(segments):
        text = seg.get("translated", seg["text"])
        tts_file = TEST_DIR / f"tts_{i:04d}.wav"
        
        print(f"  生成TTS [{i+1}/{len(segments)}]: {text[:30]}...")
        
        if generate_tts(text, str(tts_file)):
            tts_files.append({
                "file": str(tts_file),
                "start": seg["start"],
                "end": seg["end"]
            })
        else:
            print(f"    ⚠️  跳过此片段")
    
    # 使用FFmpeg拼接
    if tts_files:
        # 构建filter_complex
        inputs = []
        filter_parts = []
        
        for i, tts in enumerate(tts_files):
            inputs.extend(["-i", tts["file"]])
            delay_ms = int(tts["start"] * 1000)
            filter_parts.append(f"[{i}]adelay={delay_ms}|{delay_ms}[a{i}]")
        
        mix_inputs = "".join(f"[a{i}]" for i in range(len(tts_files)))
        filter_parts.append(f"{mix_inputs}amix=inputs={len(tts_files)}:duration=longest[out]")
        
        cmd = [
            "ffmpeg", "-y",
            "-i", str(TEST_DIR / "silent_base.wav"),
            *inputs,
            "-filter_complex", ";".join(filter_parts),
            "-map", "[out]",
            output_path
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode == 0:
            print(f"  ✓ 配音音频生成: {output_path}")
            return output_path
        else:
            print(f"  ❌ 拼接失败: {result.stderr[:200]}")
    
    return None

def main():
    """主测试流程"""
    print("="*60)
    print("本地翻译配音系统 — 完整测试")
    print(f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*60)
    
    # 选择测试视频
    test_videos = [
        "/Users/liuxi/duanju/raw/1.mp4",
        "/Users/liuxi/Desktop/视频/test_merge/test_18min.mp4"
    ]
    
    video_path = test_videos[0]  # 先用小视频测试
    
    if not Path(video_path).exists():
        print(f"❌ 视频不存在: {video_path}")
        return
    
    print(f"\n测试视频: {video_path}")
    
    # Step 1: 提取音频
    audio_path = extract_audio(video_path)
    if not audio_path:
        return
    
    # Step 2: 语音识别
    transcription = transcribe_with_whisper(audio_path)
    if not transcription:
        return
    
    # Step 3: 说话人分离
    speakers = diarize_speakers(audio_path)
    
    # 合并识别结果和说话人
    segments = transcription["segments"]
    
    # 为每个片段分配说话人
    for seg in segments:
        seg_mid = (seg["start"] + seg["end"]) / 2
        for spk in speakers:
            if spk["start"] <= seg_mid <= spk["end"]:
                seg["speaker"] = spk["speaker"]
                break
        if "speaker" not in seg:
            seg["speaker"] = "UNKNOWN"
    
    print(f"\n✓ 识别+说话人分配完成")
    print(f"  片段数: {len(segments)}")
    print(f"  说话人: {len(set(s.get('speaker', 'UNKNOWN') for s in segments))}")
    
    # 保存完整结果
    full_result = {
        "video": video_path,
        "segments": segments,
        "speakers": speakers,
        "timestamp": datetime.now().isoformat()
    }
    
    result_file = TEST_DIR / "full_result.json"
    with open(result_file, "w", encoding="utf-8") as f:
        json.dump(full_result, f, ensure_ascii=False, indent=2)
    print(f"✓ 完整结果保存: {result_file}")
    
    # Step 4: 翻译
    translated_segments = translate_segments(segments, source_lang="zh", target_lang="en")
    
    # 保存翻译结果
    translation_file = TEST_DIR / "translation_result.json"
    with open(translation_file, "w", encoding="utf-8") as f:
        json.dump(translated_segments, f, ensure_ascii=False, indent=2)
    print(f"✓ 翻译结果保存: {translation_file}")
    
    # Step 5: 生成配音
    duration_cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", audio_path]
    dur_result = subprocess.run(duration_cmd, capture_output=True, text=True)
    duration_str = dur_result.stdout.strip()
    try:
        duration = float(duration_str) if duration_str else 30.0
    except ValueError:
        duration = 30.0
    
    dubbed_path = str(TEST_DIR / "dubbed_audio.wav")
    result = assemble_dubbed_audio(translated_segments, duration, dubbed_path)
    
    if result:
        # 合并到视频
        output_video = str(TEST_DIR / "dubbed_output.mp4")
        merge_cmd = [
            "ffmpeg", "-y",
            "-i", video_path,
            "-i", dubbed_path,
            "-c:v", "copy",
            "-c:a", "aac",
            "-map", "0:v:0",
            "-map", "1:a:0",
            "-shortest",
            output_video
        ]
        
        merge_result = subprocess.run(merge_cmd, capture_output=True, text=True)
        
        if merge_result.returncode == 0:
            print(f"\n{'='*60}")
            print(f"✓ 配音视频生成完成!")
            print(f"  输出: {output_video}")
            print(f"{'='*60}")
        else:
            print(f"\n❌ 视频合并失败: {merge_result.stderr[:200]}")
    
    # 总结
    print(f"\n{'='*60}")
    print("测试总结")
    print(f"{'='*60}")
    print(f"输出目录: {TEST_DIR}")
    print(f"\n生成文件:")
    for f in sorted(TEST_DIR.glob("*")):
        print(f"  - {f.name}")
    
    print(f"\n下一步:")
    print(f"  1. 试听配音效果")
    print(f"  2. 调整翻译质量")
    print(f"  3. 优化TTS角色声音")

if __name__ == "__main__":
    main()
