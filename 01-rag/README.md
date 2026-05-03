# RAG 本地知识库

> 本文档记录在 Mac Mini M4 16G 上搭建本地 RAG 知识库的完整过程
> 创建时间：2026-04-30
> 硬件：Mac Mini M4 16G

---

## 系统架构

```
用户问题
    ↓
Embedding 模型 (nomic-embed-text-v1.5.f16.gguf)
    ↓ (端口 8081)
向量数据库 (Qdrant)
    ↓
LLM (Qwen2.5-7B-Instruct q4_0)
    ↓ (端口 8080)
回答
```

## 🌐 Web UI 局域网访问

**启动所有服务：**
```bash
cd /Volumes/扩展盘512G/claude/project01/01-rag
./startup.sh all
```

**启动后访问地址：**
- 本机访问: http://localhost:8088
- 局域网访问: http://<本机IP>:8088

**查看本机 IP：**
```bash
./startup.sh ip
```

## 服务组件

| 组件 | 端口 | 访问地址 |
|------|------|---------|
| Web UI | 8088 | http://0.0.0.0:8088 |
| Qdrant | 6333 | http://0.0.0.0:6333 |
| Embedding | 8081 | http://0.0.0.0:8081 |
| LLM | 8080 | http://0.0.0.0:8080 |

## 服务管理命令

```bash
cd /Volumes/扩展盘512G/claude/project01/01-rag

# 启动所有服务 (推荐)
./startup.sh all

# 仅启动 Web UI
./startup.sh web

# 启动 RAG 基础服务 (Qdrant + Embedding)
./startup.sh rag

# 启动 LLM
./startup.sh llama qwen2.5-7b-instruct-q4_0.gguf 8080

# 查看服务状态
./startup.sh status

# 查看本机 IP
./startup.sh ip

# 停止所有服务
./startup.sh stop
```

## Web UI 功能

- 💬 **智能问答**: 输入问题，基于知识库生成回答
- 📚 **参考资料**: 显示回答引用的文档来源
- ➕ **添加文档**: 可直接添加文本到知识库
- 📱 **响应式**: 支持手机、平板、电脑访问

## 模型文件

### Embedding 模型
- **文件**: `nomic-embed-text-v1.5.f16.gguf`
- **大小**: 262MB
- **位置**: `/Volumes/扩展盘512G/claude/project01/models/`

### LLM 模型
- **文件**: `qwen2.5-7b-instruct-q4_0.gguf`
- **大小**: 4.1GB
- **位置**: `/Volumes/扩展盘512G/claude/project01/models/Qwen2.5-7B-Instruct-GGUF/`

## 存储路径

```
/Volumes/扩展盘512G/claude/project01/
├── 01-rag/                    # RAG 项目目录
│   ├── README.md             # 本文档
│   ├── startup.sh            # 服务管理脚本
│   ├── web_app.py            # Web UI (FastAPI)
│   ├── test_rag.py           # 验证测试脚本
│   └── .venv/                # Python 虚拟环境
├── models/                    # 模型文件
│   ├── nomic-embed-text-v1.5.f16.gguf
│   └── Qwen2.5-7B-Instruct-GGUF/
│       └── qwen2.5-7b-instruct-q4_0.gguf
└── qdrant_storage/            # Qdrant 数据存储
```

## 验证测试

```bash
# 运行 RAG 验证测试
python3 test_rag.py

# 运行全方向测试
cd /Volumes/扩展盘512G/claude/project01
python3 test_all.py
```

## 常见问题

### Q: 局域网无法访问 Web UI
A: 检查防火墙设置，允许端口 8088 入站

### Q: 服务启动失败
A: 检查日志文件 `/tmp/llm-logs/`

### Q: LLM 响应慢
A: 可切换到更高量化版本 (q5_k_m, q6_k)

## 下一步计划

1. 添加用户认证
2. 支持文档上传 (PDF, Word)
3. 添加 bge-reranker 精排
4. 多知识库支持

## 相关文档

- 项目总览: [../README.md](../README.md)
- 完整技术方案: [../docs/local-ai-research-guide.md](../docs/local-ai-research-guide.md)
