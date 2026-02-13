@echo off
echo ====================================
echo Dify API Debug Test
echo ====================================
echo.

cd /d %~dp0

echo Activating virtual environment...
call .venv6\Scripts\activate.bat

echo.
echo Running test...
python test_dify_debug.py

echo.
echo Test completed.
pause
