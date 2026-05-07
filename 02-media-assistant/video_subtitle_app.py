#!/usr/bin/env python3
"""
视频语音翻译字幕 Web 应用
上传视频文件，自动转录语音并翻译生成字幕

功能:
- 支持多种视频/音频格式 (MP4, MKV, AVI, MOV, WebM, MP3, WAV 等)
- 支持自动语言检测或手动选择源语言
- 支持多种目标语言翻译 (中/英/日/韩/法/德/西/俄)
- 生成原文字幕、译文字幕、双语字幕 (SRT 格式)
- 字幕在线预览和下载

访问: http://localhost:8090
"""

import os

# 清除所有代理设置，避免 httpx/socksio 和 urllib 通过已关闭的代理连接
for _proxy_key in ("ALL_PROXY", "all_proxy", "HTTP_PROXY", "http_proxy", "HTTPS_PROXY", "https_proxy"):
    os.environ.pop(_proxy_key, None)

import json
import subprocess
import re
import traceback
import uuid
import time
import asyncio
from datetime import datetime
from pathlib import Path
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, FileResponse, PlainTextResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

from config import (
    load_config, save_config, get_port, get_data_dir, get_bundled_dir,
    build_llm_url, get_llm_api_key, get_llm_model,
    find_ffmpeg, find_ffprobe, get_whisper_model_path,
    get_whisper_backend, get_whisper_device_config,
)
from llm_manager import get_llm_manager

app = FastAPI(title="视频语音翻译字幕")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 配置
_cfg = load_config()
LLM_URL = build_llm_url(_cfg)
FRAME_INTERVAL = _cfg["app"].get("frame_interval", 60)
FFMPEG = find_ffmpeg()
FFPROBE = find_ffprobe()

# 数据目录: 环境变量 > 项目本地目录
_env_data_dir = os.environ.get('MEDIA_ASSISTANT_DATA_DIR')
if _env_data_dir:
    _BASE_DIR = _env_data_dir
else:
    _BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_DIR = os.path.join(_BASE_DIR, "uploads")
OUTPUT_DIR = os.path.join(_BASE_DIR, "output")
MAX_STORAGE_MB = 80 * 1024  # 上传+输出目录最大占用 80GB，超过后自动清理最旧的任务
MAX_TASK_COUNT = 20        # 最多保留最近 20 个任务的文件
TRANSLATE_BATCH_SIZE = 8
TRANSLATE_BULK_MAX_ITEMS = 80
TRANSLATE_BULK_MAX_CHARS = 6000
MINIMAX_BULK_MAX_ITEMS = 80
MINIMAX_BULK_MAX_CHARS = 6000

os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)

# 支持的语言
LANGUAGES = {
    "auto": "自动检测",
    "zh": "中文", "en": "英语", "ja": "日语", "ko": "韩语",
    "fr": "法语", "de": "德语", "es": "西班牙语", "ru": "俄语",
    "pt": "葡萄牙语", "it": "意大利语", "ar": "阿拉伯语",
    "th": "泰语", "vi": "越南语",
}

LANGUAGE_NAMES_EN = {
    "zh": "Chinese", "en": "English", "ja": "Japanese", "ko": "Korean",
    "fr": "French", "de": "German", "es": "Spanish", "ru": "Russian",
    "pt": "Portuguese", "it": "Italian", "ar": "Arabic",
    "th": "Thai", "vi": "Vietnamese",
}

