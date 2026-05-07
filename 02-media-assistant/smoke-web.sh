#!/bin/bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
PYTHON_BIN="${PROJECT_DIR}/.venv/bin/python"
PORT="${MEDIA_ASSISTANT_PORT:-18090}"
SERVER_LOG="/tmp/media-assistant-smoke-web.log"
HEALTH_URL="http://127.0.0.1:${PORT}/api/health"

if [ ! -x "${PYTHON_BIN}" ]; then
  echo "[ERROR] 未找到 Python 虚拟环境: ${PYTHON_BIN}" >&2
  exit 1
fi

cleanup() {
  if [ -n "${SERVER_PID:-}" ] && kill -0 "${SERVER_PID}" 2>/dev/null; then
    kill "${SERVER_PID}" 2>/dev/null || true
    wait "${SERVER_PID}" 2>/dev/null || true
  fi
}
trap cleanup EXIT

fetch_url() {
  local url="$1"
  REQUEST_URL="${url}" env -u ALL_PROXY -u all_proxy -u HTTP_PROXY -u http_proxy -u HTTPS_PROXY -u https_proxy \
    "${PYTHON_BIN}" - <<'PY'
import os
import urllib.request

url = os.environ['REQUEST_URL']
with urllib.request.urlopen(url, timeout=5) as response:
    print(response.read().decode('utf-8'))
PY
}

wait_for_health() {
  local retries=60
  while [ "${retries}" -gt 0 ]; do
    if fetch_url "${HEALTH_URL}" >/dev/null 2>&1; then
      return 0
    fi
    sleep 1
    retries=$((retries - 1))
  done
  return 1
}

probe_json_endpoint() {
  local url="$1"
  local label="$2"
  local response
  response="$(fetch_url "${url}")"
  ENDPOINT_LABEL="${label}" RESPONSE_JSON="${response}" "${PYTHON_BIN}" - <<'PY'
import json
import os

label = os.environ['ENDPOINT_LABEL']
payload = json.loads(os.environ['RESPONSE_JSON'])

if label == 'model_options':
    assert payload['whisper']['faster'], '缺少 faster-whisper 候选'
    assert 'mlx' not in payload['whisper'], '仍返回已移除的 MLX 候选'
    assert payload['llm']['local'], '缺少本地 LLM 候选'
    assert all('Qwen2-VL' not in item.get('label', '') for item in payload['llm']['local']), '仍返回已移除的视觉模型候选'
    assert all('qwen2-vl' not in item.get('value', '').lower() for item in payload['llm']['local'] if isinstance(item.get('value'), str)), '仍返回视觉模型路径'
    print('MODEL_OPTIONS_OK', len(payload['llm']['local']), len(payload['whisper']['faster']))
elif label == 'check_services':
    assert 'whisper' in payload and 'llm' in payload
    assert 'whisper_text' in payload and 'llm_text' in payload and 'external_api' in payload
    print('CHECK_SERVICES_OK', payload['whisper_text'], payload['llm_text'], payload['external_api'])
else:
    raise AssertionError(f'未知校验标签: {label}')
PY
}

echo "[1/4] 本地静态检查"
bash "${PROJECT_DIR}/quick-validate.sh"

echo "[2/4] 启动临时 Web 服务 (端口 ${PORT})"
rm -f "${SERVER_LOG}"
cd "${PROJECT_DIR}"
MEDIA_ASSISTANT_PORT="${PORT}" "${PYTHON_BIN}" video_subtitle_app.py >"${SERVER_LOG}" 2>&1 &
SERVER_PID=$!

if ! wait_for_health; then
  echo "[ERROR] Web 服务未在预期时间内就绪" >&2
  echo "--- 服务日志 tail ---" >&2
  tail -n 80 "${SERVER_LOG}" >&2 || true
  exit 1
fi

echo "[3/4] 探测关键页面与接口"
HTML_CONTENT="$(fetch_url "http://127.0.0.1:${PORT}/")"
for token in "cfg-whisper-model-path" "cfg-llm-model-path" "local-path" "/api/runtime_log"; do
  if [[ "${HTML_CONTENT}" != *"${token}"* ]]; then
    echo "[ERROR] 首页缺少关键标记: ${token}" >&2
    tail -n 80 "${SERVER_LOG}" >&2 || true
    exit 1
  fi
done
for forbidden in "upload-file-area" "input-upload" "enable-frames" "frame-gallery" "step-frames" "cfg-whisper-backend" "cfg-whisper-mlx-model"; do
  if [[ "${HTML_CONTENT}" == *"${forbidden}"* ]]; then
    echo "[ERROR] 首页仍包含已移除功能标记: ${forbidden}" >&2
    tail -n 80 "${SERVER_LOG}" >&2 || true
    exit 1
  fi
done
echo "HOME_PAGE_OK"

probe_json_endpoint "http://127.0.0.1:${PORT}/api/model_options" "model_options" ""
probe_json_endpoint "http://127.0.0.1:${PORT}/api/check_services" "check_services" ""

RUNTIME_LOG_TEXT="$(fetch_url "http://127.0.0.1:${PORT}/api/runtime_log?lines=30")"
if [ -z "${RUNTIME_LOG_TEXT}" ]; then
  echo "[ERROR] 运行日志接口返回为空" >&2
  tail -n 80 "${SERVER_LOG}" >&2 || true
  exit 1
fi
echo "RUNTIME_LOG_OK"

echo "[4/4] 结果"
echo "本地 Web smoke test 通过。"
echo "服务日志: ${SERVER_LOG}"
echo "注意: 这是临时验证服务，脚本退出后会自动停止。"
echo "如需手工点击检查，请单独启动: ./.venv/bin/python video_subtitle_app.py"
echo "临时验证地址: http://127.0.0.1:${PORT}"