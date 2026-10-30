@echo off
rem Stop suyuan services (frontend / web / worker)
net stop suyuan-worker
net stop suyuan-web
net stop suyuan-frontend
echo done.
