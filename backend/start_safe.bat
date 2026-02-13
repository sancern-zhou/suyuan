@echo off
REM Windows startup script for Air Pollution Traceability Backend (Safe Mode)
REM This script avoids multiprocessing issues on Windows

echo ==========================================
echo Air Pollution Traceability Backend (Safe Mode)
echo ==========================================
echo.

REM Check if Python is installed
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python is not installed or not in PATH
    echo Please install Python 3.8+ and add it to PATH
    pause
    exit /b 1
)

echo [INFO] Python found
python --version

REM Check if virtual environment exists
if not exist ".venv\" (
    if not exist "venv\" (
        echo.
        echo [INFO] Creating virtual environment...
        python -m venv .venv
        if errorlevel 1 (
            echo [ERROR] Failed to create virtual environment
            pause
            exit /b 1
        )
        echo [SUCCESS] Virtual environment created
    )
)

REM Activate virtual environment
if exist ".venv\Scripts\activate.bat" (
    echo.
    echo [INFO] Activating virtual environment (.venv)...
    call .venv\Scripts\activate.bat
) else if exist "venv\Scripts\activate.bat" (
    echo.
    echo [INFO] Activating virtual environment (venv)...
    call venv\Scripts\activate.bat
)

REM Check if .env file exists
if not exist ".env" (
    echo.
    echo [WARNING] .env file not found
    if exist ".env.example" (
        echo Copying .env.example to .env...
        copy .env.example .env
        echo.
        echo [IMPORTANT] Please edit .env file and configure your API keys:
        echo - LLM API keys (OpenAI, DeepSeek, or Anthropic)
        echo - AMap public key
        echo - External API endpoints (if different from defaults)
        echo.
        echo Press any key to continue...
        pause >nul
    )
)

REM Install/upgrade dependencies (only if needed)
echo.
echo [INFO] Checking dependencies...
pip show fastapi >nul 2>&1
if errorlevel 1 (
    echo [INFO] Installing dependencies...
    pip install --upgrade pip
    pip install -r requirements.txt
    if errorlevel 1 (
        echo [ERROR] Failed to install dependencies
        pause
        exit /b 1
    )
    echo [SUCCESS] Dependencies installed
) else (
    echo [INFO] Dependencies already installed
)

echo.
echo ==========================================
echo Starting FastAPI server (Safe Mode)...
echo ==========================================
echo.
echo Server will run on: http://localhost:8000
echo API docs available at: http://localhost:8000/docs
echo.
echo Press Ctrl+C to stop the server
echo.
echo [INFO] Using single-process mode (no hot-reload on Windows)
echo.

REM Start the server in single-process mode to avoid Windows multiprocessing issues
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --log-level info

REM Deactivate virtual environment on exit
deactivate