HTML_PAGE = """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta http-equiv="Cache-Control" content="no-cache, no-store, must-revalidate">
    <meta http-equiv="Pragma" content="no-cache">
    <meta http-equiv="Expires" content="0">
    <title>视频语音翻译字幕</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", sans-serif;
            background: linear-gradient(135deg, #0f0c29 0%, #302b63 50%, #24243e 100%);
            min-height: 100vh;
            color: #eee;
        }
        .container { max-width: 860px; margin: 0 auto; padding: 30px 20px; }
        header { text-align: center; margin-bottom: 30px; }
        header h1 {
            font-size: 2.2em;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            margin-bottom: 8px;
        }
        header p { color: #999; font-size: 0.95em; }
        .card {
            background: rgba(255,255,255,0.06);
            border-radius: 16px;
            padding: 28px;
            margin-bottom: 20px;
            backdrop-filter: blur(10px);
            border: 1px solid rgba(255,255,255,0.08);
        }
        .card h3 { margin-bottom: 16px; font-size: 1.1em; color: #bbb; }
        .service-status { display: flex; gap: 20px; margin-bottom: 20px; flex-wrap: wrap; }
        .service-item { display: flex; align-items: center; gap: 8px; font-size: 0.9em; color: #aaa; }
        .status-dot { width: 8px; height: 8px; border-radius: 50%; background: #555; }
        .status-dot.green { background: #4caf50; box-shadow: 0 0 6px #4caf50; }
        .status-dot.red { background: #f44336; }
        .status-dot.yellow { background: #ffc107; box-shadow: 0 0 6px #ffc107; }
        .status-dot.orange { background: #ff9800; }
        .upload-area {
            border: 2px dashed rgba(102,126,234,0.4);
            border-radius: 12px;
            padding: 50px 20px;
            text-align: center;
            cursor: pointer;
            transition: all 0.3s;
            margin-bottom: 20px;
        }
        .upload-area:hover, .upload-area.dragover {
            border-color: #667eea;
            background: rgba(102,126,234,0.1);
        }
        .upload-icon { font-size: 3em; margin-bottom: 12px; }
        .upload-text { font-size: 1.1em; margin-bottom: 6px; }
        .upload-hint { color: #777; font-size: 0.85em; }
        input[type="file"] { display: none; }
        .file-info {
            background: rgba(102,126,234,0.15);
            padding: 14px 18px;
            border-radius: 10px;
            margin-bottom: 20px;
            display: none;
            align-items: center;
            justify-content: space-between;
        }
        .file-info.show { display: flex; }
        .file-meta { flex: 1; }
        .file-name { font-size: 1em; margin-bottom: 3px; word-break: break-all; }
        .file-size { color: #888; font-size: 0.85em; }
        .remove-btn {
            background: rgba(244,67,54,0.8); color: white; border: none;
            padding: 6px 14px; border-radius: 6px; cursor: pointer; font-size: 0.85em;
        }
        .lang-row { display: flex; gap: 16px; margin-bottom: 20px; flex-wrap: wrap; }
        .lang-group { flex: 1; min-width: 200px; }
        .lang-group label { display: block; margin-bottom: 6px; font-size: 0.9em; color: #aaa; }
        .lang-group select {
            width: 100%; padding: 10px 12px; border-radius: 8px;
            border: 1px solid rgba(255,255,255,0.15);
            background: rgba(255,255,255,0.08); color: #eee; font-size: 0.95em;
            appearance: none; -webkit-appearance: none;
            background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' fill='%23999' viewBox='0 0 16 16'%3E%3Cpath d='M8 11L3 6h10z'/%3E%3C/svg%3E");
            background-repeat: no-repeat; background-position: right 12px center;
            cursor: pointer;
        }
        .lang-group select:focus { outline: none; border-color: #667eea; }
        .lang-group select option { background: #2a2a4a; color: #eee; }
        .mode-row { display: flex; gap: 12px; margin-bottom: 20px; }
        .mode-option {
            flex: 1; padding: 14px; border-radius: 10px;
            border: 2px solid rgba(255,255,255,0.1);
            text-align: center; cursor: pointer; transition: all 0.2s; font-size: 0.9em;
        }
        .mode-option:hover { border-color: rgba(102,126,234,0.5); }
        .mode-option.active { border-color: #667eea; background: rgba(102,126,234,0.15); }
        .mode-option .mode-icon { font-size: 1.6em; margin-bottom: 6px; }
        .mode-option .mode-label { font-weight: 600; margin-bottom: 3px; }
        .mode-option .mode-desc { color: #888; font-size: 0.85em; }
        .btn {
            width: 100%; padding: 16px;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white; border: none; border-radius: 12px;
            font-size: 1.1em; cursor: pointer; transition: all 0.2s; font-weight: 600;
        }
        .btn:hover { transform: scale(1.01); opacity: 0.95; }
        .btn:disabled { opacity: 0.4; cursor: not-allowed; transform: none; }
        .progress-area { display: none; margin-top: 24px; }
        .progress-area.show { display: block; }
        .step {
            display: flex; align-items: center; padding: 12px 0;
            border-bottom: 1px solid rgba(255,255,255,0.06);
        }
        .step:last-child { border-bottom: none; }
        .step-icon {
            width: 36px; height: 36px; border-radius: 50%;
            display: flex; align-items: center; justify-content: center;
            margin-right: 14px; font-size: 0.95em; font-weight: 700; flex-shrink: 0;
        }
        .step.pending .step-icon { background: #333; color: #666; }
        .step.running .step-icon { background: #667eea; color: white; animation: pulse 1.2s infinite; }
        .step.done .step-icon { background: #4caf50; color: white; }
        .step.error .step-icon { background: #f44336; color: white; }
        .step-text { flex: 1; }
        .step-title { font-size: 0.95em; }
        .step-status { color: #777; font-size: 0.85em; margin-top: 2px; }
        @keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.5; } }
        .step-progress { margin-top: 6px; display: none; align-items: center; gap: 10px; }
        .step-progress.show { display: flex; }
        .progress-track { flex: 1; height: 6px; background: rgba(255,255,255,0.1); border-radius: 3px; overflow: hidden; }
        .progress-fill { height: 100%; background: linear-gradient(90deg, #667eea, #764ba2); border-radius: 3px; transition: width 0.3s ease; width: 0%; }
        .progress-pct { font-size: 0.8em; color: #999; min-width: 38px; text-align: right; }
        .task-history { margin-bottom: 20px; }
        .task-history h3 { margin-bottom: 10px; }
        .task-item {
            display: flex; align-items: center; justify-content: space-between;
            padding: 10px 14px; border-radius: 8px; margin-bottom: 6px;
            background: rgba(255,255,255,0.04); border: 1px solid rgba(255,255,255,0.06);
            cursor: pointer; transition: all 0.2s;
        }
        .task-item:hover { background: rgba(102,126,234,0.1); border-color: rgba(102,126,234,0.3); }
        .task-item .task-name { flex: 1; font-size: 0.9em; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
        .task-item .task-time { color: #777; font-size: 0.8em; margin-left: 12px; white-space: nowrap; }
        .result-area { display: none; margin-top: 24px; }
        .result-area.show { display: block; }
        .result-header { font-size: 1.1em; margin-bottom: 14px; color: #4caf50; }
        .download-btn {
            display: block; padding: 14px 20px;
            background: rgba(76,175,80,0.15); border: 1px solid rgba(76,175,80,0.3);
            color: #4caf50; text-decoration: none; border-radius: 10px;
            text-align: center; margin: 8px 0; transition: all 0.2s; font-size: 0.95em;
        }
        .download-btn:hover { background: rgba(76,175,80,0.25); transform: scale(1.01); }
        .preview-area { display: none; margin-top: 16px; }
        .preview-area.show { display: block; }
        .preview-box {
            background: rgba(0,0,0,0.3); border-radius: 10px; padding: 16px;
            max-height: 300px; overflow-y: auto;
            font-family: "SF Mono", Monaco, Consolas, monospace;
            font-size: 0.85em; line-height: 1.6; color: #ccc; white-space: pre-wrap;
        }
        .preview-tabs { display: flex; gap: 8px; margin-bottom: 10px; }
        .preview-tab {
            padding: 6px 14px; border-radius: 6px;
            border: 1px solid rgba(255,255,255,0.15);
            background: transparent; color: #aaa; cursor: pointer; font-size: 0.85em;
        }
        .preview-tab.active { background: rgba(102,126,234,0.2); border-color: #667eea; color: #eee; }
        .frame-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(240px, 1fr)); gap: 12px; margin-bottom: 16px; }
        .frame-card {
            background: rgba(0,0,0,0.3); border-radius: 10px; overflow: hidden;
            border: 1px solid rgba(255,255,255,0.08); transition: all 0.2s;
        }
        .frame-card:hover { border-color: rgba(102,126,234,0.4); transform: translateY(-2px); }
        .frame-card img { width: 100%; aspect-ratio: 16/9; object-fit: cover; display: block; }
        .frame-card .frame-info { padding: 10px 12px; }
        .frame-card .frame-time { color: #667eea; font-size: 0.85em; font-weight: 600; margin-bottom: 4px; }
        .frame-card .frame-desc { color: #bbb; font-size: 0.82em; line-height: 1.5; }
        .summary-box {
            background: rgba(0,0,0,0.3); border-radius: 10px; padding: 18px;
            color: #ccc; font-size: 0.9em; line-height: 1.8;
            max-height: 400px; overflow-y: auto; margin-top: 12px;
        }
        .summary-box h1, .summary-box h2, .summary-box h3 { color: #ddd; margin: 12px 0 8px 0; }
        .summary-box h1 { font-size: 1.3em; border-bottom: 1px solid #444; padding-bottom: 6px; }
        .summary-box h2 { font-size: 1.15em; border-bottom: 1px solid #333; padding-bottom: 4px; }
        .summary-box h3 { font-size: 1em; color: #99aaff; }
        .summary-box hr { border: none; border-top: 1px solid #444; margin: 12px 0; }
        .summary-box p { margin: 6px 0; }
        .summary-box ul, .summary-box ol { padding-left: 20px; margin: 6px 0; }
        .preview-box.markdown { white-space: pre-wrap; }
        .preview-box.markdown h1, .preview-box.markdown h2, .preview-box.markdown h3 { color: #ddd; margin: 12px 0 8px 0; }
        .preview-box.markdown h1 { font-size: 1.3em; border-bottom: 1px solid #444; padding-bottom: 6px; }
        .preview-box.markdown h2 { font-size: 1.15em; border-bottom: 1px solid #333; padding-bottom: 4px; }
        .preview-box.markdown h3 { font-size: 1em; color: #99aaff; }
        .preview-box.markdown hr { border: none; border-top: 1px solid #444; margin: 12px 0; }
        .preview-box.markdown p { margin: 6px 0; }
        .preview-box.markdown ul, .preview-box.markdown ol { padding-left: 20px; margin: 6px 0; }
        .preview-box.markdown blockquote {
            margin: 8px 0; padding: 8px 12px;
            border-left: 3px solid rgba(102,126,234,0.6);
            background: rgba(255,255,255,0.04); color: #ddd;
        }
        .frame-toggle { display: flex; align-items: center; gap: 10px; margin-bottom: 20px; }
        .frame-toggle label { color: #aaa; font-size: 0.9em; cursor: pointer; }
        .frame-toggle input[type="checkbox"] { width: 18px; height: 18px; cursor: pointer; accent-color: #667eea; }
        ::-webkit-scrollbar { width: 6px; }
        ::-webkit-scrollbar-track { background: transparent; }
        ::-webkit-scrollbar-thumb { background: #444; border-radius: 3px; }
        @media (max-width: 600px) {
            header h1 { font-size: 1.6em; }
            .container { padding: 16px; }
            .card { padding: 20px; }
            .upload-area { padding: 30px 16px; }
            .mode-row { flex-direction: column; }
        }
    </style>
</head>
<body>
    <div class="container">
        <header style="position:relative">
            <h1>视频语音翻译字幕</h1>
            <p>上传视频文件，自动识别语音并翻译生成字幕文件</p>
            <button onclick="toggleSettings()" style="position:absolute;top:15px;right:15px;background:none;border:1px solid #555;border-radius:6px;padding:6px 12px;color:#aaa;cursor:pointer;font-size:14px" title="设置">⚙️ 设置</button>
        </header>

        <!-- Settings Panel -->
        <div class="card" id="settings-panel" style="display:none">
            <h3>⚙️ 服务配置</h3>
            <div style="margin-bottom:14px;display:flex;align-items:center;gap:8px;flex-wrap:wrap">
                <span style="color:#aaa;font-size:12px;margin-right:4px">快速切换:</span>
                <button onclick="applyPreset('local')" class="preset-btn" id="preset-local" style="padding:5px 14px;border-radius:4px;border:1px solid #555;background:#2a2a2a;color:#ccc;cursor:pointer;font-size:12px">🏠 内置模型</button>
                <button onclick="applyPreset('minimax')" class="preset-btn" id="preset-minimax" style="padding:5px 14px;border-radius:4px;border:1px solid #555;background:#2a2a2a;color:#ccc;cursor:pointer;font-size:12px">☁️ MiniMax</button>
                <button onclick="applyPreset('deepseek')" class="preset-btn" id="preset-deepseek" style="padding:5px 14px;border-radius:4px;border:1px solid #555;background:#2a2a2a;color:#ccc;cursor:pointer;font-size:12px">☁️ DeepSeek</button>
                <button onclick="applyPreset('openai')" class="preset-btn" id="preset-openai" style="padding:5px 14px;border-radius:4px;border:1px solid #555;background:#2a2a2a;color:#ccc;cursor:pointer;font-size:12px">☁️ OpenAI</button>
            </div>
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px">
                <div>
                    <label style="color:#aaa;font-size:12px">LLM API Base</label>
                    <input type="text" id="cfg-llm-api-base" style="width:100%;padding:6px;background:#2a2a2a;border:1px solid #444;border-radius:4px;color:#eee" placeholder="http://127.0.0.1:8080/v1">
                </div>
                <div>
                    <label style="color:#aaa;font-size:12px">LLM Chat Path</label>
                    <input type="text" id="cfg-llm-chat-path" style="width:100%;padding:6px;background:#2a2a2a;border:1px solid #444;border-radius:4px;color:#eee" placeholder="/chat/completions">
                </div>
                <div>
                    <label style="color:#aaa;font-size:12px">LLM API Key (可选)</label>
                    <input type="password" id="cfg-llm-api-key" style="width:100%;padding:6px;background:#2a2a2a;border:1px solid #444;border-radius:4px;color:#eee" placeholder="留空表示无需认证">
                </div>
                <div>
                    <label style="color:#aaa;font-size:12px">LLM Model (可选)</label>
                    <input type="text" id="cfg-llm-model" style="width:100%;padding:6px;background:#2a2a2a;border:1px solid #444;border-radius:4px;color:#eee" placeholder="留空使用服务默认模型">
                </div>
                <div>
                    <label style="color:#aaa;font-size:12px">Whisper 模型</label>
                    <select id="cfg-whisper-model-path" style="width:100%;padding:6px;background:#2a2a2a;border:1px solid #444;border-radius:4px;color:#eee"></select>
                </div>
                <div>
                    <label style="color:#aaa;font-size:12px">本地 LLM 模型文件</label>
                    <select id="cfg-llm-model-path" style="width:100%;padding:6px;background:#2a2a2a;border:1px solid #444;border-radius:4px;color:#eee"></select>
                </div>
                <div style="grid-column:1/-1;color:#888;font-size:12px;line-height:1.5">
                    本地模式下，以上下拉框控制实际加载的 Whisper 与 LLM 模型。外部 API 模式下，LLM Model 作为请求模型名使用。
                </div>
                <div>
                    <label style="color:#aaa;font-size:12px">帧提取间隔 (秒)</label>
                    <input type="number" id="cfg-frame-interval" style="width:100%;padding:6px;background:#2a2a2a;border:1px solid #444;border-radius:4px;color:#eee" placeholder="60" min="10" max="600">
                </div>
                <div style="display:flex;align-items:end;gap:8px;flex-wrap:wrap">
                    <button onclick="loadModelOptions()" style="padding:8px 14px;background:#2f3542;border:1px solid #555;border-radius:4px;color:#eee;cursor:pointer">刷新模型列表</button>
                    <button onclick="refreshRuntimeLog()" style="padding:8px 14px;background:#2f3542;border:1px solid #555;border-radius:4px;color:#eee;cursor:pointer">刷新日志</button>
                    <button onclick="saveSettings()" style="padding:8px 20px;background:#667eea;border:none;border-radius:4px;color:#fff;cursor:pointer">保存设置</button>
                    <span id="settings-msg" style="margin-left:10px;color:#4caf50;font-size:12px"></span>
                </div>
                <div style="grid-column:1/-1">
                    <label style="color:#aaa;font-size:12px">运行日志</label>
                    <div style="color:#777;font-size:11px;margin:4px 0 8px 0">日志文件: /tmp/llm-logs/video_subtitle.log</div>
                    <pre id="runtime-log" style="margin:0;min-height:180px;max-height:260px;overflow:auto;padding:12px;background:#111;border:1px solid #333;border-radius:6px;color:#cfd8dc;font-size:12px;line-height:1.45;white-space:pre-wrap">日志加载中...</pre>
                </div>
            </div>
        </div>

        <div class="service-status" id="service-status">
            <div class="service-item">
                <span class="status-dot" id="dot-whisper"></span>
                <span>Whisper 语音识别 <span id="text-whisper">检测中</span></span>
            </div>
            <div class="service-item">
                <span class="status-dot" id="dot-llm"></span>
                <span>LLM 翻译服务 <span id="text-llm">检测中</span></span>
                <button id="btn-llm-prewarm" onclick="llmPrewarm()" style="margin-left:12px;padding:2px 10px;font-size:11px;border-radius:4px;border:1px solid #555;background:#333;color:#ccc;cursor:pointer;display:none">预热模型</button>
                <button id="btn-llm-release" onclick="llmRelease()" style="margin-left:6px;padding:2px 10px;font-size:11px;border-radius:4px;border:1px solid #555;background:#333;color:#ccc;cursor:pointer;display:none">释放模型</button>
            </div>

        </div>

        <div class="card task-history" id="task-history" style="display:none">
            <h3>历史任务</h3>
            <div id="task-list"></div>
        </div>

        <div class="card">
            <h3>输入文件路径</h3>
            <div class="lang-group" style="margin-bottom:20px">
                <label>文件路径</label>
                <input type="text" id="local-path" placeholder="输入视频/音频文件的完整路径，如 /path/to/video.mp4"
                    style="width:100%;padding:10px 12px;border-radius:8px;border:1px solid rgba(255,255,255,0.15);background:rgba(255,255,255,0.08);color:#eee;font-size:0.95em;"
                    oninput="onPathInput()">
                <div style="color:#777;font-size:0.8em;margin-top:4px">支持 MP4, MKV, AVI, MOV, WMV, WebM, MP3, WAV 等格式</div>
            </div>

            <h3>处理模式</h3>
            <div class="mode-row">
                <div class="mode-option active" id="mode-translate" onclick="setMode('translate')">
                    <div class="mode-icon">🌐</div>
                    <div class="mode-label">转录 + 翻译</div>
                    <div class="mode-desc">识别语音并翻译为目标语言</div>
                </div>
                <div class="mode-option" id="mode-transcribe" onclick="setMode('transcribe')">
                    <div class="mode-icon">📝</div>
                    <div class="mode-label">仅转录</div>
                    <div class="mode-desc">只识别语音生成原文字幕</div>
                </div>
            </div>

            <div class="lang-row">
                <div class="lang-group">
                    <label>源语言 (视频语音)</label>
                    <select id="source-lang">
                        <option value="auto" selected>自动检测</option>
                        <option value="zh">中文</option>
                        <option value="en">英语</option>
                        <option value="ja">日语</option>
                        <option value="ko">韩语</option>
                        <option value="fr">法语</option>
                        <option value="de">德语</option>
                        <option value="es">西班牙语</option>
                        <option value="ru">俄语</option>
                        <option value="pt">葡萄牙语</option>
                        <option value="it">意大利语</option>
                        <option value="ar">阿拉伯语</option>
                        <option value="th">泰语</option>
                        <option value="vi">越南语</option>
                    </select>
                </div>
                <div class="lang-group" id="target-lang-group">
                    <label>目标语言 (字幕翻译)</label>
                    <select id="target-lang">
                        <option value="zh" selected>中文</option>
                        <option value="en">英语</option>
                        <option value="ja">日语</option>
                        <option value="ko">韩语</option>
                        <option value="fr">法语</option>
                        <option value="de">德语</option>
                        <option value="es">西班牙语</option>
                        <option value="ru">俄语</option>
                    </select>
                </div>
            </div>

            <button class="btn" id="start-btn" onclick="startProcess()" disabled>开始处理</button>

            <div class="progress-area" id="progress-area">
                <div class="step pending" id="step-upload">
                    <div class="step-icon">1</div>
                    <div class="step-text">
                        <div class="step-title">校验文件</div><div class="step-status">等待中</div>
                        <div class="step-progress"><div class="progress-track"><div class="progress-fill"></div></div><div class="progress-pct">0%</div></div>
                    </div>
                </div>
                <div class="step pending" id="step-audio">
                    <div class="step-icon">2</div>
                    <div class="step-text">
                        <div class="step-title">提取音频</div><div class="step-status">等待中</div>
                        <div class="step-progress"><div class="progress-track"><div class="progress-fill"></div></div><div class="progress-pct">0%</div></div>
                    </div>
                </div>
                <div class="step pending" id="step-transcribe">
                    <div class="step-icon">3</div>
                    <div class="step-text">
                        <div class="step-title">语音识别</div><div class="step-status">等待中</div>
                        <div class="step-progress"><div class="progress-track"><div class="progress-fill"></div></div><div class="progress-pct">0%</div></div>
                    </div>
                </div>
                <div class="step pending" id="step-translate">
                    <div class="step-icon">4</div>
                    <div class="step-text">
                        <div class="step-title">翻译字幕</div><div class="step-status">等待中</div>
                        <div class="step-progress"><div class="progress-track"><div class="progress-fill"></div></div><div class="progress-pct">0%</div></div>
                    </div>
                </div>
                <div class="step pending" id="step-subtitle">
                    <div class="step-icon">5</div>
                    <div class="step-text">
                        <div class="step-title">生成字幕文件</div><div class="step-status">等待中</div>
                        <div class="step-progress"><div class="progress-track"><div class="progress-fill"></div></div><div class="progress-pct">0%</div></div>
                    </div>
                </div>
            </div>

            <div class="result-area" id="result-area">
                <div class="result-header">✅ 处理完成</div>
                <div id="download-links"></div>
                <div class="preview-area" id="preview-area">
                    <div class="preview-tabs" id="preview-tabs"></div>
                    <div class="preview-box" id="preview-box"></div>
                </div>
            </div>
        </div>
    </div>

    <script>
        let taskId = null;
        let currentMode = 'translate';
        let previewData = {};
        let progressTimer = null;

        let _isExternalApi = false;
        async function checkServices() {
            try {
                const res = await fetch('/api/check_services');
                const data = await res.json();
                _isExternalApi = !!data.external_api;
                setDot('whisper', data.whisper, data.whisper_detail || '', data.whisper_text || '');
                setDot('llm', data.llm, data.llm_detail || '', data.llm_text || '', data.external_conflict);
                // 按钮可见性
                const btnPre = document.getElementById('btn-llm-prewarm');
                const btnRel = document.getElementById('btn-llm-release');
                if (_isExternalApi) {
                    btnPre.style.display = 'none';
                    btnRel.style.display = 'none';
                } else {
                    btnPre.style.display = data.llm ? 'none' : 'inline-block';
                    btnRel.style.display = data.llm ? 'inline-block' : 'none';
                    if (data.external_conflict) { btnPre.style.display = 'none'; btnRel.style.display = 'none'; }
                }
            } catch {
                setDot('whisper', false, 'check-failed');
                setDot('llm', false, 'check-failed');
            }
        }
        function setDot(n, ok, detail='', label='', externalConflict=false) {
            const dot = document.getElementById('dot-'+n);
            const text = document.getElementById('text-'+n);
            let color = ok ? 'green' : 'red';
            if (n === 'llm' && !ok && !externalConflict && label && !label.includes('离线')) color = 'yellow';
            if (n === 'llm' && externalConflict) color = 'orange';
            dot.className = 'status-dot ' + color;
            text.textContent = label || (ok ? '就绪' : '离线');
            const title = detail ? ((ok ? '就绪' : '离线') + ': ' + detail) : (ok ? '就绪' : '离线');
            dot.title = title;
            text.title = title;
        }
        async function llmPrewarm() {
            try {
                const res = await fetch('/api/llm_start', {method:'POST', headers:{'Content-Type':'application/json'}, body:'{}'});
                if (!res.ok) { const d = await res.json(); alert(d.error || '预热失败'); }
            } catch(e) { alert('请求失败: ' + e); }
            checkServices();
        }
        async function llmRelease() {
            try {
                const res = await fetch('/api/llm_stop', {method:'POST'});
                if (!res.ok) { const d = await res.json(); alert(d.error || '释放失败'); }
            } catch(e) { alert('请求失败: ' + e); }
            checkServices();
        }

        function onPathInput() { updateStartBtn(); }
        function updateStartBtn() {
            document.getElementById('start-btn').disabled = !document.getElementById('local-path').value.trim();
        }

        function setMode(mode) {
            currentMode = mode;
            document.getElementById('mode-translate').classList.toggle('active', mode==='translate');
            document.getElementById('mode-transcribe').classList.toggle('active', mode==='transcribe');
            document.getElementById('target-lang-group').style.display = mode==='translate'?'':'none';
            document.getElementById('step-translate').style.display = mode==='translate'?'':'none';
        }

        function setStepProgress(stepId, percent, detail) {
            const step = document.getElementById(stepId);
            const prog = step.querySelector('.step-progress');
            const fill = step.querySelector('.progress-fill');
            const pct = step.querySelector('.progress-pct');
            if (prog) { prog.classList.add('show'); fill.style.width = percent+'%'; pct.textContent = percent+'%'; }
            if (detail) step.querySelector('.step-status').textContent = detail;
        }
        function hideStepProgress(stepId) {
            const el = document.getElementById(stepId);
            if (el) { const p = el.querySelector('.step-progress'); if (p) p.classList.remove('show'); }
        }
        function startProgressPolling(tid) {
            stopProgressPolling();
            progressTimer = setInterval(async () => {
                try {
                    const res = await fetch('/api/progress/'+tid);
                    const d = await res.json();
                    const map = {audio:'step-audio', transcribe:'step-transcribe', translate:'step-translate', subtitle:'step-subtitle'};
                    const sid = map[d.step];
                    if (sid && d.percent !== undefined) setStepProgress(sid, d.percent, d.detail);
                } catch {}
            }, 500);
        }
        function stopProgressPolling() { if (progressTimer) { clearInterval(progressTimer); progressTimer = null; } }
        function setStep(id, st, msg) {
            const el = document.getElementById(id);
            el.className = 'step '+st;
            el.querySelector('.step-status').textContent = msg;
            if (st === 'done' || st === 'error') hideStepProgress(id);
        }

        async function startProcess() {
            const btn = document.getElementById('start-btn');
            btn.disabled = true; btn.textContent = '处理中...';
            const srcLang = document.getElementById('source-lang').value;
            const tgtLang = document.getElementById('target-lang').value;
            document.getElementById('progress-area').classList.add('show');
            document.getElementById('result-area').classList.remove('show');
            document.getElementById('preview-area').classList.remove('show');
            ['step-upload','step-audio','step-transcribe','step-translate','step-subtitle'].forEach(s => { setStep(s,'pending','等待中'); hideStepProgress(s); });

            try {
                setStep('step-upload','running','验证文件...');
                const localPath = document.getElementById('local-path').value.trim();
                const res = await fetch('/api/local_file', {
                    method:'POST',
                    headers:{'Content-Type':'application/json'},
                    body: JSON.stringify({path: localPath, source_lang: srcLang, target_lang: tgtLang, mode: currentMode})
                });
                const data = await res.json();
                if (data.error) throw new Error(data.error);
                taskId = data.task_id;
                localStorage.setItem('active_task_id', taskId);
                localStorage.setItem('active_task_name', localPath.split('/').pop());
                setStep('step-upload','done', data.message);

                startProgressPolling(taskId);

                setStep('step-audio','running','提取音频中...');
                setStepProgress('step-audio', 0, '提取音频中...');
                const audioRes = await fetch('/api/process/'+taskId+'/audio', { method:'POST' });
                const audioData = await audioRes.json();
                if (audioData.error) throw new Error(audioData.error);
                setStep('step-audio','done', audioData.message);

                setStep('step-transcribe','running','语音识别中...');
                setStepProgress('step-transcribe', 0, '语音识别中...');
                const trRes = await fetch('/api/process/'+taskId+'/transcribe', { method:'POST' });
                const trData = await trRes.json();
                if (trData.error) throw new Error(trData.error);
                setStep('step-transcribe','done', trData.message);

                if (currentMode === 'translate') {
                    setStep('step-translate','running','翻译中...');
                    setStepProgress('step-translate', 0, '翻译中...');
                    const tlRes = await fetch('/api/process/'+taskId+'/translate', { method:'POST' });
                    const tlData = await tlRes.json();
                    if (tlData.error) throw new Error(tlData.error);
                    setStep('step-translate','done', tlData.message);
                } else {
                    setStep('step-translate','done','跳过');
                }

                setStep('step-subtitle','running','生成字幕文件...');
                const subRes = await fetch('/api/process/'+taskId+'/subtitle', { method:'POST' });
                const subData = await subRes.json();
                if (subData.error) throw new Error(subData.error);
                setStep('step-subtitle','done', subData.message || '完成');

                stopProgressPolling();
                btn.textContent = '✅ 处理完成';
                localStorage.removeItem('active_task_id');
                localStorage.removeItem('active_task_name');
                saveTaskToHistory(taskId, document.getElementById('local-path')?.value || '');
                showResults(taskId);
            } catch (e) {
                stopProgressPolling();
                localStorage.removeItem('active_task_id');
                localStorage.removeItem('active_task_name');
                alert('处理出错: '+e.message);
                btn.disabled = false; btn.textContent = '重新处理';
            }
        }

        async function showResults(tid) {
            const res = await fetch('/api/results/'+tid);
            const data = await res.json();
            const links = document.getElementById('download-links');
            links.innerHTML = '';
            previewData = {};
            const labels = { source:'📄 原文字幕', translated:'📄 译文字幕', bilingual:'📄 双语字幕', summary:'📊 内容总结' };
            for (const [key, info] of Object.entries(data.files||{})) {
                const label = (labels[key]||'📄 '+info.name)+' ('+info.name+')';
                links.innerHTML += '<a class="download-btn" href="/download/'+tid+'/'+key+'">'+label+'</a>';
                try { const r = await fetch('/preview/'+tid+'/'+key); previewData[key] = await r.text(); } catch {}
            }
            if (Object.keys(previewData).length > 0) {
                const tabs = document.getElementById('preview-tabs');
                tabs.innerHTML = '';
                const tl = { source:'原文', translated:'译文', bilingual:'双语', summary:'总结' };
                let first = true;
                for (const key of Object.keys(previewData)) {
                    const tab = document.createElement('button');
                    tab.className = 'preview-tab'+(first?' active':'');
                    tab.textContent = tl[key]||key;
                    tab.onclick = () => switchPreview(key, tab);
                    tabs.appendChild(tab);
                    if (first) {
                        const box = document.getElementById('preview-box');
                        renderPreviewContent(key, previewData[key], box);
                        first = false;
                    }
                }
                document.getElementById('preview-area').classList.add('show');
            }
            document.getElementById('result-area').classList.add('show');
        }

        function escapeHtml(text) {
            const d = document.createElement('div');
            d.textContent = text;
            return d.innerHTML;
        }

        function simpleMarkdown(md) {
            let html = escapeHtml(md);
            // headings
            html = html.replace(/^### (.+)$/gm, '<h3>$1</h3>');
            html = html.replace(/^## (.+)$/gm, '<h2>$1</h2>');
            html = html.replace(/^# (.+)$/gm, '<h1>$1</h1>');
            // hr
            html = html.replace(/^---$/gm, '<hr>');
            // bold / italic
            html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
            html = html.replace(/\*(.+?)\*/g, '<em>$1</em>');
            // blockquote
            html = html.replace(/^> (.+)$/gm, '<blockquote>$1</blockquote>');
            // unordered list
            html = html.replace(/^[-*] (.+)$/gm, '<li>$1</li>');
            html = html.replace(/(<li>.*?<\/li>\s*)+/gs, m => '<ul>' + m + '</ul>');
            // ordered list
            html = html.replace(/^\d+[.)] (.+)$/gm, '<li>$1</li>');
            // paragraphs: double newline
            html = html.replace(/\\n{2,}/g, '</p><p>');
            html = '<p>' + html + '</p>';
            // clean up empty paragraphs around block elements
            html = html.replace(/<p>\s*(<h[123]|<hr|<ul|<\/ul|<ol|<\/ol)/g, '$1');
            html = html.replace(/<p>\s*(<blockquote>)/g, '$1');
            html = html.replace(/(<\/h[123]>|<hr>|<\/ul>|<\/ol>|<\/blockquote>)\s*<\/p>/g, '$1');
            html = html.replace(/<p>\s*<\/p>/g, '');
            return html;
        }

        function formatSrtAsMarkdown(srtText, key) {
            const titleMap = {
                source: '原文字幕预览',
                translated: '译文字幕预览',
                bilingual: '双语字幕预览',
            };
            const blocks = (srtText || '').trim().split(/\\n\s*\\n/).filter(Boolean);
            const sections = blocks.map((block, index) => {
                const lines = block.split(/\\n/).map(line => line.trim()).filter(Boolean);
                if (!lines.length) return '';
                let cursor = 0;
                let cueIndex = String(index + 1);
                if (/^\d+$/.test(lines[cursor])) {
                    cueIndex = lines[cursor];
                    cursor += 1;
                }
                let timeLine = '未知';
                if (cursor < lines.length && lines[cursor].includes('-->')) {
                    timeLine = lines[cursor];
                    cursor += 1;
                }
                const bodyLines = lines.slice(cursor);
                const body = bodyLines.length
                    ? bodyLines.map(line => `> ${line}`).join('\\n')
                    : '> [该字幕段无文本]';
                return `### 字幕 ${cueIndex}\n\n- 时间: ${timeLine}\n\n${body}`;
            }).filter(Boolean);

            if (!sections.length) {
                return `# ${titleMap[key] || '字幕预览'}\n\n暂无可显示内容。`;
            }

            return `# ${titleMap[key] || '字幕预览'}\n\n${sections.join('\\n\\n---\\n\\n')}`;
        }

        function normalizePreviewText(text) {
            const raw = String(text || '').replace(/\\r\\n/g, '\\n');
            if (!raw.includes('\\n') && raw.includes('\\\\n')) {
                return raw.replace(/\\\\r\\\\n/g, '\\n').replace(/\\\\n/g, '\\n');
            }
            return raw;
        }

        function renderPreviewContent(key, content, box) {
            box.className = 'preview-box markdown';
            const normalizedText = normalizePreviewText(content);
            if (key === 'summary') {
                box.innerHTML = simpleMarkdown(normalizedText);
                return;
            }

            const rawText = normalizedText;
            if (rawText.includes('-->')) {
                box.innerHTML = simpleMarkdown(formatSrtAsMarkdown(rawText, key));
                return;
            }

            box.innerHTML = simpleMarkdown(rawText);
        }

        function switchPreview(key, tab) {
            document.querySelectorAll('.preview-tab').forEach(t => t.classList.remove('active'));
            tab.classList.add('active');
            const box = document.getElementById('preview-box');
            renderPreviewContent(key, previewData[key], box);
        }

        function saveTaskToHistory(tid, fileName) {
            try {
                let hist = JSON.parse(localStorage.getItem('subtitle_tasks')||'[]');
                hist = hist.filter(h => h.id !== tid);
                const name = fileName.split('/').pop() || fileName;
                hist.unshift({id: tid, name: name, time: new Date().toLocaleString()});
                if (hist.length > 20) hist = hist.slice(0, 20);
                localStorage.setItem('subtitle_tasks', JSON.stringify(hist));
                renderHistory();
            } catch {}
        }
        function renderHistory() {
            try {
                const hist = JSON.parse(localStorage.getItem('subtitle_tasks')||'[]');
                const box = document.getElementById('task-history');
                const list = document.getElementById('task-list');
                if (!hist.length) { box.style.display = 'none'; return; }
                box.style.display = '';
                list.innerHTML = hist.map(h =>
                    '<div class="task-item" onclick="loadTask(&quot;'+h.id+'&quot;)">' +
                    '<span class="task-name">'+h.name+'</span>' +
                    '<span class="task-time">'+h.time+'</span>' +
                    '</div>'
                ).join('');
            } catch {}
        }
        async function loadTask(tid) {
            try {
                const res = await fetch('/api/results/'+tid);
                const data = await res.json();
                if (data.error) { removeTaskFromHistory(tid); return; }
                if (!data.files || Object.keys(data.files).length === 0) { alert('该任务结果不可用'); removeTaskFromHistory(tid); return; }
                taskId = tid;
                document.getElementById('progress-area').classList.remove('show');
                showResults(tid);
            } catch { removeTaskFromHistory(tid); }
        }
        function removeTaskFromHistory(tid) {
            try {
                let hist = JSON.parse(localStorage.getItem('subtitle_tasks')||'[]');
                hist = hist.filter(h => h.id !== tid);
                localStorage.setItem('subtitle_tasks', JSON.stringify(hist));
                renderHistory();
            } catch {}
        }

        async function restoreActiveTask() {
            const tid = localStorage.getItem('active_task_id');
            if (!tid) return;
            try {
                const res = await fetch('/api/task_status/'+tid);
                const data = await res.json();
                if (!data.exists) {
                    localStorage.removeItem('active_task_id');
                    localStorage.removeItem('active_task_name');
                    return;
                }
                taskId = tid;
                const btn = document.getElementById('start-btn');
                const stepMap = {upload:'step-upload',audio:'step-audio',transcribe:'step-transcribe',translate:'step-translate',subtitle:'step-subtitle'};

                if (data.completed) {
                    btn.textContent = '✅ 处理完成'; btn.disabled = true;
                    document.getElementById('progress-area').classList.add('show');
                    for (const [k,v] of Object.entries(data.steps)) {
                        const sid = stepMap[k];
                        if (sid) setStep(sid, 'done', v==='skip'?'跳过':'完成');
                    }
                    const taskName = localStorage.getItem('active_task_name') || data.file_name || '';
                    localStorage.removeItem('active_task_id');
                    localStorage.removeItem('active_task_name');
                    saveTaskToHistory(tid, taskName);
                    showResults(tid);
                    return;
                }

                document.getElementById('progress-area').classList.add('show');
                if (data.mode==='transcribe') setMode('transcribe');
                for (const [k,v] of Object.entries(data.steps)) {
                    const sid = stepMap[k];
                    if (!sid) continue;
                    if (v==='done') setStep(sid,'done','完成');
                    else if (v==='skip') setStep(sid,'done','跳过');
                    else if (v==='running') {
                        setStep(sid,'running',data.progress.detail||'处理中...');
                        if (data.progress.percent) setStepProgress(sid,data.progress.percent,data.progress.detail);
                    }
                }
                btn.disabled = true; btn.textContent = '处理中...';
                startProgressPolling(tid);
                await resumeProcessing(tid, data);
            } catch (e) { console.error('Restore failed:', e); }
        }

        async function resumeProcessing(tid, st) {
            const btn = document.getElementById('start-btn');
            try {
                if (st.steps.audio!=='done') {
                    setStep('step-audio','running','提取音频中...');
                    setStepProgress('step-audio',0,'提取音频中...');
                    const r = await fetch('/api/process/'+tid+'/audio',{method:'POST'});
                    const d = await r.json();
                    if (d.error) throw new Error(d.error);
                    setStep('step-audio','done',d.message);
                }
                if (st.steps.transcribe!=='done') {
                    setStep('step-transcribe','running','语音识别中...');
                    setStepProgress('step-transcribe',0,'语音识别中...');
                    const r = await fetch('/api/process/'+tid+'/transcribe',{method:'POST'});
                    const d = await r.json();
                    if (d.error) throw new Error(d.error);
                    setStep('step-transcribe','done',d.message);
                }
                if (st.steps.translate!=='done' && st.steps.translate!=='skip') {
                    setStep('step-translate','running','翻译中...');
                    setStepProgress('step-translate',0,'翻译中...');
                    const r = await fetch('/api/process/'+tid+'/translate',{method:'POST'});
                    const d = await r.json();
                    if (d.error) throw new Error(d.error);
                    setStep('step-translate','done',d.message);
                }
                if (st.steps.subtitle!=='done') {
                    setStep('step-subtitle','running','生成字幕文件...');
                    const r = await fetch('/api/process/'+tid+'/subtitle',{method:'POST'});
                    const d = await r.json();
                    if (d.error) throw new Error(d.error);
                    setStep('step-subtitle','done', d.message || '完成');
                }
                stopProgressPolling();
                btn.textContent = '✅ 处理完成';
                const taskName = localStorage.getItem('active_task_name') || st.file_name || '';
                localStorage.removeItem('active_task_id');
                localStorage.removeItem('active_task_name');
                saveTaskToHistory(tid, taskName);
                showResults(tid);
            } catch (e) {
                stopProgressPolling();
                localStorage.removeItem('active_task_id');
                localStorage.removeItem('active_task_name');
                alert('处理出错: '+e.message);
                btn.disabled = false; btn.textContent = '重新处理';
            }
        }

        // ──── Settings ────
        const PRESETS = {
            local: { api_base: 'http://127.0.0.1:8080/v1', chat_path: '/chat/completions', model: '' },
            minimax: { api_base: 'https://api.minimaxi.com/v1', chat_path: '/chat/completions', model: 'MiniMax-M2.7' },
            deepseek: { api_base: 'https://api.deepseek.com/v1', chat_path: '/chat/completions', model: 'deepseek-chat' },
            openai: { api_base: 'https://api.openai.com/v1', chat_path: '/chat/completions', model: 'gpt-4o-mini' },
        };
        function populateModelSelect(selectId, options, currentValue, currentMeta) {
            const select = document.getElementById(selectId);
            if (!select) return;
            const normalizedCurrent = currentValue ?? '';
            select.innerHTML = '';
            let hasCurrent = normalizedCurrent === '';
            for (const item of (options || [])) {
                const opt = document.createElement('option');
                opt.value = item.value ?? '';
                opt.textContent = item.label || item.value || '未命名模型';
                if (item.detail) opt.title = item.detail;
                select.appendChild(opt);
                if (opt.value === normalizedCurrent) {
                    hasCurrent = true;
                }
            }
            if (!hasCurrent && normalizedCurrent) {
                const extra = document.createElement('option');
                extra.value = normalizedCurrent;
                extra.textContent = '当前配置: ' + normalizedCurrent.split('/').pop();
                select.appendChild(extra);
            }
            select.value = normalizedCurrent;
        }
        async function loadModelOptions(cfg) {
            try {
                const r = await fetch('/api/model_options');
                const data = await r.json();
                const current = cfg || data.current || {};
                populateModelSelect('cfg-whisper-model-path', data.whisper?.faster || [], current.whisper?.model_path ?? 'bundled');
                populateModelSelect('cfg-llm-model-path', data.llm?.local || [], current.llm?.model_path ?? '');
            } catch (e) {
                console.error('loadModelOptions:', e);
            }
        }
        async function refreshRuntimeLog() {
            try {
                const r = await fetch('/api/runtime_log?lines=200');
                const text = await r.text();
                document.getElementById('runtime-log').textContent = text || '暂无日志';
            } catch (e) {
                document.getElementById('runtime-log').textContent = '读取日志失败: ' + e.message;
            }
        }
        function highlightPreset() {
            const base = document.getElementById('cfg-llm-api-base').value.replace(/\/+$/, '');
            document.querySelectorAll('.preset-btn').forEach(b => {
                b.style.background = '#2a2a2a'; b.style.borderColor = '#555'; b.style.color = '#ccc';
            });
            for (const [k, v] of Object.entries(PRESETS)) {
                if (base === v.api_base.replace(/\/+$/, '')) {
                    const btn = document.getElementById('preset-' + k);
                    if (btn) { btn.style.background = '#667eea33'; btn.style.borderColor = '#667eea'; btn.style.color = '#99aaff'; }
                    break;
                }
            }
        }
        function applyPreset(name) {
            const p = PRESETS[name];
            if (!p) return;
            document.getElementById('cfg-llm-api-base').value = p.api_base;
            document.getElementById('cfg-llm-chat-path').value = p.chat_path;
            document.getElementById('cfg-llm-model').value = p.model;
            // 切换到内置模型时清空 key，切换到外部时保留已有 key
            if (name === 'local') {
                document.getElementById('cfg-llm-api-key').value = '';
            }
            highlightPreset();
            // 自动保存
            saveSettings();
        }
        function toggleSettings() {
            const p = document.getElementById('settings-panel');
            if (p.style.display === 'none') {
                p.style.display = 'block';
                loadSettings();
            } else {
                p.style.display = 'none';
            }
        }
        async function loadSettings() {
            try {
                const r = await fetch('/api/settings');
                const cfg = await r.json();
                document.getElementById('cfg-llm-api-base').value = cfg.llm?.api_base || '';
                document.getElementById('cfg-llm-chat-path').value = cfg.llm?.chat_path || '';
                document.getElementById('cfg-llm-api-key').value = cfg.llm?.api_key || '';
                document.getElementById('cfg-llm-model').value = cfg.llm?.model || '';
                document.getElementById('cfg-frame-interval').value = cfg.app?.frame_interval || 60;
                await loadModelOptions(cfg);
                await refreshRuntimeLog();
                highlightPreset();
            } catch(e) { console.error('loadSettings:', e); }
        }
        async function saveSettings() {
            const llmSelect = document.getElementById('cfg-llm-model-path');
            const body = {
                llm: {
                    api_base: document.getElementById('cfg-llm-api-base').value,
                    chat_path: document.getElementById('cfg-llm-chat-path').value,
                    api_key: document.getElementById('cfg-llm-api-key').value,
                    model: document.getElementById('cfg-llm-model').value,
                    model_path: llmSelect?.value || '',
                },
                whisper: {
                    model_path: document.getElementById('cfg-whisper-model-path').value || 'bundled',
                },
                app: {
                    frame_interval: parseInt(document.getElementById('cfg-frame-interval').value) || 60,
                }
            };
            try {
                const r = await fetch('/api/settings', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(body)});
                const data = await r.json();
                const msg = document.getElementById('settings-msg');
                msg.textContent = '✓ ' + (data.message || '已保存');
                setTimeout(() => msg.textContent = '', 3000);
                await loadModelOptions(data.config);
                await refreshRuntimeLog();
                checkServices();
            } catch(e) { alert('保存失败: ' + e.message); }
        }

        checkServices();
        setInterval(checkServices, 15000);
        renderHistory();
        restoreActiveTask();
    </script>
</body>
</html>
"""

