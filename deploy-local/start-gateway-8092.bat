@echo off
rem Start unified entry gateway: nginx on 8092 (public 113.108.142.147:8093 maps to this host 8092)
rem   /        -> ops platform (IIS "Operation" site, rebound to 8094)
rem   /suyuan/ -> agent platform (serve-frontend.mjs : 5176)
if not exist M:\suyuan-guangdong\deploy-local\nginx-8092\logs mkdir M:\suyuan-guangdong\deploy-local\nginx-8092\logs
start "suyuan-gd-nginx-8092" /MIN "L:\nginx\nginx.exe" -p M:/suyuan-guangdong/deploy-local/nginx-8092/ -c conf/nginx.conf
echo gateway started: :8092/ = ops platform,  :8092/suyuan/ = agent platform
timeout /t 2 /nobreak >nul
netstat -ano | findstr ":8092" | findstr "LISTENING"
