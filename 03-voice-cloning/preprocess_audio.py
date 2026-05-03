#!/usr/bin/env python3
"""
音频预处理脚本
使用 Demucs 分离人声和背景音

用法:
    python3 preprocess_audio.py <audio_file> [output_dir]

输出:
    <name>/vocals.wav   - 分离出的人声
    <name>/no_drums.wav - 去除鼓点的音乐
    <name>/other.wav    - 其他声音
"""

import sys
import os
import subprocess
from pathlib import Path

def preprocess_audio(audio_path, output_dir=None):
    """使用 Demucs 分离音频"""
    input_path = Path(audio_path)

    if not input_path.exists():
        print(f"错误: 文件不存在: {audio_path}")
        return

    # 输出目录默认为输入文件同目录下的 stem 目录
    if output_dir is None:
        output_dir = input_path.parent / input_path.stem
    else:
        output_dir = Path(output_dir) / input_path.stem

    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n=== 音频预处理: {input_path.name} ===")
    print(f"输出目录: {output_dir}")

    print("\n  运行 Demucs 分离...")
    cmd = ["demucs", "--two-stems=vocals", "-o", str(output_dir), str(audio_path)]
    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode != 0:
        print(f"  错误: {result.stderr}")
        return

    # 查找输出文件
    # Demucs 输出格式: <output_dir>/<model>/<stem>/<name>.wav
    # 默认模型: htdemucs
    stems_dir = output_dir / "htdemucs" / input_path.stem

    if stems_dir.exists():
        files = list(stems_dir.glob("*.wav"))
        print(f"\n  生成文件:")
        for f in files:
            size_mb = f.stat().st_size / (1024 * 1024)
            print(f"    {f.name} ({size_mb:.2f} MB)")

        # 复制主要文件到输出目录根
        vocals = stems_dir / "vocals.wav"
        if vocals.exists():
            import shutil
            shutil.copy(vocals, output_dir / "vocals.wav")
            print(f"\n  人声文件: {output_dir / 'vocals.wav'}")

        print("\n✓ 预处理完成!")
    else:
        print("  错误: 未找到输出文件")
        print(f"  实际输出: {list(output_dir.glob('**/*.wav'))}")

def main():
    if len(sys.argv) < 2:
        print("用法: python3 preprocess_audio.py <audio_file> [output_dir]")
        sys.exit(1)

    audio_file = sys.argv[1]
    output_dir = sys.argv[2] if len(sys.argv) > 2 else None

    preprocess_audio(audio_file, output_dir)

if __name__ == "__main__":
    main()
