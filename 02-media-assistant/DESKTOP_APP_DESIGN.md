# Media Assistant 桌面应用设计文档

## 概述

将现有 FastAPI + 嵌入式前端 Web 应用打包为桌面应用，首发提供 macOS DMG（仅 Apple Silicon）和 Windows EXE（x64）。使用 Electron 作为外壳，Python 后端冻结为独立可执行文件。

---

## 技术选型

| 层 | 技术 | 说明 |
|----|------|------|
| 桌面外壳 | Electron 33+ | 跨平台窗口、托盘、自动更新 |
| 前端 | 现有嵌入式 HTML SPA | 由 FastAPI 提供，Electron BrowserWindow 加载 |
| 后端 | Python 3.11 + FastAPI | PyInstaller 冻结为单文件可执行 |
| 语音识别 | faster-whisper (large-v3-turbo) | 预置模型，GPU 自适应 |
| 翻译/总结 | MiniMax API (OpenAI 兼容) | 用户配置 API Key |
| 视觉分析 | 本地 llama-server + Qwen2-VL | 首发要求用户本地自配服务 |
| 音视频处理 | ffmpeg/ffprobe 静态编译版 | 捆绑在应用内 |
| 自动更新 | electron-updater + GitHub Releases | Windows 应用内自动更新，macOS 检测更新并跳转下载 |
| 打包 | electron-builder | 输出 DMG (macOS) + NSIS (Windows) |

---

## 架构图

```
┌──────────────────────────────────────────────────────────────┐
│                    Electron Application                        │
├──────────────────────────────────────────────────────────────┤
│  Main Process (Node.js)                                       │
│  ├── app lifecycle (启动/退出)                                │
│  ├── spawn Python backend                                     │
│  ├── BrowserWindow → http://127.0.0.1:{port}                 │
│  ├── Tray (系统托盘: 打开窗口/设置/退出)                      │
│  └── autoUpdater (检查更新/下载/安装)                         │
├──────────────────────────────────────────────────────────────┤
│  Python Backend (frozen binary, child process)                │
│  ├── FastAPI + uvicorn                                        │
│  ├── faster-whisper (turbo 模型, GPU 自适应)                  │
│  ├── ffmpeg/ffprobe (bundled)                                 │
│  ├── Pillow (网格帧拼接)                                      │
│  ├── config.py (读写 config.json)                             │
│  └── API endpoints (现有 + 新增设置接口)                      │
├──────────────────────────────────────────────────────────────┤
│  External Services (用户自配)                                  │
│  ├── LLM (翻译/总结): MiniMax API 或其他 OpenAI 兼容服务      │
│  └── Vision (帧分析): 本地 llama-server + Qwen2-VL            │
└──────────────────────────────────────────────────────────────┘
```

---

## 模型与服务配置

### Whisper 模型 (内置)

| 属性 | 值 |
|------|-----|
| 模型 | Systran/faster-whisper-large-v3-turbo |
| 大小 | ~1.6GB (FP16) / ~850MB (int8) |
| 精度 | 接近 large-v3 (WER 差距 <1%) |
| macOS | device=cpu, compute_type=int8 |
| Windows (NVIDIA GPU) | device=cuda, compute_type=float16 |
| Windows (无 GPU) | device=cpu, compute_type=int8 |

### LLM 翻译服务 (用户配置)

MiniMax OpenAI 兼容接口：

```
API Base: https://api.minimaxi.com/v1
Model: MiniMax-M2.7-highspeed
Context: 204,800 tokens
Speed: ~100 TPS
```

也支持任何 OpenAI 兼容 API（本地 llama-server、DeepSeek、OpenAI 等）。

### Vision 视觉服务 (本地)

```
Service: llama-server (用户自行启动)
Model: Qwen2-VL-7B-Instruct-Q4_K_M.gguf + mmproj
Endpoint URL: http://127.0.0.1:8080/v1/chat/completions
```

应用内提供启动引导，检测 llama-server 是否在线。Vision 功能在服务不可用时自动禁用。

### Windows GPU 前置条件

