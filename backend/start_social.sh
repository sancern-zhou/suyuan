#!/bin/bash
# Social Platform Integration Startup Script

set -e  # Exit on error

echo "=========================================="
echo "Social Platform Integration"
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
    echo "Please create .env file with necessary configuration"
    exit 1
fi

# Check if social config exists
if [ ! -f "config/social_config.yaml" ]; then
    echo ""
    echo "[WARNING] Social config file not found"
    echo "Using default configuration"
fi

# Install/upgrade dependencies
echo ""
echo "[INFO] Installing/updating dependencies..."
pip install --upgrade pip
pip install -r requirements.txt

echo ""
echo "[SUCCESS] Dependencies installed"
echo ""
echo "=========================================="
echo "Starting Social Platform Integration..."
echo "=========================================="
echo ""

# Start the social platform integration
python -m app.social.cli

# Deactivate virtual environment on exit
deactivate
