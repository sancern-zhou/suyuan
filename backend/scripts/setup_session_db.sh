#!/bin/bash
# 会话数据库初始化脚本
#
# 使用方法：
# 1. 确保已激活 conda 环境：conda activate /root/miniconda3/envs/backend_py311
# 2. 运行此脚本：bash setup_session_db.sh

set -e

echo "=== 初始化会话数据库 ==="

# 1. 确保 asyncpg 已安装
echo "检查 asyncpg..."
if ! python -c "import asyncpg" 2>/dev/null; then
    echo "安装 asyncpg..."
    pip install asyncpg==0.30.0
fi

# 2. 运行数据库初始化
echo "创建数据库表..."
python -m app.db.init_session_db

echo "=== 初始化完成 ==="
echo ""
echo "接下来需要："
echo "1. 重启后端服务"
echo "2. 后端将自动使用数据库存储会话"