# ========== 任务管理 ==========
tasks = {}
_whisper_model = None  # Whisper 模型全局单例，避免重复加载
_whisper_model_key = None
_RUNTIME_LOG_DIR = Path('/tmp/llm-logs')
_RUNTIME_LOG_FILE = _RUNTIME_LOG_DIR / 'video_subtitle.log'
_SPLIT_GGUF_RE = re.compile(r'-\d{5}-of-\d{5}\.gguf$', re.IGNORECASE)


def _append_runtime_log(tag, message):
    try:
        _RUNTIME_LOG_DIR.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        with _RUNTIME_LOG_FILE.open('a', encoding='utf-8') as f:
            f.write(f'[{timestamp}] [{tag}] {message}\n')
    except Exception:
        pass


def _append_runtime_exception(tag, context, exc):
    detail = ''.join(traceback.format_exception(type(exc), exc, exc.__traceback__)).strip()
    _append_runtime_log(tag, f"{context}\n{detail}")


def _classify_whisper_model_source(model_path):
    bundled_dir = get_bundled_dir()
    if bundled_dir:
        bundled_models_dir = os.path.join(bundled_dir, "models")
        if model_path.startswith(bundled_models_dir):
            return "内置模型"
    if "/bundled/models/" in model_path:
        return "内置模型"
    if os.path.exists(model_path):
        return "本地路径"
    return "HuggingFace"


