#!/usr/bin/env python3
"""简单的 RAG 验证脚本"""

import urllib.request
import urllib.error
import json

# 配置
EMBEDDING_URL = "http://127.0.0.1:8081/v1/embeddings"
LLM_URL = "http://127.0.0.1:8080/v1/chat/completions"
QDRANT_URL = "http://127.0.0.1:6333"
COLLECTION_NAME = "knowledge_base"

# 测试文档
test_docs = [
    "人工智能(AI)是计算机科学的一个分支，致力于开发能够执行通常需要人类智能的任务的系统。",
    "机器学习是AI的一个子集，它使系统能够从数据中学习并改进，而无需明确编程。",
    "深度学习是机器学习的一个分支，使用多层神经网络来分析各种因素的数据。"
]

def post_json(url, data, method='POST'):
    """发送 JSON POST/PUT 请求"""
    req = urllib.request.Request(
        url,
        data=json.dumps(data).encode('utf-8'),
        headers={'Content-Type': 'application/json'},
        method=method
    )
    with urllib.request.urlopen(req) as response:
        return json.loads(response.read().decode('utf-8'))

def get_embedding(text):
    """获取文本的 embedding"""
    result = post_json(EMBEDDING_URL, {
        "input": text,
        "model": "nomic-embed-text-v1.5.f16.gguf"
    })
    return result["data"][0]["embedding"]

def create_collection():
    """创建 Qdrant collection (如果已存在则跳过)"""
    payload = {
        "vectors": {
            "size": 768,
            "distance": "Cosine"
        }
    }
    try:
        result = post_json(f"{QDRANT_URL}/collections/{COLLECTION_NAME}", payload, 'PUT')
        print(f"  Created collection: {result.get('status', result)}")
    except urllib.error.HTTPError as e:
        if e.code == 409:
            print(f"  Collection already exists, skipping creation")
        else:
            raise

def add_documents():
    """添加文档到向量数据库"""
    create_collection()

    for i, doc in enumerate(test_docs):
        print(f"  Getting embedding for doc {i}...")
        embedding = get_embedding(doc)
        payload = {
            "points": [{
                "id": i,
                "vector": embedding,
                "payload": {"text": doc}
            }]
        }
        result = post_json(
            f"{QDRANT_URL}/collections/{COLLECTION_NAME}/points",
            payload,
            'PUT'
        )
        print(f"  Added doc {i}: {result.get('status', result)}")

def search(query, top_k=2):
    """搜索相似文档"""
    print(f"  Getting embedding for query...")
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
    return result.get("result", [])

def ask_llm(context, query):
    """使用 LLM 生成回答"""
    prompt = f"""基于以下上下文信息回答问题。如果上下文中没有相关信息，请说明不知道。

上下文：
{context}

问题：{query}

回答："""

    result = post_json(LLM_URL, {
        "model": "qwen2.5-7b-instruct-q4_0.gguf",
        "messages": [
            {"role": "user", "content": prompt}
        ],
        "stream": False
    })
    return result.get("choices", [{}])[0].get("message", {}).get("content", "")

def main():
    print("=== RAG 验证测试 ===\n")

    # 1. 添加文档
    print("1. 添加测试文档到 Qdrant...")
    add_documents()

    # 2. 查询
    print("\n2. 测试搜索...")
    query = "什么是人工智能？"
    results = search(query)
    print(f"\n  查询: {query}")
    print(f"  找到 {len(results)} 个相关文档:")
    for r in results:
        print(f"    - {r['payload']['text']}")

    # 3. RAG 回答
    print("\n3. RAG 回答 (使用本地 Qwen2.5-7B)...")
    context = "\n".join([r['payload']['text'] for r in results])
    answer = ask_llm(context, query)
    print(f"\n  回答:\n{answer}")

if __name__ == "__main__":
    main()