- 仅 Windows x64 首发支持 NVIDIA GPU 加速。
- 运行前需满足 `CUDA 12` 与 `cuDNN 9` 运行时要求，版本矩阵与 `ctranslate2` 保持一致。
- 首发版不把 CUDA/cuDNN 一并塞进安装包，安装器只做环境检测与引导；缺少依赖时自动回退 CPU `int8`。
- 安装器需要提供两种结果：`GPU 就绪` 和 `已回退 CPU 模式`，避免用户误以为已经启用 GPU。

---

## 配置系统

### 配置文件位置

- macOS: `~/Library/Application Support/MediaAssistant/config.json`
- Windows: `%APPDATA%/MediaAssistant/config.json`

### 配置结构

```json
{
  "llm": {
    "provider": "minimax",
    "api_base": "https://api.minimaxi.com/v1",
    "chat_path": "/chat/completions",
    "api_key": "",
    "model": "MiniMax-M2.7-highspeed",
    "timeout": 60
  },
  "vision": {
    "endpoint_url": "http://127.0.0.1:8080/v1/chat/completions",
    "timeout": 180
  },
  "whisper": {
    "model_path": "bundled",
    "device": "auto",
    "compute_type": "auto"
  },
  "app": {
    "port": 8090,
    "data_dir": "auto",
    "auto_update": true,
    "language": "zh"
  }
}
```

### 数据目录

- macOS: `~/Documents/MediaAssistant/`
- Windows: `%USERPROFILE%/Documents/MediaAssistant/`

子目录：`uploads/`, `output/`, `frames/`

---

## 自动更新方案

### 技术栈

- `electron-updater` — Electron 官方更新模块
- 更新源：**GitHub Releases**（免费，无需自建服务器）
- 平台策略：Windows 使用应用内自动更新；macOS 在无开发者证书阶段只做版本检测和下载引导

### 更新流程

```
应用启动
  → 检查 GitHub Releases 最新正式版本
  → Windows: 后台下载更新包 → 下载完成后提示重启安装
  → macOS: 提示发现新版本 → 跳转 Release 下载页
```

### 发布流程

```bash
# 1. 更新 package.json version
npm version patch  # 或 minor/major

# 2. electron-builder 构建并发布到 GitHub Releases
npx electron-builder --mac --win --publish always

# 3. GitHub Release 自动包含:
#    - Media-Assistant-1.1.0-arm64.dmg (macOS)
#    - Media-Assistant-1.1.0-x64.exe (Windows NSIS)
#    - latest.yml (Windows 更新元数据)
#    - macOS 版本通过 Release 页面下载，不依赖应用内静默更新
```

### electron-builder 更新配置

```yaml
# electron-builder.yml
publish:
  provider: github
  owner: your-github-username
  repo: media-assistant
  releaseType: release
```

### 版本号规则

- `major.minor.patch` (语义化版本)
- 仅正式 Release 触发更新（Draft/Pre-release 不触发）

---

## 项目结构

```
02-media-assistant/
├── electron/                              # Electron 层
│   ├── package.json                       # Electron 依赖 + electron-builder 配置
│   ├── main.js                            # Main process 入口
│   ├── preload.js                         # 预加载脚本（安全桥接）
│   ├── tray.js                            # 系统托盘管理
│   ├── updater.js                         # 自动更新逻辑
│   ├── backend-manager.js                 # Python 后端进程管理
│   └── assets/
│       ├── icon.icns                      # macOS 应用图标
│       ├── icon.ico                       # Windows 应用图标
│       ├── icon.png                       # 通用图标 (256x256)
│       └── tray-icon.png                  # 托盘图标 (22x22)
│
├── backend/                               # Python 后端
│   ├── video_subtitle_app.py             # 主应用（改造后）
│   ├── config.py                          # 配置管理模块
│   ├── requirements.txt                   # Python 依赖
│   └── media-assistant.spec               # PyInstaller 打包配置
│
├── bundled/                               # 捆绑资源
│   ├── ffmpeg/
│   │   ├── mac-arm64/                     # macOS arm64 静态 ffmpeg
│   │   └── win-x64/                       # Windows x64 静态 ffmpeg
│   └── models/
│       └── faster-whisper-large-v3-turbo/ # 预置 Whisper 模型
│           ├── model.bin
│           ├── config.json
│           ├── tokenizer.json
│           ├── vocabulary.json
│           └── preprocessor_config.json
│
├── build/                                 # 构建脚本
│   ├── electron-builder.yml              # electron-builder 主配置
│   ├── build-backend-mac.sh              # macOS PyInstaller 脚本
│   ├── build-backend-win.bat             # Windows PyInstaller 脚本
│   ├── build-all.sh                      # 一键完整构建
│   └── .github/
│       └── workflows/
│           └── release.yml               # GitHub Actions CI/CD
│
└── DESKTOP_APP_DESIGN.md                  # 本文档
```

