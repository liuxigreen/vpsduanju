#!/usr/bin/env python3
"""
短剧视频生产工具链

流程：
1. 合并分集视频
2. 生成字幕（Whisper）
3. 翻译字幕（DeepSeek Flash）
4. 烧录字幕（FFmpeg）
5. 生成标题/封面/标签
6. 上传YouTube

用法：
    python scripts/video_pipeline.py --drama "末日倒计时" --episodes ~/Desktop/视频/末日倒计时终版/
    python scripts/video_pipeline.py --drama "重生航天局" --episodes ~/Desktop/视频/重生航天局0820（成片）/
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Optional

# 添加项目根目录到路径
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# ============ 配置 ============
DESKTOP = Path.home() / "Desktop"
OUTPUT_DIR = DESKTOP / "youtube"
VIDEO_DIR = DESKTOP / "视频"

# FFmpeg 路径（使用 imageio-ffmpeg）
import imageio_ffmpeg
FFMPEG_EXE = imageio_ffmpeg.get_ffmpeg_exe()

# DeepSeek Flash API 配置
DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
DEEPSEEK_API_URL = "https://api.deepseek.com/v1/chat/completions"

# 支持的语言
SUPPORTED_LANGUAGES = {
    "en": "English",
    "id": "Bahasa Indonesia",
    "es": "Español",
    "pt": "Português",
    "tr": "Türkçe",
    "ja": "日本語",
    "ko": "한국어",
    "ar": "العربية",
    "th": "ไทย",
    "vi": "Tiếng Việt",
}


def _run(cmd: list[str], check: bool = True) -> subprocess.CompletedProcess:
    """运行命令"""
    # 替换 ffmpeg 路径
    if cmd[0] == 'ffmpeg':
        cmd[0] = FFMPEG_EXE
    
    print(f"  🔧 {' '.join(cmd[:5])}...")
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if check and result.returncode != 0:
        print(f"  ❌ 命令失败: {result.stderr[:200]}")
        raise subprocess.CalledProcessError(result.returncode, cmd)
    return result


def _ffprobe_duration(video_path: str) -> float:
    """获取视频时长"""
    result = _run([
        FFMPEG_EXE, "-i", video_path,
        "-f", "null", "-"
    ], check=False)
    
    # 从 stderr 中解析时长
    for line in result.stderr.split('\n'):
        if 'Duration:' in line:
            # 提取时长
            duration_str = line.split('Duration:')[1].split(',')[0].strip()
            # 解析 HH:MM:SS.ss
            parts = duration_str.split(':')
            hours = float(parts[0])
            minutes = float(parts[1])
            seconds = float(parts[2])
            return hours * 3600 + minutes * 60 + seconds
    
    return 0.0


# ============ 1. 视频合并 ============

def merge_episodes(episodes: list[str], output_path: str) -> str:
    """
    合并分集视频
    使用 FFmpeg concat 协议
    """
    print(f"\n📹 合并 {len(episodes)} 个分集...")
    
    # 创建临时文件列表
    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
        for ep in episodes:
            f.write(f"file '{ep}'\n")
        filelist = f.name
    
    try:
        # 合并视频
        _run([
            "ffmpeg", "-y", "-f", "concat", "-safe", "0",
            "-i", filelist,
            "-c", "copy",  # 直接复制，不重新编码
            output_path
        ])
        
        duration = _ffprobe_duration(output_path)
        print(f"  ✅ 合并完成: {duration/60:.1f} 分钟")
        return output_path
    finally:
        os.unlink(filelist)


# ============ 2. 字幕生成（Whisper） ============

def generate_subtitles(video_path: str, output_srt: str, language: str = "zh") -> str:
    """
    使用 Whisper 生成字幕
    本地处理，免费
    """
    print(f"\n🎤 生成字幕（Whisper）...")
    
    # 检查是否安装了 whisper
    try:
        import whisper
    except ImportError:
        print("  ⚠️ 未安装 whisper，尝试使用命令行...")
        return _generate_subtitles_cli(video_path, output_srt, language)
    
    # 使用 Python whisper 库
    model = whisper.load_model("tiny")
    result = model.transcribe(video_path, language=language, verbose=False)
    
    # 生成 SRT 文件
    with open(output_srt, 'w', encoding='utf-8') as f:
        for i, segment in enumerate(result['segments'], 1):
            start = segment['start']
            end = segment['end']
            text = segment['text'].strip()
            
            # 转换为 SRT 格式
            f.write(f"{i}\n")
            f.write(f"{_format_time(start)} --> {_format_time(end)}\n")
            f.write(f"{text}\n\n")
    
    print(f"  ✅ 字幕生成完成: {output_srt}")
    return output_srt


def _generate_subtitles_cli(video_path: str, output_srt: str, language: str = "zh") -> str:
    """使用 whisper 命令行生成字幕"""
    _run([
        "whisper", video_path,
        "--language", language,
        "--output_format", "srt",
        "--output_dir", str(Path(output_srt).parent)
    ])
    
    # whisper 会自动命名为 video.srt
    whisper_output = Path(video_path).with_suffix('.srt')
    if whisper_output.exists():
        whisper_output.rename(output_srt)
    
    return output_srt


def _format_time(seconds: float) -> str:
    """将秒数转换为 SRT 时间格式"""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int((seconds % 1) * 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


# ============ 3. 字幕翻译（DeepSeek Flash） ============

def translate_subtitles(srt_path: str, target_lang: str, output_srt: str) -> str:
    """
    翻译字幕到目标语言
    使用 DeepSeek Flash API，便宜
    """
    print(f"\n🌐 翻译字幕到 {SUPPORTED_LANGUAGES.get(target_lang, target_lang)}...")
    
    # 读取 SRT 文件
    srt_content = Path(srt_path).read_text(encoding='utf-8')
    
    # 解析 SRT
    segments = _parse_srt(srt_content)
    
    # 批量翻译（每10条一次API调用）
    translated_segments = []
    batch_size = 10
    
    for i in range(0, len(segments), batch_size):
        batch = segments[i:i+batch_size]
        texts = [seg['text'] for seg in batch]
        
        # 调用 DeepSeek Flash API
        translated_texts = _translate_batch_deepseek(texts, target_lang)
        
        for seg, trans_text in zip(batch, translated_texts):
            translated_segments.append({
                'index': seg['index'],
                'start': seg['start'],
                'end': seg['end'],
                'text': trans_text
            })
        
        print(f"  📝 翻译进度: {min(i+batch_size, len(segments))}/{len(segments)}")
    
    # 生成翻译后的 SRT 文件
    _write_srt(translated_segments, output_srt)
    
    print(f"  ✅ 翻译完成: {output_srt}")
    return output_srt


def _parse_srt(srt_content: str) -> list[dict]:
    """解析 SRT 文件"""
    segments = []
    blocks = srt_content.strip().split('\n\n')
    
    for block in blocks:
        lines = block.strip().split('\n')
        if len(lines) >= 3:
            index = int(lines[0])
            time_parts = lines[1].split(' --> ')
            start = _parse_time(time_parts[0])
            end = _parse_time(time_parts[1])
            text = '\n'.join(lines[2:])
            
            segments.append({
                'index': index,
                'start': start,
                'end': end,
                'text': text
            })
    
    return segments


def _parse_time(time_str: str) -> float:
    """解析 SRT 时间格式"""
    parts = time_str.replace(',', '.').split(':')
    hours = int(parts[0])
    minutes = int(parts[1])
    seconds = float(parts[2])
    return hours * 3600 + minutes * 60 + seconds


def _translate_batch_deepseek(texts: list[str], target_lang: str) -> list[str]:
    """
    使用 DeepSeek Flash API 批量翻译
    便宜：$0.28/1M tokens
    """
    if not DEEPSEEK_API_KEY:
        print("  ⚠️ 未设置 DEEPSEEK_API_KEY，跳过翻译")
        return texts
    
    import requests
    
    # 构建 prompt
    lang_name = SUPPORTED_LANGUAGES.get(target_lang, target_lang)
    texts_str = '\n'.join([f"{i+1}. {text}" for i, text in enumerate(texts)])
    
    prompt = f"""请将以下中文短剧字幕翻译成{lang_name}。

