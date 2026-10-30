@echo off
rem Start backend worker process (must run together with web, otherwise some APIs return 503)
cd /d M:\suyuan-guangdong\backend
if not exist logs mkdir logs
set "PY=M:\suyuan-tools\envs\backend_py311\Scripts\python.exe"
start "suyuan-gd-worker" /B cmd /c ""%PY%" -m app.worker --env-file .env.guangdong > logs\worker.log 2>&1"
echo worker process started. Log: M:\suyuan-guangdong\backend\logs\worker.log