def _display_model_name(model_value, empty_label="未指定模型"):
    if not model_value:
        return empty_label
    model_value = str(model_value).strip()
    if not model_value:
        return empty_label
    return os.path.basename(model_value.rstrip('/')) or model_value


def _reset_whisper_runtime(reason):
    global _whisper_model, _whisper_model_key
    _whisper_model = None
    _whisper_model_key = None
    _append_runtime_log("Whisper", f"reset reason={reason}")


def _iter_local_gguf_files(root_dir):
    if not root_dir or not os.path.isdir(root_dir):
        return
    for current_root, dirnames, filenames in os.walk(root_dir):
        dirnames[:] = [name for name in dirnames if not name.startswith('.')]
        for filename in sorted(filenames):
            if not filename.lower().endswith('.gguf'):
                continue
            if _SPLIT_GGUF_RE.search(filename):
                continue
            yield os.path.join(current_root, filename)


def _append_option(options, seen, value, label, detail="", **extra):
    if value in seen:
        return
    option = {"value": value, "label": label}
    if detail:
        option["detail"] = detail
    for key, extra_value in extra.items():
        if extra_value not in (None, ""):
            option[key] = extra_value
    options.append(option)
    seen.add(value)


def _get_bundled_models_dirs():
    result = []
    bundled = get_bundled_dir()
    if bundled:
        candidate = os.path.join(bundled, 'models')
        if os.path.isdir(candidate):
            result.append(candidate)
    dev_candidate = os.path.join(os.path.dirname(__file__), 'bundled', 'models')
    if os.path.isdir(dev_candidate):
        result.append(dev_candidate)
    return result