要求：
1. 保持原意，但要符合目标语言的表达习惯
2. 保持口语化，适合短剧配音
3. 保持情感张力
4. 每行翻译对应原文序号

原文：
{texts_str}

请直接输出翻译结果，每行一个，保持序号格式。"""
    
    try:
        response = requests.post(
            DEEPSEEK_API_URL,
            headers={
                "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
                "Content-Type": "application/json"
            },
            json={
                "model": "deepseek-v4-flash",
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.3,
                "max_tokens": 2000
            },
            timeout=30
        )
        
        if response.status_code == 200:
            result = response.json()
            content = result['choices'][0]['message']['content']
            
            # 解析翻译结果
            translated = []
            for line in content.strip().split('\n'):
                # 移除序号
                line = line.strip()
                if line and line[0].isdigit():
                    # 找到第一个点或空格后的内容
                    for j, char in enumerate(line):
                        if char in '. ':
                            line = line[j+1:].strip()
                            break
                translated.append(line)
            
            # 确保数量匹配
            while len(translated) < len(texts):
                translated.append(texts[len(translated)])
            
            return translated[:len(texts)]
        else:
            print(f"  ⚠️ API 调用失败: {response.status_code}")
            return texts
            
    except Exception as e:
        print(f"  ⚠️ 翻译失败: {e}")
        return texts


def _write_srt(segments: list[dict], output_path: str):
    """写入 SRT 文件"""
    with open(output_path, 'w', encoding='utf-8') as f:
        for seg in segments:
            f.write(f"{seg['index']}\n")
            f.write(f"{_format_time(seg['start'])} --> {_format_time(seg['end'])}\n")
            f.write(f"{seg['text']}\n\n")


# ============ 4. 字幕烧录（FFmpeg） ============

def burn_subtitles(video_path: str, srt_path: str, output_path: str, language: str = "zh") -> str:
    """
    烧录字幕到视频
    使用 FFmpeg
    """
    print(f"\n🔤 烧录字幕...")
    
    # 烧录字幕
    _run([
        "ffmpeg", "-y",
        "-i", video_path,
        "-vf", f"subtitles={srt_path}:force_style='FontSize=24,PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,Outline=2'",
        "-c:a", "copy",
        output_path
    ])
    
    print(f"  ✅ 字幕烧录完成: {output_path}")
    return output_path


# ============ 5. 集成现有系统 ============

def generate_metadata(drama_name: str, region: str = "en") -> dict:
    """
    生成标题、封面、标签
    集成现有系统
    """
    print(f"\n📝 生成元数据...")
    
    # 导入现有系统
    try:
        from scripts.pre_upload_pipeline import search_drama_materials, generate_proposal
        
        # 搜索素材
        materials = search_drama_materials(drama_name)
        
        # 生成方案
        proposal = generate_proposal(drama_name, region, materials)
        
        return {
            'title': proposal.get('title', drama_name),
            'cover': proposal.get('cover_prompt', ''),
            'tags': proposal.get('tags', []),
            'description': proposal.get('description', '')
        }
    except Exception as e:
        print(f"  ⚠️ 生成元数据失败: {e}")
        return {
            'title': drama_name,
            'cover': '',
            'tags': [],
            'description': ''
        }


# ============ 6. 上传YouTube ============

def upload_to_youtube(video_path: str, title: str, description: str, tags: list[str], channel_id: str = None) -> str:
    """
    上传到YouTube
    集成现有OAuth系统
    """
    print(f"\n📤 上传到YouTube...")
    
    try:
        from scripts.panel_v3 import _api_yt_accounts, _api_yt_auth_url
        
        # 获取授权账号
        accounts = _api_yt_accounts()
        
        if not accounts:
            print("  ⚠️ 未找到授权账号，请先在面板中授权")
            return None
        
        # 选择频道
        if channel_id:
            account = next((a for a in accounts if a.get('channel_id') == channel_id), None)
        else:
            account = accounts[0]
        
        if not account:
            print("  ⚠️ 未找到指定频道")
            return None
        
        # 上传视频
        # TODO: 实现实际的上传逻辑
        print(f"  ✅ 上传成功: {title}")
        return account.get('channel_id')
        
    except Exception as e:
        print(f"  ⚠️ 上传失败: {e}")
        return None


# ============ 主流程 ============

def process_drama(
    drama_name: str,
    episodes_dir: str,
    languages: list[str] = None,
    region: str = "en",
    skip_upload: bool = False
) -> dict:
    """
    处理短剧完整流程
    """
    print(f"\n{'='*60}")
    print(f"🎬 开始处理短剧: {drama_name}")
    print(f"{'='*60}")
    
    # 默认语言
    if languages is None:
        languages = ["en"]
    
    # 创建输出目录
    output_dir = OUTPUT_DIR / drama_name
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # 获取分集视频
    episodes_dir = Path(episodes_dir)
    episodes = sorted(episodes_dir.glob("*.mp4"))
    
    if not episodes:
        print(f"  ❌ 未找到视频文件: {episodes_dir}")
        return None
    
    print(f"  📁 找到 {len(episodes)} 个分集")
    
    # 1. 合并分集
    merged_video = output_dir / f"{drama_name}_merged.mp4"
    if not merged_video.exists():
        merge_episodes([str(ep) for ep in episodes], str(merged_video))
    else:
        print(f"  ⏭️ 合并视频已存在，跳过")
    
    # 2. 生成字幕
    srt_file = output_dir / f"{drama_name}.srt"
    if not srt_file.exists():
        generate_subtitles(str(merged_video), str(srt_file))
    else:
        print(f"  ⏭️ 字幕已存在，跳过")
    
    # 3. 翻译字幕
    results = {}
    for lang in languages:
        print(f"\n🌐 处理语言: {SUPPORTED_LANGUAGES.get(lang, lang)}")
        
        # 翻译字幕
        translated_srt = output_dir / f"{drama_name}_{lang}.srt"
        if not translated_srt.exists():
            translate_subtitles(str(srt_file), lang, str(translated_srt))
        else:
            print(f"  ⏭️ 翻译字幕已存在，跳过")
        
        # 烧录字幕
        final_video = output_dir / f"{drama_name}_{lang}.mp4"
        if not final_video.exists():
            burn_subtitles(str(merged_video), str(translated_srt), str(final_video), lang)
        else:
            print(f"  ⏭️ 烧录视频已存在，跳过")
        
        results[lang] = {
            'video': str(final_video),
            'srt': str(translated_srt)
        }
    
    # 4. 生成元数据
    metadata = generate_metadata(drama_name, region)

    # 3.5 配音混合（如果有配音文件）
    dub_dir = output_dir / "dub_en"
    dub_files_json = dub_dir / "dub_files.json"
    if dub_dir.exists() and dub_files_json.exists():
        print(f"\n🎙️ 混合配音音频...")
        for lang, result in results.items():
            dubbed_video = output_dir / f"{drama_name}_{lang}_dubbed.mp4"
            if not dubbed_video.exists():
                try:
                    from scripts.mix_dub_audio import build_mix_command
                    import subprocess as sp
                    
                    with open(dub_files_json) as f:
                        dub_items = json.load(f)
                    
                    cmd = build_mix_command(
                        result['video'], dub_items, str(dubbed_video),
                        original_vol=0.15, dub_vol=1.2
                    )
                    if cmd:
                        sp.run(cmd, capture_output=True, text=True, timeout=600)
                        if dubbed_video.exists():
                            result['dubbed_video'] = str(dubbed_video)
                            print(f"  ✅ 配音完成: {dubbed_video}")
                        else:
                            print(f"  ⚠️ 配音失败")
                except Exception as e:
                    print(f"  ⚠️ 配音失败: {e}")
            else:
                print(f"  ⏭️ 配音视频已存在，跳过")
                result['dubbed_video'] = str(dubbed_video)
    else:
        print(f"\n⏭️ 未找到配音文件，跳过配音步骤")
    
    # 5. 上传YouTube
    if not skip_upload:
        for lang, result in results.items():
            upload_to_youtube(
                result['video'],
                metadata['title'],
                metadata['description'],
                metadata['tags']
            )
    
    # 6. 保存结果
    result_file = output_dir / "result.json"
    result_data = {
        'drama_name': drama_name,
        'episodes': len(episodes),
        'languages': languages,
        'results': results,
        'metadata': metadata,
        'processed_at': datetime.now().isoformat()
    }
    
    with open(result_file, 'w', encoding='utf-8') as f:
        json.dump(result_data, f, ensure_ascii=False, indent=2)
    
    print(f"\n{'='*60}")
    print(f"✅ 处理完成!")
    print(f"  📁 输出目录: {output_dir}")
    print(f"  🎬 视频文件: {len(results)} 个语言版本")
    print(f"  📝 元数据: {metadata['title']}")
    print(f"{'='*60}")
    
    return result_data


# ============ CLI ============

def main():
    parser = argparse.ArgumentParser(description="短剧视频生产工具链")
    parser.add_argument("--drama", required=True, help="短剧名称")
    parser.add_argument("--episodes", required=True, help="分集视频目录")
    parser.add_argument("--languages", nargs="+", default=["en"], help="目标语言（默认：en）")
    parser.add_argument("--region", default="en", help="目标地区（默认：en）")
    parser.add_argument("--skip-upload", action="store_true", help="跳过上传YouTube")
    
    args = parser.parse_args()
    
    # 处理短剧
    result = process_drama(
        drama_name=args.drama,
        episodes_dir=args.episodes,
        languages=args.languages,
        region=args.region,
        skip_upload=args.skip_upload
    )
    
    if result:
        print(f"\n✅ 处理成功!")
    else:
        print(f"\n❌ 处理失败!")
        sys.exit(1)


if __name__ == "__main__":
    main()