---

## Electron Main Process 详细设计

### main.js — 应用入口

```javascript
const { app, BrowserWindow, Menu, shell } = require('electron');
const path = require('path');
const BackendManager = require('./backend-manager');
const TrayManager = require('./tray');
const { setupAutoUpdater } = require('./updater');

let mainWindow = null;
const backendManager = new BackendManager();

app.whenReady().then(async () => {
  // 1. 启动 Python 后端
  await backendManager.start();

  // 2. 创建主窗口
  mainWindow = new BrowserWindow({
    width: 1400,
    height: 900,
    minWidth: 1024,
    minHeight: 700,
    title: 'Media Assistant',
    icon: path.join(__dirname, 'assets', 'icon.png'),
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });

  mainWindow.loadURL(`http://127.0.0.1:${backendManager.port}`);

  // 3. 系统托盘
  TrayManager.create(mainWindow, backendManager);

  // 4. 自动更新
  setupAutoUpdater(mainWindow);

  // 5. 外部链接用系统浏览器打开
  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    shell.openExternal(url);
    return { action: 'deny' };
  });

  // 关闭窗口 → 隐藏到托盘（不退出）
  mainWindow.on('close', (e) => {
    if (!app.isQuitting) {
      e.preventDefault();
      mainWindow.hide();
    }
  });
});

app.on('before-quit', () => {
  app.isQuitting = true;
  backendManager.stop();
});
```

### backend-manager.js — Python 后端进程管理

```javascript
const { spawn } = require('child_process');
const path = require('path');
const net = require('net');
const { app } = require('electron');

class BackendManager {
  constructor() {
    this.process = null;
    this.port = 8090;
  }

  getBackendPath() {
    if (app.isPackaged) {
      const ext = process.platform === 'win32' ? '.exe' : '';
      return path.join(process.resourcesPath, 'backend', `media-assistant${ext}`);
    }
    // 开发模式: 直接运行 Python
    return process.platform === 'win32'
      ? path.join(__dirname, '..', 'backend', '.venv', 'Scripts', 'python.exe')
      : path.join(__dirname, '..', 'backend', '.venv', 'bin', 'python');
  }

  async start() {
    // 检测端口占用，自动递增
    this.port = await this.findAvailablePort(8090);

    const backendPath = this.getBackendPath();
    const args = app.isPackaged ? [] : ['video_subtitle_app.py'];
    const cwd = app.isPackaged
      ? path.join(process.resourcesPath, 'backend')
      : path.join(__dirname, '..', 'backend');

    this.process = spawn(backendPath, args, {
      cwd,
      env: {
        ...process.env,
        MEDIA_ASSISTANT_PORT: String(this.port),
        MEDIA_ASSISTANT_DATA_DIR: this.getDataDir(),
        MEDIA_ASSISTANT_BUNDLED_DIR: this.getBundledDir(),
      },
      stdio: ['ignore', 'pipe', 'pipe'],
    });

    this.process.stdout.on('data', (d) => console.log(`[backend] ${d}`));
    this.process.stderr.on('data', (d) => console.error(`[backend] ${d}`));
    this._setupCrashRecovery();

    await this.waitForReady();
  }

  stop() {
    if (this.process) {
      this.process.kill('SIGTERM');
      this.process = null;
    }
  }

