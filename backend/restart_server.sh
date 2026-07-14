#!/bin/bash
# 重启后端服务器脚本
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONDA_ENV_PATH="${CONDA_ENV_PATH:-/root/miniconda3/envs/backend_py311}"
PYTHON_BIN="${CONDA_ENV_PATH}/bin/python"

echo "=== 重启后端服务器 ==="

if [ ! -x "${PYTHON_BIN}" ]; then
    echo "[ERROR] Python not found at ${PYTHON_BIN}"
    exit 1
fi

# 1. 停止现有进程
echo "停止现有uvicorn进程..."
pkill -9 -f "uvicorn.*app.main"
sleep 2

# 2. 切换到后端目录，uvicorn 使用 --env-file 安全加载 .env
cd "${SCRIPT_DIR}"

# 3. 启动服务器
echo "启动服务器..."
# Authentication must see the raw TCP peer; Nginx owns public-client-IP logging.
nohup "${PYTHON_BIN}" -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000 --env-file .env --no-proxy-headers > /tmp/backend.log 2>&1 &
NEW_PID=$!

# 4. 等待启动
sleep 5

# 5. 检查状态
echo "=== 服务器状态 ==="
ps aux | grep "uvicorn.*app.main" | grep -v grep
echo ""
echo "测试健康检查..."
curl -s --max-time 3 http://localhost:8000/health || echo "服务器尚未就绪，请稍后测试"

echo ""
echo "新进程PID: $NEW_PID"
echo "日志文件: /tmp/backend.log"
