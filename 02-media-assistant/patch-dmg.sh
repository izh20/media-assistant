#!/bin/bash
set -e

#=============================================================================
# Media Assistant - DMG 快速补丁脚本
#
# 仅当 Python 代码变更时使用（不涉及模型/依赖变化）
# 流程: PyInstaller 重打包 → 替换 .app 中的 backend → 更新 Electron JS → 重签名 → 重建 DMG
# 耗时: ~2-3 分钟（vs 全量构建 ~20 分钟）
#
# 使用方法:
#   cd /Volumes/扩展盘512G/claude/project01/02-media-assistant
#   ./patch-dmg.sh
#=============================================================================

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'
info()  { echo -e "${GREEN}[INFO]${NC} $1"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $1"; }
error() { echo -e "${RED}[ERROR]${NC} $1"; exit 1; }

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
VERSION="1.0.0"
DMG_NAME="Media-Assistant-${VERSION}-mac-arm64.dmg"
DMG_OUTPUT="${PROJECT_DIR}/${DMG_NAME}"
MOUNT_POINT="/tmp/media-patch-mount"
WORK_DIR="/tmp/media-patch-app"

info "============================================"
info "  Media Assistant DMG 快速补丁"
info "============================================"

# 检查现有 DMG
[ -f "${DMG_OUTPUT}" ] || error "找不到现有 DMG: ${DMG_OUTPUT}\n请先运行 build-dmg.sh 全量构建"

# ===== 第1步: PyInstaller 重打包后端 =====
info "[1/4] PyInstaller 打包 Python 后端..."
cd "${PROJECT_DIR}"

# 清理 ._ 文件
CLEANED=$(find "${PROJECT_DIR}" -path "${PROJECT_DIR}/dist" -prune \
    -o -path "${PROJECT_DIR}/.venv" -prune \
    -o -path "${PROJECT_DIR}/node_modules" -prune \
    -o -name "._*" -print -delete 2>/dev/null | wc -l | tr -d ' ')
info "  清理了 ${CLEANED} 个 ._ 文件"

"${PROJECT_DIR}/.venv/bin/pyinstaller" media-assistant.spec --noconfirm 2>&1 | tail -3
[ -f "${PROJECT_DIR}/dist/media-assistant/media-assistant" ] || error "PyInstaller 打包失败"
info "PyInstaller 完成 ✓"

# ===== 第2步: 从 DMG 提取 .app 并替换 backend =====
info "[2/4] 从 DMG 提取 .app 并替换后端..."

# 清理工作目录
rm -rf "${WORK_DIR}"
mkdir -p "${WORK_DIR}"

# 挂载 DMG
mkdir -p "${MOUNT_POINT}"
hdiutil attach "${DMG_OUTPUT}" -mountpoint "${MOUNT_POINT}" -nobrowse -quiet 2>/dev/null || error "无法挂载 DMG"

# 复制 .app 到可写工作目录
cp -R "${MOUNT_POINT}/Media Assistant.app" "${WORK_DIR}/"

# 卸载 DMG
hdiutil detach "${MOUNT_POINT}" -quiet 2>/dev/null

APP_PATH="${WORK_DIR}/Media Assistant.app"
BACKEND_DIR="${APP_PATH}/Contents/Resources/backend"

[ -d "${BACKEND_DIR}" ] || error ".app 中找不到 backend 目录"

# 删除旧后端，复制新后端
info "  替换 backend..."
rm -rf "${BACKEND_DIR}"
cp -R "${PROJECT_DIR}/dist/media-assistant" "${BACKEND_DIR}/"

info "后端替换完成 ✓"

# ===== 第2.5步: 更新 Electron JS 文件 =====
info "[2.5/4] 更新 Electron JS 文件..."

ASAR_FILE="${APP_PATH}/Contents/Resources/app.asar"
ASAR_EXTRACT="/tmp/media-patch-asar"
ASAR_BIN="/tmp/media-build/node_modules/.bin/asar"

if [ -f "${ASAR_FILE}" ]; then
    # 使用项目中已安装的 asar 工具
    if [ -x "${ASAR_BIN}" ]; then
        rm -rf "${ASAR_EXTRACT}"
        "${ASAR_BIN}" extract "${ASAR_FILE}" "${ASAR_EXTRACT}"
        
        # 复制更新的 JS 文件
        for jsfile in main.js backend-manager.js preload.js; do
            if [ -f "${PROJECT_DIR}/electron/${jsfile}" ]; then
                cp "${PROJECT_DIR}/electron/${jsfile}" "${ASAR_EXTRACT}/${jsfile}"
                info "  更新 ${jsfile}"
            fi
        done
        
        # 重新打包 asar
        "${ASAR_BIN}" pack "${ASAR_EXTRACT}" "${ASAR_FILE}"
        rm -rf "${ASAR_EXTRACT}"
        info "Electron JS 更新完成 ✓"
    else
        warn "asar 工具不可用 (${ASAR_BIN})，跳过 Electron JS 更新"
    fi
else
    warn "未找到 app.asar，跳过 Electron JS 更新"
fi

# ===== 第3步: 重新签名 =====
info "[3/4] 重新签名..."

# 清理 ._ 文件（ExFAT→APFS 复制产生，会导致 codesign 失败）
find "${APP_PATH}" -name "._*" -delete 2>/dev/null

# 签名新的后端二进制
codesign --force --sign - "${BACKEND_DIR}/media-assistant" 2>/dev/null || true
# 签名 .app
codesign --force --deep --sign - "${APP_PATH}" 2>/dev/null || true
info "签名完成 ✓"

# ===== 第4步: 重建 DMG =====
info "[4/4] 重建 DMG..."

rm -f "${DMG_OUTPUT}"
hdiutil create \
    -volname "Media Assistant" \
    -srcfolder "${APP_PATH}" \
    -ov -format UDRO \
    "${DMG_OUTPUT}" 2>&1 | grep -E "created:|error|fail" || true

[ -f "${DMG_OUTPUT}" ] || error "DMG 创建失败"

DMG_SIZE=$(du -sh "${DMG_OUTPUT}" | cut -f1)

# 清理
rm -rf "${WORK_DIR}" "${MOUNT_POINT}"

info "============================================"
info "  补丁完成！"
info "  DMG: ${DMG_OUTPUT}"
info "  大小: ${DMG_SIZE}"
info "============================================"