  // 崩溃自动恢复（最多 3 次）
  _restartCount = 0;
  _setupCrashRecovery() {
    this.process.on('exit', (code) => {
      console.log(`[backend] exited: ${code}`);
      if (code !== 0 && code !== null && !this._stopping) {
        if (this._restartCount < 3) {
          this._restartCount++;
          console.log(`[backend] crash detected, restart attempt ${this._restartCount}/3`);
          setTimeout(() => this.start(), 1000);
        } else {
          this._onFatalCrash && this._onFatalCrash();
        }
      }
    });
  }

  onFatalCrash(callback) { this._onFatalCrash = callback; }

  getDataDir() {
    const { app } = require('electron');
    return path.join(app.getPath('documents'), 'MediaAssistant');
  }

  getBundledDir() {
    return app.isPackaged
      ? path.join(process.resourcesPath, 'bundled')
      : path.join(__dirname, '..', 'bundled');
  }

  findAvailablePort(startPort) {
    return new Promise((resolve) => {
      const server = net.createServer();
      server.listen(startPort, '127.0.0.1', () => {
        server.close(() => resolve(startPort));
      });
      server.on('error', () => resolve(this.findAvailablePort(startPort + 1)));
    });
  }

  waitForReady(timeout = 30000) {
    const start = Date.now();
    return new Promise((resolve, reject) => {
      const check = () => {
        if (Date.now() - start > timeout) {
          reject(new Error('Backend startup timeout'));
          return;
        }
        const socket = new net.Socket();
        socket.setTimeout(300);
        socket.on('connect', () => { socket.destroy(); resolve(); });
        socket.on('error', () => { setTimeout(check, 300); });
        socket.on('timeout', () => { socket.destroy(); setTimeout(check, 300); });
        socket.connect(this.port, '127.0.0.1');
      };
      check();
    });
  }
}

module.exports = BackendManager;
```

### updater.js — 自动更新

```javascript
const { autoUpdater } = require('electron-updater');
const { dialog, shell } = require('electron');

function setupAutoUpdater(mainWindow) {
  const isMac = process.platform === 'darwin';
  autoUpdater.autoDownload = !isMac;
  autoUpdater.autoInstallOnAppQuit = !isMac;

  autoUpdater.on('checking-for-update', () => {
    console.log('[updater] Checking for updates...');
  });

  autoUpdater.on('update-available', (info) => {
    console.log(`[updater] Update available: ${info.version}`);
    if (isMac) {
      dialog.showMessageBox(mainWindow, {
        type: 'info',
        title: '发现新版本',
        message: `发现新版本 ${info.version}，请前往 Release 页面下载。`,
        buttons: ['打开下载页', '稍后'],
        defaultId: 0,
      }).then(({ response }) => {
        if (response === 0) {
          shell.openExternal('https://github.com/your-github-username/media-assistant/releases/latest');
        }
      });
      return;
    }
    mainWindow.webContents.send('update-available', info.version);
  });

  autoUpdater.on('update-not-available', () => {
    console.log('[updater] Already up to date');
  });

  autoUpdater.on('download-progress', (progress) => {
    mainWindow.webContents.send('update-progress', progress.percent);
  });

  autoUpdater.on('update-downloaded', (info) => {
    if (isMac) {
      return;
    }
    dialog.showMessageBox(mainWindow, {
      type: 'info',
      title: '更新就绪',
      message: `新版本 ${info.version} 已下载完成，重启应用即可完成更新。`,
      buttons: ['立即重启', '稍后'],
      defaultId: 0,
    }).then(({ response }) => {
      if (response === 0) {
        autoUpdater.quitAndInstall();
      }
    });
  });

  autoUpdater.on('error', (err) => {
    console.error('[updater] Error:', err.message);
  });

  // 启动后延迟 10s 检查更新（避免启动卡顿）
  setTimeout(() => {
    autoUpdater.checkForUpdatesAndNotify();
  }, 10000);

  // 之后每 4 小时检查一次
  setInterval(() => {
    autoUpdater.checkForUpdatesAndNotify();
  }, 4 * 60 * 60 * 1000);
}

