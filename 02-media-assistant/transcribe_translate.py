#!/usr/bin/env python3
"""
日语视频自动翻译字幕工具
使用 faster-whisper 识别日语语音，再翻译成中文生成字幕

用法:
    python3 transcribe_translate.py <视频文件> [输出目录]
"""

import sys
import os
import json
import subprocess
import re
from pathlib import Path

# 配置
MODEL_SIZE = "small"  # tiny/small/base/medium/large-v3
DEVICE = "cpu"  # cpu/mps/cuda
COMPUTE_TYPE = "int8"  # int8/float16/float32
SOURCE_LANGUAGE = "ja"  # 日语
TARGET_LANGUAGE = "zh"  # 中文

# LLM 翻译配置
LLM_URL = "http://127.0.0.1:8082/v1/chat/completions"

def extract_audio(video_path, audio_path):
    """使用 FFmpeg 从视频提取音频"""
    print(f"  提取音频...")
    cmd = [
        "ffmpeg", "-y", "-i", video_path,
        "-vn", "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1",
        audio_path
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    print(f"  音频提取完成: {audio_path}")

def transcribe_audio(audio_path):
    """使用 faster-whisper 转录音频 (日语)"""
    from faster_whisper import WhisperModel

    print(f"  加载 Whisper 模型: {MODEL_SIZE}...")
    model = WhisperModel(MODEL_SIZE, device=DEVICE, compute_type=COMPUTE_TYPE)

    print(f"  开始转录 (日语)...")
    segments, info = model.transcribe(
        audio_path,
        vad_filter=True,
        language=SOURCE_LANGUAGE
    )

    print(f"  检测到语言: {info.language} (概率: {info.language_probability:.2f})")

    results = []
    for segment in segments:
        results.append({
            "start": segment.start,
            "end": segment.end,
            "text": segment.text.strip()
        })
        print(f"    [{segment.start:.2f}s - {segment.end:.2f}s] {segment.text[:50]}...")

    return results

def translate_with_llm(text_list, batch_size=10):
    """使用本地 LLM 翻译日语文本为中文"""
    import urllib.request
    import urllib.error

    def post_json(url, data):
        req = urllib.request.Request(
            url,
            data=json.dumps(data).encode('utf-8'),
            headers={'Content-Type': 'application/json'},
            method='POST'
        )
        with urllib.request.urlopen(req, timeout=120) as response:
            return json.loads(response.read().decode('utf-8'))

    translations = []
    total = len(text_list)

    print(f"\n  开始翻译 ({total} 段)...")

    for i in range(0, total, batch_size):
        batch = text_list[i:i+batch_size]
        batch_text = "\n".join([f"{j+1}. {text}" for j, text in enumerate(batch)])

        prompt = f"""将以下日语字幕翻译成中文。保持简洁，符合字幕风格。

{len(batch)} 条字幕:
{batch_text}

中文翻译 (每行一条):"""

        try:
            result = post_json(LLM_URL, {
                "model": "qwen2.5-7b-instruct-q4_0.gguf",
                "messages": [
                    {"role": "system", "content": "你是一个专业的日语翻译，擅长将日语字幕翻译成简洁的中文。"},
                    {"role": "user", "content": prompt}
                ],
                "stream": False
            })

            response = result.get("choices", [{}])[0].get("message", {}).get("content", "")

            # 解析翻译结果
            lines = response.strip().split('\n')
            for line in lines:
                line = line.strip()
                # 去掉可能的序号
                line = re.sub(r'^\d+[\.\、\：\:]?\s*', '', line)
                if line:
                    translations.append(line)
                else:
                    translations.append("[翻译失败]")

            print(f"    翻译进度: {min(i+batch_size, total)}/{total}")

        except Exception as e:
            print(f"    翻译出错: {e}")
            # 使用原文作为后备
            for _ in batch:
                translations.append("[翻译失败]")

    return translations

def create_srt(segments, translations, output_path):
    """生成 SRT 字幕文件 (中文字幕)"""
    with open(output_path, 'w', encoding='utf-8') as f:
        for i, (seg, trans) in enumerate(zip(segments, translations), 1):
            start = format_time(seg['start'])
            end = format_time(seg['end'])
            f.write(f"{i}\n")
            f.write(f"{start} --> {end}\n")
            f.write(f"{trans}\n\n")

    print(f"\n  中文字幕已保存: {output_path}")

def create_bilingual_srt(segments, japanese_text, chinese_text, output_path):
    """生成双语字幕 (日语在上，中文在下)"""
    with open(output_path, 'w', encoding='utf-8') as f:
        for i, ((seg, jp), cn) in enumerate(zip(zip(segments, japanese_text), chinese_text), 1):
            start = format_time(seg['start'])
            end = format_time(seg['end'])
            f.write(f"{i}\n")
            f.write(f"{start} --> {end}\n")
            f.write(f"{jp}\n{cn}\n\n")

def create_japanese_srt(segments, output_path):
    """生成日语字幕文件"""
    with open(output_path, 'w', encoding='utf-8') as f:
        for i, seg in enumerate(segments, 1):
            start = format_time(seg['start'])
            end = format_time(seg['end'])
            f.write(f"{i}\n")
            f.write(f"{start} --> {end}\n")
            f.write(f"{seg['text']}\n\n")

def format_time(seconds):
    """将秒数转换为 SRT 时间格式 HH:MM:SS,mmm"""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int((seconds % 1) * 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"

def main():
    if len(sys.argv) < 2:
        print("用法: python3 transcribe_translate.py <视频文件> [输出目录]")
        print("\n示例:")
        print("  python3 transcribe_translate.py video.mp4")
        print("  python3 transcribe_translate.py video.mp4 ./subtitles")
        sys.exit(1)

    input_file = sys.argv[1]
    output_dir = sys.argv[2] if len(sys.argv) > 2 else "."

    if not os.path.exists(input_file):
        print(f"错误: 文件不存在: {input_file}")
        sys.exit(1)

    input_path = Path(input_file)
    output_path = Path(output_dir)

    print(f"\n{'='*50}")
    print(f"日语视频翻译字幕工具")
    print(f"{'='*50}")
    print(f"\n输入文件: {input_path.name}")
    print(f"输出目录: {output_path}")

    temp_audio = Path("/tmp") / f"{input_path.stem}_audio.wav"

    try:
        # 1. 提取音频
        print(f"\n[步骤1] 提取音频...")
        extract_audio(str(input_path), str(temp_audio))

        # 2. 转录日语
        print(f"\n[步骤2] 转录日语语音...")
        segments = transcribe_audio(str(temp_audio))
        japanese_texts = [s['text'] for s in segments]
        print(f"\n  共识别 {len(segments)} 段日语")

        # 3. 翻译成中文
        print(f"\n[步骤3] 翻译为中文...")
        chinese_texts = translate_with_llm(japanese_texts)

        # 4. 生成字幕文件
        print(f"\n[步骤4] 生成字幕文件...")

        # 保存中文字幕
        chinese_srt = output_path / f"{input_path.stem}_chinese.srt"
        create_srt(segments, chinese_texts, str(chinese_srt))

        # 保存日语字幕 (备份)
        japanese_srt = output_path / f"{input_path.stem}_japanese.srt"
        create_japanese_srt(segments, str(japanese_srt))

        # 保存双语字幕
        bilingual_srt = output_path / f"{input_path.stem}_bilingual.srt"
        create_bilingual_srt(segments, japanese_texts, chinese_texts, str(bilingual_srt))

        print(f"\n{'='*50}")
        print(f"✅ 处理完成!")
        print(f"{'='*50}")
        print(f"\n生成的文件:")
        print(f"  📄 中文字幕: {chinese_srt.name}")
        print(f"  📄 日语字幕: {japanese_srt.name}")
        print(f"  📄 双语字幕: {bilingual_srt.name}")
        print(f"\n下一步: 使用视频播放器加载 .srt 字幕文件")

    finally:
        # 清理临时文件
        if temp_audio.exists():
            os.remove(temp_audio)

if __name__ == "__main__":
    main()