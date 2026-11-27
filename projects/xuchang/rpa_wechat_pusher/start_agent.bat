@echo off
chcp 65001 >nul
cd /d %~dp0
if not exist .venv\Scripts\python.exe (
    echo [错误] 尚未安装，请先运行 install.bat
    pause
    exit /b 1
)
if not exist config.toml (
    echo [错误] 缺少 config.toml，请复制 config.example.toml 并填写
    pause
    exit /b 1
)
echo 启动告警推送 agent（日志见 data\agent.log；停止：关闭本窗口或 Ctrl+C）
.venv\Scripts\python.exe agent.py
pause
