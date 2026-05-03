# AI 声音克隆服务

> Mac Mini M4 16G 上的语音克隆与合成系统
> 存储路径: `/Volumes/扩展盘512G/claude/project01/03-voice-cloning`

---

## 功能概述

- 零样本语音克隆 (XTTS v2)
- 批量语音合成
- 音频预处理 (人声分离)

## 系统架构

```
MVP (零样本克隆):
参考音频 (30秒+) → XTTS v2 → 语音输出

预处理 (可选):
原始音频 → Demucs → 干净人声 → XTTS v2 → 更好的克隆效果
```

## 环境要求

| 组件 | 要求 | 说明 |
|------|------|------|
| Python | 3.11+ | via Homebrew |
| Demucs | 最新版 | 已安装 (人声分离) |
| TTS (Coqui) | XTTS v2 | **安装中** (首次使用自动下载模型) |

## ⚠️ 重要提示

> **合规要求**
> - 仅处理已获得明确授权的声音素材
> - 商业化优先企业配音、课程配音、品牌旁白
> - 不建议做名人或角色声音克隆

> **XTTS 状态**
> - Coqui 公司已关闭，当前为社区维护
> - 模型仍可正常使用

## 安装依赖

```bash
cd /Volumes/扩展盘512G/claude/project01/03-voice-cloning

# 创建虚拟环境 (如尚未创建)
/opt/homebrew/bin/python3.11 -m venv .venv

# 激活虚拟环境
source .venv/bin/activate

# 安装 TTS (XTTS)
pip install TTS

# 安装 Demucs (音频预处理)
pip install demucs
```

## 使用方法

### 1. 预处理音频 (推荐)

如果参考音频有背景噪音，建议先进行人声分离:

```bash
source .venv/bin/activate
python3 preprocess_audio.py <audio_file> [output_dir]

# 示例
python3 preprocess_audio.py reference.wav .
```

输出文件:
- `vocals.wav` - 分离出的人声
- `other.wav` - 背景音

### 2. 克隆语音

```bash
source .venv/bin/activate
python3 clone_voice.py tts --text "要合成的文本" --ref_audio reference.wav --output output.wav

# 指定语言
python3 clone_voice.py tts --text "要合成的文本" --ref_audio reference.wav --output output.wav --language "zh-cn"
```

### 3. 批量合成

```bash
source .venv/bin/activate

# 直接指定文本
python3 batch_tts.py --ref_audio ref.wav --texts "文本1" "文本2" "文本3" --output_dir ./output

# 从文件读取文本
python3 batch_tts.py --ref_audio ref.wav --texts texts.txt --output_dir ./output
```

### 4. 查看可用模型

```bash
source .venv/bin/activate
python3 clone_voice.py list_models
python3 clone_voice.py list_local
```

## 参考音频要求

| 要求 | 说明 |
|------|------|
| 时长 | 建议 30 秒以上 |
| 质量 | 清晰、无噪音 |
| 内容 | 纯人声、无音乐 |
| 格式 | WAV/MP3/FLAC |

## XTTS v2 参数说明

| 参数 | 默认值 | 说明 |
|------|--------|------|
| language | zh-cn | 语言代码 |
| --text | 必需 | 要合成的文本 |
| --ref_audio | 必需 | 参考音频路径 |
| --output | output.wav | 输出文件路径 |

## 硬件分工

| 设备 | 任务 |
|------|------|
| **Mac Mini M4** | XTTS 推理 (~4GB 内存) |
| **4070 Ti S** | GPT-SoVITS 训练 (需要时) |

## 目录结构

```
03-voice-cloning/
├── README.md                 # 本文档
├── clone_voice.py           # 语音克隆脚本
├── batch_tts.py             # 批量合成脚本
├── preprocess_audio.py       # 音频预处理脚本
└── .venv/                   # Python 虚拟环境
```

## 下一步计划

1. 集成 GPT-SoVITS (更高质量中文克隆)
2. 添加声音增强 (UVR/Demucs)
3. LoRA 微调专属声音模型
4. Web UI 界面

## 常见问题

### Q: XTTS 模型下载失败
A: 首次使用会自动下载模型。如失败，可手动下载:
```bash
# 设置代理 (如需要)
export https_proxy=http://127.0.0.1:7896
```

### Q: 克隆效果不佳
A: 尝试以下方法:
1. 使用更长的参考音频 (30秒+)
2. 先用 preprocess_audio.py 去除噪音
3. 使用更清晰的参考音频

### Q: 内存不足
A: XTTS 在 Mac Mini 上约需 4GB 内存。请关闭其他占用内存的应用。

## 相关文档

- 完整技术方案: [../docs/local-ai-research-guide.md](../docs/local-ai-research-guide.md)
- RAG 实施记录: [../01-rag/README.md](../01-rag/README.md)
- 媒体助理: [../02-media-assistant/README.md](../02-media-assistant/README.md)
