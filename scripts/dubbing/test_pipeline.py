#!/usr/bin/env python3
"""
本地翻译配音系统 — 基础测试脚本
测试ASR + 翻译基础流程
"""

import os
import sys
import json
import subprocess
from pathlib import Path
from datetime import datetime

# 测试目录
TEST_DIR = Path(__file__).parent.parent / "data" / "dubbing" / "test"
TEST_DIR.mkdir(parents=True, exist_ok=True)

def test_whisper_asr(audio_path: str, language: str = "zh"):
    """测试Whisper语音识别"""
    print(f"\n{'='*60}")
    print(f"测试Whisper ASR")
    print(f"{'='*60}")
    
    import whisper
    
    print(f"加载Whisper模型 (large-v3)...")
    model = whisper.load_model("large-v3", device="mps")
    
    print(f"识别音频: {audio_path}")
    result = model.transcribe(
        audio_path,
        language=language,
        task="transcribe",
        verbose=False
    )
    
    print(f"\n识别结果:")
    print(f"  检测语言: {result.get('language', 'unknown')}")
    print(f"  段落数: {len(result['segments'])}")
    
    for i, seg in enumerate(result['segments'][:5]):  # 只显示前5段
        print(f"  [{seg['start']:.1f}s - {seg['end']:.1f}s] {seg['text']}")
    
    if len(result['segments']) > 5:
        print(f"  ... 还有 {len(result['segments'])-5} 段")
    
    return result

def test_nllb_translation(text: str, source_lang: str = "zho_Hans", target_lang: str = "eng_Latn"):
    """测试NLLB-200翻译"""
    print(f"\n{'='*60}")
    print(f"测试NLLB-200翻译")
    print(f"{'='*60}")
    
    try:
        from transformers import AutoModelForSeq2SeqLM, AutoTokenizer
    except ImportError:
        print("❌ transformers未安装，跳过NLLB测试")
        print("   安装命令: pip install transformers sentencepiece")
        return None
    
    model_name = "facebook/nllb-200-3.3B"
    print(f"加载NLLB模型: {model_name}")
    print(f"（首次运行需要下载模型，约7GB）")
    
    try:
        tokenizer = AutoTokenizer.from_pretrained(model_name)
        model = AutoModelForSeq2SeqLM.from_pretrained(model_name)
        
        # 设置源语言
        tokenizer.src_lang = source_lang
        
        # 编码
        inputs = tokenizer(text, return_tensors="pt")
        
        # 翻译
        translated = model.generate(
            **inputs,
            forced_bos_token_id=tokenizer.lang_code_to_id[target_lang],
            max_length=256
        )
        
        result = tokenizer.batch_decode(translated, skip_special_tokens=True)[0]
        
        print(f"\n翻译结果:")
        print(f"  原文 ({source_lang}): {text}")
        print(f"  译文 ({target_lang}): {result}")
        
        return result
        
    except Exception as e:
        print(f"❌ NLLB翻译失败: {e}")
        print(f"   可能需要HuggingFace token或网络问题")
        return None

def test_whisper_translation(audio_path: str, target_lang: str = "en"):
    """测试Whisper内置翻译（中文→英文）"""
    print(f"\n{'='*60}")
    print(f"测试Whisper翻译功能")
    print(f"{'='*60}")
    
    import whisper
    
    print(f"加载Whisper模型...")
    model = whisper.load_model("large-v3", device="mps")
    
    print(f"识别并翻译: {audio_path}")
    result = model.transcribe(
        audio_path,
        language="zh",
        task="translate",  # 翻译成英文
        verbose=False
    )
    
    print(f"\n翻译结果（中文→英文）:")
    for i, seg in enumerate(result['segments'][:5]):
        print(f"  [{seg['start']:.1f}s - {seg['end']:.1f}s] {seg['text']}")
    
    return result

def create_test_audio():
    """创建测试音频（如果没有现成的）"""
    test_audio = TEST_DIR / "test_audio.wav"
    
    if test_audio.exists():
        return str(test_audio)
    
    print("创建测试音频...")
    
    # 使用ffmpeg生成静音音频（用于测试）
    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", "sine=frequency=440:duration=5",
        "-ar", "16000",
        str(test_audio)
    ]
    
    try:
        subprocess.run(cmd, capture_output=True, check=True)
        print(f"✓ 测试音频已创建: {test_audio}")
        return str(test_audio)
    except Exception as e:
        print(f"❌ 创建测试音频失败: {e}")
        return None

def main():
    """主测试流程"""
    print("="*60)
    print("本地翻译配音系统 — 基础测试")
    print("="*60)
    
    # 检查是否有测试音频
    test_audio = create_test_audio()
    
    if not test_audio:
        print("\n❌ 无法创建测试音频，请手动提供音频文件")
        print(f"   放置位置: {TEST_DIR}/test_audio.wav")
        return
    
    # 测试1: Whisper ASR
    print("\n" + "="*60)
    print("测试1: Whisper语音识别")
    print("="*60)
    
    try:
        asr_result = test_whisper_asr(test_audio, language="zh")
        
        # 保存结果
        result_file = TEST_DIR / "asr_result.json"
        with open(result_file, "w", encoding="utf-8") as f:
            json.dump(asr_result, f, ensure_ascii=False, indent=2)
        print(f"\n✓ ASR结果已保存: {result_file}")
        
    except Exception as e:
        print(f"\n❌ Whisper测试失败: {e}")
        import traceback
        traceback.print_exc()
    
    # 测试2: Whisper翻译功能
    print("\n" + "="*60)
    print("测试2: Whisper翻译功能")
    print("="*60)
    
    try:
        translation_result = test_whisper_translation(test_audio, target_lang="en")
        
        result_file = TEST_DIR / "translation_result.json"
        with open(result_file, "w", encoding="utf-8") as f:
            json.dump(translation_result, f, ensure_ascii=False, indent=2)
        print(f"\n✓ 翻译结果已保存: {result_file}")
        
    except Exception as e:
        print(f"\n❌ Whisper翻译测试失败: {e}")
        import traceback
        traceback.print_exc()
    
    # 测试3: NLLB翻译（可选）
    print("\n" + "="*60)
    print("测试3: NLLB-200翻译（可选）")
    print("="*60)
    
    test_text = "你好，我是短剧出海系统的AI助手。"
    try:
        nllb_result = test_nllb_translation(
            test_text,
            source_lang="zho_Hans",
            target_lang="eng_Latn"
        )
    except Exception as e:
        print(f"\n❌ NLLB测试失败: {e}")
        import traceback
        traceback.print_exc()
    
    # 总结
    print("\n" + "="*60)
    print("测试总结")
    print("="*60)
    print("\n✓ 基础测试完成")
    print("\n下一步:")
    print("  1. 测试说话人分离 (pyannote)")
    print("  2. 测试TTS (CosyVoice/Fish Speech)")
    print("  3. 集成完整Pipeline")
    print(f"\n测试文件位置: {TEST_DIR}")

if __name__ == "__main__":
    main()
