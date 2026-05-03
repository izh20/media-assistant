#!/usr/bin/env python3
"""
简单 Agent 框架
使用现有的 RAG 基础设施 (Qdrant + LLM) 构建 Agent

用法:
    # 通用对话 Agent
    python3 agent.py chat "你好"

    # 带知识检索的 Agent
    python3 agent.py ask "什么是 RAG"

    # 带工具调用的 Agent
    python3 agent.py tool "帮我查询天气"
"""

import sys
import json
import urllib.request
import urllib.error

# 配置 - 使用现有的 RAG 服务
LLM_URL = "http://127.0.0.1:8080/v1/chat/completions"
EMBEDDING_URL = "http://127.0.0.1:8081/v1/embeddings"
QDRANT_URL = "http://127.0.0.1:6333"
KNOWLEDGE_COLLECTION = "knowledge_base"

# 工具定义
TOOLS = {
    "search_knowledge": {
        "name": "search_knowledge",
        "description": "搜索知识库中的相关内容",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "搜索查询"}
            },
            "required": ["query"]
        }
    },
    "calculate": {
        "name": "calculate",
        "description": "执行数学计算",
        "parameters": {
            "type": "object",
            "properties": {
                "expression": {"type": "string", "description": "数学表达式，如 '2+3*5'"}
            },
            "required": ["expression"]
        }
    }
}

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

def search_knowledge(query, top_k=3):
    """搜索知识库"""
    query_embedding = get_embedding(query)
    payload = {
        "vector": query_embedding,
        "limit": top_k,
        "with_payload": True
    }
    result = post_json(
        f"{QDRANT_URL}/collections/{KNOWLEDGE_COLLECTION}/points/search",
        payload
    )
    return result.get("result", [])

def calculate(expression):
    """执行计算"""
    try:
        # 安全计算，只允许基本数学运算
        allowed_chars = set('0123456789+-*/.() ')
        if all(c in allowed_chars for c in expression):
            result = eval(expression)
            return str(result)
        return "错误: 只允许基本数学运算"
    except Exception as e:
        return f"错误: {e}"

def call_tool(tool_name, args):
    """调用工具"""
    if tool_name == "search_knowledge":
        return search_knowledge(args["query"])
    elif tool_name == "calculate":
        return calculate(args["expression"])
    else:
        return f"未知工具: {tool_name}"

def chat_with_llm(messages, tools=None):
    """与 LLM 对话"""
    payload = {
        "model": "qwen2.5-7b-instruct-q4_0.gguf",
        "messages": messages,
        "stream": False
    }
    if tools:
        payload["tools"] = tools

    result = post_json(LLM_URL, payload)
    return result.get("choices", [{}])[0].get("message", {}).get("content", "")

def format_tools_description():
    """格式化工具描述"""
    lines = ["可用的工具:"]
    for tool in TOOLS.values():
        lines.append(f"- {tool['name']}: {tool['description']}")
    return "\n".join(lines)

def agent_chat(query):
    """Agent 对话模式"""
    system_prompt = """你是一个智能助手。如果需要查询信息，可以使用知识库搜索工具。
遇到计算问题时，可以使用计算工具。
请始终尽可能帮助用户解决问题。"""

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": query}
    ]

    print(f"\n问题: {query}")
    print("\n思考中...")

    response = chat_with_llm(messages)
    print(f"\n回答: {response}")

def agent_ask(query):
    """Agent 问答模式 (先检索知识库)"""
    print(f"\n查询: {query}")
    print("\n检索知识库...")

    results = search_knowledge(query, top_k=3)

    if results:
        print(f"\n找到 {len(results)} 条相关信息:")
        context_parts = []
        for i, r in enumerate(results, 1):
            text = r['payload']['text']
            print(f"  {i}. {text[:80]}...")
            context_parts.append(text)

        context = "\n".join(context_parts)
        system_prompt = f"""基于以下上下文信息回答问题。如果上下文中没有相关信息，请说明不知道。

上下文：
{context}
"""
    else:
        print("  未找到相关内容")
        system_prompt = "请回答用户的问题。如果不知道答案，请说明不知道。"

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": query}
    ]

    print("\n生成回答...")
    response = chat_with_llm(messages)
    print(f"\n回答: {response}")

def agent_with_tools(query):
    """带工具调用的 Agent"""
    system_prompt = f"""你是一个智能助手。你有以下工具可用：

{format_tools_description()}

当用户提出问题时，判断是否需要使用工具：
- 如果需要搜索知识库，使用 search_knowledge
- 如果需要进行计算，使用 calculate

请以 JSON 格式返回你的响应：
{{"thought": "你的思考过程", "tool": "工具名或null", "args": {{"参数"}}, "response": "直接回答或'等待工具结果'"}}
"""

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": query}
    ]

    print(f"\n问题: {query}")
    print("\n思考中...")

    # 第一轮：让 LLM 决定是否需要工具
    response = chat_with_llm(messages)

    try:
        # 尝试解析 JSON 响应
        import re
        json_match = re.search(r'\{.*\}', response, re.DOTALL)
        if json_match:
            result = json.loads(json_match.group())
            thought = result.get("thought", "")
            tool = result.get("tool")
            args = result.get("args", {})
            print(f"\n思考: {thought}")

            if tool:
                print(f"\n调用工具: {tool}")
                if args:
                    print(f"参数: {args}")

                tool_result = call_tool(tool, args)
                print(f"工具结果: {tool_result}")

                # 第二轮：用工具结果生成最终回答
                messages.append({"role": "assistant", "content": response})
                messages.append({"role": "user", "content": f"工具返回结果: {tool_result}"})
                final_response = chat_with_llm(messages)
                print(f"\n最终回答: {final_response}")
            else:
                print(f"\n回答: {result.get('response', response)}")
        else:
            print(f"\n回答: {response}")
    except Exception as e:
        print(f"\n回答: {response}")
        print(f"\n(解析辅助信息时出错: {e})")

def main():
    if len(sys.argv) < 2:
        print("用法:")
        print("  python3 agent.py chat \"你好\"              # 普通对话")
        print("  python3 agent.py ask \"什么是 RAG\"         # 知识库问答")
        print("  python3 agent.py tool \"2+3等于多少\"      # 带工具调用")
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd == "chat":
        query = sys.argv[2] if len(sys.argv) > 2 else "你好"
        agent_chat(query)
    elif cmd == "ask":
        query = sys.argv[2] if len(sys.argv) > 2 else ""
        if not query:
            print("错误: 请提供查询内容")
            sys.exit(1)
        agent_ask(query)
    elif cmd == "tool":
        query = sys.argv[2] if len(sys.argv) > 2 else ""
        if not query:
            print("错误: 请提供问题内容")
            sys.exit(1)
        agent_with_tools(query)
    else:
        print(f"未知命令: {cmd}")
        sys.exit(1)

if __name__ == "__main__":
    main()