module.exports = { setupAutoUpdater };
```

---

## Python 后端改造

### 改动清单

| 改动项 | 文件 | 说明 |
|--------|------|------|
| 环境变量读取 | video_subtitle_app.py | PORT, DATA_DIR, BUNDLED_DIR 从环境变量获取 |
| 配置模块 | config.py (新建) | 读写 config.json，提供默认值 |
| API Key 支持 | video_subtitle_app.py | post_json() 添加 Authorization header |
| ffmpeg 路径 | video_subtitle_app.py | 优先查 bundled 目录，fallback PATH |
| GPU 自适应 | video_subtitle_app.py | Whisper 加载时探测 CUDA 可用性 |
| 设置 API | video_subtitle_app.py | 新增 GET/POST /api/settings 端点 |
| 前端设置页 | video_subtitle_app.py | HTML_PAGE 新增 Settings tab |
| Vision 状态 | video_subtitle_app.py | check_services 时检测 vision 在线 → 动态启停帧分析功能 |

### config.py 核心逻辑

```python
import os
import json
from pathlib import Path

def get_config_dir():
    """获取配置文件目录"""
    if os.name == 'nt':  # Windows
        base = os.environ.get('APPDATA', os.path.expanduser('~'))
    else:  # macOS/Linux
        base = os.path.expanduser('~/Library/Application Support')
    config_dir = os.path.join(base, 'MediaAssistant')
    os.makedirs(config_dir, exist_ok=True)
    return config_dir

def get_data_dir():
    """获取数据目录（可被环境变量覆盖）"""
    env_dir = os.environ.get('MEDIA_ASSISTANT_DATA_DIR')
    if env_dir:
        os.makedirs(env_dir, exist_ok=True)
        return env_dir
    data_dir = os.path.join(os.path.expanduser('~/Documents'), 'MediaAssistant')
    os.makedirs(data_dir, exist_ok=True)
    return data_dir

DEFAULT_CONFIG = {
    "llm": {
    "api_base": "https://api.minimaxi.com/v1",
    "chat_path": "/chat/completions",
        "api_key": "",
        "model": "MiniMax-M2.7-highspeed",
        "timeout": 60
    },
    "vision": {
    "endpoint_url": "http://127.0.0.1:8080/v1/chat/completions",
        "timeout": 180
    },
    "whisper": {
        "device": "auto",
        "compute_type": "auto"
    },
    "app": {
        "auto_update": True,
        "language": "zh"
    }
}

def load_config():
    config_path = os.path.join(get_config_dir(), 'config.json')
    if os.path.exists(config_path):
        with open(config_path, 'r', encoding='utf-8') as f:
            user_config = json.load(f)
        # 合并默认值
        merged = {**DEFAULT_CONFIG}
        for key in merged:
            if key in user_config:
                if isinstance(merged[key], dict):
                    merged[key] = {**merged[key], **user_config[key]}
                else:
                    merged[key] = user_config[key]
        return merged
    return DEFAULT_CONFIG.copy()

def save_config(config):
    config_path = os.path.join(get_config_dir(), 'config.json')
    with open(config_path, 'w', encoding='utf-8') as f:
        json.dump(config, f, indent=2, ensure_ascii=False)
```

### post_json 改造

```python
def build_chat_url(api_base, chat_path="/chat/completions"):
  return api_base.rstrip("/") + "/" + chat_path.lstrip("/")


def post_json(url, data, api_key=None, timeout=180):
    """发送 JSON POST 请求，支持 API Key"""
    import urllib.request
    headers = {'Content-Type': 'application/json'}
    if api_key:
        headers['Authorization'] = f'Bearer {api_key}'
    req = urllib.request.Request(
        url,
        data=json.dumps(data).encode('utf-8'),
        headers=headers,
        method='POST'
    )
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return json.loads(response.read().decode('utf-8'))
```

### GPU 自适应

```python
def get_whisper_model_path():
    """解析模型路径，'bundled' 映射为实际捆绑目录"""
    config = load_config()
    model_path = config["whisper"].get("model_path", "bundled")
    if model_path == "bundled":
        bundled_dir = os.environ.get("MEDIA_ASSISTANT_BUNDLED_DIR", ".")
        model_path = os.path.join(bundled_dir, "models", "faster-whisper-large-v3-turbo")
    return model_path


