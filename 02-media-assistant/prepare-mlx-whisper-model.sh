#!/bin/bash
set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'
info()  { echo -e "${GREEN}[INFO]${NC} $1"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $1"; }
error() { echo -e "${RED}[ERROR]${NC} $1"; exit 1; }

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
PYTHON_BIN="${PROJECT_DIR}/.venv/bin/python"
TARGET_DIR="${PROJECT_DIR}/bundled/models/mlx-whisper-large-v3-turbo"
MODEL_REPO="mlx-community/whisper-large-v3-turbo"

[ -x "${PYTHON_BIN}" ] || error ".venv Python 不存在: ${PYTHON_BIN}"
mkdir -p "${TARGET_DIR}"

info "准备 MLX Whisper 模型: ${MODEL_REPO}"
info "目标目录: ${TARGET_DIR}"

env -u ALL_PROXY -u all_proxy -u HTTP_PROXY -u http_proxy -u HTTPS_PROXY -u https_proxy \
"${PYTHON_BIN}" - <<'PY'
from huggingface_hub import snapshot_download
from pathlib import Path

target_dir = Path(r"/Volumes/扩展盘512G/claude/project01/02-media-assistant/bundled/models/mlx-whisper-large-v3-turbo")
target_dir.mkdir(parents=True, exist_ok=True)

snapshot_download(
    repo_id="mlx-community/whisper-large-v3-turbo",
    local_dir=str(target_dir),
)
print(target_dir)
PY

[ -f "${TARGET_DIR}/config.json" ] || error "MLX 模型准备失败，缺少 config.json"
SIZE=$(du -sh "${TARGET_DIR}" | cut -f1)
info "MLX 模型已就绪: ${TARGET_DIR} (${SIZE})"