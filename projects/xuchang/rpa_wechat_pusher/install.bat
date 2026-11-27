@echo off
chcp 65001 >nul
rem 许昌微信群告警推送 agent 安装：创建虚拟环境并安装依赖
setlocal

if not defined PYTHON (
    where py >nul 2>nul && set "PYTHON=py -3.11"
)
if not defined PYTHON set "PYTHON=python"

echo [1/3] 使用解释器: %PYTHON%
%PYTHON% -m venv .venv
if errorlevel 1 (
    echo [错误] 创建虚拟环境失败，请确认已安装 Python 3.11+ 并重试
    exit /b 1
)

echo [2/3] 安装依赖...
.venv\Scripts\python -m pip install -r requirements.txt
if errorlevel 1 (
    echo [错误] 依赖安装失败，请检查网络后重新运行本脚本
    exit /b 1
)
rem wechatauto-replica 以 --no-deps 安装：跳过 winsdk（仅 OCR 兜底用，
rem Python 3.13 无预编译 wheel；跳过它不影响 UIA 主通道发送）
.venv\Scripts\python -m pip install --no-deps wechatauto-replica
if errorlevel 1 (
    echo [错误] wechatauto-replica 安装失败，请检查网络后重新运行本脚本
    exit /b 1
)

echo [3/3] 初始化配置...
if not exist config.toml copy config.example.toml config.toml >nul
if not exist data mkdir data

echo.
echo 安装完成。下一步：
echo   1. 微信电脑版登录后先用文件传输助手验证:
echo      .venv\Scripts\python agent.py --test "测试"  （config.toml 群名先填 filehelper）
echo   2. 编辑 config.toml 填写后端地址、token 和真实群名
echo   3. 验证通过后运行 start_agent.bat 常驻
endlocal
