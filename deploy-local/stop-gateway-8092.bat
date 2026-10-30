@echo off
rem Stop the unified entry gateway (nginx on 8092). The IIS "Operation" site keeps running on 8094.
L:\nginx\nginx.exe -p M:/suyuan-guangdong/deploy-local/nginx-8092/ -c conf/nginx.conf -s stop
timeout /t 1 /nobreak >nul
netstat -ano | findstr ":8092" | findstr "LISTENING"
if errorlevel 1 echo 8092 released, gateway stopped
