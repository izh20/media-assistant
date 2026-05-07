# 私人媒体 AI 助理

> Mac Mini M4 16G 上的媒体内容理解与检索系统
> 存储路径: `/Volumes/扩展盘512G/claude/project01/02-media-assistant`

---

## 功能概述

- **Web 应用**: 视频语音识别 + 多语言翻译 + 字幕导出 + 字幕摘要 (端口 8090)
- 视频/音频转录为文字 (命令行)
- 转录文本语义搜索
- 视频内容片段定位

## 系统架构

### Web 应用 (视频字幕)

```
视频文件 (本地路径 / 上传)
    ↓ FFmpeg (-ar 16000 -ac 1 mono WAV)
音频轨道
    ↓ 分块 (每块 10 分钟，控制内存)
    ↓ faster-whisper
文字转录
    ↓ llama-server (Qwen2.5-7B, 端口 8080)
翻译文本
    ↓
SRT 字幕 (原文 / 译文 / 双语)
```

### 命令行工具 (语义搜索)

```
视频文件 (mp4/mkv)
    ↓ FFmpeg
音频轨道
    ↓ Whisper (faster-whisper)
文字转录
    ↓ Embedding (nomic-embed-text)
向量存储 (Qdrant)
    ↓
语义搜索 → 定位片段
```

## 环境要求

| 组件 | 要求 | 说明 |
|------|------|------|
| Python | 3.11+ | via Homebrew |
| FFmpeg | 最新版 | 音频提取 |
| faster-whisper | 最新版 | 语音识别 |
| llama-server | - | 翻译与字幕总结 LLM (Qwen2.5-7B-Instruct, 端口 8080) |
| Qdrant | 运行中 | 127.0.0.1:6333 (语义搜索用) |

## 安装依赖

```bash
cd /Volumes/扩展盘512G/claude/project01/02-media-assistant

# 创建虚拟环境 (如尚未创建)
/opt/homebrew/bin/python3.11 -m venv .venv

# 激活虚拟环境
source .venv/bin/activate

# 安装依赖
pip install faster-whisper fastapi uvicorn python-multipart
```

## 使用方法

### 1. 查看媒体文件信息

```bash
source .venv/bin/activate
python3 media_info.py <视频文件>
```

输出示例:
```
=== 媒体文件信息 ===
文件名: video.mp4
时长: 5:32
大小: 256.34 MB
比特率: 6500 kbps

流 0 (video):
  编码: h264
  分辨率: 1920x1080
  帧率: 30.00 fps

流 1 (audio):
  编码: aac
  采样率: 48000 Hz
  声道数: 2
```

### 2. 转录视频/音频

```bash
source .venv/bin/activate
python3 transcribe.py <输入文件> [输出目录]

# 示例
python3 transcribe.py /path/to/video.mp4 .
```

将生成:
- `.json` 文件: 包含所有段落的时间戳和文本
- `.srt` 文件: 字幕格式，可用视频播放器直接加载

### 3. 添加转录到向量库

```bash
source .venv/bin/activate
python3 search_transcripts.py add <transcript.json> [来源名称]

# 示例
python3 search_transcripts.py add ./video.json "我的视频"
```

### 4. 语义搜索

```bash
source .venv/bin/activate
python3 search_transcripts.py search <查询> [top_k]

# 示例
python3 search_transcripts.py search "有关AI的内容" 5
```

## Whisper 模型选择

| 模型 | 参数量 | 速度 | 精度 | 推荐场景 |
|------|--------|------|------|----------|
| tiny | 39M | 最快 | 较低 | 快速测试 |
| small | 244M | 快 | 中等 | **推荐日常使用** |
| base | 74M | 中 | 中等 | 平衡选择 |
| medium | 769M | 慢 | 较高 | 高精度需求 |
| large | 1550M | 最慢 | 最高 | 最高精度 |

当前配置:
- Whisper 统一使用 `faster-whisper`
- 默认优先使用内置 bundled 模型
- 运行设备自动选择 `cpu/int8` 或 `cuda/float16`

离线打包时会直接包含 bundled 的 faster-whisper 模型，随后执行：

```bash
bash build-dmg.sh
```

或者在已有 DMG 基础上增量同步：

```bash
bash patch-dmg.sh
```

### 快速验证（不生成 DMG）

大多数代码修改不需要立刻重新打包 DMG，可以先跑本地 smoke test：

```bash
cd /Volumes/扩展盘512G/claude/project01/02-media-assistant
bash quick-validate.sh
```

这个脚本会检查：

- Python 语法是否通过
- 模型选择接口 `/api/model_options` 是否可用
- 运行日志接口 `/api/runtime_log` 是否可用
- Whisper / LLM 候选是否能被发现
- 当前 HTML 设置面板里是否包含模型选择控件

如果要进一步做本地端到端验证，但仍然不生成 DMG，可以直接跑：

```bash
cd /Volumes/扩展盘512G/claude/project01/02-media-assistant
bash smoke-web.sh
```

这个脚本会：

- 先执行 `quick-validate.sh`
- 在本地临时启动 Web 服务，默认使用端口 `18090`
- 自动探测首页、`/api/model_options`、`/api/check_services`、`/api/runtime_log`
- 如果失败，直接打印服务日志尾部，方便定位问题
- 脚本结束后会自动停止这个临时服务，因此它不会持续占用 `8090`

如果需要进一步手动点界面验证，而不想生成 DMG：

```bash
cd /Volumes/扩展盘512G/claude/project01/02-media-assistant
.venv/bin/python video_subtitle_app.py
```

然后直接打开：

- http://127.0.0.1:8090

只有在准备分发给别的机器测试时，才需要执行：

```bash
bash patch-dmg.sh
```

## 端口占用

