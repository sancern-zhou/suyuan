@echo off
chcp 65001 >nul
echo ============================================
echo EKMA场景预计算 - 完整ODE模式
echo ============================================
echo.
echo 预计算3个典型场景 (约10-15分钟):
echo   [1] urban      - 城市场景 (VOC/NOx ~ 5)
echo   [2] industrial - 工业区场景 (VOC/NOx ~ 3)
echo   [3] rural      - 农村场景 (VOC/NOx ~ 10)
echo.
echo ============================================
echo.

cd /d "%~dp0"

REM 运行预计算脚本
python app\tools\analysis\pybox_integration\precompute_scenes.py

echo.
pause
