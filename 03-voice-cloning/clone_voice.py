#!/usr/bin/env python3
"""
语音克隆脚本
使用 Coqui TTS (XTTS v2) 进行零样本语音克隆

用法:
    # 克隆语音
    python3 clone_voice.py tts --text "要合成的文本" --ref_audio reference.wav --output output.wav

    # 检查可用模型
    python3 clone_voice.py list_models

    # 列出已下载模型
    python3 clone_voice.py list_local

注意:
    - 参考音频建议 30 秒以上
    - 参考音频需要清晰、无背景噪音
    - 如效果不佳，先用 preprocess_audio.py 预处理
"""

import sys
import os
from pathlib import Path

# 检查是否已安装 TTS
try:
    from TTS.api import TTS
    TTS_AVAILABLE = True
except ImportError:
    TTS_AVAILABLE = False
    print("警告: TTS 未安装")
    print("请运行: pip install TTS")

def list_models():
    """列出可用模型"""
    if not TTS_AVAILABLE:
        return

    print("\nXTTS 模型:")
    print("  tts_models/multilingual/multi-dataset/xtts_v2 - 推荐 (零样本克隆)")
    print("\n其他 TTS 模型:")
    print("  (运行 python3 -c \"from TTS.utils.manage import ModelManager; m = ModelManager(); print(m.list_models())\" 查看完整列表)")

def list_local_models():
    """列出本地已下载的模型"""
    if not TTS_AVAILABLE:
        return

    tts = TTS()
    print("\n已下载模型:")
    for model in tts.models:
        print(f"  - {model}")

def clone_with_xtts(text, ref_audio, output, language="zh-cn"):
    """使用 XTTS v2 进行语音克隆"""
    if not TTS_AVAILABLE:
        print("错误: TTS 未安装")
        return

    ref_path = Path(ref_audio)
    if not ref_path.exists():
        print(f"错误: 参考音频不存在: {ref_audio}")
        return

    print(f"\n=== XTTS v2 语音克隆 ===")
    print(f"文本: {text[:50]}...")
    print(f"参考: {ref_audio}")
    print(f"输出: {output}")

    print("\n加载 XTTS v2 模型...")
    try:
        tts = TTS("tts_models/multilingual/multi-dataset/xtts_v2")
    except Exception as e:
        print(f"加载模型失败: {e}")
        print("可能需要下载模型，首次运行会自动下载")
        return

    print("生成语音...")
    try:
        tts.tts_to_file(
            text=text,
            speaker_wav=ref_audio,
            language=language,
            file_path=output
        )
        print(f"\n✓ 生成完成: {output}")

        # 显示文件大小
        size_mb = Path(output).stat().st_size / (1024 * 1024)
        print(f"  文件大小: {size_mb:.2f} MB")
    except Exception as e:
        print(f"生成失败: {e}")

def main():
    if not TTS_AVAILABLE:
        print("错误: TTS 模块不可用")
        print("\n安装 TTS:")
        print("  source .venv/bin/activate")
        print("  pip install TTS")
        sys.exit(1)

    if len(sys.argv) < 2:
        print("用法:")
        print("  python3 clone_voice.py tts --text '文本' --ref_audio ref.wav --output out.wav")
        print("  python3 clone_voice.py list_models")
        print("  python3 clone_voice.py list_local")
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd == "list_models":
        list_models()

    elif cmd == "list_local":
        list_local_models()

    elif cmd == "tts":
        # 解析参数
        args = sys.argv[2:]
        text = None
        ref_audio = None
        output = "output.wav"
        language = "zh-cn"

        i = 0
        while i < len(args):
            if args[i] == "--text" and i + 1 < len(args):
                text = args[i + 1]
                i += 2
            elif args[i] == "--ref_audio" and i + 1 < len(args):
                ref_audio = args[i + 1]
                i += 2
            elif args[i] == "--output" and i + 1 < len(args):
                output = args[i + 1]
                i += 2
            elif args[i] == "--language" and i + 1 < len(args):
                language = args[i + 1]
                i += 2
            else:
                i += 1

        if not text:
            print("错误: 请指定 --text 参数")
            sys.exit(1)
        if not ref_audio:
            print("错误: 请指定 --ref_audio 参数")
            sys.exit(1)

        clone_with_xtts(text, ref_audio, output, language)

    else:
        print(f"未知命令: {cmd}")
        sys.exit(1)

if __name__ == "__main__":
    main()
