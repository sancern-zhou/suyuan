#!/bin/bash

echo "=== 测试微信状态保存和加载 ==="
echo ""

# 1. 检查状态文件
echo "1. 检查状态文件..."
STATE_DIR="/home/xckj/suyuan/backend/backend_data_registry/social/weixin"

for account_dir in "$STATE_DIR"/*/; do
    if [ -d "$account_dir" ]; then
        account_id=$(basename "$account_dir")
        echo "  账号: $account_id"
        if [ -f "$account_dir/account.json" ]; then
            echo "    ✓ 状态文件存在"
            token=$(python3 -c "import json; print(json.load(open('$account_dir/account.json')).get('token', '')[:20] + '...'))" 2>/dev/null)
            if [ -n "$token" ] && [ "$token" != "None..." ]; then
                echo "    ✓ Token: $token"
            else
                echo "    ✗ Token 为空或无效"
            fi
        else
            echo "    ✗ 状态文件不存在"
        fi
    fi
done

echo ""
echo "2. 检查配置文件..."
CONFIG_FILE="/home/xckj/suyuan/backend/config/social_config.yaml"
if [ -f "$CONFIG_FILE" ]; then
    echo "  ✓ 配置文件存在"
    python3 << EOF
import yaml
with open('$CONFIG_FILE') as f:
    config = yaml.safe_load(f)
    if 'weixin' in config and 'accounts' in config['weixin']:
        accounts = config['weixin']['accounts']
        print(f"  配置中的账号数量: {len(accounts)}")
        for acc in accounts:
            print(f"    - {acc.get('id')}: {acc.get('name')} (enabled={acc.get('enabled')})")
EOF
else
    echo "  ✗ 配置文件不存在"
fi

echo ""
echo "3. 查看后端日志..."
echo "最近的微信相关日志:"
tail -100 /dev/null 2>/dev/null | grep -i "weixin\|state" || echo "  (无日志输出)"

echo ""
echo "=== 测试完成 ==="
echo ""
echo "建议："
echo "1. 重启后端服务"
echo "2. 观察启动日志，查看 'state_loaded' 和 'weixin_start' 相关日志"
echo "3. 如果状态加载成功，应该看到 'loaded_saved_state' 日志"
echo "4. 如果需要重新登录，会看到 'no_saved_state_starting_qr_login' 日志"
