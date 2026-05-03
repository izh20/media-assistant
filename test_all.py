#!/usr/bin/env python3
"""
全方向测试脚本
测试 RAG、媒体助理、声音克隆、Agent 四个方向

用法:
    python3 test_all.py [direction]

参数:
    all     - 测试所有方向 (默认)
    rag     - 只测试 RAG
    media   - 只测试媒体助理
    voice   - 只测试声音克隆
    agent   - 只测试 Agent
"""

import sys
import os
import json
import subprocess
import urllib.request
import urllib.error

# 配置
LLM_URL = "http://127.0.0.1:8080/v1/chat/completions"
EMBEDDING_URL = "http://127.0.0.1:8081/v1/embeddings"
QDRANT_URL = "http://127.0.0.1:6333"

def green(text):
    return f"\033[92m✓ {text}\033[0m"

def red(text):
    return f"\033[91m✗ {text}\033[0m"

def yellow(text):
    return f"\033[93m→ {text}\033[0m"

def post_json(url, data, method='POST'):
    req = urllib.request.Request(
        url,
        data=json.dumps(data).encode('utf-8'),
        headers={'Content-Type': 'application/json'},
        method=method
    )
    with urllib.request.urlopen(req) as response:
        return json.loads(response.read().decode('utf-8'))

def test_services():
    """测试基础服务"""
    print("\n" + "="*50)
    print("测试 1: 基础服务状态")
    print("="*50)

    services = [
        ("Qdrant", f"{QDRANT_URL}/collections"),
        ("LLM (Qwen)", f"{LLM_URL}/models"),
        ("Embedding", f"{EMBEDDING_URL}/models"),
    ]

    all_ok = True
    for name, url in services:
        try:
            result = urllib.request.urlopen(url, timeout=5)
            print(green(f"{name} 运行正常"))
        except Exception as e:
            print(red(f"{name} 不可用: {e}"))
            all_ok = False

    return all_ok

def test_rag():
    """测试 RAG 功能"""
    print("\n" + "="*50)
    print("测试 2: RAG 知识库")
    print("="*50)

    try:
        # 测试 embedding
        result = post_json(EMBEDDING_URL, {
            "input": "测试文本",
            "model": "nomic-embed-text-v1.5.f16.gguf"
        })
        vec = result["data"][0]["embedding"]
        print(green(f"Embedding 服务正常 (向量维度: {len(vec)})"))

        # 测试 LLM
        result = post_json(LLM_URL, {
            "model": "qwen2.5-7b-instruct-q4_0.gguf",
            "messages": [{"role": "user", "content": "你好"}],
            "stream": False
        })
        response = result.get("choices", [{}])[0].get("message", {}).get("content", "")
        print(green(f"LLM 服务正常 (回复: {response[:50]}...)"))

        return True
    except Exception as e:
        print(red(f"RAG 测试失败: {e}"))
        return False

def test_agent():
    """测试 Agent 功能"""
    print("\n" + "="*50)
    print("测试 3: Agent")
    print("="*50)

    try:
        # 简单的知识库搜索测试
        query_embedding = post_json(EMBEDDING_URL, {
            "input": "人工智能",
            "model": "nomic-embed-text-v1.5.f16.gguf"
        })["data"][0]["embedding"]

        payload = {
            "vector": query_embedding,
            "limit": 2,
            "with_payload": True
        }
        result = post_json(
            f"{QDRANT_URL}/collections/knowledge_base/points/search",
            payload
        )

        results = result.get("result", [])
        print(green(f"Agent 知识库检索正常 (找到 {len(results)} 条结果)"))

        # 测试 LLM 对话
        result = post_json(LLM_URL, {
            "model": "qwen2.5-7b-instruct-q4_0.gguf",
            "messages": [
                {"role": "system", "content": "你是一个智能助手"},
                {"role": "user", "content": "1+1等于几？"}
            ],
            "stream": False
        })
        response = result.get("choices", [{}])[0].get("message", {}).get("content", "")
        print(green(f"Agent 对话正常 (回复: {response[:30]}...)"))

        return True
    except Exception as e:
        print(red(f"Agent 测试失败: {e}"))
        return False

def test_media():
    """测试媒体助理"""
    print("\n" + "="*50)
    print("测试 4: 媒体助理")
    print("="*50)

    try:
        venv_python = "/Volumes/扩展盘512G/claude/project01/02-media-assistant/.venv/bin/python"
        result = subprocess.run(
            [venv_python, "-c", "from faster_whisper import WhisperModel; print('OK')"],
            capture_output=True, text=True, timeout=30
        )
        if result.returncode == 0 and "OK" in result.stdout:
            print(green("faster-whisper 可用"))
        else:
            print(yellow(f"faster-whisper 可能有问题: {result.stderr}"))

        # 检查 ffmpeg
        result = subprocess.run(["which", "ffmpeg"], capture_output=True)
        if result.returncode == 0:
            print(green("FFmpeg 已安装"))
        else:
            print(red("FFmpeg 未安装"))

        return True
    except Exception as e:
        print(red(f"媒体助理测试失败: {e}"))
        return False

def test_voice():
    """测试声音克隆"""
    print("\n" + "="*50)
    print("测试 5: 声音克隆")
    print("="*50)

    try:
        venv_python = "/Volumes/扩展盘512G/claude/project01/03-voice-cloning/.venv/bin/python"
        result = subprocess.run(
            [venv_python, "-c", "from TTS.api import TTS; print('OK')"],
            capture_output=True, text=True, timeout=30
        )
        if result.returncode == 0 and "OK" in result.stdout:
            print(green("Coqui TTS (XTTS v2) 可用"))
        else:
            print(yellow(f"TTS 可能有问题"))

        return True
    except Exception as e:
        print(red(f"声音克隆测试失败: {e}"))
        return False

def main():
    print("\n" + "="*50)
    print("本地 AI 研究项目 - 全方向测试")
    print("="*50)

    direction = sys.argv[1] if len(sys.argv) > 1 else "all"

    if direction == "all":
        results = []
        results.append(("基础服务", test_services()))
        results.append(("RAG", test_rag()))
        results.append(("Agent", test_agent()))
        results.append(("媒体助理", test_media()))
        results.append(("声音克隆", test_voice()))

        print("\n" + "="*50)
        print("测试结果汇总")
        print("="*50)
        for name, ok in results:
            print(f"{green('✓') if ok else red('✗')} {name}")

    elif direction == "rag":
        test_services()
        test_rag()
    elif direction == "agent":
        test_services()
        test_agent()
    elif direction == "media":
        test_media()
    elif direction == "voice":
        test_voice()
    else:
        print(f"未知方向: {direction}")
        print("用法: python3 test_all.py [all|rag|agent|media|voice]")
        sys.exit(1)

if __name__ == "__main__":
    main()
