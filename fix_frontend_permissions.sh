#!/bin/bash
# 修复前端权限问题并重启服务

echo "========================================="
echo "修复前端权限并重启"
echo "========================================="
echo ""

echo "步骤1: 清理 Vite 缓存..."
sudo rm -rf node_modules/.vite
if [ $? -eq 0 ]; then
    echo "✓ Vite缓存已清理"
else
    echo "✗ 清理失败，请手动执行: sudo rm -rf node_modules/.vite"
    exit 1
fi

echo ""
echo "步骤2: 启动前端服务..."
npm run dev
