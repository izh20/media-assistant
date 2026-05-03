#!/usr/bin/env python3
"""
工具定义文件
定义 Agent 可用的工具

用法:
    python3 define_tools.py list          # 列出所有工具
    python3 define_tools.py add          # 添加新工具
"""

import sys

# 内置工具
BUILTIN_TOOLS = {
    "search_knowledge": {
        "name": "search_knowledge",
        "description": "搜索知识库中的相关内容",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "搜索查询"
                },
                "top_k": {
                    "type": "integer",
                    "description": "返回结果数量，默认3",
                    "default": 3
                }
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
                "expression": {
                    "type": "string",
                    "description": "数学表达式，如 '2+3*5'"
                }
            },
            "required": ["expression"]
        }
    },
    "get_time": {
        "name": "get_time",
        "description": "获取当前时间",
        "parameters": {
            "type": "object",
            "properties": {}
        }
    }
}

def list_tools():
    """列出所有可用工具"""
    print("\n=== 可用工具 ===\n")
    for name, tool in BUILTIN_TOOLS.items():
        print(f"工具: {tool['name']}")
        print(f"描述: {tool['description']}")
        print(f"参数: {json.dumps(tool['parameters'], indent=2, ensure_ascii=False)}")
        print()

def add_tool():
    """添加新工具 (预留接口)"""
    print("\n添加自定义工具...")
    print("提示: 请编辑 define_tools.py 文件添加新工具")
    print("\n示例工具结构:")
    print("""
{
    "name": "my_tool",
    "description": "我的自定义工具",
    "parameters": {
        "type": "object",
        "properties": {
            "param1": {"type": "string"}
        },
        "required": ["param1"]
    }
}
""")

def get_tools_schemas():
    """获取所有工具的 schemas (用于 LLM 函数调用)"""
    return list(BUILTIN_TOOLS.values())

if __name__ == "__main__":
    import json

    if len(sys.argv) < 2:
        list_tools()
    else:
        cmd = sys.argv[1]
        if cmd == "list":
            list_tools()
        elif cmd == "add":
            add_tool()
        else:
            print(f"未知命令: {cmd}")