| 端口 | 服务 |
|------|------|
| 8090 | Web 应用 (视频字幕) |
| 8080 | llama-server (翻译 LLM) |
| 6333 | Qdrant (向量库) |
| 8081 | Embedding 服务 |

## 目录结构

```
02-media-assistant/
├── README.md                 # 本文档
├── video_subtitle_app.py     # Web 应用 (视频语音翻译字幕, 端口 8090)
├── transcribe.py             # 转录脚本 (命令行)
├── transcribe_translate.py   # 翻译脚本 (命令行)
├── search_transcripts.py     # 语义搜索脚本
├── media_info.py             # 媒体信息查看
├── uploads/                  # 上传的视频文件 (自动管理)
├── output/                   # 临时音频文件 + 字幕输出
├── frames/                   # 历史目录，当前主流程不再使用图像识别
└── .venv/                    # Python 虚拟环境
```

## Web 应用 (视频语音翻译字幕)

启动 Web 服务:
```bash
source .venv/bin/activate
python3 video_subtitle_app.py
```

访问地址:
- 本机访问: http://localhost:8090
- 局域网访问: http://<本机IP>:8090 (运行 `hostname -I | awk '{print $1}'` 查看 IP)

### 依赖服务

翻译功能需要 llama-server 运行:
```bash
cd /Volumes/扩展盘512G/claude/project01
bash startup.sh llama
```

### 功能特性

- **两种输入方式**: 本地路径直接引用 / 拖拽上传文件
- **多格式支持**: MP4, MKV, AVI, MOV, WebM, FLV, MP3, WAV 等
- **语言自动检测**: 自动识别视频中的语言，也可手动指定
- **多语言翻译**: 支持中/英/日/韩/法/德/西/俄等语言互译 (通过 llama-server)
- **两种模式**: 转录+翻译 / 仅转录
- **字幕输出**: 原文字幕、译文字幕、双语字幕 (SRT 格式)
- **在线预览**: 处理完成后可直接预览字幕内容
- **任务历史**: 历史任务保存在浏览器 localStorage，刷新后可恢复
- **实时进度**: 音频提取和语音识别均有实时进度显示
- **自动清理**: 最多保留 20 个任务 / 80GB 存储，超限自动清理旧任务

### 长视频优化
- **分块转录**: 超过 15 分钟的音频自动切分为 10 分钟/块
- **内存控制**: 每次只加载一个分块到内存，适合 16GB 机器处理 2+ 小时电影
- **逐块进度**: 每完成一块即更新进度，避免长时间无反馈
- **自动清理**: 转录完成后自动删除中间 WAV 文件释放磁盘

## 已知限制

- Whisper `small` 模型对背景音乐较多的场景准确率下降
- NFS 挂载的视频文件 (`/Volumes/nfs/`) 提取音频较慢，建议用本地文件
- 翻译质量取决于 Qwen2.5-7B 模型能力，专业术语可能不准确
- 16GB 内存下处理超长视频 (>4 小时) 仍可能有压力

## 故障排查

### 1. Web 服务无法访问

**检查服务状态:**
```bash
# 检查进程是否运行
ps aux | grep video_subtitle_app

# 检查端口是否监听
lsof -i :8090

# 查看错误日志
tail -50 /tmp/llm-logs/video_subtitle.log
```

**解决方法:**
```bash
# 重启服务
cd /Volumes/扩展盘512G/claude/project01/02-media-assistant
source .venv/bin/activate
python3 video_subtitle_app.py
```

### 2. 翻译功能不可用

**检查 llama-server:**
```bash
# 检查是否运行
ps aux | grep llama-server | grep -v grep

# 检查端口 8080
curl -s http://127.0.0.1:8080/v1/models

# 启动 llama-server
cd /Volumes/扩展盘512G/claude/project01
./startup.sh llama qwen2.5-7b-instruct-q4_k_m.gguf 8080
```

### 3. 转录很慢或卡住

**原因:**
- 网络挂载文件 (NFS/SMB) 读取慢
- VPN 可能影响连接
- 视频文件过大

**解决方法:**
1. 使用本地磁盘文件而非网络挂载
2. 关闭 VPN
3. 提前提取音频到本地 `/tmp`:
   ```bash
   ffmpeg -i video.mp4 -vn -acodec pcm_s16le -ar 16000 -ac 1 /tmp/audio.wav
   ```

### 4. 磁盘空间不足

**检查占用:**
```bash
# 查看目录大小
du -sh /Volumes/扩展盘512G/claude/project01/02-media-assistant/*

# 查看磁盘空间
df -h /Volumes/扩展盘512G/
```

**清理方法:**
```bash
# 删除已完成任务的输出文件
rm -rf /Volumes/扩展盘512G/claude/project01/02-media-assistant/output/*

# 删除上传文件 (处理完成后)
rm -rf /Volumes/扩展盘512G/claude/project01/02-media-assistant/uploads/*
```

### 5. 字幕生成失败

**检查 Whisper 安装:**
```bash
cd /Volumes/扩展盘512G/claude/project01/02-media-assistant
source .venv/bin/activate
python3 -c "from faster_whisper import WhisperModel; print('OK')"
```

### 6. 语言检测不准确

- 手动指定源语言而非使用自动检测
- 对于日语/中文/韩语等 Asian 语言，使用 `ja`/`zh`/`ko` 明确指定
- 背景噪音多的视频建议使用 `large` 模型

## 下一步计划

1. 集成视频帧理解 (LLaVA)
2. 实现自动剪辑功能
3. 添加多模态搜索 (视频帧 + 音频双通道)

## 相关文档

- 完整技术方案: [../docs/local-ai-research-guide.md](../docs/local-ai-research-guide.md)
- RAG 实施记录: [../01-rag/README.md](../01-rag/README.md)
