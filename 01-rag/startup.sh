#!/bin/bash
# startup.sh - RAG 服务启动脚本
# 用法: ./startup.sh [rag|web|ollama|llama|stop|status]

set -euo pipefail

# 项目根目录
PROJECT_DIR="/Volumes/扩展盘512G/claude/project01"
MODEL_DIR="$PROJECT_DIR/models"
QDRANT_STORAGE="$PROJECT_DIR/qdrant_storage"
LOG_DIR="/tmp/llm-logs"

start_qdrant() {
    echo "Starting Qdrant..."

    # Stop existing container if exists
    docker stop qdrant 2>/dev/null || true
    docker rm qdrant 2>/dev/null || true

    # 改为监听所有网卡，方便局域网访问
    docker run -d --name qdrant \
        -p 0.0.0.0:6333:6333 \
        -p 0.0.0.0:6334:6334 \
        -v "$QDRANT_STORAGE:/qdrant/storage" \
        qdrant/qdrant
    echo "  Qdrant started at 0.0.0.0:6333"
}

start_embedding_service() {
    echo "Starting Embedding service (port 8081)..."

    # Kill existing if running
    pkill -f "llama-server.*8081" 2>/dev/null || true

    mkdir -p "$LOG_DIR"
    cd "$MODEL_DIR"

    # 改为监听所有网卡
    nohup llama-server \
        -m nomic-embed-text-v1.5.f16.gguf \
        --host 0.0.0.0 \
        --port 8081 \
        --embedding \
        > "$LOG_DIR/embed.log" 2>&1 &

    # Wait for service
    for i in {1..30}; do
        curl -sf http://127.0.0.1:8081/v1/models >/dev/null 2>&1 && break
        sleep 1
    done

    if curl -sf http://127.0.0.1:8081/v1/models >/dev/null 2>&1; then
        echo "  Embedding service started at 0.0.0.0:8081"
    else
        echo "  ERROR: Embedding service failed. Check $LOG_DIR/embed.log"
    fi
}

start_llm_llama() {
    local model_file="$1"
    local port="${2:-8080}"

    echo "Starting LLM service (port $port) with $model_file..."

    # Kill existing if running
    pkill -f "llama-server.*port $port" 2>/dev/null || true

    if [ ! -f "$MODEL_DIR/$model_file" ]; then
        echo "  ERROR: Model file not found: $MODEL_DIR/$model_file"
        return 1
    fi

    mkdir -p "$LOG_DIR"
    cd "$MODEL_DIR"

    # 改为监听所有网卡
    nohup llama-server \
        -m "$model_file" \
        -c 8192 \
        --host 0.0.0.0 \
        --port "$port" \
        > "$LOG_DIR/llm-$port.log" 2>&1 &

    # Wait for service
    echo "  Waiting for LLM service..."
    for i in {1..60}; do
        curl -sf http://127.0.0.1:$port/v1/models >/dev/null 2>&1 && break
        sleep 2
    done

    if curl -sf http://127.0.0.1:$port/v1/models >/dev/null 2>&1; then
        echo "  LLM service started on port $port"
    else
        echo "  ERROR: LLM service failed. Check $LOG_DIR/llm-$port.log"
    fi
}

start_web() {
    echo "Starting RAG Web UI (port 8088)..."

    # Kill existing if running
    pkill -f "web_app.py.*8088" 2>/dev/null || true

    cd "$PROJECT_DIR/01-rag"
    nohup .venv/bin/python web_app.py > "$LOG_DIR/web.log" 2>&1 &

    # Wait for web service
    for i in {1..10}; do
        curl -sf http://127.0.0.1:8088/ >/dev/null 2>&1 && break
        sleep 1
    done

    if curl -sf http://127.0.0.1:8088/ >/dev/null 2>&1; then
        echo "  Web UI started at http://0.0.0.0:8088"
    else
        echo "  ERROR: Web UI failed. Check $LOG_DIR/web.log"
    fi
}

start_ollama() {
    echo "Starting Ollama..."

    if pgrep -f "ollama serve" >/dev/null 2>&1; then
        echo "  Ollama already running"
    else
        brew services start ollama 2>/dev/null || true
        sleep 2
        echo "  Ollama started"
    fi

    echo "  Ollama running at 127.0.0.1:11434"
}

stop_services() {
    echo "Stopping services..."

    pkill -f "llama-server" 2>/dev/null || true
    echo "  llama-server stopped"

    pkill -f "web_app.py" 2>/dev/null || true
    echo "  Web UI stopped"

    docker stop qdrant 2>/dev/null || true
    echo "  Qdrant stopped"

    if [ "${1:-}" == "--ollama" ]; then
        brew services stop ollama 2>/dev/null || true
        echo "  Ollama stopped"
    fi

    echo "Done"
}

