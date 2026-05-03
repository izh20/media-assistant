#!/usr/bin/env python3
"""
批量语音合成脚本
使用相同的参考音频批量生成多个文本的语音

用法:
    python3 batch_tts.py --ref_audio ref.wav --texts "文本1" "文本2" --output_dir ./output
"""

import sys
import os
import argparse
from pathlib import Path

def batch_tts(texts, ref_audio, output_dir, language="zh-cn"):
    """批量生成语音"""
    if not os.path.exists(ref_audio):
        print(f"错误: 参考音频不存在: {ref_audio}")
        return

    try:
        from TTS.api import TTS
    except ImportError:
        print("错误: TTS 未安装")
        return

    print(f"\n=== 批量语音合成 ===")
    print(f"参考音频: {ref_audio}")
    print(f"文本数量: {len(texts)}")
    print(f"输出目录: {output_dir}")

    # 创建输出目录
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    print("\n加载 XTTS v2 模型...")
    tts = TTS("tts_models/multilingual/multi-dataset/xtts_v2")

    for i, text in enumerate(texts, 1):
        output_file = output_path / f"output_{i:03d}.wav"
        print(f"\n[{i}/{len(texts)}] 生成: {output_file.name}")
        print(f"  文本: {text[:60]}...")

        try:
            tts.tts_to_file(
                text=text,
                speaker_wav=ref_audio,
                language=language,
                file_path=str(output_file)
            )
            size_mb = output_file.stat().st_size / (1024 * 1024)
            print(f"  ✓ 完成 ({size_mb:.2f} MB)")
        except Exception as e:
            print(f"  ✗ 失败: {e}")

    print(f"\n✓ 批量生成完成! 共 {len(texts)} 个文件")

def main():
    parser = argparse.ArgumentParser(description="批量语音合成")
    parser.add_argument("--ref_audio", required=True, help="参考音频文件")
    parser.add_argument("--texts", nargs="+", required=True, help="要合成的文本列表")
    parser.add_argument("--output_dir", default="./output", help="输出目录")
    parser.add_argument("--language", default="zh-cn", help="语言 (默认: zh-cn)")

    args = parser.parse_args()

    if len(args.texts) == 1 and os.path.isfile(args.texts[0]):
        # 如果第一个参数是文件，读取文本列表
        with open(args.texts[0], 'r', encoding='utf-8') as f:
            texts = [line.strip() for line in f if line.strip()]
    else:
        texts = args.texts

    batch_tts(texts, args.ref_audio, args.output_dir, args.language)

if __name__ == "__main__":
    main()
