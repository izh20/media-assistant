#!/bin/bash
set -e

#=============================================================================
# Media Assistant - macOS DMG 一键打包脚本
#
# 使用方法:
#   cd /Volumes/扩展盘512G/claude/project01/02-media-assistant
#   chmod +x build-dmg.sh
#   ./build-dmg.sh
#
# 前提条件:
#   - .venv 虚拟环境已创建且安装了所有依赖
#   - bundled/ 目录下已有 llama-server、ffmpeg、models
#   - models/ 目录下已有 Qwen GGUF 模型文件
#   - Node.js 和 npm 已安装
#=============================================================================

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

info()  { echo -e "${GREEN}[INFO]${NC} $1"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $1"; }
error() { echo -e "${RED}[ERROR]${NC} $1"; exit 1; }

# ===== 配置 =====
PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
MODELS_DIR="$(dirname "$PROJECT_DIR")/models"
BUILD_DIR="/tmp/media-build"
DIST_DIR="/tmp/media-dist"
VERSION="1.0.0"
DMG_NAME="Media-Assistant-${VERSION}-mac-arm64.dmg"
DMG_OUTPUT="${PROJECT_DIR}/${DMG_NAME}"

# npm 镜像（国内加速）
export ELECTRON_MIRROR="https://npmmirror.com/mirrors/electron/"
NPM_REGISTRY="https://registry.npmmirror.com"

info "============================================"
info "  Media Assistant DMG 打包"
info "  版本: ${VERSION}"
info "  项目: ${PROJECT_DIR}"
info "============================================"

# ===== 第0步：检查前提条件 =====
info "[0/7] 检查前提条件..."

[ -d "${PROJECT_DIR}/.venv" ] || error ".venv 虚拟环境不存在"
[ -f "${PROJECT_DIR}/media-assistant.spec" ] || error "media-assistant.spec 不存在"
[ -f "${PROJECT_DIR}/bundled/llama-server/llama-server" ] || error "bundled/llama-server/llama-server 不存在"
[ -f "${PROJECT_DIR}/bundled/ffmpeg/mac-arm64/ffmpeg" ] || error "bundled/ffmpeg/mac-arm64/ffmpeg 不存在"
[ -f "${PROJECT_DIR}/bundled/models/faster-whisper-large-v3-turbo/model.bin" ] || error "bundled/models/faster-whisper-large-v3-turbo/model.bin 不存在"

# 检查 LLM 模型
TEXT_MODEL="${MODELS_DIR}/Qwen2.5-7B-Instruct-GGUF/qwen2.5-7b-instruct-q4_0.gguf"
VISION_MODEL="${MODELS_DIR}/Qwen2-VL-7B-Instruct-GGUF/Qwen2-VL-7B-Instruct-Q4_K_M.gguf"
MMPROJ_MODEL="${MODELS_DIR}/Qwen2-VL-7B-Instruct-GGUF/mmproj-Qwen2-VL-7B-Instruct-f16.gguf"
[ -f "${TEXT_MODEL}" ] || error "文本模型不存在: ${TEXT_MODEL}"
[ -f "${VISION_MODEL}" ] || error "视觉模型不存在: ${VISION_MODEL}"
[ -f "${MMPROJ_MODEL}" ] || error "MMProj 模型不存在: ${MMPROJ_MODEL}"

command -v npm >/dev/null 2>&1 || error "npm 未安装"
command -v node >/dev/null 2>&1 || error "node 未安装"

info "前提条件检查通过 ✓"

# ===== 第1步：清理 ._ 文件 =====
info "[1/7] 清理 AppleDouble ._ 文件..."

CLEANED=$(find "${PROJECT_DIR}" -path "${PROJECT_DIR}/dist" -prune \
    -o -path "${PROJECT_DIR}/.venv" -prune \
    -o -path "${PROJECT_DIR}/node_modules" -prune \
    -o -name "._*" -print -delete 2>/dev/null | wc -l | tr -d ' ')
find "${PROJECT_DIR}/bundled" -name "._*" -delete 2>/dev/null
info "  清理了 ${CLEANED} 个 ._ 文件"

# ===== 第2步：PyInstaller 打包后端 =====
info "[2/7] PyInstaller 打包 Python 后端..."

cd "${PROJECT_DIR}"
.venv/bin/pyinstaller media-assistant.spec --noconfirm 2>&1 | tail -3

[ -f "${PROJECT_DIR}/dist/media-assistant/media-assistant" ] || error "PyInstaller 打包失败"
info "PyInstaller 打包完成 ✓"

# ===== 第3步：准备 Electron 构建目录 =====
info "[3/7] 准备 Electron 构建目录 (${BUILD_DIR})..."

rm -rf "${BUILD_DIR}" "${DIST_DIR}"
mkdir -p "${BUILD_DIR}"

# 复制 Electron 源文件
cp "${PROJECT_DIR}/electron/main.js" \
   "${PROJECT_DIR}/electron/backend-manager.js" \
   "${PROJECT_DIR}/electron/preload.js" \
   "${PROJECT_DIR}/electron/updater.js" \
   "${PROJECT_DIR}/electron/package.json" \
   "${BUILD_DIR}/"
cp -r "${PROJECT_DIR}/electron/assets" "${BUILD_DIR}/"

# 清理构建目录中的 ._ 文件
find "${BUILD_DIR}" -name "._*" -delete 2>/dev/null

info "构建目录准备完成 ✓"

# ===== 第4步：修改 package.json 的 extraResources =====
info "[4/7] 配置 extraResources..."

cd "${BUILD_DIR}"
python3 -c "
import json
pkg = json.load(open('package.json'))
pkg['build']['extraResources'] = [
    {'from': '${PROJECT_DIR}/dist/media-assistant/', 'to': 'backend/', 'filter': ['**/*']},
    {'from': '${PROJECT_DIR}/bundled/llama-server/', 'to': 'bundled/llama-server/', 'filter': ['**/*']},
    {'from': '${PROJECT_DIR}/bundled/ffmpeg/', 'to': 'bundled/ffmpeg/', 'filter': ['**/*']},
    {'from': '${PROJECT_DIR}/bundled/models/faster-whisper-large-v3-turbo/', 'to': 'bundled/models/faster-whisper-large-v3-turbo/', 'filter': ['**/*']},
    {'from': '${TEXT_MODEL}', 'to': 'bundled/models/Qwen2.5-7B-Instruct-GGUF/qwen2.5-7b-instruct-q4_0.gguf'},
    {'from': '${VISION_MODEL}', 'to': 'bundled/models/Qwen2-VL-7B-Instruct-GGUF/Qwen2-VL-7B-Instruct-Q4_K_M.gguf'},
    {'from': '${MMPROJ_MODEL}', 'to': 'bundled/models/Qwen2-VL-7B-Instruct-GGUF/mmproj-Qwen2-VL-7B-Instruct-f16.gguf'}
]
pkg['build']['directories']['output'] = '${DIST_DIR}'
json.dump(pkg, open('package.json','w'), indent=2)
print('extraResources 已配置')
"

# ===== 第5步：npm install + electron-builder =====
info "[5/7] npm install && electron-builder..."

cd "${BUILD_DIR}"
npm install --registry="${NPM_REGISTRY}" 2>&1 | tail -5

# 再次清理（npm install 可能从 ExFAT 源带入 ._ 文件）
find "${BUILD_DIR}" -name "._*" -delete 2>/dev/null

info "开始 electron-builder..."
npx electron-builder --mac --arm64 --dir 2>&1 | tail -5

APP_PATH="${DIST_DIR}/mac-arm64/Media Assistant.app"
[ -d "${APP_PATH}" ] || error "electron-builder 失败，未生成 .app"
info "electron-builder 完成 ✓"

# ===== 第5.5步：清除 xattr + 重新签名 =====
info "[5.5/7] 清除 xattr 并重新签名..."

# 清除所有 provenance/quarantine xattr（防止 Gatekeeper 阻止执行）
xattr -cr "${APP_PATH}" 2>/dev/null
info "  xattr 已清除"

# 对所有 Mach-O 二进制重新 ad-hoc 签名（由内到外顺序）
# 先签名 dylib/so（依赖项）
find "${APP_PATH}" -type f \( -name "*.dylib" -o -name "*.so" \) -print0 | while IFS= read -r -d '' f; do
    codesign --force --sign - "$f" 2>/dev/null || true
done
# 再签名可执行文件（llama-server, media-assistant, ffmpeg, ffprobe 等）
find "${APP_PATH}/Contents/Resources" -type f -perm -0111 -print0 2>/dev/null | while IFS= read -r -d '' f; do
    file "$f" 2>/dev/null | grep -q "Mach-O" && codesign --force --sign - "$f" 2>/dev/null || true
done
# 最后签名整个 .app
codesign --force --deep --sign - "${APP_PATH}" 2>/dev/null || true
info "  代码签名完成"

# ===== 第5.6步：验证 .app 完整性 =====
info "[5.6/7] 验证 .app 内容..."

RESOURCES="${APP_PATH}/Contents/Resources"
CHECKS=(
    "${RESOURCES}/backend/media-assistant"
    "${RESOURCES}/backend/_internal/faster_whisper/assets/silero_vad_v6.onnx"
    "${RESOURCES}/bundled/llama-server/llama-server"
    "${RESOURCES}/bundled/ffmpeg/mac-arm64/ffmpeg"
    "${RESOURCES}/bundled/ffmpeg/mac-arm64/ffprobe"
    "${RESOURCES}/bundled/models/faster-whisper-large-v3-turbo/model.bin"
    "${RESOURCES}/bundled/models/Qwen2.5-7B-Instruct-GGUF/qwen2.5-7b-instruct-q4_0.gguf"
    "${RESOURCES}/bundled/models/Qwen2-VL-7B-Instruct-GGUF/Qwen2-VL-7B-Instruct-Q4_K_M.gguf"
    "${RESOURCES}/bundled/models/Qwen2-VL-7B-Instruct-GGUF/mmproj-Qwen2-VL-7B-Instruct-f16.gguf"
)
FAIL=0
for f in "${CHECKS[@]}"; do
    if [ -f "$f" ]; then
        SIZE=$(du -sh "$f" 2>/dev/null | cut -f1)
        info "  ✓ $(basename "$f") ($SIZE)"
    else
        warn "  ✗ 缺少: $f"
        FAIL=1
    fi
done
[ $FAIL -eq 0 ] || error "应用验证失败，缺少关键文件"
info ".app 验证通过 ✓"

# ===== 第6步：生成 DMG =====
info "[6/7] 生成 DMG: ${DMG_NAME}..."

# 使用外置盘临时目录（/tmp 空间可能不够 10GB+ DMG）
EXT_TMP="/Volumes/扩展盘512G/tmp"
mkdir -p "${EXT_TMP}" 2>/dev/null

# 检查可用空间
AVAIL_MB=$(df -m /tmp | tail -1 | awk '{print $4}')
if [ "${AVAIL_MB}" -lt 15000 ] 2>/dev/null; then
    info "  /tmp 空间不足 (${AVAIL_MB}MB)，使用外置盘临时目录"
    export TMPDIR="${EXT_TMP}"
fi

hdiutil create \
    -volname "Media Assistant" \
    -srcfolder "${APP_PATH}" \
    -ov -format UDRO \
    "${DMG_OUTPUT}" 2>&1 | grep -E "created:|error|fail" || true

[ -f "${DMG_OUTPUT}" ] || error "DMG 创建失败"

DMG_SIZE=$(du -sh "${DMG_OUTPUT}" | cut -f1)
info "DMG 已生成: ${DMG_OUTPUT} (${DMG_SIZE})"

# ===== 第7步：清理 =====
info "[7/7] 清理临时文件..."

rm -rf "${BUILD_DIR}" "${DIST_DIR}" "${EXT_TMP}" 2>/dev/null
# 恢复 TMPDIR
unset TMPDIR

info "============================================"
info "  打包完成！"
info "  DMG: ${DMG_OUTPUT}"
info "  大小: ${DMG_SIZE}"
info "============================================"
info ""
info "安装方法: 双击 DMG → 拖动 Media Assistant 到 Applications"
