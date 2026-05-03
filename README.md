# 本地 AI 研究项目

> Mac Mini M4 16G 上的本地 AI 服务平台
> 存储路径: `/Volumes/扩展盘512G/claude/project01`

---

## 项目状态

| 方向 | 目录 | 状态 | 说明 |
|------|------|------|------|
| RAG 本地知识库 | [01-rag/](01-rag/) | ✅ 已完成 | Qdrant + Embedding + Qwen2.5-7B |
| 私人媒体 AI 助理 | [02-media-assistant/](02-media-assistant/) | ✅ 已完成 | faster-whisper 转录 + Qdrant 搜索 |
| AI 声音克隆服务 | [03-voice-cloning/](03-voice-cloning/) | ✅ 已完成 | XTTS v2 零样本克隆 |
| 垂直行业 Agent | [04-agent/](04-agent/) | ✅ 已完成 | 知识库问答 + 工具调用 |

---

## 当前运行服务

| 服务 | 地址 | 状态 |
|------|------|------|
| Qdrant (向量数据库) | 127.0.0.1:6333 | ✅ |
| Embedding (nomic) | 127.0.0.1:8081 | ✅ |
| LLM (Qwen2.5-7B q4_0) | 127.0.0.1:8080 | ✅ |
| Ollama | 127.0.0.1:11434 | ✅ |

---

## 快速启动

```bash
cd /Volumes/扩展盘512G/claude/project01

# 查看服务状态
./startup.sh status

# 启动 RAG 模式 (Qdrant + Embedding)
./startup.sh rag

# 启动 LLM (Qwen2.5-7B)
./startup.sh llama qwen2.5-7b-instruct-q4_0.gguf 8080

# 停止所有服务
./startup.sh stop

# 运行全方向测试
python3 test_all.py
```

---

## 各方向使用

### 方向1: RAG 知识库

```bash
# 运行 RAG 验证测试
python3 test_rag.py
```

### 方向2: 媒体助理

```bash
cd 02-media-assistant
source .venv/bin/activate

# 查看媒体信息
python3 media_info.py <视频文件>

# 转录视频
python3 transcribe.py <视频文件>

# 添加转录到向量库
python3 search_transcripts.py add <transcript.json>

# 语义搜索
python3 search_transcripts.py search "查询内容"
```

### 方向3: 声音克隆

```bash
cd 03-voice-cloning
source .venv/bin/activate

# 预处理音频 (去噪音)
python3 preprocess_audio.py <audio_file>

# 克隆语音
python3 clone_voice.py tts --text "文本" --ref_audio ref.wav --output out.wav

# 批量合成
python3 batch_tts.py --ref_audio ref.wav --texts "文本1" "文本2"
```

### 方向4: Agent

```bash
cd 04-agent
source .venv/bin/activate

# 普通对话
python3 agent.py chat "你好"

# 知识库问答
python3 agent.py ask "什么是 RAG"

# 带工具调用
python3 agent.py tool "2+3*5 等于多少"

# 工作流
python3 workflow.py list
python3 workflow.py run ask_with_search "人工智能的定义"
```

---

## 目录结构

```
project01/
├── 01-rag/                      # ✅ RAG 知识库
│   ├── README.md               # 详细实施文档
│   ├── startup.sh              # 服务管理脚本
│   └── test_rag.py             # 验证测试脚本
│
├── 02-media-assistant/         # ✅ 私人媒体 AI 助理
│   ├── README.md               # 详细文档
│   ├── transcribe.py           # 视频转录脚本
│   ├── search_transcripts.py   # 语义搜索脚本
│   ├── media_info.py           # 媒体信息查看
│   └── .venv/                  # Python 虚拟环境
│
├── 03-voice-cloning/          # ✅ AI 声音克隆服务
│   ├── README.md               # 详细文档
│   ├── clone_voice.py          # 语音克隆脚本
│   ├── batch_tts.py            # 批量合成脚本
│   ├── preprocess_audio.py     # 音频预处理脚本
│   └── .venv/                  # Python 虚拟环境
│
├── 04-agent/                   # ✅ 垂直行业 Agent
│   ├── README.md               # 详细文档
│   ├── agent.py                # Agent 主程序
│   ├── define_tools.py         # 工具定义
│   ├── workflow.py             # 工作流执行器
│   └── .venv/                  # Python 虚拟环境
│
├── docs/                       # 技术文档
│   └── local-ai-research-guide.md
│
├── models/                     # 模型文件 (~110GB)
│   ├── nomic-embed-text-v1.5.f16.gguf
│   └── Qwen2.5-7B-Instruct-GGUF/
│
├── qdrant_storage/             # Qdrant 数据存储
│
├── startup.sh                  # 服务管理脚本
└── test_rag.py                 # RAG 验证脚本
```

---

## 技术栈

| 组件 | 技术 | 方向 |
|------|------|------|
| 向量数据库 | Qdrant (Docker) | RAG, 媒体 |
| Embedding | nomic-embed-text-v1.5.f16.gguf | RAG, 媒体, Agent |
| LLM | Qwen2.5-7B-Instruct (GGUF) | RAG, Agent |
| LLM 框架 | llama.cpp (llama-server) | RAG, Agent |
| 语音识别 | faster-whisper | 媒体 |
| 音频分离 | Demucs | 媒体, 声音 |
| 语音克隆 | XTTS v2 (Coqui TTS) | 声音 |
| Agent 框架 | 自定义 Python | Agent |

---

## 端口占用

| 端口 | 服务 |
|------|------|
| 6333 | Qdrant |
| 8080 | llama-server (LLM) |
| 8081 | llama-server (Embedding) |
| 11434 | Ollama |

---

## 模型文件位置

| 模型 | 路径 |
|------|------|
| Embedding | `/Volumes/扩展盘512G/claude/project01/models/nomic-embed-text-v1.5.f16.gguf` |
| LLM | `/Volumes/扩展盘512G/claude/project01/models/Qwen2.5-7B-Instruct-GGUF/` |

---

## 参考文档

- 技术方案: [docs/local-ai-research-guide.md](docs/local-ai-research-guide.md)
- RAG 实施记录: [01-rag/README.md](01-rag/README.md)
- 媒体助理: [02-media-assistant/README.md](02-media-assistant/README.md)
- 声音克隆: [03-voice-cloning/README.md](03-voice-cloning/README.md)
- Agent: [04-agent/README.md](04-agent/README.md)
