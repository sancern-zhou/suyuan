#!/bin/bash

echo "=== 微信二维码修复验证 ==="
echo ""

cd /home/xckj/suyuan/backend

# 1. 检查代码语法
echo "1. 检查代码语法..."
python -c "
import sys
sys.path.insert(0, '.')
from app.channels.weixin import WeixinChannel
print('✓ WeixinChannel 类定义正确')
print('✓ _init_qr_login 方法存在' if hasattr(WeixinChannel, '_init_qr_login') else '✗ 缺少 _init_qr_login')
print('✓ _wait_for_qr_scan 方法存在' if hasattr(WeixinChannel, '_wait_for_qr_scan') else '✗ 缺少 _wait_for_qr_scan')
"

echo ""
echo "2. 检查后端进程..."
if ps aux | grep -v grep | grep "uvicorn app.main:app" > /dev/null; then
    echo "✓ 后端正在运行"
    PID=$(ps aux | grep -v grep | grep "uvicorn app.main:app" | awk '{print $2}')
    echo "  PID: $PID"
else
    echo "✗ 后端未运行"
    echo "  启动命令: cd /home/xckj/suyuan/backend && python -m uvicorn app.main:app --reload --port 8000"
fi

echo ""
echo "3. 清理旧的临时账号（可选）..."
echo "  编辑文件: vim /home/xckj/suyuan/backend/config/social_config.yaml"
echo "  删除 auto_ 开头的账号配置"

echo ""
echo "=== 修复说明 ==="
echo ""
echo "✓ 新增 _init_qr_login() 方法 - 只生成二维码，不等待扫码"
echo "✓ 新增 _wait_for_qr_scan() 方法 - 等待已有二维码的扫码"
echo "✓ 修改 start() 方法 - 检测已有二维码，避免重复生成"
echo "✓ 修改 auto-create API - 异步生成二维码，快速响应"
echo ""
echo "=== 测试步骤 ==="
echo ""
echo "1. 刷新前端页面"
echo "2. 点击'扫码添加微信'"
echo "3. 观察：第一次就应该能看到二维码（不需要刷新第二次）"
echo ""
echo "如果仍有问题，请分享："
echo "- 前端控制台的错误信息"
echo "- 后端日志中的 'qrcode_' 相关日志"
