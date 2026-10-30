@echo off
rem Start local frontend static server + reverse proxy (port 5176)
if not exist M:\suyuan-guangdong\backend\logs mkdir M:\suyuan-guangdong\backend\logs
start "suyuan-gd-frontend" /B cmd /c ""M:\suyuan-tools\node\node.exe" M:\suyuan-guangdong\deploy-local\serve-frontend.mjs > M:\suyuan-guangdong\backend\logs\frontend.log 2>&1"
echo frontend started: http://localhost:5176/suyuan/
timeout /t 2 /nobreak >nul
netstat -ano | findstr ":5176" | findstr "LISTENING"
