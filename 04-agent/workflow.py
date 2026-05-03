#!/usr/bin/env python3
"""
工作流执行器
定义和执行多步骤工作流

用法:
    python3 workflow.py run <workflow_name> [args...]

示例工作流:
    python3 workflow.py run ask_with_search "什么是人工智能"
"""

import sys
import json
from pathlib import Path

# 工作流定义
WORKFLOWS = {
    "ask_with_search": {
        "name": "知识库问答",
        "description": "先搜索知识库，再基于结果生成回答",
        "steps": [
            {"type": "search", "query": "{input}", "top_k": 3},
            {"type": "format_context"},
            {"type": "generate", "prompt": "基于上下文回答问题，如果不知道请说明不知道。\n\n上下文：\n{context}\n\n问题：{input}\n\n回答："}
        ]
    },
    "analyze_and_calculate": {
        "name": "分析计算",
        "description": "先理解问题，再执行计算",
        "steps": [
            {"type": "calculate", "expression": "{input}"},
            {"type": "generate", "prompt": "用户问：{input}\n\n计算结果：{calc_result}\n\n请给出清晰的解释。"}
        ]
    }
}

def run_workflow(workflow_name, input_text):
    """执行工作流"""
    if workflow_name not in WORKFLOWS:
        print(f"错误: 未找到工作流 '{workflow_name}'")
        print(f"可用工作流: {', '.join(WORKFLOWS.keys())}")
        return

    workflow = WORKFLOWS[workflow_name]
    print(f"\n=== 执行工作流: {workflow['name']} ===")
    print(f"描述: {workflow['description']}")
    print(f"输入: {input_text}\n")

    context = {"input": input_text}

    for i, step in enumerate(workflow['steps'], 1):
        print(f"[步骤 {i}] {step['type']}")

        if step['type'] == 'search':
            # 搜索知识库
            from agent import search_knowledge
            query = step['query'].format(**context)
            results = search_knowledge(query, step.get('top_k', 3))
            context['search_results'] = results
            print(f"  查询: {query}")
            print(f"  找到 {len(results)} 条结果")

        elif step['type'] == 'format_context':
            # 格式化上下文
            if 'search_results' in context:
                parts = [r['payload']['text'] for r in context['search_results']]
                context['context'] = '\n'.join(parts)
                print(f"  上下文: {context['context'][:100]}...")

        elif step['type'] == 'generate':
            # 生成回答
            from agent import chat_with_llm
            prompt = step['prompt'].format(**context)
            messages = [{"role": "user", "content": prompt}]
            response = chat_with_llm(messages)
            context['response'] = response
            print(f"  回答: {response}")

        elif step['type'] == 'calculate':
            # 计算
            from agent import calculate
            expr = step['expression'].format(**context)
            result = calculate(expr)
            context['calc_result'] = result
            print(f"  计算结果: {result}")

    print(f"\n=== 工作流完成 ===")
    return context.get('response', '')

def list_workflows():
    """列出所有工作流"""
    print("\n=== 可用工作流 ===\n")
    for name, wf in WORKFLOWS.items():
        print(f"名称: {name}")
        print(f"描述: {wf['description']}")
        print(f"步骤数: {len(wf['steps'])}")
        print()

def main():
    if len(sys.argv) < 2:
        print("用法:")
        print("  python3 workflow.py list                     # 列出所有工作流")
        print("  python3 workflow.py run <workflow> [args]   # 执行工作流")
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd == "list":
        list_workflows()
    elif cmd == "run":
        if len(sys.argv) < 3:
            print("错误: 请指定工作流名称")
            sys.exit(1)
        workflow_name = sys.argv[2]
        input_text = sys.argv[3] if len(sys.argv) > 3 else ""
        run_workflow(workflow_name, input_text)
    else:
        print(f"未知命令: {cmd}")

if __name__ == "__main__":
    main()