def _discover_whisper_model_options():
    faster = []
    faster_seen = set()
    resolved_faster = get_whisper_model_path()

    _append_option(faster, faster_seen, 'bundled', '自动使用内置 faster-whisper 模型', detail=resolved_faster)
    _append_option(faster, faster_seen, 'deepdml/faster-whisper-large-v3-turbo-ct2', 'HuggingFace: deepdml/faster-whisper-large-v3-turbo-ct2')

    cfg = load_config()
    faster_current = cfg.get('whisper', {}).get('model_path', 'bundled')
    if faster_current and faster_current != 'bundled':
        _append_option(faster, faster_seen, faster_current, f"当前配置: {_display_model_name(faster_current)}", detail=faster_current)

    for models_dir in _get_bundled_models_dirs():
        for entry in sorted(os.listdir(models_dir)):
            path = os.path.join(models_dir, entry)
            if not os.path.isdir(path):
                continue
            lower_name = entry.lower()
            if 'whisper' not in lower_name or 'mlx' in lower_name:
                continue
            _append_option(faster, faster_seen, path, f"本地 faster-whisper: {entry}", detail=path)

    return {'faster': faster}


def _discover_local_model_options():
    """扫描本地所有可用文本 GGUF 模型"""
    mgr = get_llm_manager()
    options = []
    seen = set()
    _append_option(options, seen, '', '自动选择默认模型')
    cfg = load_config()
    current = cfg.get('llm', {}).get('model_path', '')
    if current and 'qwen2-vl' not in current.lower() and 'mmproj' not in current.lower():
        _append_option(options, seen, current, f"当前配置: {_display_model_name(current)}", detail=current)

    for path in _iter_local_gguf_files(mgr._model_dir):
        filename = os.path.basename(path).lower()
        if 'mmproj' in filename or 'embed' in filename or 'qwen2-vl' in filename:
            continue
        label = os.path.basename(path)
        detail = os.path.relpath(path, mgr._model_dir)
        _append_option(options, seen, path, label, detail=detail)
    return options


def _get_whisper_runtime_summary():
    backend = get_whisper_backend()
    model_path = get_whisper_model_path()
    summary = {
        "backend": backend,
        "model_path": model_path,
        "model_source": _classify_whisper_model_source(model_path),
        "model_name": os.path.basename(model_path.rstrip('/')) or model_path,
    }
    device, compute_type = get_whisper_device_config()
    summary["device"] = device
    summary["compute_type"] = compute_type
    return summary


def _get_whisper_status_payload():
    summary = _get_whisper_runtime_summary()
    backend = summary["backend"]
    model_source = summary["model_source"]
    model_name = summary["model_name"]
    label_backend = "faster-whisper"

    device = summary["device"]
    compute_type = summary["compute_type"]
    try:
        from faster_whisper import WhisperModel  # noqa: F401
        return {
            "ok": True,
            "text": f"就绪 · {label_backend} · {model_source}",
            "detail": f"backend=faster-whisper; source={model_source}; model={model_name}; device={device}; compute={compute_type}",
        }
    except Exception as exc:
        return {
            "ok": False,
            "text": f"离线 · {label_backend} · {model_source}",
            "detail": f"backend=faster-whisper; source={model_source}; model={model_name}; device={device}; compute={compute_type}; error={type(exc).__name__}",
        }


def _dir_size_mb(path):
    """计算目录大小 (MB)"""
    total = 0
    for f in Path(path).rglob('*'):
        if f.is_file():
            total += f.stat().st_size
    return total / (1024 * 1024)


def _cleanup_old_files():
    """滚动清理：按修改时间删除最旧的文件，直到满足空间和数量限制"""
    # 收集所有任务文件，按修改时间排序
    all_files = []
    for d in (UPLOAD_DIR, OUTPUT_DIR):
        for f in Path(d).iterdir():
            if f.is_file():
                all_files.append(f)
    all_files.sort(key=lambda f: f.stat().st_mtime)

    # 按 task_id 分组 (文件名格式: {task_id}_xxx)
    from collections import OrderedDict
    task_groups = OrderedDict()
    for f in all_files:
        tid = f.name.split('_')[0] if '_' in f.name else f.name
        task_groups.setdefault(tid, []).append(f)

    # 按数量限制清理
    while len(task_groups) > MAX_TASK_COUNT:
        oldest_tid, files = task_groups.popitem(last=False)
        for f in files:
            f.unlink(missing_ok=True)
        tasks.pop(oldest_tid, None)

    # 按空间限制清理
    while _dir_size_mb(UPLOAD_DIR) + _dir_size_mb(OUTPUT_DIR) > MAX_STORAGE_MB and task_groups:
        oldest_tid, files = task_groups.popitem(last=False)
        for f in files:
            f.unlink(missing_ok=True)
        tasks.pop(oldest_tid, None)


def _is_external_api():
    """判断是否配置了外部 API（非本地 llama-server）"""
    cfg = load_config()
    api_base = cfg["llm"]["api_base"].rstrip("/")
    # 本地 llama-server 的默认地址
    return not api_base.startswith("http://127.0.0.1:8080") and not api_base.startswith("http://localhost:8080")


def _is_minimax_external_api(config=None):
    """当前是否使用 MiniMax OpenAI 兼容外部接口。"""
    if config is None:
        config = load_config()
    api_base = (config.get("llm", {}).get("api_base", "") or "").rstrip("/").lower()
    model_name = (config.get("llm", {}).get("model", "") or "").strip().lower()
    is_local = api_base.startswith("http://127.0.0.1:8080") or api_base.startswith("http://localhost:8080")
    if is_local:
        return False
    return "minimaxi.com" in api_base or model_name.startswith("minimax-")


def _resolve_translation_request_options(body):
    """根据请求体和当前 provider 决定翻译策略默认值。"""
    config = load_config()
    use_minimax_bulk = _is_minimax_external_api(config)
    strategy_value = (body.get("strategy") or "").strip().lower()
    if strategy_value not in {"batch", "bulk"}:
        strategy_value = "bulk" if use_minimax_bulk else "batch"

    batch_size = _normalize_translation_limit(body.get("batch_size"), TRANSLATE_BATCH_SIZE, minimum=1, maximum=64)
    max_items_default = MINIMAX_BULK_MAX_ITEMS if use_minimax_bulk else TRANSLATE_BULK_MAX_ITEMS
    max_chars_default = MINIMAX_BULK_MAX_CHARS if use_minimax_bulk else TRANSLATE_BULK_MAX_CHARS
    max_items = _normalize_translation_limit(body.get("max_items"), max_items_default, minimum=1, maximum=200)
    max_chars = _normalize_translation_limit(body.get("max_chars"), max_chars_default, minimum=200, maximum=20000)
    return strategy_value, batch_size, max_items, max_chars


def _ensure_llm():
    """确保 LLM 服务运行，返回是否就绪（推理入口专用：按需启动）"""
    # 外部 API 不需要启动本地 llama-server
    if _is_external_api():
        return True
    mgr = get_llm_manager()
    if mgr.ensure_running_for_inference():
        # 动态更新 URL 指向本地管理的服务
        global LLM_URL
        LLM_URL = mgr.get_chat_url()
        return True
    return False


def _llm_inference_guard():
    """推理计数守卫：在 _ensure_llm 之后调用，返回后在 finally 中释放"""
    if not _is_external_api():
        get_llm_manager().acquire_inference()

