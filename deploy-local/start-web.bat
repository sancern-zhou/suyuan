@echo off
rem Start suyuan services (frontend 5176 / web 8000 / worker)
net start suyuan-frontend 2>nul
net start suyuan-web 2>nul
net start suyuan-worker 2>nul
timeout /t 3 /nobreak >nul
net start | findstr /I "suyuan"
