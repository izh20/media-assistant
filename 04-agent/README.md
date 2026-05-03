# 垂直行业 Agent

> 基于本地 RAG 基础设施的 Agent 框架
> 存储路径: `/Volumes/扩展盘512G/claude/project01/04-agent`

---

## 功能概述

- 智能对话 Agent
- 知识库问答
- 工具调用 (搜索、计算等)
- 工作流自动化

## 系统架构

```
用户查询 → Agent Framework → 工具调用 → 知识库/计算 → LLM → 回答
                        ↓
                  记忆模块 (规划中)
                  工具箱
```

## 依赖服务

| 服务 | 地址 | 说明 |
|------|------|------|
| LLM | 127.0.0.1:8080 | Qwen2.5-7B |
| Embedding | 127.0.0.1:8081 | nomic-embed-text |
| Qdrant | 127.0.0.1:6333 | 知识库 |

> 确保 RAG 服务已启动: `../startup.sh rag`

## 使用方法

### 1. 普通对话

```bash
source .venv/bin/activate
python3 agent.py chat "你好，介绍一下你自己"
```

### 2. 知识库问答

```bash
source .venv/bin/activate
python3 agent.py ask "什么是 RAG"
```

### 3. 带工具调用的 Agent

```bash
source .venv/bin/activate
python3 agent.py tool "2+3*5 等于多少"
```

### 4. 工作流执行

```bash
source .venv/bin/activate

# 列出可用工作流
python3 workflow.py list

# 执行知识库问答工作流
python3 workflow.py run ask_with_search "人工智能的定义"
```

## 工具定义

### search_knowledge
- **功能**: 搜索知识库相关内容
- **参数**: `query` (搜索词), `top_k` (返回数量)

### calculate
- **功能**: 执行数学计算
- **参数**: `expression` (数学表达式)

### get_time (预留)
- **功能**: 获取当前时间

## 工作流

### ask_with_search
先搜索知识库，再基于检索结果生成回答。

### analyze_and_calculate
先理解问题，再执行计算并给出解释。

## 目录结构

```
04-agent/
├── README.md           # 本文档
├── agent.py            # Agent 主程序
├── define_tools.py     # 工具定义
├── workflow.py         # 工作流执行器
└── .venv/             # Python 虚拟环境
```

## 下一步计划

1. 添加更多工具 (天气查询、网页搜索等)
2. 记忆模块 (对话历史)
3. 多 Agent 协作
4. Dify 集成

## 硬件要求

| 设备 | 任务 |
|------|------|
| **Mac Mini M4** | Agent 框架 + LLM 推理 |

## 相关文档

- 完整技术方案: [../docs/local-ai-research-guide.md](../docs/local-ai-research-guide.md)
- RAG 实施记录: [../01-rag/README.md](../01-rag/README.md)