def _llm_inference_done():
    """推理结束释放计数"""
    if not _is_external_api():
        get_llm_manager().release_inference()


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
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return json.loads(response.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        body = ""
        try:
            body = e.read().decode('utf-8')
        except Exception:
            pass
        _append_runtime_log("HTTP", f"post-failed url={url} model={data.get('model', '') or 'default'} status={e.code} body={body[:1200]}")
        raise RuntimeError(f"HTTP {e.code}: {body[:300]}") from e
    except Exception as exc:
        _append_runtime_exception("HTTP", f"post-exception url={url} model={data.get('model', '') or 'default'}", exc)
        raise


def format_time(seconds):
    """将秒数转换为 SRT 时间格式 HH:MM:SS,mmm"""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int((seconds % 1) * 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _normalize_translation_limit(value, default, minimum=1, maximum=None):
    try:
        normalized = int(value)
    except (TypeError, ValueError):
        normalized = default
    normalized = max(minimum, normalized)
    if maximum is not None:
        normalized = min(maximum, normalized)
    return normalized


def _build_translation_windows(text_list, batch_size, strategy, max_items, max_chars):
    if strategy != "bulk":
        return [text_list[i:i + batch_size] for i in range(0, len(text_list), batch_size)]

    windows = []
    current = []
    current_chars = 0
    for text in text_list:
        text = text or ""
        estimated_chars = len(text) + 12
        should_flush = current and (
            len(current) >= max_items or current_chars + estimated_chars > max_chars
        )
        if should_flush:
            windows.append(current)
            current = []
            current_chars = 0
        current.append(text)
        current_chars += estimated_chars

    if current:
        windows.append(current)
    return windows


def _build_translation_prompt(batch, src_name, tgt_name):
    numbered = "\n".join(f"{j + 1}. {t}" for j, t in enumerate(batch))
    return f"""Translate the following {src_name} subtitles into {tgt_name}. Keep it concise and natural for subtitles. Output only the translations, one per line, numbered.

{len(batch)} subtitles:
{numbered}

{tgt_name} translations (numbered, one per line):"""


def _estimate_translation_max_tokens(batch):
    estimated_chars = sum(len(text or "") for text in batch)
    estimated_tokens = int(estimated_chars * 1.6) + len(batch) * 24
    return max(256, min(4096, estimated_tokens))


def _request_translation_batch(batch, src_name, tgt_name):
    prompt = _build_translation_prompt(batch, src_name, tgt_name)
    req_data = {
        "messages": [
            {"role": "system", "content": f"You are a professional subtitle translator. Translate {src_name} to {tgt_name}. Be concise and natural."},
            {"role": "user", "content": prompt}
        ],
        "stream": False,
        "temperature": 0.3,
        "max_tokens": _estimate_translation_max_tokens(batch),
    }
    model_name = get_llm_model()
    if model_name:
        req_data["model"] = model_name
    result = post_json(LLM_URL, req_data, api_key=get_llm_api_key())
    response = result.get("choices", [{}])[0].get("message", {}).get("content", "")
    response = re.sub(r'<think>.*?</think>', '', response, flags=re.DOTALL).strip()
    lines = response.strip().split('\n')

    parsed = []
    for line in lines:
        line = line.strip()
        line = re.sub(r'^\d+[\.、\:\：\)）]?\s*', '', line)
        if line:
            parsed.append(line)

    translations = []
    for idx, text in enumerate(batch):
        if idx < len(parsed):
            translations.append(parsed[idx])
        else:
            translations.append(f"[翻译失败] {text}")
    return translations


def translate_batch(text_list, source_lang, target_lang, batch_size=TRANSLATE_BATCH_SIZE,
                    task=None, strategy="batch", max_items=TRANSLATE_BULK_MAX_ITEMS,
                    max_chars=TRANSLATE_BULK_MAX_CHARS):
    _ensure_llm()
    _llm_inference_guard()
    try:
        return _translate_batch_impl(
            text_list,
            source_lang,
            target_lang,
            batch_size,
            task,
            strategy=strategy,
            max_items=max_items,
            max_chars=max_chars,
        )
    finally:
        _llm_inference_done()

def _translate_batch_impl(text_list, source_lang, target_lang, batch_size=TRANSLATE_BATCH_SIZE,
                          task=None, strategy="batch", max_items=TRANSLATE_BULK_MAX_ITEMS,
                          max_chars=TRANSLATE_BULK_MAX_CHARS):
    """使用 LLM 批量翻译文本"""
    src_name = LANGUAGE_NAMES_EN.get(source_lang, source_lang)
    tgt_name = LANGUAGE_NAMES_EN.get(target_lang, target_lang)
    batch_size = _normalize_translation_limit(batch_size, TRANSLATE_BATCH_SIZE, minimum=1, maximum=64)
    max_items = _normalize_translation_limit(max_items, TRANSLATE_BULK_MAX_ITEMS, minimum=1, maximum=200)
    max_chars = _normalize_translation_limit(max_chars, TRANSLATE_BULK_MAX_CHARS, minimum=200, maximum=20000)
    strategy = "bulk" if strategy == "bulk" else "batch"

    translations = []
    total = len(text_list)
    windows = _build_translation_windows(text_list, batch_size, strategy, max_items, max_chars)
    total_batches = max(1, len(windows))
    if task is not None:
        task["translate_stats"] = {
            "strategy": strategy,
            "batch_size": batch_size,
            "window_count": total_batches,
            "max_items": max_items,
            "max_chars": max_chars,
        }

    done_count = 0
    for batch_idx, batch in enumerate(windows):

        try:
            translations.extend(_request_translation_batch(batch, src_name, tgt_name))

        except Exception as e:
            import traceback
            traceback.print_exc()
            err_msg = str(e)[:100]
            for t in batch:
                translations.append(f"[翻译失败: {err_msg}] {t}")

        done_count += len(batch)
        if task:
            pct = min(99, int((batch_idx + 1) / total_batches * 100))
            detail_prefix = "整批翻译" if strategy == "bulk" else "翻译中"
            task["progress"] = {"step": "translate", "percent": pct, "detail": f"{detail_prefix} {done_count}/{total} 段"}

    return translations


def write_srt(segments, texts, path):
    """写入 SRT 字幕文件"""
    with open(path, 'w', encoding='utf-8') as f:
        for i, (seg, text) in enumerate(zip(segments, texts), 1):
            start = format_time(seg['start'])
            end = format_time(seg['end'])
            f.write(f"{i}\n{start} --> {end}\n{text}\n\n")


def write_bilingual_srt(segments, texts_top, texts_bottom, path):
    """写入双语 SRT 字幕文件"""
    with open(path, 'w', encoding='utf-8') as f:
        for i, (seg, top, bot) in enumerate(zip(segments, texts_top, texts_bottom), 1):
            start = format_time(seg['start'])
            end = format_time(seg['end'])
            f.write(f"{i}\n{start} --> {end}\n{top}\n{bot}\n\n")


# ========== API 路由 ==========

@app.get("/")
async def root():
    return HTMLResponse(HTML_PAGE, headers={"Cache-Control": "no-cache, no-store, must-revalidate", "Pragma": "no-cache"})


@app.get("/api/check_services")
async def check_services():
    whisper_ok = False
    whisper_detail = ""
    whisper_text = "检测中"
    llm_ok = False
    llm_detail = ""
    llm_text = "检测中"

    whisper_status = _get_whisper_status_payload()
    whisper_ok = whisper_status["ok"]
    whisper_detail = whisper_status["detail"]
    whisper_text = whisper_status["text"]

    def _check_http_ok(url, api_key=""):
        try:
            import urllib.request
            headers = {"Accept": "application/json"}
            if api_key:
                headers["Authorization"] = f"Bearer {api_key}"
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=5) as resp:
                return resp.status == 200
        except Exception:
            return False

    def _check_services():
        cfg = load_config()
        api_base = cfg["llm"]["api_base"].rstrip("/")
        api_key = cfg["llm"].get("api_key", "")

        if _is_external_api():
            models_ok = _check_http_ok(api_base + "/models", api_key)
            llm_ready = models_ok or bool(api_base and api_key)
            llm_model_name = _display_model_name(cfg["llm"].get("model", ""), "服务默认模型")
            llm_reason = f"{('external-models-ok' if models_ok else ('external-configured' if llm_ready else 'external-missing-config'))}; model={llm_model_name}; base={api_base or 'n/a'}"
            llm_text = f"{('就绪' if llm_ready else '离线')} · {llm_model_name}"
            return llm_ready, llm_reason, llm_text, False

        mgr = get_llm_manager()
        ok, reason, text, external_conflict = mgr.get_check_services_status()
        return ok, reason, text, external_conflict

    llm_ok, llm_detail, llm_text, external_conflict = await asyncio.to_thread(_check_services)

    return {
        "whisper": whisper_ok,
        "whisper_detail": whisper_detail,
        "whisper_text": whisper_text,
        "llm": llm_ok,
        "llm_detail": llm_detail,
        "llm_text": llm_text,
        "external_api": _is_external_api(),
        "external_conflict": external_conflict,
    }


@app.get("/api/progress/{task_id}")
async def get_progress(task_id: str):
    """获取任务当前进度"""
    task = tasks.get(task_id)
    if not task:
        return {"step": "", "percent": 0, "detail": "任务不存在"}
    return task.get("progress", {"step": "", "percent": 0, "detail": ""})


@app.get("/api/task_status/{task_id}")
async def task_status(task_id: str):
    """获取任务完整状态，用于页面刷新后恢复"""
    if task_id not in tasks:
        return {"exists": False}
    task = tasks[task_id]
    steps = {"upload": "done"}

    if task["audio_path"] and os.path.exists(task["audio_path"]):
        steps["audio"] = "done"
    elif task.get("progress", {}).get("step") == "audio":
        steps["audio"] = "running"
    else:
        steps["audio"] = "pending"

    if task["source_texts"] is not None:
        steps["transcribe"] = "done"
    elif task.get("progress", {}).get("step") == "transcribe":
        steps["transcribe"] = "running"
    else:
        steps["transcribe"] = "pending"

    if task["mode"] != "translate":
        steps["translate"] = "skip"
    elif task["translated_texts"] is not None:
        steps["translate"] = "done"
    elif task.get("progress", {}).get("step") == "translate":
        steps["translate"] = "running"
    else:
        steps["translate"] = "pending"

    if task.get("results"):
        steps["subtitle"] = "done"
    elif task.get("progress", {}).get("step") == "subtitle":
        steps["subtitle"] = "running"
    else:
        steps["subtitle"] = "pending"

    steps["frames"] = "skip"

    return {
        "exists": True,
        "steps": steps,
        "progress": task.get("progress", {}),
        "completed": steps.get("subtitle") == "done",
        "mode": task["mode"],
        "file_name": Path(task["video_path"]).name,
    }


ALLOWED_EXT = {'.mp4', '.mkv', '.avi', '.mov', '.wmv', '.webm', '.flv', '.mp3', '.wav', '.m4a', '.flac', '.ogg'}


@app.post("/api/local_file")
async def local_file(req: dict):
    """本地路径模式：直接读取本地文件，不复制"""
    file_path = req.get("path", "").strip()
    source_lang = req.get("source_lang", "auto")
    target_lang = req.get("target_lang", "zh")
    mode = req.get("mode", "translate")
    if not file_path:
        return {"error": "请输入文件路径"}

    # 验证参数
    if source_lang not in LANGUAGES:
        return {"error": f"不支持的源语言: {source_lang}"}
    if target_lang not in LANGUAGES or target_lang == "auto":
        return {"error": f"不支持的目标语言: {target_lang}"}
    if mode not in ("translate", "transcribe"):
        return {"error": f"不支持的模式: {mode}"}

    # 规范化路径，防止路径注入
    file_path = os.path.realpath(file_path)
    if not os.path.isfile(file_path):
        return {"error": f"文件不存在: {file_path}"}

    ext = Path(file_path).suffix.lower()
    if ext not in ALLOWED_EXT:
        return {"error": f"不支持的文件格式: {ext}"}

    task_id = uuid.uuid4().hex[:8]

    tasks[task_id] = {
        "video_path": file_path,
        "audio_path": None,
        "segments": None,
        "source_lang": source_lang,
        "detected_lang": None,
        "target_lang": target_lang,
        "mode": mode,
        "source_texts": None,
        "translated_texts": None,
        "results": {},
        "created_at": time.time(),
        "is_local": True,
        "enable_frames": False,
        "frame_descriptions": None,
        "video_summary": None,
        "progress": {"step": "", "percent": 0, "detail": ""},
    }

    file_size = os.path.getsize(file_path)
    size_str = f"{file_size / (1024*1024):.1f} MB" if file_size < 1073741824 else f"{file_size / (1024*1024*1024):.2f} GB"
    return {"task_id": task_id, "message": f"文件就绪: {Path(file_path).name} ({size_str})"}


@app.post("/api/upload")
async def upload(
    file: UploadFile = File(...),
    source_lang: str = Form("auto"),
    target_lang: str = Form("zh"),
    mode: str = Form("translate"),
):
    # 验证参数
    if source_lang not in LANGUAGES:
        return {"error": f"不支持的源语言: {source_lang}"}
    if target_lang not in LANGUAGES or target_lang == "auto":
        return {"error": f"不支持的目标语言: {target_lang}"}
    if mode not in ("translate", "transcribe"):
        return {"error": f"不支持的模式: {mode}"}

    # 验证文件类型
    ext = Path(file.filename).suffix.lower()
    if ext not in ALLOWED_EXT:
        return {"error": f"不支持的文件格式: {ext}"}

    # 滚动清理旧文件
    _cleanup_old_files()

    task_id = uuid.uuid4().hex[:8]

    # 安全文件名
    safe_name = re.sub(r'[^\w\-\.]', '_', file.filename)
    video_path = os.path.join(UPLOAD_DIR, f"{task_id}_{safe_name}")

    with open(video_path, "wb") as f:
        while True:
            chunk = await file.read(1024 * 1024)
            if not chunk:
                break
            f.write(chunk)

    tasks[task_id] = {
        "video_path": video_path,
        "audio_path": None,
        "segments": None,
        "source_lang": source_lang,
        "detected_lang": None,
        "target_lang": target_lang,
        "mode": mode,
        "source_texts": None,
        "translated_texts": None,
        "results": {},
        "created_at": time.time(),
        "enable_frames": False,
        "frame_descriptions": None,
        "video_summary": None,
        "progress": {"step": "", "percent": 0, "detail": ""},
    }

    return {"task_id": task_id, "message": "上传成功"}


def _get_duration(video_path):
    """获取视频/音频时长(秒)"""
    try:
        r = subprocess.run(
            [FFPROBE, "-v", "quiet", "-show_entries", "format=duration",
             "-of", "csv=p=0", video_path],
            capture_output=True, text=True, timeout=30,
        )
        return float(r.stdout.strip())
    except Exception:
        return 0


def _run_ffmpeg_with_progress(task, video_path, audio_path, duration):
    """运行 FFmpeg 提取音频并更新进度"""
    cmd = [
        FFMPEG, "-y", "-i", video_path,
        "-vn", "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1",
        "-progress", "pipe:1", "-nostats",
        audio_path,
    ]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    # 使用 readline() 代替迭代器，避免 Python 内部缓冲导致进度更新延迟
    import time as _time
    _start_time = _time.monotonic()
    while True:
        line = proc.stdout.readline()
        if not line:
            break
        line = line.strip()
        if line.startswith("out_time_us="):
            try:
                us = int(line.split("=")[1])
                elapsed = int(_time.monotonic() - _start_time)
                if duration > 0 and us > 0:
                    pct = max(1, min(99, int(us / (duration * 1_000_000) * 100)))
                    processed_min = us / 60_000_000
                    total_min = duration / 60
                    task["progress"] = {"step": "audio", "percent": pct, "detail": f"提取音频中 {processed_min:.1f}/{total_min:.0f}分钟 ({pct}%) 已用时{elapsed}s"}
                elif us > 0:
                    task["progress"] = {"step": "audio", "percent": 0, "detail": f"提取音频中... 已用时 {elapsed}s"}
            except (ValueError, ZeroDivisionError):
                pass
    proc.wait(timeout=600)
    if proc.returncode != 0:
        stderr = proc.stderr.read()
        raise RuntimeError(stderr[:300])


@app.post("/api/process/{task_id}/audio")
async def step_audio(task_id: str):
    if task_id not in tasks:
        return {"error": "任务不存在"}

    task = tasks[task_id]

    # 幂等：已完成直接返回
    if task["audio_path"] and os.path.exists(task["audio_path"]):
        return {"message": "音频已提取"}
    # 正在处理：等待完成
    if task.get("_proc_audio"):
        while task.get("_proc_audio"):
            await asyncio.sleep(0.5)
        if task["audio_path"] and os.path.exists(task["audio_path"]):
            return {"message": "音频已提取"}
        return {"error": "音频提取失败"}

    task["_proc_audio"] = True
    task["progress"] = {"step": "audio", "percent": 0, "detail": "获取视频信息..."}
    video_path = task["video_path"]
    audio_path = os.path.join(OUTPUT_DIR, f"{task_id}_audio.wav")

    duration = await asyncio.to_thread(_get_duration, video_path)
    task["progress"] = {"step": "audio", "percent": 0, "detail": "提取音频中..."}

    try:
        await asyncio.to_thread(_run_ffmpeg_with_progress, task, video_path, audio_path, duration)
    except Exception as e:
        task["_proc_audio"] = False
        return {"error": f"音频提取失败: {str(e)[:200]}"}

    task["audio_path"] = audio_path
    task["progress"] = {"step": "audio", "percent": 100, "detail": "音频提取完成"}
    task["_proc_audio"] = False
    return {"message": "音频提取完成"}


CHUNK_DURATION = 600  # 每块 10 分钟，控制内存


def _get_audio_duration(audio_path):
    """获取音频文件时长（秒）"""
    import wave
    try:
        with wave.open(audio_path, 'r') as wf:
            return wf.getnframes() / wf.getframerate()
    except Exception:
        return 0


def _split_audio_chunks(audio_path, chunk_dur=CHUNK_DURATION):
    """将长音频拆分为多个小块文件，返回 [(chunk_path, offset)] 列表"""
    import wave
    duration = _get_audio_duration(audio_path)
    if duration <= 0:
        return [(audio_path, 0.0)]

    # 短音频无需拆分
    if duration <= chunk_dur * 1.5:
        return [(audio_path, 0.0)]

    chunks = []
    base = audio_path.rsplit('.', 1)[0]

    with wave.open(audio_path, 'r') as wf:
        sr = wf.getframerate()
        nch = wf.getnchannels()
        sw = wf.getsampwidth()
        total_frames = wf.getnframes()
        chunk_frames = int(chunk_dur * sr)

        offset = 0
        idx = 0
        while offset < total_frames:
            end = min(offset + chunk_frames, total_frames)
            wf.setpos(offset)
            data = wf.readframes(end - offset)

            chunk_path = f"{base}_chunk{idx:03d}.wav"
            with wave.open(chunk_path, 'w') as out:
                out.setnchannels(nch)
                out.setsampwidth(sw)
                out.setframerate(sr)
                out.writeframes(data)

            chunks.append((chunk_path, offset / sr))
            offset = end
            idx += 1
            del data  # 立即释放内存

    return chunks


def _load_whisper_model(task=None):
    summary = _get_whisper_runtime_summary()
    backend = summary["backend"]
    try:
        model_path = summary["model_path"]
        device = summary["device"]
        compute_type = summary["compute_type"]
        if task:
            task["progress"] = {"step": "transcribe", "percent": 0, "detail": "加载模型中..."}
        print(f"[Whisper] 加载模型: {model_path}, backend={backend}, device={device}, compute={compute_type}")
        _append_runtime_log("Whisper", f"load backend=faster-whisper source={summary['model_source']} model={summary['model_name']} path={model_path} device={device} compute={compute_type}")
        from faster_whisper import WhisperModel
        return WhisperModel(model_path, device=device, compute_type=compute_type), (backend, model_path, device, compute_type)
    except Exception as exc:
        _append_runtime_exception("Whisper", f"load-failed backend={backend} model={summary['model_name']} path={summary['model_path']}", exc)
        raise


def _run_transcribe(audio_path, source_lang, task=None):
    """CPU 密集型 Whisper 转录 - 分块处理以控制内存"""
    global _whisper_model, _whisper_model_key
    import gc

    # 全局单例，避免每次加载模型占用大量内存
    expected_backend = get_whisper_backend()
    model_path = get_whisper_model_path()
    device, compute_type = get_whisper_device_config()
    expected_key = (expected_backend, model_path, device, compute_type)

    if _whisper_model is None or _whisper_model_key != expected_key:
        _whisper_model, _whisper_model_key = _load_whisper_model(task)

    # 拆分长音频为小块
    if task:
        task["progress"] = {"step": "transcribe", "percent": 0, "detail": "准备音频分块..."}
    chunks = _split_audio_chunks(audio_path)
    total_chunks = len(chunks)

    if task:
        detail = f"共 {total_chunks} 块" if total_chunks > 1 else "开始识别..."
        task["progress"] = {"step": "transcribe", "percent": 1, "detail": detail}

    lang_param = source_lang if source_lang != "auto" else None
    detected_info = None
    result = []

    for ci, (chunk_path, time_offset) in enumerate(chunks):
        if task:
            pct = max(1, int(ci / total_chunks * 95))
            task["progress"] = {"step": "transcribe", "percent": pct,
                               "detail": f"识别第 {ci+1}/{total_chunks} 块..."}

        try:
            segments, info = _whisper_model.transcribe(
                chunk_path,
                vad_filter=True,
                vad_parameters=dict(min_silence_duration_ms=500),
                language=lang_param,
            )
        except Exception as exc:
            _append_runtime_exception("Whisper", f"transcribe-failed chunk={ci+1}/{total_chunks} audio={chunk_path} backend={expected_backend}", exc)
            raise

        if detected_info is None:
            detected_info = info
            # 第一块检测到语言后锁定，避免后续块检测错误
            if lang_param is None and info.language:
                lang_param = info.language

        for seg in segments:
            result.append({
                "start": seg.start + time_offset,
                "end": seg.end + time_offset,
                "text": seg.text.strip()
            })

        # 清理分块临时文件（保留原始完整文件）
        if chunk_path != audio_path:
            try:
                os.remove(chunk_path)
            except OSError:
                pass

        # 每块处理完强制回收内存
        gc.collect()

        if task:
            pct = max(1, int((ci + 1) / total_chunks * 95))
            task["progress"] = {"step": "transcribe", "percent": pct,
                               "detail": f"已完成 {ci+1}/{total_chunks} 块，共 {len(result)} 段"}

    return result, detected_info


@app.post("/api/process/{task_id}/transcribe")
async def step_transcribe(task_id: str):
    if task_id not in tasks:
        return {"error": "任务不存在"}

    task = tasks[task_id]

    # 幂等：已完成直接返回
    if task["source_texts"] is not None:
        lang_label = LANGUAGES.get(task.get("detected_lang", ""), task.get("detected_lang", ""))
        return {"message": f"识别已完成: {len(task['source_texts'])} 段, 语言: {lang_label}"}
    # 正在处理：等待完成
    if task.get("_proc_transcribe"):
        while task.get("_proc_transcribe"):
            await asyncio.sleep(0.5)
        if task["source_texts"] is not None:
            return {"message": f"识别已完成: {len(task['source_texts'])} 段"}
        return {"error": "语音识别失败"}

    audio_path = task["audio_path"]
    if not audio_path or not os.path.exists(audio_path):
        return {"error": "请先提取音频"}

    task["_proc_transcribe"] = True
    try:
        task["progress"] = {"step": "transcribe", "percent": 0, "detail": "语音识别中..."}
        result, info = await asyncio.to_thread(
            _run_transcribe, audio_path, task["source_lang"], task
        )

        task["progress"] = {"step": "transcribe", "percent": 100, "detail": "语音识别完成"}
        task["segments"] = result
        task["source_texts"] = [s["text"] for s in result]
        task["detected_lang"] = info.language

        # 转录完成后删除大 WAV 文件释放磁盘空间
        try:
            if audio_path and os.path.exists(audio_path):
                os.remove(audio_path)
                task["audio_path"] = None
        except OSError:
            pass

        lang_label = LANGUAGES.get(info.language, info.language)
        probability = getattr(info, "language_probability", 1.0)
        return {"message": f"识别完成: {len(result)} 段, 语言: {lang_label} ({probability:.0%})"}

    except Exception as e:
        return {"error": f"语音识别失败: {str(e)}"}
    finally:
        task["_proc_transcribe"] = False


@app.post("/api/process/{task_id}/translate")
async def step_translate(task_id: str, request: Request):
    if task_id not in tasks:
        return {"error": "任务不存在"}

    task = tasks[task_id]
    body = {}
    try:
        raw_body = await request.body()
        if raw_body:
            body = json.loads(raw_body.decode('utf-8'))
    except json.JSONDecodeError:
        return JSONResponse({"error": "请求体不是合法 JSON"}, status_code=400)

    strategy, batch_size, max_items, max_chars = _resolve_translation_request_options(body)
    if task["mode"] != "translate":
        task["translated_texts"] = None
        return {"message": "跳过翻译"}

    # 幂等：已完成直接返回
    if task["translated_texts"] is not None:
        return {"message": f"翻译已完成: {len(task['translated_texts'])} 段"}
    # 正在处理：等待完成
    if task.get("_proc_translate"):
        while task.get("_proc_translate"):
            await asyncio.sleep(0.5)
        if task["translated_texts"] is not None:
            return {"message": f"翻译已完成: {len(task['translated_texts'])} 段"}
        return {"error": "翻译失败"}

    source_texts = task["source_texts"]
    if source_texts is None:
        return {"error": "请先进行语音识别"}
    if len(source_texts) == 0:
        task["translated_texts"] = []
        return {"message": "转录结果为空，无需翻译"}

    src_lang = task["detected_lang"] or task["source_lang"]
    tgt_lang = task["target_lang"]

    if src_lang == tgt_lang:
        task["translated_texts"] = list(source_texts)
        return {"message": "源语言与目标语言相同，无需翻译"}

    task["_proc_translate"] = True
    try:
        task["progress"] = {"step": "translate", "percent": 0, "detail": "翻译中..."}
        translated = await asyncio.to_thread(
            translate_batch,
            source_texts,
            src_lang,
            tgt_lang,
            batch_size,
            task,
            strategy,
            max_items,
            max_chars,
        )
        task["translated_texts"] = translated
        task["progress"] = {"step": "translate", "percent": 100, "detail": "翻译完成"}
        return {
            "message": f"翻译完成: {len(translated)} 段",
            "strategy": task.get("translate_stats", {}).get("strategy", strategy),
            "window_count": task.get("translate_stats", {}).get("window_count", 0),
            "max_items": task.get("translate_stats", {}).get("max_items", max_items),
            "max_chars": task.get("translate_stats", {}).get("max_chars", max_chars),
        }
    except Exception as e:
        return {"error": f"翻译失败: {str(e)}"}
    finally:
        task["_proc_translate"] = False


@app.post("/api/process/{task_id}/subtitle")
async def step_subtitle(task_id: str):
    if task_id not in tasks:
        return {"error": "任务不存在"}

    task = tasks[task_id]

    existing_results = task.get("results", {})
    existing_summary = existing_results.get("summary")
    if existing_results and existing_summary and os.path.exists(existing_summary):
        video_path = Path(task["video_path"])
        return {"message": f"字幕已保存到: {video_path.parent}/"}

    segments = task["segments"]
    if segments is None:
        return {"error": "请先进行语音识别"}
    if len(segments) == 0:
        task["results"] = {}
        return {"message": "转录结果为空，未生成字幕"}

    source_texts = task["source_texts"]
    translated_texts = task["translated_texts"]
    src_lang = task["detected_lang"] or task["source_lang"]
    tgt_lang = task["target_lang"]
    mode = task["mode"]

    # 字幕输出到原视频所在目录，以视频文件名为前缀
    video_path = Path(task["video_path"])
    out_dir = str(video_path.parent)
    stem = video_path.stem  # 视频文件名（不含扩展名）

    results = {}
    task["progress"] = {"step": "subtitle", "percent": 10, "detail": "生成字幕文件..."}

    # 原文字幕
    src_name = f"{stem}_{src_lang}.srt"
    src_srt = os.path.join(out_dir, src_name)
    write_srt(segments, source_texts, src_srt)
    results["source"] = src_srt

    if mode == "translate" and translated_texts:
        task["progress"] = {"step": "subtitle", "percent": 55, "detail": "写入译文和双语字幕..."}
        # 译文字幕
        tgt_name = f"{stem}_{tgt_lang}.srt"
        tgt_srt = os.path.join(out_dir, tgt_name)
        write_srt(segments, translated_texts, tgt_srt)
        results["translated"] = tgt_srt

        # 双语字幕
        bi_name = f"{stem}_bilingual.srt"
        bi_srt = os.path.join(out_dir, bi_name)
        write_bilingual_srt(segments, source_texts, translated_texts, bi_srt)
        results["bilingual"] = bi_srt

    task["progress"] = {"step": "subtitle", "percent": 85, "detail": "生成内容总结..."}
    summary = await asyncio.to_thread(
        _generate_summary,
        source_texts,
        translated_texts if mode == "translate" else None,
    )
    summary_path = os.path.join(out_dir, f"{stem}_summary.md")
    with open(summary_path, 'w', encoding='utf-8') as f:
        f.write("# 视频内容总结\n\n")
        f.write(summary)
        f.write("\n")
    results["summary"] = summary_path
    task["video_summary"] = summary

    task["results"] = results
    task["progress"] = {"step": "subtitle", "percent": 100, "detail": "字幕与总结已生成"}
    return {"message": f"字幕与总结已保存到: {out_dir}/"}


@app.get("/api/results/{task_id}")
async def get_results(task_id: str):
    if task_id not in tasks:
        return {"error": "任务不存在"}
    task = tasks[task_id]
    results = task.get("results", {})
    files = {}
    for key, filepath in results.items():
        if os.path.exists(filepath):
            files[key] = {"name": os.path.basename(filepath), "path": filepath}
    return {"files": files}


@app.get("/download/{task_id}/{key}")
async def download(task_id: str, key: str):
    if task_id not in tasks:
        raise HTTPException(status_code=404, detail="任务不存在")
    results = tasks[task_id].get("results", {})
    filepath = results.get(key)
    if not filepath or not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="文件不存在")
    return FileResponse(filepath, media_type="application/x-subrip", filename=os.path.basename(filepath))