def get_whisper_device_config():
    """检测最佳 Whisper 运行设备"""
    config = load_config()
    device = config["whisper"]["device"]
    compute_type = config["whisper"]["compute_type"]

    if device == "auto":
        try:
            import ctranslate2
            if "cuda" in ctranslate2.get_supported_compute_types("cuda"):
                device = "cuda"
                compute_type = "float16" if compute_type == "auto" else compute_type
            else:
                device = "cpu"
                compute_type = "int8" if compute_type == "auto" else compute_type
        except Exception:
            device = "cpu"
            compute_type = "int8" if compute_type == "auto" else compute_type
    elif compute_type == "auto":
        compute_type = "float16" if device == "cuda" else "int8"

    return device, compute_type
```

  ### Windows GPU 环境检测

  ```python
  def check_windows_gpu_runtime():
    """返回 GPU 运行时是否就绪，未就绪则说明原因"""
    if os.name != "nt":
      return True, "not-windows"
    try:
      import ctranslate2
      supported = ctranslate2.get_supported_compute_types("cuda")
      if "float16" in supported or "int8_float16" in supported:
        return True, "cuda-ready"
      return False, "cuda-runtime-missing"
    except Exception as exc:
      return False, f"cuda-check-failed: {exc}"
  ```

### 新增 Settings API

```python
from fastapi import Request

@app.get("/api/settings")
async def get_settings():
    return load_config()

@app.post("/api/settings")
async def update_settings(request: Request):
    body = await request.json()
    config = load_config()
    # 安全合并（只更新已知字段）
    for section in ["llm", "vision", "whisper", "app"]:
        if section in body:
            for key, value in body[section].items():
                if key in config.get(section, {}):
                    config[section][key] = value
    save_config(config)
    return {"message": "设置已保存", "config": config}
```

---

## 打包配置

### electron-builder.yml

```yaml
appId: com.media-assistant.desktop
productName: Media Assistant
copyright: Copyright © 2026

directories:
  output: dist

files:
  - "**/*"
  - "!node_modules/.cache"

extraResources:
  # Python frozen backend (one-folder 模式，整个目录)
  - from: ../backend/dist/media-assistant/
    to: backend/
    filter:
      - "**/*"
  # Bundled resources
  - from: ../bundled/
    to: bundled/
    filter:
      - "**/*"

publish:
  provider: github
  owner: ${GH_OWNER}
  repo: media-assistant
  releaseType: release

# 注: 无 Apple Developer 证书阶段，macOS 仍通过 GitHub Releases 分发，
# 应用内只做检测与跳转下载，不做静默安装。

mac:
  category: public.app-category.video
  target:
    - target: dmg
      arch: [arm64]
  icon: electron/assets/icon.icns
  hardenedRuntime: true
  gatekeeperAssess: false

dmg:
  title: "Media Assistant"
  artifactName: "Media-Assistant-${version}-mac-${arch}.dmg"
  contents:
    - x: 130
      y: 220
    - x: 410
      y: 220
      type: link
      path: /Applications

win:
  target:
    - target: nsis
      arch: [x64]
  icon: electron/assets/icon.ico
  publisherName: Media Assistant

nsis:
  oneClick: false
  perMachine: false
  allowToChangeInstallationDirectory: true
  installerIcon: electron/assets/icon.ico
  uninstallerIcon: electron/assets/icon.ico
  artifactName: "Media-Assistant-${version}-win-x64-setup.exe"
  installerLanguages:
    - 2052  # zh_CN
    - 1033  # en_US
```

### PyInstaller spec (backend/media-assistant.spec)

```python
# -*- mode: python ; coding: utf-8 -*-
import sys
import os

block_cipher = None

