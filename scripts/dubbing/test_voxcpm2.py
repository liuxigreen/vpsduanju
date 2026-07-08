#!/usr/bin/env python3
"""
VoxCPM2 测试脚本
测试声音克隆、Voice Design、情绪控制
"""

import os
import sys
import subprocess
from pathlib import Path

# 测试目录
TEST_DIR = Path(__file__).parent.parent.parent / "data" / "dubbing" / "test"
TEST_DIR.mkdir(parents=True, exist_ok=True)

def install_voxcpm():
    """安装 VoxCPM2"""
    print("安装 VoxCPM2...")
    
    cmd = [
        sys.executable, "-m", "pip", "install",
        "voxcpm",
        "--quiet"
    ]
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    if result.returncode == 0:
        print("✓ VoxCPM2 安装成功")
        return True
    else:
        print(f"❌ 安装失败: {result.stderr}")
        return False

def download_model():
    """下载 VoxCPM2 模型"""
    print("下载 VoxCPM2 模型...")
    print("（首次运行需要下载约4GB模型文件）")
    
    try:
        from voxcpm import VoxCPM
        
        model = VoxCPM.from_pretrained(
            "openbmb/VoxCPM2",
            load_denoiser=False
        )
        
        print("✓ 模型下载完成")
        return model
        
    except Exception as e:
        print(f"❌ 模型下载失败: {e}")
        return None

def test_voice_design(model):
    """测试 Voice Design — 文字描述生成声音"""
    print("\n" + "="*60)
    print("测试 Voice Design — 文字描述生成声音")
    print("="*60)
    
    import soundfile as sf
    
    # 测试不同角色的声音设计
    voice_designs = [
        {
            "name": "总裁",
            "description": "A deep, commanding male voice with cold authority. Speaks slowly with deliberate pauses, exuding power and control.",
            "text_en": "You dare defy me? Know your place.",
            "text_zh": "你敢违抗我？认清你的位置。"
        },
        {
            "name": "女主",
            "description": "A warm but resilient female voice, slightly husky. Gentle yet determined, with underlying strength.",
            "text_en": "I won't give up. Not this time.",
            "text_zh": "我不会放弃。这次不会。"
        },
        {
            "name": "反派",
            "description": "A sharp, mocking voice with contempt. Slightly nasal, dripping with sarcasm and disdain.",
            "text_en": "How pathetic. You really thought you could win?",
            "text_zh": "真可悲。你真以为你能赢？"
        }
    ]
    
    results = []
    
    for design in voice_designs:
        print(f"\n生成声音: {design['name']}")
        print(f"  描述: {design['description']}")
        
        try:
            # 生成英文版本
            wav_en = model.generate(
                text=design["text_en"],
                cfg_value=2.0,
                inference_timesteps=10
            )
            
            # 保存
            output_file = TEST_DIR / f"voxcpm2_{design['name']}_en.wav"
            sf.write(str(output_file), wav_en, model.tts_model.sample_rate)
            print(f"  ✓ 英文: {output_file}")
            
            # 生成中文版本
            wav_zh = model.generate(
                text=design["text_zh"],
                cfg_value=2.0,
                inference_timesteps=10
            )
            
            output_file = TEST_DIR / f"voxcpm2_{design['name']}_zh.wav"
            sf.write(str(output_file), wav_zh, model.tts_model.sample_rate)
            print(f"  ✓ 中文: {output_file}")
            
            results.append({
                "name": design["name"],
                "success": True
            })
            
        except Exception as e:
            print(f"  ❌ 失败: {e}")
            results.append({
                "name": design["name"],
                "success": False,
                "error": str(e)
            })
    
    return results

def test_controllable_cloning(model, reference_audio: str):
    """测试 Controllable Cloning — 克隆+控制情绪"""
    print("\n" + "="*60)
    print("测试 Controllable Cloning — 克隆+控制情绪")
    print("="*60)
    
    import soundfile as sf
    
    # 情绪变体
    emotion_variants = [
        {
            "name": "愤怒",
            "text": "你怎么敢这样对我！",
            "guidance": "Speak with intense anger, raised voice, sharp tones"
        },
        {
            "name": "悲伤",
            "text": "一切都结束了...",
            "guidance": "Speak with deep sadness, slow pace, trembling voice"
        },
        {
            "name": "甜蜜",
            "text": "我真的很喜欢你。",
            "guidance": "Speak with warmth and tenderness, gentle and soft"
        }
    ]
    
    results = []
    
    for variant in emotion_variants:
        print(f"\n情绪变体: {variant['name']}")
        print(f"  文本: {variant['text']}")
        
        try:
            wav = model.generate(
                text=variant["text"],
                reference_audio=reference_audio,
                guidance=variant["guidance"],
                cfg_value=2.0,
                inference_timesteps=10
            )
            
            output_file = TEST_DIR / f"voxcpm2_clone_{variant['name']}.wav"
            sf.write(str(output_file), wav, model.tts_model.sample_rate)
            print(f"  ✓ 保存: {output_file}")
            
            results.append({
                "name": variant["name"],
                "success": True
            })
            
        except Exception as e:
            print(f"  ❌ 失败: {e}")
            results.append({
                "name": variant["name"],
                "success": False,
                "error": str(e)
            })
    
    return results

def main():
    """主测试流程"""
    print("="*60)
    print("VoxCPM2 测试 — 声音克隆 + Voice Design + 情绪控制")
    print("="*60)
    
    # 安装
    if not install_voxcpm():
        return
    
    # 下载模型
    model = download_model()
    if not model:
        return
    
    # 测试1: Voice Design
    print("\n" + "="*60)
    print("测试1: Voice Design — 为短剧角色创建声音")
    print("="*60)
    
    voice_results = test_voice_design(model)
    
    # 测试2: Controllable Cloning（需要参考音频）
    reference_audio = TEST_DIR / "reference_voice.wav"
    
    if reference_audio.exists():
        print("\n" + "="*60)
        print("测试2: Controllable Cloning — 克隆+情绪控制")
        print("="*60)
        
        clone_results = test_controllable_cloning(model, str(reference_audio))
    else:
        print(f"\n⚠️  跳过克隆测试（无参考音频）")
        print(f"   请将参考音频放在: {reference_audio}")
        clone_results = []
    
    # 总结
    print("\n" + "="*60)
    print("测试总结")
    print("="*60)
    
    print("\nVoice Design 测试:")
    for r in voice_results:
        status = "✓" if r["success"] else "❌"
        print(f"  {status} {r['name']}")
    
    if clone_results:
        print("\nControllable Cloning 测试:")
        for r in clone_results:
            status = "✓" if r["success"] else "❌"
            print(f"  {status} {r['name']}")
    
    print(f"\n输出目录: {TEST_DIR}")
    print("\n下一步:")
    print("  1. 试听生成的音频，评估质量")
    print("  2. 提供参考音频测试克隆功能")
    print("  3. 集成到完整Pipeline")

if __name__ == "__main__":
    main()
