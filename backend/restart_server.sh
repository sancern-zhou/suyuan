#!/bin/bash
# 重启后端服务器脚本
echo "=== 重启后端服务器 ==="

# 1. 停止现有进程
echo "停止现有uvicorn进程..."
pkill -9 -f "uvicorn.*app.main"
sleep 2

# 2. 确保环境变量生效
cd /home/xckj/suyuan/backend
export $(cat .env | grep -v '^#' | xargs)

# 3. 启动服务器
echo "启动服务器..."
nohup python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000 > /tmp/backend.log 2>&1 &
NEW_PID=$!

# 4. 等待启动
sleep 5

# 5. 检查状态
echo "=== 服务器状态 ==="
ps aux | grep "uvicorn.*app.main" | grep -v grep
echo ""
echo "测试健康检查..."
curl -s --max-time 3 http://localhost:8000/health || echo "服务器尚未就绪，请稍后测试"

echo ""
echo "新进程PID: $NEW_PID"
echo "日志文件: /tmp/backend.log"
