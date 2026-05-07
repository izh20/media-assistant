#!/bin/bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
PYTHON_BIN="${PROJECT_DIR}/.venv/bin/python"

if [ ! -x "${PYTHON_BIN}" ]; then
  echo "[ERROR] 未找到 Python 虚拟环境: ${PYTHON_BIN}" >&2
  exit 1
fi

echo "[1/3] Python 语法编译检查"
"${PYTHON_BIN}" -m py_compile \
  "${PROJECT_DIR}/config.py" \
  "${PROJECT_DIR}/llm_manager.py" \
  "${PROJECT_DIR}/video_subtitle_app.py"

echo "[2/3] 模型选择与日志接口检查"
PYTHONPATH="${PROJECT_DIR}" "${PYTHON_BIN}" - <<'PY'
import asyncio
from pathlib import Path

import video_subtitle_app as app
from llm_manager import get_llm_manager

required_html_tokens = [
    'cfg-whisper-model-path',
    'cfg-llm-model-path',
  'local-path',
    '/api/model_options',
    '/api/runtime_log',
]
missing = [token for token in required_html_tokens if token not in app.HTML_PAGE]
if missing:
    raise SystemExit(f"HTML_PAGE 缺少关键标记: {missing}")

for forbidden in ['upload-file-area', 'input-upload', 'enable-frames', 'frame-gallery', 'step-frames', 'cfg-whisper-backend', 'cfg-whisper-mlx-model']:
  if forbidden in app.HTML_PAGE:
    raise SystemExit(f"HTML_PAGE 仍包含已移除的页面标记: {forbidden}")

options = asyncio.run(app.get_model_options())
assert 'whisper' in options and 'llm' in options
assert options['whisper']['faster'], '未发现 faster-whisper 候选'
assert 'mlx' not in options['whisper'], 'Whisper 选项仍包含已移除的 MLX 候选'
assert options['llm']['local'], '未发现本地 LLM 候选'
assert all('Qwen2-VL' not in item.get('label', '') for item in options['llm']['local']), '本地 LLM 候选仍包含 Qwen2-VL'
assert all('qwen2-vl' not in item.get('value', '').lower() for item in options['llm']['local'] if isinstance(item.get('value'), str)), '本地 LLM 候选仍包含视觉模型路径'

whisper_status = app._get_whisper_status_payload()
assert 'text' in whisper_status and 'detail' in whisper_status

mgr = get_llm_manager()
llm_status = mgr.get_status()
assert 'model' in llm_status and 'mmproj' not in llm_status and 'vision_capable' not in llm_status

log_response = asyncio.run(app.get_runtime_log(lines=20))
log_text = log_response.body.decode('utf-8', errors='replace')

print('WHISPER_STATUS=', whisper_status['text'])
print('WHISPER_OPTIONS_FAST=', len(options['whisper']['faster']))
print('LLM_OPTIONS=', len(options['llm']['local']))
print('LLM_MODEL=', llm_status['model'] or 'NONE')
print('LOG_LINES=', len([line for line in log_text.splitlines() if line.strip()]))
print('LOG_PATH=', Path('/tmp/llm-logs/video_subtitle.log'))
PY

echo "[3/3] 结果"
echo "快速验证通过。"
echo "如需手动点击验证 UI，请执行:"
echo "  cd \"${PROJECT_DIR}\" && ./.venv/bin/python video_subtitle_app.py"
echo "然后打开: http://127.0.0.1:8090"