a = Analysis(
    ['video_subtitle_app.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=[
        'faster_whisper',
        'ctranslate2',
        'uvicorn',
        'uvicorn.logging',
        'uvicorn.loops',
        'uvicorn.loops.auto',
        'uvicorn.protocols',
        'uvicorn.protocols.http',
        'uvicorn.protocols.http.auto',
        'uvicorn.protocols.websockets',
        'uvicorn.protocols.websockets.auto',
        'uvicorn.lifespan',
        'uvicorn.lifespan.on',
        'fastapi',
        'starlette',
        'starlette.routing',
        'starlette.responses',
        'starlette.middleware',
        'starlette.middleware.cors',
        'pydantic',
        'pydantic_core',
        'anyio',
        'anyio._backends',
        'anyio._backends._asyncio',
        'sniffio',
        'PIL',
        'config',  # 自建配置模块
    ],
    # 注: Phase 4 冻结验证时需逐步补全，可用 --debug imports 排查缺失
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter', 'matplotlib', 'scipy'],
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    name='media-assistant',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,  # 无控制台窗口
    icon='../electron/assets/icon.ico' if sys.platform == 'win32' else None,
)

# one-folder 模式: 避免单文件每次启动解压 200MB+ 造成 10-30s 延迟
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    name='media-assistant',
)
```

---

## GitHub Actions CI/CD

### .github/workflows/release.yml

```yaml
name: Build & Release

on:
  push:
    tags:
      - 'v*'

