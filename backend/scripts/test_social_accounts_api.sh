#!/bin/bash
# 社交账号API测试脚本

BASE_URL="http://localhost:8000"

echo "========================================="
echo "社交账号API测试"
echo "========================================="
echo ""

# 颜色定义
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 测试函数
test_api() {
    local name=$1
    local method=$2
    local url=$3
    local data=$4

    echo -e "${YELLOW}测试: ${name}${NC}"
    echo "请求: ${method} ${url}"

    if [ -z "$data" ]; then
        response=$(curl -s -X ${method} "${BASE_URL}${url}" \
            -H "Content-Type: application/json")
    else
        response=$(curl -s -X ${method} "${BASE_URL}${url}" \
            -H "Content-Type: application/json" \
            -d "${data}")
    fi

    echo "响应: ${response}"
    echo ""

    # 检查是否成功
    if echo "$response" | grep -q "detail"; then
        echo -e "${RED}❌ 失败${NC}"
    else
        echo -e "${GREEN}✅ 成功${NC}"
    fi
    echo ""
    echo "----------------------------------------"
    echo ""
}

# 1. 获取账号列表
test_api "获取账号列表" "GET" "/api/social/accounts"

# 2. 创建新账号
test_api "创建微信账号" "POST" "/api/social/accounts/weixin" \
    '{
        "id": "test_account",
        "name": "测试账号",
        "base_url": "https://ilinkai.weixin.qq.com",
        "allow_from": ["*"],
        "auto_start": false
    }'

# 3. 获取账号状态
test_api "获取账号状态" "GET" "/api/social/accounts/weixin/test_account/status"

# 4. 启动账号
test_api "启动账号" "POST" "/api/social/accounts/weixin/test_account/start"

# 5. 刷新QR码
test_api "刷新QR码" "POST" "/api/social/accounts/weixin/test_account/refresh-qrcode"

# 6. 删除账号
test_api "删除账号" "DELETE" "/api/social/accounts/weixin/test_account"

echo ""
echo "========================================="
echo "测试完成"
echo "========================================="
