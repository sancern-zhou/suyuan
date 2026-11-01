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

echo [3/3] 初始化配置...
if not exist config.toml copy config.example.toml config.toml >nul
if not exist data mkdir data

echo.
echo 安装完成。下一步：
echo   1. 编辑 config.toml，填写后端地址、token 和目标群名
echo   2. 微信电脑版登录后运行: .venv\Scripts\python agent.py --test "测试"
echo   3. 验证通过后运行 start_agent.bat 常驻
endlocal