@app.get("/preview/{task_id}/{key}")
async def preview(task_id: str, key: str):
    """预览字幕文件内容 (前80行)"""
    if task_id not in tasks:
        raise HTTPException(status_code=404, detail="任务不存在")
    results = tasks[task_id].get("results", {})
    filepath = results.get(key)
    if not filepath or not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="文件不存在")
    with open(filepath, 'r', encoding='utf-8') as f:
        lines = f.readlines()[:80]
    return "".join(lines)


MOVIE_SUMMARY_RULES = """你是影视内容分析助手，负责仅基于字幕内容总结电影或电视剧片段。

请严格遵守以下规则：
1. 只依据输入中的字幕内容进行总结，不补充演员背景、完整剧情、作品设定或外部常识。
2. 优先提炼当前片段中可直接确认的信息，无法确认的身份、关系、动机、时间线和因果，不要擅自推断。
3. 总结要聚焦人物对话、旁白、信息披露、情绪表达和冲突推进，不要简单重复原句。
4. 重点总结与剧情推进有关的事件、人物关系变化、目标冲突和情绪转折，弱化无关细节。
5. 不要输出“可能是”“应该是”这类空泛猜测；证据不足时明确写“当前字幕中无法确认”。
6. 输出必须使用中文 Markdown，并严格按以下结构组织：
## 整体概述
用 2-3 句话概括片段主题、主要场景和核心矛盾。

## 关键信息
- 2-4 条，概括人物说了什么、透露了什么信息、情绪或立场如何。

## 人物与关系
- 2-4 条，概括当前字幕中能确认的人物关系、立场对立或协作状态。

## 情节推进与看点
- 2-4 条，概括该片段推动了什么剧情、建立了什么悬念或冲突。

整体保持简洁、客观、可核对，总字数控制在 350-600 字。"""