jobs:
  build-backend-mac:
    runs-on: macos-14  # M1 runner (arm64)
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - name: Install dependencies
        run: |
          cd backend
          pip install -r requirements.txt
          pip install pyinstaller
      - name: Build frozen backend
        run: |
          cd backend
          pyinstaller media-assistant.spec
      - name: Upload artifact
        uses: actions/upload-artifact@v4
        with:
          name: backend-mac-arm64
          path: backend/dist/media-assistant

  build-backend-win:
    runs-on: windows-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - name: Install dependencies
        run: |
          cd backend
          pip install -r requirements.txt
          pip install pyinstaller
      - name: Build frozen backend
        run: |
          cd backend
          pyinstaller media-assistant.spec
      - name: Upload artifact
        uses: actions/upload-artifact@v4
        with:
          name: backend-win-x64
          path: backend/dist/media-assistant.exe

  build-electron-mac:
    needs: [build-backend-mac]
    runs-on: macos-14
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: '20'

      - name: Download backend artifact
        uses: actions/download-artifact@v4
        with:
          name: backend-mac-arm64

      - name: Place backend
        run: |
          mkdir -p backend/dist
          cp backend-mac-arm64/media-assistant backend/dist/media-assistant
          chmod +x backend/dist/media-assistant

      - name: Cache Whisper model
        uses: actions/cache@v4
        with:
          path: bundled/models/faster-whisper-large-v3-turbo
          key: whisper-turbo-v1

      - name: Download Whisper model
        run: |
          if [ ! -f bundled/models/faster-whisper-large-v3-turbo/model.bin ]; then
            pip install huggingface-hub
            huggingface-cli download Systran/faster-whisper-large-v3-turbo \
              --local-dir bundled/models/faster-whisper-large-v3-turbo
          fi

      - name: Download ffmpeg + ffprobe
        run: |
          # macOS arm64
          mkdir -p bundled/ffmpeg/mac-arm64
          curl -L "https://evermeet.cx/ffmpeg/getrelease/ffmpeg/zip" -o /tmp/ffmpeg.zip
          unzip /tmp/ffmpeg.zip -d bundled/ffmpeg/mac-arm64/
          curl -L "https://evermeet.cx/ffmpeg/getrelease/ffprobe/zip" -o /tmp/ffprobe.zip
          unzip /tmp/ffprobe.zip -d bundled/ffmpeg/mac-arm64/

      - name: Install Electron deps
        run: |
          cd electron
          npm ci

      - name: Build macOS DMG
        env:
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        run: |
          cd electron
          npx electron-builder --mac --arm64 --publish always

  build-electron-win:
    needs: [build-backend-win]
    runs-on: windows-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: '20'

      - name: Download backend artifact
        uses: actions/download-artifact@v4
        with:
          name: backend-win-x64
          path: backend/dist/

      - name: Cache Whisper model
        uses: actions/cache@v4
        with:
          path: bundled/models/faster-whisper-large-v3-turbo
          key: whisper-turbo-v1

      - name: Download Whisper model
        shell: pwsh
        run: |
          if (-not (Test-Path bundled/models/faster-whisper-large-v3-turbo/model.bin)) {
            pip install huggingface-hub
            huggingface-cli download Systran/faster-whisper-large-v3-turbo `
              --local-dir bundled/models/faster-whisper-large-v3-turbo
          }

      - name: Download ffmpeg
        shell: pwsh
        run: |
          New-Item -ItemType Directory -Force -Path bundled/ffmpeg/win-x64
          Invoke-WebRequest -Uri "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip" -OutFile ffmpeg.zip
          Expand-Archive ffmpeg.zip -DestinationPath temp
          Copy-Item temp/*/bin/ffmpeg.exe bundled/ffmpeg/win-x64/
          Copy-Item temp/*/bin/ffprobe.exe bundled/ffmpeg/win-x64/

      - name: Install Electron deps
        run: |
          cd electron
          npm ci

      - name: Build Windows installer
        env:
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        run: |
          cd electron
          npx electron-builder --win --x64 --publish always
```

---

## 产物体积

| 组件 | macOS (arm64) | Windows (x64) |
|------|---------------|---------------|
| Electron shell | ~120MB | ~120MB |
| Python frozen backend | ~200MB | ~250MB |
| Whisper turbo 模型 (int8) | ~850MB | ~850MB |
| ffmpeg + ffprobe 静态版 | ~80MB | ~130MB |
| **安装包总大小** | **~1.25GB** | **~1.35GB** |
| **压缩后 (DMG/NSIS)** | **~900MB** | **~950MB** |

> 注: CUDA/cuDNN 由用户自行安装，不含在安装包内。

---

## 无证书分发

| 平台 | 问题 | 用户操作 |
|------|------|----------|
| macOS | Gatekeeper 阻止 | 右键 → 打开 → 确认；或终端 `xattr -cr /Applications/Media\ Assistant.app` |
| Windows | SmartScreen 警告 | 点「更多信息」→「仍要运行」 |

**DMG 内附 README**：说明首次打开方式。

说明：在无证书阶段，macOS 的“自动更新”定义为应用内发现新版本并跳转到 Release 页面下载，不包含应用内直接安装。

---

## 开发阶段规划

| 阶段 | 工作内容 | 产出 |
|------|----------|------|
| **Phase 1** | Python 后端改造 | config.py + video_subtitle_app.py 改造 + Settings API |
| **Phase 2** | Electron 壳搭建 | main.js + backend-manager + tray + updater |
| **Phase 3** | 开发模式联调 | `npm start` 启动 Electron + Python，功能完整 |
| **Phase 4** | PyInstaller 冻结 macOS | 验证 frozen binary 独立运行 |
| **Phase 5** | electron-builder macOS DMG | 可分发 DMG |
| **Phase 6** | Windows 环境构建 | PyInstaller + electron-builder → NSIS 安装包 |
| **Phase 7** | GitHub Actions CI/CD | 自动化双平台构建 + 发布 |
| **Phase 8** | 自动更新测试 | 发布 v1.0.1 验证更新流程 |

---

## 前置条件

| 需求 | 说明 |
|------|------|
| Node.js 20+ | Electron 开发 |
| Python 3.11 | 后端 |
| GitHub 仓库 | 存放代码 + Releases (自动更新源) |
| Hugging Face 访问 | 下载 Whisper turbo 模型 |
| Windows 测试机 (NVIDIA GPU) | 验证 CUDA 加速 |

---

## 后续可选优化

1. **macOS 公证** — 购买 Apple Developer 证书后可消除 Gatekeeper 警告
2. **Windows 代码签名** — EV 证书消除 SmartScreen
3. **增量更新** — electron-updater 支持 delta update，减小更新包体积
4. **Vision 服务内置管理** — Electron 进程直接管理 llama-server 启动/停止
5. **模型按需下载** — 首次启动时从 CDN 下载模型，减小安装包体积
