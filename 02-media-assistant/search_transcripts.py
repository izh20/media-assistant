#!/usr/bin/env python3
"""
媒体内容语义搜索
将转录文本存入 Qdrant，支持语义搜索

用法:
    # 添加转录文件到索引
    python3 search_transcripts.py add <transcript.json>

    # 搜索内容
    python3 search_transcripts.py search <query> [top_k]
"""

import sys
import json
import urllib.request
import urllib.error

# 配置
EMBEDDING_URL = "http://127.0.0.1:8081/v1/embeddings"
QDRANT_URL = "http://127.0.0.1:6333"
COLLECTION_NAME = "media_transcripts"

def post_json(url, data, method='POST'):
    """发送 JSON 请求"""
    req = urllib.request.Request(
        url,
        data=json.dumps(data).encode('utf-8'),
        headers={'Content-Type': 'application/json'},
        method=method
    )
    with urllib.request.urlopen(req) as response:
        return json.loads(response.read().decode('utf-8'))

def get_embedding(text):
    """获取文本 embedding"""
    result = post_json(EMBEDDING_URL, {
        "input": text,
        "model": "nomic-embed-text-v1.5.f16.gguf"
    })
    return result["data"][0]["embedding"]

def create_collection():
    """创建 Collection"""
    payload = {
        "vectors": {
            "size": 768,
            "distance": "Cosine"
        }
    }
    try:
        post_json(f"{QDRANT_URL}/collections/{COLLECTION_NAME}", payload, 'PUT')
        print("  Collection 创建成功")
    except urllib.error.HTTPError as e:
        if e.code == 409:
            print("  Collection 已存在")
        else:
            raise

def add_transcript(transcript_path, file_name=None):
    """添加转录文本到向量库"""
    create_collection()

    with open(transcript_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    segments = data.get('segments', [])
    if not segments:
        print("  未找到转录段落")
        return

    print(f"  添加 {len(segments)} 个段落到向量库...")

    points = []
    for i, seg in enumerate(segments):
        text = seg['text']
        if not text.strip():
            continue

        print(f"    [{i}] {text[:50]}...")
        embedding = get_embedding(text)

        points.append({
            "id": f"{file_name or transcript_path}_{i}".__hash__(),
            "vector": embedding,
            "payload": {
                "text": text,
                "start": seg['start'],
                "end": seg['end'],
                "source": file_name or transcript_path
            }
        })

    if points:
        payload = {"points": points}
        result = post_json(
            f"{QDRANT_URL}/collections/{COLLECTION_NAME}/points",
            payload,
            'PUT'
        )
        print(f"  添加完成: {result.get('status', result)}")

def search_transcripts(query, top_k=5):
    """搜索转录内容"""
    print(f"\n  查询: {query}")
    query_embedding = get_embedding(query)

    payload = {
        "vector": query_embedding,
        "limit": top_k,
        "with_payload": True
    }

    result = post_json(
        f"{QDRANT_URL}/collections/{COLLECTION_NAME}/points/search",
        payload
    )

    results = result.get("result", [])
    print(f"\n  找到 {len(results)} 个相关片段:\n")

    for r in results:
        payload = r['payload']
        print(f"  [{payload['start']:.1f}s - {payload['end']:.1f}s] {payload['text']}")
        print(f"    来源: {payload['source']}\n")

    return results

def main():
    if len(sys.argv) < 2:
        print("用法:")
        print("  python3 search_transcripts.py add <transcript.json>")
        print("  python3 search_transcripts.py search <query> [top_k]")
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd == "add":
        if len(sys.argv) < 3:
            print("错误: 请指定转录文件")
            sys.exit(1)
        transcript_file = sys.argv[2]
        file_name = sys.argv[3] if len(sys.argv) > 3 else None
        add_transcript(transcript_file, file_name)

    elif cmd == "search":
        if len(sys.argv) < 3:
            print("错误: 请输入搜索查询")
            sys.exit(1)
        query = sys.argv[2]
        top_k = int(sys.argv[3]) if len(sys.argv) > 3 else 5
        search_transcripts(query, top_k)

    else:
        print(f"未知命令: {cmd}")
        sys.exit(1)

if __name__ == "__main__":
    main()
