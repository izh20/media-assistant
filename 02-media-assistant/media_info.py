#!/usr/bin/env python3
"""
媒体文件信息查看工具
使用 FFprobe 获取视频/音频文件的详细信息

用法:
    python3 media_info.py <media_file>
"""

import sys
import json
import subprocess
from pathlib import Path

def get_media_info(file_path):
    """使用 ffprobe 获取媒体信息"""
    cmd = [
        "ffprobe",
        "-v", "quiet",
        "-print_format", "json",
        "-show_format",
        "-show_streams",
        file_path
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)
    return json.loads(result.stdout)

def format_duration(seconds):
    """格式化时长"""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    if hours > 0:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"

def print_media_info(info):
    """打印媒体信息"""
    format_info = info.get('format', {})

    print(f"\n=== 媒体文件信息 ===")
    print(f"文件名: {format_info.get('filename', 'N/A')}")
    print(f"时长: {format_duration(float(format_info.get('duration', 0)))}")
    print(f"大小: {int(format(format_info.get('size', 0), 0)) / (1024**2):.2f} MB")
    print(f"比特率: {int(format_info.get('bit_rate', 0)) / 1000:.0f} kbps")
    print()

    streams = info.get('streams', [])
    for i, stream in enumerate(streams):
        codec_type = stream.get('codec_type', 'unknown')
        print(f"流 {i} ({codec_type}):")

        if codec_type == 'video':
            print(f"  编码: {stream.get('codec_name', 'N/A')}")
            print(f"  分辨率: {stream.get('width', 'N/A')}x{stream.get('height', 'N/A')}")
            print(f"  帧率: {eval(stream.get('r_frame_rate', '0')):.2f} fps")
            print(f"  像素格式: {stream.get('pix_fmt', 'N/A')}")

        elif codec_type == 'audio':
            print(f"  编码: {stream.get('codec_name', 'N/A')}")
            print(f"  采样率: {stream.get('sample_rate', 'N/A')} Hz")
            print(f"  声道数: {stream.get('channels', 'N/A')}")
            print(f"  语言: {stream.get('tags', {}).get('language', 'N/A')}")

        print()

def main():
    if len(sys.argv) < 2:
        print("用法: python3 media_info.py <media_file>")
        sys.exit(1)

    file_path = sys.argv[1]

    if not Path(file_path).exists():
        print(f"错误: 文件不存在: {file_path}")
        sys.exit(1)

    try:
        info = get_media_info(file_path)
        print_media_info(info)
    except Exception as e:
        print(f"错误: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