def _generate_summary(source_texts, translated_texts=None, task=None):
    """仅基于字幕内容生成视频总结。"""
    _ensure_llm()
    _llm_inference_guard()
    try:
        primary_lines = translated_texts or source_texts or []
        primary_context = "\n".join(primary_lines[:120])
        original_context = "\n".join((source_texts or [])[:120])
        if not primary_context:
            return "[总结生成失败: 缺少可用字幕内容]"

        prompt = f"""{MOVIE_SUMMARY_RULES}

以下是待总结的影视片段字幕素材，请仅依据字幕内容生成总结。

优先使用的字幕内容：
{primary_context[:4000]}

原始字幕参考：
{original_context[:3000]}

请开始总结。"""

        data = {
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 800,
            "temperature": 0.5,
        }

        _model = get_llm_model()
        if _model:
            data["model"] = _model
        result = post_json(LLM_URL, data, api_key=get_llm_api_key())
        content = result["choices"][0]["message"]["content"]
        # 移除推理模型的 <think>...</think> 标签
        content = re.sub(r'<think>.*?</think>', '', content, flags=re.DOTALL).strip()
        return content
    except Exception as e:
        return f"[总结生成失败: {str(e)[:200]}]"
    finally:
        _llm_inference_done()


@app.post("/api/process/{task_id}/frames")
async def step_frames(task_id: str):
    if task_id not in tasks:
        return {"error": "任务不存在"}

    task = tasks[task_id]
    task["frame_descriptions"] = []
    task["video_summary"] = task.get("video_summary") or ""
    return {"message": "视频帧分析功能已移除，当前版本仅基于字幕生成总结"}


@app.get("/api/frames/{task_id}")
async def get_frames(task_id: str):
    """获取帧分析结果"""
    if task_id not in tasks:
        return {"frames": [], "summary": ""}
    task = tasks[task_id]
    return {"frames": [], "summary": task.get("video_summary", "")}


@app.get("/api/frame_image/{task_id}/{idx}")
async def serve_frame(task_id: str, idx: int):
    """提供帧图片"""
    raise HTTPException(status_code=404, detail="当前版本已移除视频帧图片功能")


# ────────────────── Settings API ──────────────────

@app.get("/api/settings")
async def get_settings():
    """获取当前配置"""
    return load_config()


@app.get("/api/model_options")
async def get_model_options():
    cfg = load_config()
    return {
        "current": cfg,
        "whisper": _discover_whisper_model_options(),
        "llm": {
            "local": _discover_local_model_options(),
        },
    }


@app.get("/api/runtime_log")
async def get_runtime_log(lines: int = 200):
    lines = max(20, min(lines, 1000))
    if not _RUNTIME_LOG_FILE.exists():
        return PlainTextResponse("日志文件尚未生成\n路径: /tmp/llm-logs/video_subtitle.log\n")
    from collections import deque
    with _RUNTIME_LOG_FILE.open('r', encoding='utf-8', errors='replace') as f:
        tail_lines = deque(f, maxlen=lines)
    return PlainTextResponse(''.join(tail_lines) or '暂无日志\n')


@app.post("/api/settings")
async def update_settings(request: Request):
    """更新配置（安全合并，只更新已知字段）"""
    global LLM_URL, FRAME_INTERVAL
    body = await request.json()
    config = load_config()
    original = json.loads(json.dumps(config, ensure_ascii=False))
    for section in ["llm", "whisper", "app"]:
        if section in body:
            for key, value in body[section].items():
                if key in config.get(section, {}):
                    config[section][key] = value
    config["whisper"]["backend"] = "faster-whisper"
    config["whisper"].pop("mlx_model", None)
    save_config(config)

    llm_changed = any(original["llm"].get(key) != config["llm"].get(key) for key in ["api_base", "chat_path", "model", "model_path"])
    whisper_changed = any(original["whisper"].get(key) != config["whisper"].get(key) for key in ["model_path", "device", "compute_type"])

    _append_runtime_log(
        "Config",
        "save "
        f"whisper_backend=faster-whisper "
        f"whisper_model={config['whisper'].get('model_path')} "
        f"llm_model={config['llm'].get('model') or 'default'} "
        f"llm_model_path={config['llm'].get('model_path') or 'default'}"
    )

    if whisper_changed:
        _reset_whisper_runtime("settings-updated")

    if llm_changed:
        mgr = get_llm_manager()
        if mgr.is_running:
            mgr.stop()
        _append_runtime_log("LLM", f"config-updated llm_changed={llm_changed}; service_stopped_for_reload")

    # 热更新运行时变量
    LLM_URL = build_llm_url(config)
    FRAME_INTERVAL = config["app"].get("frame_interval", 60)
    return {"message": "设置已保存", "config": config}


@app.get("/api/health")
async def health_check():
    """健康检查端点（供 Electron 心跳检测）"""
    return {"status": "ok"}


@app.get("/api/llm_status")
async def llm_status():
    """获取 LLM 服务状态"""
    mgr = get_llm_manager()
    return mgr.get_status()


@app.post("/api/llm_start")
async def llm_start():
    """预热本地 LLM 服务（异步启动）"""
    if _is_external_api():
        return JSONResponse({"success": False, "error": "外部 API 模式无需预热"}, status_code=400)
    mgr = get_llm_manager()
    conflict = mgr.detect_external_conflict()
    if conflict:
        return JSONResponse({"success": False, "error": "端口被外部进程占用", "external_conflict": True}, status_code=409)
    import threading
    threading.Thread(target=mgr.start, daemon=True).start()
    return JSONResponse({"success": True, "message": "正在预热"}, status_code=202)


@app.post("/api/llm_stop")
async def llm_stop():
    """释放本地 LLM 服务"""
    if _is_external_api():
        return JSONResponse({"success": False, "error": "外部 API 模式无需释放"}, status_code=400)
    mgr = get_llm_manager()
    stopped = mgr.stop()
    if stopped is False:
        return JSONResponse({"success": False, "error": "进程非本应用所有，无法停止", "external_conflict": True}, status_code=409)
    return {"success": True}


if __name__ == "__main__":
    _port = get_port()
    import socket
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
    except Exception:
        ip = "127.0.0.1"
    finally:
        s.close()

    print(f"""
╔══════════════════════════════════════════════════════════╗
║          视频语音翻译字幕 Web 服务已启动                ║
╠══════════════════════════════════════════════════════════╣
║                                                          ║
║  本机访问: http://localhost:{_port}                         ║
║  局域网:   http://{ip}:{_port}{' ' * max(0, 25 - len(f'{ip}:{_port}'))}║
║                                                          ║
║  功能: 视频语音识别 + 多语言翻译 + 字幕导出             ║
║                                                          ║
╚══════════════════════════════════════════════════════════╝
    """)

    # 自动启动 LLM 服务（在 uvicorn startup event 中启动，确保端口先绑定成功）
    import atexit
    _llm_mgr = get_llm_manager()
    print(f"[LLM] 模型目录: {_llm_mgr._model_dir}")
    print(f"[LLM] llama-server: {_llm_mgr._llama_server}")

    @app.on_event("startup")
    async def _auto_start_llm():
        whisper_summary = _get_whisper_runtime_summary()
        whisper_parts = [
            f"backend={whisper_summary['backend']}",
            f"source={whisper_summary['model_source']}",
            f"model={whisper_summary['model_name']}",
            f"path={whisper_summary['model_path']}",
            f"device={whisper_summary['device']}",
            f"compute={whisper_summary['compute_type']}",
        ]
        _append_runtime_log("Whisper", "startup " + " ".join(whisper_parts))

        # 不再自动启动 LLM，由推理请求按需触发
        if _llm_mgr._get_text_model_path():
            print("[LLM] 模型就绪，等待推理请求时按需启动")
        else:
            print("[LLM] 未找到文本模型")

    def _cleanup():
        print("[LLM] 正在停止...")
        _llm_mgr.stop()
    atexit.register(_cleanup)

    uvicorn.run(app, host="0.0.0.0", port=_port, log_level="info")