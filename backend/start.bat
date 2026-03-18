@echo off
REM Windows startup script for Air Pollution Traceability Backend

echo ==========================================
echo Air Pollution Traceability Backend
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
if not exist "venv\" (
    echo.
    echo [INFO] Creating virtual environment...
    python -m venv venv
    if errorlevel 1 (
        echo [ERROR] Failed to create virtual environment
        pause
        exit /b 1
    )
    echo [SUCCESS] Virtual environment created
)

REM Activate virtual environment
echo.
echo [INFO] Activating virtual environment...
call venv\Scripts\activate.bat

REM Check if .env file exists
if not exist ".env" (
    echo.
    echo [WARNING] .env file not found
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

REM Install/upgrade dependencies
echo.
echo [INFO] Installing dependencies...
pip install --upgrade pip
pip install -r requirements.txt
if errorlevel 1 (
    echo [ERROR] Failed to install dependencies
    pause
    exit /b 1
)

echo.
echo [SUCCESS] Dependencies installed
echo.
echo ==========================================
echo Starting FastAPI server...
echo ==========================================
echo.
echo Server will run on: http://localhost:8000
echo API docs available at: http://localhost:8000/docs
echo.
echo Press Ctrl+C to stop the server
echo.

REM Start the server
REM Windows上 --reload 模式有兼容性问题，改用单进程模式
REM 如需热重载，请使用 IDE 的自动重启功能或 start_safe.bat
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --log-level info

REM Deactivate virtual environment on exit
deactivate
