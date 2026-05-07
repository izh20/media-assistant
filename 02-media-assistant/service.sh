#!/bin/bash
set -euo pipefail

APP_DIR="$(cd "$(dirname "$0")" && pwd)"
PYTHON_BIN="$APP_DIR/.venv/bin/python"
APP_FILE="$APP_DIR/video_subtitle_app.py"
LOG_DIR="/tmp/llm-logs"
LOG_FILE="$LOG_DIR/media-assistant.log"
PID_FILE="/tmp/media-assistant.pid"
PORT="${MEDIA_ASSISTANT_PORT:-8090}"

info() {
    echo "[media-service] $1"
}

fail() {
    echo "[media-service] ERROR: $1" >&2
    exit 1
}

is_pid_running() {
    local pid="$1"
    [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null
}

read_pid_file() {
    [[ -f "$PID_FILE" ]] || return 1
    tr -d '[:space:]' < "$PID_FILE"
}

listener_pid() {
    lsof -tiTCP:"$PORT" -sTCP:LISTEN 2>/dev/null | head -n 1
}

command_for_pid() {
    local pid="$1"
    ps -p "$pid" -o command= 2>/dev/null
}

is_managed_pid() {
    local pid="$1"
    local cmd
    cmd="$(command_for_pid "$pid")"
    [[ -n "$cmd" && "$cmd" == *"$APP_FILE"* ]]
}

wait_until_ready() {
    local url="http://127.0.0.1:${PORT}/api/check_services"
    for _ in {1..30}; do
        if curl --noproxy '*' -sf "$url" >/dev/null 2>&1; then
            return 0
        fi
        sleep 1
    done
    return 1
}

cleanup_stale_pid() {
    local pid=""
    pid="$(read_pid_file || true)"
    if [[ -n "$pid" ]] && ! is_pid_running "$pid"; then
        rm -f "$PID_FILE"
    fi
}

start_service() {
    [[ -x "$PYTHON_BIN" ]] || fail "Python 环境不存在: $PYTHON_BIN"
    [[ -f "$APP_FILE" ]] || fail "应用入口不存在: $APP_FILE"

    mkdir -p "$LOG_DIR"
    cleanup_stale_pid

    local pid=""
    pid="$(read_pid_file || true)"
    if [[ -n "$pid" ]] && is_pid_running "$pid"; then
        info "已在运行: PID=$pid PORT=$PORT"
        return 0
    fi

    local occupied_pid=""
    occupied_pid="$(listener_pid || true)"
    if [[ -n "$occupied_pid" ]]; then
        if is_managed_pid "$occupied_pid"; then
            echo "$occupied_pid" > "$PID_FILE"
            info "发现已运行实例，已接管 PID 文件: PID=$occupied_pid PORT=$PORT"
            return 0
        fi
        fail "端口 $PORT 已被其他进程占用: PID=$occupied_pid"
    fi

    APP_DIR="$APP_DIR" \
    APP_FILE="$APP_FILE" \
    LOG_FILE="$LOG_FILE" \
    PID_FILE="$PID_FILE" \
    PYTHON_BIN="$PYTHON_BIN" \
    MEDIA_ASSISTANT_PORT="$PORT" \
    "$PYTHON_BIN" - <<'PY'
import os
import subprocess

app_dir = os.environ["APP_DIR"]
app_file = os.environ["APP_FILE"]
log_file = os.environ["LOG_FILE"]
pid_file = os.environ["PID_FILE"]
python_bin = os.environ["PYTHON_BIN"]

env = os.environ.copy()
with open(log_file, "ab", buffering=0) as log:
    process = subprocess.Popen(
        [python_bin, app_file],
        cwd=app_dir,
        env=env,
        stdin=subprocess.DEVNULL,
        stdout=log,
        stderr=log,
        start_new_session=True,
        close_fds=True,
    )

with open(pid_file, "w", encoding="utf-8") as handle:
    handle.write(f"{process.pid}\n")

print(process.pid)
PY

    pid="$(read_pid_file || true)"
    if [[ -z "$pid" ]]; then
        fail "启动失败，未写入 PID 文件"
    fi

    if wait_until_ready; then
        info "启动成功: PID=$pid URL=http://127.0.0.1:$PORT"
        info "日志: $LOG_FILE"
        return 0
    fi

    if ! is_pid_running "$pid"; then
        rm -f "$PID_FILE"
    fi
    fail "启动后健康检查未通过，请查看日志: $LOG_FILE"
}

stop_service() {
    cleanup_stale_pid

    local pid=""
    pid="$(read_pid_file || true)"
    if [[ -n "$pid" ]] && is_pid_running "$pid"; then
        kill "$pid" 2>/dev/null || true
        for _ in {1..15}; do
            if ! is_pid_running "$pid"; then
                break
            fi
            sleep 1
        done
        if is_pid_running "$pid"; then
            kill -9 "$pid" 2>/dev/null || true
        fi
        rm -f "$PID_FILE"
        info "已停止: PID=$pid"
    else
        rm -f "$PID_FILE"
    fi

    local occupied_pid=""
    occupied_pid="$(listener_pid || true)"
    if [[ -n "$occupied_pid" && $(command_for_pid "$occupied_pid") == *"$APP_FILE"* ]]; then
        kill "$occupied_pid" 2>/dev/null || true
        sleep 1
        if is_pid_running "$occupied_pid"; then
            kill -9 "$occupied_pid" 2>/dev/null || true
        fi
        info "已清理遗留实例: PID=$occupied_pid"
    fi

    if [[ -n "$(listener_pid || true)" ]]; then
        fail "端口 $PORT 仍被占用"
    fi

    info "服务已停止"
}

status_service() {
    cleanup_stale_pid

    local pid=""
    pid="$(read_pid_file || true)"
    if [[ -n "$pid" ]] && is_pid_running "$pid"; then
        if curl --noproxy '*' -sf "http://127.0.0.1:${PORT}/api/check_services" >/dev/null 2>&1; then
            info "运行中: PID=$pid URL=http://127.0.0.1:$PORT"
        else
            info "进程存在但健康检查未通过: PID=$pid PORT=$PORT"
        fi
        info "日志: $LOG_FILE"
        return 0
    fi

    local occupied_pid=""
    occupied_pid="$(listener_pid || true)"
    if [[ -n "$occupied_pid" ]]; then
        info "端口 $PORT 被其他进程占用: PID=$occupied_pid"
        echo "$(command_for_pid "$occupied_pid")"
        return 1
    fi

    info "未运行"
    return 1
}

show_logs() {
    [[ -f "$LOG_FILE" ]] || fail "日志文件不存在: $LOG_FILE"
    tail -n 80 "$LOG_FILE"
}

case "${1:-start}" in
    start)
        start_service
        ;;
    stop)
        stop_service
        ;;
    restart)
        stop_service || true
        start_service
        ;;
    status)
        status_service
        ;;
    logs)
        show_logs
        ;;
    *)
        echo "Usage: $0 [start|stop|restart|status|logs]"
        exit 1
        ;;
esac