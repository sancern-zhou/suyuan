@echo off
REM Fix unpack_office tool - Install missing dependencies
echo ================================================================
echo Fix unpack_office Tool - Install Missing Dependencies
echo ================================================================

echo.
echo [Step 1] Activating conda environment...
call conda activate suyuan
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Failed to activate conda environment 'suyuan'
    pause
    exit /b 1
)

echo.
echo [Step 2] Installing openpyxl...
pip install openpyxl>=3.1.0
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Failed to install openpyxl
    pause
    exit /b 1
)

echo.
echo [Step 3] Verifying installation...
python -c "import openpyxl; print(f'[OK] openpyxl version: {openpyxl.__version__}')"
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] openpyxl import failed
    pause
    exit /b 1
)

echo.
echo [Step 4] Cleaning Python cache...
cd /d D:\溯源\backend
python -c "import pathlib, shutil; cache_dirs = list(pathlib.Path('.').rglob('__pycache__')); [shutil.rmtree(p) for p in cache_dirs]; print(f'[OK] Removed {len(cache_dirs)} cache directories')"

echo.
echo ================================================================
echo Installation Complete!
echo ================================================================
echo.
echo Next steps:
echo 1. Restart the backend server
echo 2. Check startup logs for:
echo    - [info] tool_loaded tool=unpack_office
echo    - [info] agent_instances_created ... multi_expert_tools=61
echo.
echo Press any key to start the backend server...
pause >nul

echo.
echo [Step 5] Starting backend server...
python -m uvicorn app.main:app --reload

pause
