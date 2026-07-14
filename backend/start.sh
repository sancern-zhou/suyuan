#!/bin/bash
# Linux/macOS startup script for Air Pollution Traceability Backend

set -e  # Exit on error

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${SCRIPT_DIR}"

echo "=========================================="
echo "Air Pollution Traceability Backend"
echo "=========================================="
echo ""

# Use the project conda environment.
CONDA_ENV_PATH="${CONDA_ENV_PATH:-/root/miniconda3/envs/backend_py311}"
PYTHON_BIN="${CONDA_ENV_PATH}/bin/python"

if [ ! -x "${PYTHON_BIN}" ]; then
    echo "[ERROR] Python not found at ${PYTHON_BIN}"
    echo "Please check CONDA_ENV_PATH or create the backend_py311 conda environment"
    exit 1
fi

echo "[INFO] Using Python: ${PYTHON_BIN}"
"${PYTHON_BIN}" --version

# Check if .env file exists
if [ ! -f ".env" ]; then
    echo ""
    echo "[WARNING] .env file not found"
    echo "Copying .env.example to .env..."
    cp .env.example .env
    echo ""
    echo "[IMPORTANT] Please edit .env file and configure your API keys:"
    echo "- LLM API keys (OpenAI, DeepSeek, or Anthropic)"
    echo "- AMap public key"
    echo "- External API endpoints (if different from defaults)"
    echo ""
    read -p "Press Enter to continue..."
fi

echo "=========================================="
echo "Starting FastAPI server..."
echo "=========================================="
echo ""
echo "Server will run on: http://localhost:8000"
echo "API docs available at: http://localhost:8000/docs"
echo ""
echo "Press Ctrl+C to stop the server"
echo ""

# Start the server
APP_ROLE="${APP_ROLE:-web}"
export APP_ROLE
WORKERS="${WORKERS:-4}"
echo "[INFO] Starting role=${APP_ROLE} with ${WORKERS} worker(s)"
# Authentication must see the raw TCP peer; Nginx owns public-client-IP logging.
"${PYTHON_BIN}" -m uvicorn app.main:app \
    --host 0.0.0.0 \
    --port 8000 \
    --workers "${WORKERS}" \
    --env-file .env \
    --no-proxy-headers
