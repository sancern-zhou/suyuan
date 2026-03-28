#!/bin/bash

echo "=== 微信账号状态诊断 ==="
echo ""

STATE_DIR="/home/xckj/suyuan/backend/backend_data_registry/social/weixin"

echo "1. 状态文件检查:"
for account_id in auto_mn87vnmu auto_mn8860lf; do
    state_file="$STATE_DIR/$account_id/account.json"
    if [ -f "$state_file" ]; then
        echo "  [$account_id]"
        python3 << EOF
import json
with open('$state_file') as f:
    data = json.load(f)
    token = data.get('token', '')
    bot_id = data.get('bot_id', '')
    print(f"    Token: {'✓ 有效' if token else '✗ 空'} ({token[:20]}...)")
    print(f"    Bot ID: {bot_id or '(空)'}")
    print(f"    Context tokens: {len(data.get('context_tokens', {}))} 个")
EOF
    else
        echo "  [$account_id] ✗ 状态文件不存在"
    fi
done

echo ""
echo "2. 当前运行中的后端进程:"
ps aux | grep "uvicorn app.main:app" | grep -v grep || echo "  ✗ 后端未运行"

echo ""
echo "3. 建议操作:"
echo "  如果重启后登录丢失，请查看后端日志中的以下信息："
echo "  - 'weixin_start_token_check': 检查配置 token"
echo "  - 'state_load_attempt': 状态加载尝试"
echo "  - 'loaded_saved_state': 状态加载成功"
echo "  - 'no_saved_state_starting_qr_login': 需要重新扫码"
echo ""
echo "4. 重启后端命令:"
echo "  cd /home/xckj/suyuan/backend && python -m uvicorn app.main:app --reload --port 8000"
