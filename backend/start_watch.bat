@echo off
REM Windows startup script with hot-reload using watchfiles
REM Requires: pip install watchfiles

echo ==========================================
echo Air Pollution Traceability Backend (Watch Mode)
echo ==========================================
echo.

REM Check if Python is installed
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python is not installed or not in PATH
    pause
    exit /b 1
)

echo [INFO] Python found
python --version

REM Activate virtual environment
if exist ".venv\Scripts\activate.bat" (
    call .venv\Scripts\activate.bat
) else if exist "venv\Scripts\activate.bat" (
    call venv\Scripts\activate.bat
)

REM Check if watchfiles is installed
pip show watchfiles >nul 2>&1
if errorlevel 1 (
    echo [INFO] Installing watchfiles for hot-reload support...
    pip install watchfiles
)

echo.
echo ==========================================
echo Starting FastAPI server (Watch Mode)...
echo ==========================================
echo.
echo Server will run on: http://localhost:8000
echo API docs available at: http://localhost:8000/docs
echo.
echo Press Ctrl+C to stop the server
echo.
echo [INFO] Using watchfiles for hot-reload (Windows compatible)
echo.

REM Start the server with watchfiles
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --log-level info --reload

deactivate
