# 本地 AI 研究方向技术方案

> 独立开发者研究指南
> 更新时间：2026-04-28
> 硬件：4070 Ti S + MacBook Air M4 16G + Mac Mini M4 16G

---

## 目录

1. [资源分析](#资源分析)
2. [方向一：本地化 AI 知识库（RAG）](#方向一本地化-ai-知识库rag)
3. [方向二：私人媒体 AI 助理](#方向二私人媒体-ai-助理)
4. [方向三：AI 声音克隆定制服务](#方向三ai-声音克隆定制服务)
5. [方向四：垂直行业 Agent](#方向四垂直行业-agent)
6. [资源分配建议](#资源分配建议)
7. [推荐学习路径](#推荐学习路径)

---

## 资源分析

### 硬件战力

| 设备                       | 能力                                 | 建议用途  |
| -------------------------- | ------------------------------------ | --------- |
| **4070 Ti S (16GB)** | 训练小模型、7-13B 推理、视频处理     | 训练主力  |
| **MacBook Air M4 16G** | 移动办公、轻量推理、数据清洗        | 移动开发  |
| **Mac Mini M4 16G**    | 轻量服务器、向量库、单服务推理节点  | 24/7 服务 |

### 合理分工

```
Mac Mini → 24/7 待机的 AI 服务节点
4070 Ti S → 训练、推理加速
MacBook Air → 移动开发、日常使用
```

### 执行基线（按现有 16G 版本规划）

- Mac Mini 16G 常驻 Qdrant + 一个 UI/API 服务即可，llama.cpp、Whisper、Jellyfin 不建议同机长期并发常驻。
- 4070 Ti S 负责 LLaVA、Qwen-VL、GPT-SoVITS、批量转写等高峰值任务。
- MacBook Air 16G 只承担开发、评估和轻量本地验证，不作为稳定服务节点。

---

## 方向一：本地化 AI 知识库（RAG）

### 系统架构

```
用户问题
    ↓
Embedding 模型 (nomic-embed-text，MVP 基线)
    ↓
向量数据库 (Qdrant) ← → 文档数据
    ↓
重排序 (bge-reranker)
    ↓
LLM (Llama3.1 8B / Qwen2.5 7B)
    ↓
回答
```

### 开源项目清单

| 组件                 | 推荐项目              | GitHub                                                                       | 备注                    |
| -------------------- | --------------------- | ---------------------------------------------------------------------------- | ----------------------- |
| **向量数据库** | Qdrant                | [qdrant/qdrant](https://github.com/qdrant/qdrant)                               | Rust 写的，支持本地部署 |
|                      | ChromaDB              | [chroma-core/chroma](https://github.com/chroma-core/chroma)                     | 最流行，简单易用        |
|                      | Milvus                | [milvus-io/milvus](https://github.com/milvus-io/milvus)                         | 大规模数据用            |
| **Embedding**  | sentence-transformers | [UKPLab/sentence-transformers](https://github.com/UKPLab/sentence-transformers) | all-MiniLM-L6-v2 首发地 |
|                      | bge-large-zh-v1.5     | [BAAI/bge-large-zh-v1.5](https://huggingface.co/BAAI/bge-large-zh-v1.5)         | 中文 embedding          |
| **LLM 框架**   | llama.cpp             | [ggerganov/llama.cpp](https://github.com/ggerganov/llama.cpp)                     | RAG 基线推荐，性能与显存控制最优 |
|                      | Ollama                | [ollama/ollama](https://github.com/ollama/ollama)                                 | 本机体验友好，适合快速验证 |
|                      | vLLM                  | [vllm-project/vllm](https://github.com/vllm-project/vllm)                       | 高吞吐推理              |
| **RAG 框架**   | LangChain             | [langchain-ai/langchain](https://github.com/langchain-ai/langchain)             | 生态最全                |
|                      | LlamaIndex            | [run-llama/llama-index](https://github.com/run-llama/llama-index)               | 数据连接更强            |
|                      | RAGFlow               | [infiniflow/ragflow](https://github.com/infiniflow/ragflow)                     | 国产、界面好看          |
|                      | MaxKB                 | [1Panel-dev/MaxKB](https://github.com/1Panel-dev/MaxKB)                         | 1Panel 出品，快速部署   |
| **重排序**     | bge-reranker          | [BAAI/bge-reranker](https://huggingface.co/BAAI/bge-reranker-large)             | 提升 RAG 效果           |
| **前端UI**     | AnythingLLM           | [Mintplex-Labs/anything-llm](https://github.com/Mintplex-Labs/anything-llm)     | 开源 ChatGPT 平替       |
|                      | FastGPT               | [labring/FastGPT](https://github.com/labring/FastGPT)                           | 国产、功能完整          |

### 16G MVP 基线

- 为了先跑通最小闭环，本文后续命令统一按 nomic-embed-text + qwen2.5:7b + Qdrant 编写。
- 如果你的语料以中文长文档为主，第二阶段再把 embedding 切换到 bge-m3 或 bge-large-zh-v1.5。
- UI 放到第二阶段，不再使用单容器 FastGPT 命令冒充生产方案。

### llama.cpp MVP 配置示例

```python
# 文件与服务配置
LLM_MODEL_FILE = "qwen2.5-7b-instruct-q4_k_m.gguf"
EMBEDDING_MODEL_FILE = "nomic-embed-text-v1.5.f16.gguf"
VECTOR_DB = "qdrant"
COLLECTION_NAME = "knowledge_base"

# llama.cpp 对应参数
CONTEXT_LENGTH = 8192
LLM_PORT = 8080
EMBEDDING_PORT = 8081
QDRANT_URL = "http://127.0.0.1:6333"
```

- 如果后续切到 vLLM，再单独引入 GPU 显存利用率、张量并行等参数；不要和 llama.cpp 的启动方式混写。

### 快速启动命令

```bash
# 1. 安装 llama.cpp (macOS 推荐通过 Homebrew 安装)
brew install llama.cpp

# 2. 下载量化模型 (GGUF 格式)
curl -L -O https://huggingface.co/Qwen/Qwen2.5-7B-Instruct-GGUF/resolve/main/qwen2.5-7b-instruct-q4_k_m.gguf
curl -L -O https://huggingface.co/nomic-ai/nomic-embed-text-v1.5-GGUF/resolve/main/nomic-embed-text-v1.5.f16.gguf

# 3. 启动 LLM API 服务 (提供 OpenAI 兼容接口)
llama-server -m qwen2.5-7b-instruct-q4_k_m.gguf -c 8192 --host 127.0.0.1 --port 8080 >/tmp/llm.log 2>&1 &

# 4. 启动 Embedding API 服务 (分离端口)
llama-server -m nomic-embed-text-v1.5.f16.gguf --host 127.0.0.1 --port 8081 --embedding >/tmp/embed.log 2>&1 &

# 5. 启动 Qdrant（仅绑定到本机回环地址）
docker run -d --name qdrant -p 127.0.0.1:6333:6333 -p 127.0.0.1:6334:6334 \
    -v ~/qdrant_storage:/qdrant/storage \
    qdrant/qdrant

# 6. 验证本地模型服务
curl http://127.0.0.1:8080/v1/models
```

> FastGPT、Dify、AnythingLLM 都建议在第二阶段按官方 docker compose 部署；不要用单容器示例直接当生产方案。

### 安全基线

- llama-server 和 Qdrant 默认都只建议监听本机或内网，不要把 8080/8081/6333/6334 直接暴露到公网。
- Ollama 默认也更适合本机调用，不要把 11434 端口直接暴露到公网。
- 需要远程访问时，把 Web UI/API 放到 Caddy、Nginx 或 Traefik 后面做鉴权，模型服务只对内网开放。
- 生产环境优先把知识库服务与推理服务分开，避免单机故障放大。

### 变现路径

```
第1个月：搭好架构，跑通 RAG 流程
第2个月：做 UI，做 1-2 个演示案例
第3个月：在 V2EX/小红书/即刻推广
第4个月：开始有付费客户
```

---

## 方向二：私人媒体 AI 助理

### 系统架构

```
视频文件 (mp4/mkv)
    ↓ FFmpeg 提取
音频轨道 + 视频帧
    ↓          ↓
Whisper ASR  LLaVA 视频理解
    ↓          ↓
音频文本     场景描述
    ↓          ↓
音频向量库   视频向量库
    ↓          ↓
───────────── ↓ ─────────────
       用户查询入口
       ↓
   意图识别
   ↓        ↓
  找视频    找片段
       ↓
   生成回答 / 剪辑
```

### 开源项目清单

| 功能                 | 推荐项目       | GitHub                                                           | 备注                      |
| -------------------- | -------------- | ---------------------------------------------------------------- | ------------------------- |
| **视频处理**   | FFmpeg         | [ffmpeg.org](https://ffmpeg.org/)                                   | 音视频提取转码            |
| **语音识别**   | Faster-Whisper | [SYSTRAN/faster-whisper](https://github.com/SYSTRAN/faster-whisper) | Whisper 优化版，快 2-4 倍 |
|                      | SenseVoice     | [FunAudioLLM/SenseVoice](https://github.com/FunAudioLLM/SenseVoice) | 阿里出品，效果好          |
| **视频理解**   | LLaVA          | [haotian-liu/LLaVA](https://github.com/haotian-liu/LLaVA)           | 开源多模态模型            |
|                      | Qwen2-VL       | [QwenLM/Qwen2-VL](https://github.com/QwenLM/Qwen2-VL)               | 阿里多模态，中文好        |
|                      | VideoChat      | [OpenGVLab/VideoChat](https://github.com/OpenGVLab/VideoChat)       | 专为视频理解设计          |
| **声音克隆**   | XTTS           | [coqui-ai/TTS](https://github.com/coqui-ai/TTS)                     | 13秒克隆；社区维护中      |
|                      | GPT-SoVITS     | [RVC-Boss/GPT-SoVITS](https://github.com/RVC-Boss/GPT-SoVITS)       | 国产效果好                |
| **媒体服务器** | Jellyfin       | [jellyfin/jellyfin](https://github.com/jellyfin/jellyfin)           | 开源媒体库                |
|                      | Plex           | [plex.tv](https://www.plex.tv/)                                     | 生态成熟                  |

### 核心代码示例

```python
# 1. 视频理解 pipeline
import torch
from faster_whisper import WhisperModel
from llava.model.builder import load_pretrained_model
from llava.mm_utils import get_model_name_from_path

# Whisper 语音转文字（Mac Mini 16G 基线：CPU + int8）
model = WhisperModel("small", device="cpu", compute_type="int8")
segments, info = model.transcribe("audio.wav")
transcript = "\n".join([f"{s.text}" for s in segments])

# LLaVA 视频帧理解（放到 4070 Ti S 节点，CUDA + fp16）
model_path = "liuhaotian/llava-v1.5-7b"
model_name = get_model_name_from_path(model_path)
tokenizer, model, image_processor, context_len = load_pretrained_model(
    model_path, None, model_name, device="cuda"
)
model.eval()

# 批量处理视频帧（示例）
# frames = load_video_frames("video.mp4", num_frames=16)
# with torch.no_grad():
#     outputs = model(frames)
```

### Mac Mini 部署

```bash
# 1. Jellyfin
# macOS 上优先原生安装 Jellyfin；Docker on macOS 不作为主路径

# 2. Whisper 批处理（faster-whisper 本体不自带 server 命令）
python3 -m venv .venv
source .venv/bin/activate
pip install faster-whisper

python - <<'PY'
from faster_whisper import WhisperModel

model = WhisperModel("small", device="cpu", compute_type="int8")
segments, _ = model.transcribe("audio.wav", vad_filter=True)
for segment in segments:
    print(f"[{segment.start:.2f}s -> {segment.end:.2f}s] {segment.text}")
PY

# 3. 视频理解
# 放到 4070 Ti S 机器上启动模型服务，再由 Mac Mini 通过 HTTP 调用
```

### 16G 版本落地顺序

- 第一版先做音频转写、字幕检索、片段定位，不在 Mac Mini 上常驻多模态模型。
- 视频帧理解作为增强功能，按需把任务发到 4070 Ti S 机器处理。
- 媒体库先跑通索引和搜索，再考虑自动剪辑与角色配音。

### 能做什么

- "找出所有有枪战场景的电影"
- "这部电影里主角穿的什么牌子衣服"
- "帮我剪辑所有搞笑片段"
- "用我喜欢的角色声音生成解说"

---

## 方向三：AI 声音克隆定制服务

### 系统架构

```
MVP（先做零样本）:
参考音频 (30秒+) → XTTS v2 / Fish Speech → 音频输出

训练增强（第二阶段，4070 Ti S）:
参考音频 (30秒+) → 清洗/切分 → LoRA / SoVITS 训练 → 专属声音模型
```

### 合规前置

- 只处理已获得明确授权的声音素材，默认把授权作为交付前提。
- 商业化第一版更适合做企业配音、课程配音、品牌旁白，而不是名人或角色声音克隆。

### 开源项目清单

| 环节                 | 推荐项目        | GitHub                                                                             | 备注             |
| -------------------- | --------------- | ---------------------------------------------------------------------------------- | ---------------- |
| **声音克隆**   | XTTS v2         | [coqui-ai/TTS](https://github.com/coqui-ai/TTS)                                       | 13秒克隆；Coqui 公司已关闭，社区维护中 |
|                      | GPT-SoVITS      | [RVC-Boss/GPT-SoVITS](https://github.com/RVC-Boss/GPT-SoVITS)                         | 国产、对中文友好 |
|                      | OpenVoice       | [myshell-ai/OpenVoice](https://github.com/myshell-ai/OpenVoice)                    | MyShell 出品     |
|                      | Fish Speech     | [fishaudio/fish-speech](https://github.com/fishaudio/fish-speech)                     | 国产、效果不错   |
| **声音增强**   | UVR             | [Anjok07/ultimatevocalremovergui](https://github.com/Anjok07/ultimatevocalremovergui) | 人声提取/去伴奏  |
|                      | Demucs          | [facebookresearch/demucs](https://github.com/facebookresearch/demucs)                 | Meta 出品        |
| **推理优化**   | onnxruntime-gpu | [microsoft/onnxruntime](https://github.com/microsoft/onnxruntime)                     | 加速推理         |
| **声音数据集** | LibriTTS        | [openslr.org/144](https://www.openslr.org/144/)                                       | 开源语音数据     |
|                      | AISHELL-3       | [aishelltech.com](https://www.aishelltech.com/aishell_3)                              | 中文多说话人     |

### 克隆流程

> GPT-SoVITS 版本迭代很快，下面流程只用于说明训练步骤，具体命令以当期 README 为准。

```python
# XTTS 克隆（最简单）
from TTS.api import TTS

tts = TTS("tts_models/multilingual/multi-dataset/xtts_v2")

# 方法1：直接克隆（需30秒以上干净音频）
tts.tts_to_file(
    text="你好，这是一段测试语音。",
    speaker_wav="path/to/reference.wav",
    language="zh-cn",
    file_path="output.wav"
)
```

```bash
# GPT-SoVITS 克隆（中文效果更好）
# 具体命令以当期官方 README 为准，以下仅为说明步骤

# 1. 音频预处理
cd GPT-SoVITS
python preprocess.py --input_path /path/to/audio --output_path /path/to/output

# 2. 训练（示例，参数请参考最新版文档）
python train.py --config configs/train.yaml

# 3. 推理（示例）
python inference.py --model_path /path/to/model --ref_audio reference.wav --text "要合成的文本"
```

> **警告**：GPT-SoVITS 版本迭代较快，训练参数、配置文件格式在不同版本间可能有较大变化。上述示例仅用于说明流程，**请始终以项目官方 README 中的命令为准**。不要直接复制上述命令到生产环境。

### 声音增强 pipeline

```python
# Demucs 去伴奏 + 去噪
import demucs.api

# 分离人声
separator = demucs.api.Separator(model="htdemucs")
origin, separated = separator.separate_audio_file("input.wav")

# 提取干净人声（返回值为 tensor）
vocals = separated["vocals"]
```

### 显存优化（4070 Ti S）

> 以下为显存优化思路示意，非可直接运行的代码；实际参数请以 Coqui TTS 或所选框架的文档为准。

```python
# XTTS 优化配置（示意）
config = {
    "model": "xtts",
    "batch_size": 8,  # 4070 Ti S 16GB 够用
    "use_deepspeed": True,
    "precision": "fp16",
    "compile": True,  # 加速 20-30%
}

# 或者用 LoRA 减少显存占用（示意）
model.train_lora(
    dataset_path="data",
    rank=16,  # LoRA rank，越小越省显存
    lr=1e-4,
    num_epochs=50
)
```

### 变现方式

- 按声音收费（克隆一个声音 ¥500-2000）
- 月订阅制（每月提供一定额度）
- API 调用计费

---

## 方向四：垂直行业 Agent

### 系统架构

```
用户查询 → Agent Framework → 工具调用 → 知识库 → LLM → 回答
                    ↓
              记忆模块
              规划模块
              工具箱
```

### 落地优先级

- 如果目标是最快跑出商业化 MVP，优先 Dify 或 LangGraph，不要一开始就堆多 Agent。
- CrewAI 更适合研究和演示，下方代码用来说明概念，不建议直接复制成第一版生产脚手架。

### 开源项目清单

| 组件                 | 推荐项目  | GitHub                                                           | 备注                    |
| -------------------- | --------- | ---------------------------------------------------------------- | ----------------------- |
| **Agent 框架** | CrewAI    | [crewAI/crewAI](https://github.com/crewAI/crewAI)                   | 多 Agent 协作，简单易用 |
|                      | AutoGen   | [microsoft/autogen](https://github.com/microsoft/autogen)           | 微软出品，成熟          |
|                      | LangGraph | [langchain-ai/langgraph](https://github.com/langchain-ai/langgraph) | 状态机编排              |
|                      | Dify      | [langgenius/dify](https://github.com/langgenius/dify)               | 国产可视化 Agent        |
| **工作流**     | n8n       | [n8n-io/n8n](https://github.com/n8n-io/n8n)                         | 自动化工作流            |
|                      | FastGPT   | [labring/FastGPT](https://github.com/labring/FastGPT)               | 国产 Agent 平台         |
| **前端**       | Dify      | [dify.ai](https://dify.ai/)                                         | 一站式 AI 应用平台      |
|                      | Flowise   | [FlowiseAI/Flowise](https://github.com/FlowiseAI/Flowise)           | 可视化 LangChain        |

### 推荐垂直领域

| 领域     | 痛点               | 付费意愿 |
| -------- | ------------------ | -------- |
| 法律咨询 | 小律所买不起贵方案 | 高       |
| 心理咨询 | 隐私敏感、适合本地 | 高       |
| 教育答疑 | 家长愿意为效果付费 | 中       |
| 简历优化 | 需求大、标准化容易 | 中       |

### 法律 Agent 实施思路

> 以下说明 Agent 的构建思路，不提供可直接复制的代码——CrewAI 等框架迭代较快，代码示例容易过时，请以官方文档为准。

1. **定义工具（Tools）**
   - 法律条文检索：自建向量库 + bge-reranker 精排
   - 类似判例检索：同上
   - 合同生成器：LLM 调用 + 模板填充

2. **定义 Agent**
   - role：资深律师
   - goal：为用户提供准确的法律咨询
   - backstory：10年执业律师，擅长合同纠纷

3. **定义任务**
   - description：用户问题（如"租房合同到期房东不退押金怎么办？"）
   - expected_output：法律分析 + 建议 + 可执行解决方案

4. **编排方式**
   - 优先用 Dify 或 LangGraph 可视化编排，零代码配置工作流
   - 多 Agent 协作作为第二阶段目标，第一版先跑通单 Agent + 检索 + 工具调用

### 部署架构（Mac Mini）

- Dify、FastGPT 都建议按官方 docker compose 部署，不再使用单容器 docker run 示例。
- 16G Mac Mini 同一时间只保留一个 Agent 平台，LLM 复用方向一的推理节点。
- 如果你的目标是做行业 Demo，先把检索、表单、工具调用跑通，再考虑复杂的多 Agent 规划。

---

## 资源分配建议

### 4070 Ti S (训练)

| 任务               | 显存占用 | 备注              |
| ------------------ | -------- | ----------------- |
| 声音克隆 LoRA 微调 | 8GB      | XTTS / GPT-SoVITS |
| 视频理解模型微调   | 6GB      | LLaVA / Qwen-VL   |
| 剩余显存跑推理     | 2GB      | 备用              |

### Mac Mini M4 16G（常驻服务预算）

| 服务 | 是否常驻 | 内存预算 | 备注 |
| ---- | -------- | -------- | ---- |
| Qdrant | 是 | 1.5-2GB | 知识库向量库 |
| UI/API/反向代理 | 是 | 1-2GB | MaxKB / AnythingLLM / 自建 API 三选一 |
| llama.cpp | 否 | 6-8GB | 仅在 RAG 模式下启动服务 |
| faster-whisper | 否 | 2-4GB | small/base 为主，批处理优先 |
| Jellyfin | 视场景 | 2-4GB | 更建议原生安装或放 NAS/Linux |
| 系统预留 | 是 | 3-4GB | 保证桌面和后台稳定 |

### 16G Mac Mini 可承载矩阵

| 模式 | 组合 | 预估总内存 | 结论 |
| ---- | ---- | ---------- | ---- |
| RAG 模式 | Qdrant + UI/API + llama-server | 12-14GB | 可行 |
| 转写模式 | Qdrant + UI/API + faster-whisper small | 8-11GB | 可行 |
| 媒体模式 | Jellyfin + 轻量索引 | 8-10GB | 可行 |
| 全家桶模式 | Qdrant + UI + llama.cpp + Whisper + Jellyfin | >18GB | 不建议 |

### 一键启动脚本

```bash
#!/bin/bash
# startup.sh - 16G Mac Mini 按模式启动

set -euo pipefail

MODE="${1:-rag}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

start_qdrant() {
    docker start qdrant 2>/dev/null || docker run -d --name qdrant \
        -p 127.0.0.1:6333:6333 -p 127.0.0.1:6334:6334 \
        -v ~/qdrant_storage:/qdrant/storage qdrant/qdrant
}

require_file() {
    if [ ! -f "$SCRIPT_DIR/$1" ]; then
        echo "Missing model file: $SCRIPT_DIR/$1"
        exit 1
    fi
}

wait_for_service() {
    local url="$1"
    local name="$2"
    for i in {1..30}; do
        if curl -sf "$url" >/dev/null 2>&1; then
            return 0
        fi
        sleep 1
    done
    echo "$name did not become ready within 30 seconds" >&2
    exit 1
}

case "$MODE" in
    rag)
        echo "Starting RAG mode..."
        start_qdrant
        require_file "qwen2.5-7b-instruct-q4_k_m.gguf"
        require_file "nomic-embed-text-v1.5.f16.gguf"
        llama-server -m "$SCRIPT_DIR/qwen2.5-7b-instruct-q4_k_m.gguf" -c 8192 --host 127.0.0.1 --port 8080 \
            >/tmp/llm.log 2>&1 &
        llama-server -m "$SCRIPT_DIR/nomic-embed-text-v1.5.f16.gguf" --host 127.0.0.1 --port 8081 --embedding \
            >/tmp/embed.log 2>&1 &
        wait_for_service "http://127.0.0.1:8080/v1/models" "llama-server (LLM)"
        wait_for_service "http://127.0.0.1:8081/v1/models" "llama-server (Embedding)"
        ;;
    transcribe)
        echo "Starting transcription mode..."
        start_qdrant
        echo "Run faster-whisper as a batch job instead of keeping a resident API on 16G."
        ;;
    media)
        echo "Run Jellyfin natively on macOS; avoid Docker host networking on Mac."
        ;;
    *)
        echo "Usage: ./startup.sh [rag|transcribe|media]"
        exit 1
        ;;
esac

echo "Mode ready: $MODE"
```

---

## 推荐学习路径

```
第1周：搭 RAG 知识库（最简单，先跑通）
       ↓
第2周：跑通声音克隆（XTTS 13秒克隆）
       ↓
第3周：视频理解 + Whisper 字幕生成
       ↓
第4周：搭 Agent（Dify / CrewAI）
       ↓
第5-8周：选择一个方向深耕 + 商业化
```

---

## 技术栈速查

### 环境选择指南

| 环境 | 推荐方案 | 说明 |
| ---- | -------- | ---- |
| **开发与生产** | llama.cpp | macOS 上对统一内存和显存分配最友好，性能与资源控制最优 |
| **大规模流式** | vLLM | 适合 Linux + NVIDIA CUDA 节点处理高吞吐并发请求 |

### 推荐模型

| 用途       | 推荐模型                        | 量化/配置 |
| ---------- | ------------------------------- | --------- |
| LLM (本地) | qwen2.5:7b / llama3.1:8b        | Q4_K_M (GGUF)  |
| Embedding  | nomic-embed-text / bge-m3       | fp16 (GGUF)   |
| Whisper    | faster-whisper small / distil-large-v3 | int8 / fp16 |
| TTS        | xtts_v2 / gpt-sovits            | Zero-shot / LoRA |
| 多模态     | qwen2-vl-7b / llava-v1.5-7b     | 放在 4070 节点 |

### 端口占用

| 端口  | 服务        | 说明       |
| ----- | ----------- | ---------- |
| 3000  | FastGPT     | Web UI     |
| 6333  | Qdrant      | 向量 API   |
| 8080  | llama.cpp(LLM) | 推理服务 |
| 8081  | llama.cpp(Emb) | 向量服务 |
| 8096  | Jellyfin    | 媒体服务   |
| 11434 | Ollama      | 本机推理   |

### GPU 监控（4070 Ti S）

训练任务在 4070 Ti S 上运行时，建议始终开一个监控窗口：

```bash
# NVIDIA GPU 监控（显存、温度、利用率）
watch -n 2 nvidia-smi

# 或详细日志输出到文件
nvidia-smi dmon -s u -d 10 > /tmp/gpu_log.txt &
```

常见问题排查：
- **OOM（OutOfMemory）**：减少 batch_size 或切换到更小的量化模型
- **显存利用率 0%**：确认模型确实加载到了 GPU（`nvidia-smi` 应显示进程显存占用）
- **温度过高（>83°C）**：降低学习率或暂停训练，4070 Ti S 长期跑 70°C 以上建议加风扇

---

## 实施修订说明（2026-04-28）

### 第二轮 Review 修正

- llama-server 启动命令全部补上 `--host 127.0.0.1`，与安全基线保持一致（快速启动 + startup.sh）。
- 修正 Demucs API 调用方式，改用 `demucs.api.Separator` 的正确方法签名。
- XTTS `tts_to_file` 补上 `language="zh-cn"` 参数。
- Qwen-VL 链接更新为 Qwen2-VL（`QwenLM/Qwen2-VL`），与推荐模型表一致。
- Coqui TTS / XTTS v2 标注项目状态：Coqui 公司已关闭，当前为社区维护。
- 统一 Qdrant 存储路径为 `~/qdrant_storage`。
- Demucs 标注由 "Facebook 出品" 改为 "Meta 出品"。
- 端口速查表补充 Ollama 11434。
- XTTS 显存优化代码块标注为示意性质。

### 第一轮修正

- 全文已统一按 MacBook Air M4 16G + Mac Mini M4 16G 规划。
- Mac Mini 16G 改为按模式运行，不再承诺把 RAG、Whisper、Jellyfin、Agent 平台全都长期常驻在同一台机器上。
- 已移除或修正三类高风险命令：单容器 FastGPT、faster_whisper_server、macOS 上的 Jellyfin Docker host networking。
- 已补齐 llama.cpp 安全说明，并把 Qdrant 示例改为默认仅绑定本机回环地址。
- 已修正 startup.sh 示例中的失败路径，避免模型文件缺失或服务未就绪时无限等待。
- 安全策略改为：模型服务仅对本机或内网开放，公网入口统一走反向代理鉴权。
- 声音克隆路线已经补上授权与合规前置条件。
- 已修正 LLaVA 示例（添加 torch import 和 cuda device）。
- 已修正 Demucs 代码中的中文变量名。
- 已修正 GPT-SoVITS 命令格式并加强警告。
- 已将 CrewAI 代码示例替换为实施思路说明。
- 新增 GPU 监控说明。

---

## 参考链接

- [Ollama 官方](https://ollama.com/)
- [llama.cpp GitHub](https://github.com/ggerganov/llama.cpp)
- [Qdrant 文档](https://qdrant.tech/documentation/)
- [Coqui TTS](https://github.com/coqui-ai/TTS)
- [GPT-SoVITS](https://github.com/RVC-Boss/GPT-SoVITS)
- [CrewAI 文档](https://docs.crewai.com/)
- [Dify 部署](https://docs.dify.ai/getting-started/install)
- [FastGPT](https://github.com/labring/FastGPT)
- [LLaVA](https://github.com/haotian-liu/LLaVA)
- [Faster-Whisper](https://github.com/SYSTRAN/faster-whisper)
