@echo off
REM suyuan maintenance daemon launcher (logon autostart or manual)
REM Stop: find PID listening on 8013 and taskkill it.

set SCRIPT_DIR=%~dp0
set ENV_FILE=%SCRIPT_DIR%maintenance.env
if not exist "%ENV_FILE%" (
    echo [ERROR] %ENV_FILE% not found. Copy maintenance.env.example first.
    exit /b 1
)

powershell -NoProfile -Command "try { (New-Object Net.Sockets.TcpClient('127.0.0.1',8013)).Close(); exit 0 } catch { exit 1 }" >nul 2>&1
if %errorlevel%==0 (
    echo maintenance daemon already running on 8013, skip
    exit /b 0
)

start "suyuan-maintenance" /min python "%SCRIPT_DIR%maintenance_daemon.py" --env-file "%ENV_FILE%"
echo maintenance daemon started on 127.0.0.1:8013
