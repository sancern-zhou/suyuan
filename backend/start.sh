#!/bin/bash
# Linux/macOS startup script for Air Pollution Traceability Backend

set -e  # Exit on error

echo "=========================================="
echo "Air Pollution Traceability Backend"
echo "=========================================="
echo ""

# Check if Python is installed
if ! command -v python3 &> /dev/null; then
    echo "[ERROR] Python 3 is not installed"
    echo "Please install Python 3.8+ and try again"
    exit 1
fi

echo "[INFO] Python found"
python3 --version

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo ""
    echo "[INFO] Creating virtual environment..."
    python3 -m venv venv
    echo "[SUCCESS] Virtual environment created"
fi

# Activate virtual environment
echo ""
echo "[INFO] Activating virtual environment..."
source venv/bin/activate

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

# Install/upgrade dependencies
echo ""
echo "[INFO] Installing dependencies..."
pip install --upgrade pip
pip install -r requirements.txt

echo ""
echo "[SUCCESS] Dependencies installed"
echo ""
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
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# Deactivate virtual environment on exit
deactivate