status() {
    echo "=== Service Status ==="
    echo ""

    echo "Qdrant:"
    if docker ps --format '{{.Names}}' | grep -q '^qdrant$'; then
        echo "  ✅ Running (0.0.0.0:6333)"
    else
        echo "  ❌ Not running"
    fi

    echo ""
    echo "Embedding Service (llama-server):"
    if curl -sf http://127.0.0.1:8081/v1/models >/dev/null 2>&1; then
        echo "  ✅ Running (0.0.0.0:8081)"
    else
        echo "  ❌ Not running"
    fi

    echo ""
    echo "LLM Service (llama-server):"
    if curl -sf http://127.0.0.1:8080/v1/models >/dev/null 2>&1; then
        echo "  ✅ Running (0.0.0.0:8080)"
    else
        echo "  ❌ Not running"
    fi

    echo ""
    echo "Web UI:"
    if curl -sf http://127.0.0.1:8088/ >/dev/null 2>&1; then
        echo "  ✅ Running (http://0.0.0.0:8088)"
    else
        echo "  ❌ Not running"
    fi

    echo ""
    echo "Ollama:"
    if pgrep -f "ollama serve" >/dev/null 2>&1; then
        echo "  ✅ Running (127.0.0.1:11434)"
    else
        echo "  ❌ Not running"
    fi

    echo ""
    echo "Model files in $MODEL_DIR:"
    ls -lh "$MODEL_DIR"/*.gguf 2>/dev/null || echo "  No .gguf files"
    echo ""
    echo "Qwen models:"
    ls -lh "$MODEL_DIR/Qwen2.5-7B-Instruct-GGUF"/*.gguf 2>/dev/null | head -10 || echo "  No Qwen GGUF files"
}

get_local_ip() {
    if [[ "$OSTYPE" == "darwin"* ]]; then
        ifconfig en0 2>/dev/null | grep 'inet ' | awk '{print $2}' || echo "127.0.0.1"
    else
        hostname -I 2>/dev/null | awk '{print $1}' || echo "127.0.0.1"
    fi
}

case "${1:-rag}" in
    rag)
        echo "=== Starting RAG Mode ==="
        start_qdrant
        start_embedding_service
        echo ""
        echo "RAG mode ready!"
        echo "  - Qdrant: 0.0.0.0:6333"
        echo "  - Embedding: 0.0.0.0:8081"
        echo "  - LLM: Use 'startup.sh llama' to start"
        ;;
    web)
        echo "=== Starting Web UI ==="
        start_web
        LOCAL_IP=$(get_local_ip)
        echo ""
        echo "🌐 Web UI 已启动!"
        echo "   本机访问: http://localhost:8088"
        echo "   局域网访问: http://$LOCAL_IP:8088"
        ;;
    all)
        echo "=== Starting ALL RAG Services ==="
        start_qdrant
        start_embedding_service
        start_llm_llama "Qwen2.5-7B-Instruct-GGUF/qwen2.5-7b-instruct-q4_0.gguf" "8080"
        start_web
        LOCAL_IP=$(get_local_ip)
        echo ""
        echo "╔══════════════════════════════════════════════════════════╗"
        echo "║          ✅ 所有 RAG 服务已启动                        ║"
        echo "╠══════════════════════════════════════════════════════════╣"
        echo "║                                                          ║"
        echo "║  📱 Web UI:     http://$LOCAL_IP:8088                 ║"
        echo "║  🔢 Qdrant:     0.0.0.0:6333                          ║"
        echo "║  📊 Embedding:  0.0.0.0:8081                          ║"
        echo "║  🤖 LLM:        0.0.0.0:8080                         ║"
        echo "║                                                          ║"
        echo "║  其他设备访问: http://$LOCAL_IP:8088                  ║"
        echo "╚══════════════════════════════════════════════════════════╝"
        ;;
    ollama)
        echo "=== Starting Ollama ==="
        start_ollama
        ;;
    llama)
        echo "=== Starting llama-server LLM ==="
        MODEL="${2:-qwen2.5-7b-instruct-q4_0.gguf}"
        PORT="${3:-8080}"
        start_llm_llama "Qwen2.5-7B-Instruct-GGUF/$MODEL" "$PORT"
        ;;
    stop)
        stop_services "${2:-}"
        ;;
    status)
        status
        echo ""
        LOCAL_IP=$(get_local_ip)
        echo "🌐 Web UI 访问地址: http://$LOCAL_IP:8088"
        ;;
    ip)
        LOCAL_IP=$(get_local_ip)
        echo "本机 IP: $LOCAL_IP"
        echo ""
        echo "局域网用户访问: http://$LOCAL_IP:8088"
        ;;
    *)
        echo "Usage: $0 [rag|web|all|ollama|llama|stop|status|ip]"
        echo ""
        echo "Commands:"
        echo "  rag              - Start Qdrant + Embedding (RAG mode)"
        echo "  web              - Start Web UI only"
        echo "  all              - Start ALL services (Qdrant + Embedding + LLM + Web)"
        echo "  ollama           - Start Ollama service"
        echo "  llama <model>   - Start llama-server LLM"
        echo "                    Models: qwen2.5-7b-instruct-q4_0.gguf (recommended)"
        echo "                    Example: $0 llama qwen2.5-7b-instruct-q4_0.gguf 8080"
        echo "  stop [--ollama] - Stop all services"
        echo "  status          - Show service status"
        echo "  ip              - Show LAN IP address"
        exit 1
        ;;
esac
