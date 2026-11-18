#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
PORT="${1:-8000}"

echo "=========================================================="
echo "       Smart AI Gateway - Production Deployment          "
echo "=========================================================="
echo "Project Root: $PROJECT_ROOT"
echo "Target Port : $PORT"
echo ""

cd "$PROJECT_ROOT"

test_health() {
    local target_port="$1"
    local max_attempts=15
    local attempt=1
    echo "Verifying service health..."
    while [ $attempt -le $max_attempts ]; do
        if curl -s -f "http://localhost:${target_port}/health/live" > /dev/null 2>&1; then
            echo "[✔] Liveness probe passed: http://localhost:${target_port}/health/live"
            return 0
        fi
        sleep 1
        attempt=$((attempt + 1))
    done
    return 1
}

if command -v docker > /dev/null 2>&1 && docker ps > /dev/null 2>&1; then
    echo "[INFO] Docker engine detected. Deploying via Docker Compose..."
    docker compose -f "$SCRIPT_DIR/docker-compose.yml" build
    docker compose -f "$SCRIPT_DIR/docker-compose.yml" up -d
    if test_health "$PORT"; then
        echo ""
        echo "=========================================================="
        echo "       DEPLOYMENT SUCCESSFUL (Docker Container)           "
        echo "=========================================================="
        echo "Playground UI : http://localhost:$PORT"
        echo "Swagger Docs  : http://localhost:$PORT/docs"
        echo "Health Check  : http://localhost:$PORT/health/live"
        echo "=========================================================="
        exit 0
    else
        echo "[ERROR] Health check failed."
        exit 1
    fi
else
    echo "[INFO] Deploying native production server with Python/Uvicorn..."
    pip install -q -r "$PROJECT_ROOT/requirements.txt"
    pip install -q -e "$PROJECT_ROOT"
    export APP_ENV=production
    export APP_PORT="$PORT"
    export APP_HOST=0.0.0.0
    export PYTHONPATH="$PROJECT_ROOT"
    [ -z "$GATEWAY_API_KEY" ] && export GATEWAY_API_KEY="prod-gw-key-$(openssl rand -hex 16 2>/dev/null || date +%s%N)"
    [ -z "$ENCRYPTION_MASTER_KEY" ] && export ENCRYPTION_MASTER_KEY="prod-enc-master-$(openssl rand -hex 16 2>/dev/null || date +%s%N)"
    [ -z "$ALLOWED_CORS_ORIGINS" ] || [ "$ALLOWED_CORS_ORIGINS" = '["*"]' ] && export ALLOWED_CORS_ORIGINS='["http://localhost:8000","http://127.0.0.1:8000"]'
    export ENABLE_MOCK_GATEWAY="false"
    
    nohup uvicorn app.main:app --host 0.0.0.0 --port "$PORT" > "$PROJECT_ROOT/gateway.log" 2>&1 &
    
    if test_health "$PORT"; then
        echo ""
        echo "=========================================================="
        echo "       DEPLOYMENT SUCCESSFUL (Native Production Server)   "
        echo "=========================================================="
        echo "Playground UI : http://localhost:$PORT"
        echo "Swagger Docs  : http://localhost:$PORT/docs"
        echo "Health Check  : http://localhost:$PORT/health/live"
        echo "Logs          : $PROJECT_ROOT/gateway.log"
        echo "=========================================================="
        exit 0
    else
        echo "[ERROR] Service did not become ready within timeout."
        exit 1
    fi
fi
