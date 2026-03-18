@echo off
REM Clean restart script for backend
echo ========================================
echo Backend Clean Restart Script
echo ========================================

echo.
echo [Step 1] Cleaning Python cache files...
cd /d D:\溯源\backend
for /d /r %%d in (__pycache__) do @if exist "%%d" rd /s /q "%%d"
del /s /q *.pyc 2>nul
echo [OK] Cache cleaned

echo.
echo [Step 2] Stopping any running backend process...
echo Please manually stop the backend (Ctrl+C in the terminal)
echo Press any key after you have stopped the backend...
pause >nul

echo.
echo [Step 3] Starting backend server...
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

pause
