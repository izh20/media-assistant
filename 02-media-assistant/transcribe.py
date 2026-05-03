#!/usr/bin/env python3
"""
视频/音频转录脚本
使用 faster-whisper 将视频或音频文件转录为文字

用法:
    python3 transcribe.py <输入文件> [输出目录]
"""

import sys
import json
import os
import subprocess
from pathlib import Path

# 配置
MODEL_SIZE = "small"  # tiny/small/base/medium/large
DEVICE = "cpu"  # cpu/mps/cuda
COMPUTE_TYPE = "int8"  # int8/float16/float32
VAD_FILTER = True  # 语音活动检测
QDRANT_URL = "http://127.0.0.1:6333"
COLLECTION_NAME = "media_transcripts"

def extract_audio(video_path, audio_path):
    """使用 FFmpeg 从视频提取音频"""
    print(f"  提取音频到 {audio_path}...")
    cmd = [
        "ffmpeg", "-y", "-i", video_path,
        "-vn", "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1",
        audio_path
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    print("  音频提取完成")

def transcribe_audio(audio_path):
    """使用 faster-whisper 转录音频"""
    from faster_whisper import WhisperModel

    print(f"  加载模型: {MODEL_SIZE}...")
    model = WhisperModel(
        MODEL_SIZE,
        device=DEVICE,
        compute_type=COMPUTE_TYPE
    )

    print("  开始转录...")
    segments, info = model.transcribe(
        audio_path,
        vad_filter=VAD_FILTER,
        language="zh"
    )

    print(f"  检测到语言: {info.language} (概率: {info.language_probability:.2f})")

    results = []
    for segment in segments:
        results.append({
            "start": segment.start,
            "end": segment.end,
            "text": segment.text.strip()
        })
        print(f"    [{segment.start:.2f}s -> {segment.end:.2f}s] {segment.text}")

    return results, info.language

def save_transcript(results, output_path, info):
    """保存转录结果为 JSON 和 SRT 格式"""
    base = Path(output_path).with_suffix("")

    # JSON 格式
    json_path = f"{base}.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump({
            "language": info.language if hasattr(info, 'language') else "unknown",
            "segments": results
        }, f, ensure_ascii=False, indent=2)
    print(f"  已保存: {json_path}")

    # SRT 格式
    srt_path = f"{base}.srt"
    with open(srt_path, "w", encoding="utf-8") as f:
        for i, seg in enumerate(results, 1):
            start = format_time(seg["start"])
            end = format_time(seg["end"])
            f.write(f"{i}\n{start} --> {end}\n{seg['text']}\n\n")
    print(f"  已保存: {srt_path}")

    return json_path, srt_path

def format_time(seconds):
    """将秒数转换为 SRT 时间格式 HH:MM:SS,mmm"""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int((seconds % 1) * 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"

def main():
    if len(sys.argv) < 2:
        print("用法: python3 transcribe.py <输入文件> [输出目录]")
        sys.exit(1)

    input_file = sys.argv[1]
    output_dir = sys.argv[2] if len(sys.argv) > 2 else "."

    if not os.path.exists(input_file):
        print(f"错误: 文件不存在: {input_file}")
        sys.exit(1)

    input_path = Path(input_file)
    output_path = Path(output_dir) / input_path.stem

    print(f"\n=== 转录: {input_path.name} ===\n")

    # 临时音频文件
    temp_audio = Path("/tmp") / f"{input_path.stem}_audio.wav"

    try:
        # 1. 提取音频
        extract_audio(str(input_path), str(temp_audio))

        # 2. 转录
        results, language = transcribe_audio(str(temp_audio))

        # 3. 保存结果
        save_transcript(results, str(output_path), type('obj', (object,), {'language': language}))

        print(f"\n✓ 转录完成!")
        print(f"  输出: {output_path}.json, {output_path}.srt")

    finally:
        # 清理临时文件
        if temp_audio.exists():
            os.remove(temp_audio)

if __name__ == "__main__":
    main()
