#!/bin/bash
# 配置检查脚本 - 验证批量处理环境是否配置正确

echo "======================================"
echo "臭氧批量处理 - 配置检查"
echo "======================================"
echo ""

# 颜色定义
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 检查计数
PASS=0
FAIL=0

# 检查函数
check_pass() {
    echo -e "${GREEN}✓${NC} $1"
    ((PASS++))
}

check_fail() {
    echo -e "${RED}✗${NC} $1"
    ((FAIL++))
}

check_warn() {
    echo -e "${YELLOW}⚠${NC} $1"
}

# 1. 检查Python环境
echo "1. 检查Python环境..."
if command -v python3 &> /dev/null; then
    PYTHON_VERSION=$(python3 --version)
    check_pass "Python已安装: $PYTHON_VERSION"
else
    check_fail "Python未安装"
fi

# 2. 检查依赖包
echo ""
echo "2. 检查依赖包..."
REQUIRED_PACKAGES=("httpx" "docx" "structlog")
for package in "${REQUIRED_PACKAGES[@]}"; do
    if python3 -c "import $package" 2>/dev/null; then
        check_pass "依赖包已安装: $package"
    else
        check_fail "依赖包未安装: $package"
    fi
done

# 3. 检查API密钥
echo ""
echo "3. 检查API密钥配置..."
if [ -z "$QWEN_VL_API_KEY" ]; then
    check_fail "未设置QWEN_VL_API_KEY环境变量"
    echo "  请运行: export QWEN_VL_API_KEY='your-api-key'"
else
    KEY_LENGTH=${#QWEN_VL_API_KEY}
    if [ $KEY_LENGTH -gt 20 ]; then
        check_pass "API密钥已配置 (长度: $KEY_LENGTH)"
    else
        check_warn "API密钥长度较短 (长度: $KEY_LENGTH)，请确认是否正确"
    fi
fi

# 4. 检查配置文件
echo ""
echo "4. 检查配置文件..."
CONFIG_FILE="batch_ozone_config.json"
if [ -f "$CONFIG_FILE" ]; then
    check_pass "配置文件存在: $CONFIG_FILE"

    # 检查配置内容
    if command -v jq &> /dev/null; then
        CONCURRENT=$(jq -r '.concurrent_tasks' $CONFIG_FILE)
        if [ "$CONCURRENT" == "1" ]; then
            check_pass "并发配置正确: $CONCURRENT (顺序执行)"
        else
            check_warn "并发配置: $CONCURRENT (建议设置为1)"
        fi

        INTERVAL=$(jq -r '.api_request_interval' $CONFIG_FILE)
        if [ "$INTERVAL" -ge 2 ]; then
            check_pass "请求间隔配置: ${INTERVAL}秒"
        else
            check_warn "请求间隔较短: ${INTERVAL}秒 (建议≥2秒)"
        fi
    else
        check_warn "未安装jq工具，跳过配置文件详细检查"
    fi
else
    check_fail "配置文件不存在: $CONFIG_FILE"
fi

# 5. 检查报告目录
echo ""
echo "5. 检查报告目录..."
if [ -f "$CONFIG_FILE" ]; then
    REPORTS_DIR=$(python3 -c "import json; print(json.load(open('$CONFIG_FILE'))['reports_dir'])" 2>/dev/null)
    if [ -d "$REPORTS_DIR" ]; then
        DOC_COUNT=$(find "$REPORTS_DIR" -name "*.docx" 2>/dev/null | wc -l)
        check_pass "报告目录存在: $REPORTS_DIR (包含 $DOC_COUNT 份报告)"
        if [ $DOC_COUNT -eq 0 ]; then
            check_warn "报告目录为空，请添加待处理的报告文件"
        fi
    else
        check_fail "报告目录不存在: $REPORTS_DIR"
    fi
else
    check_warn "无法检查报告目录（配置文件不存在）"
fi

# 6. 检查脚本权限
echo ""
echo "6. 检查脚本权限..."
SCRIPTS=("batch_ozone_report_processor.py" "test_single_report.py" "run_batch_processor.sh" "run_test.sh")
for script in "${SCRIPTS[@]}"; do
    if [ -f "$script" ]; then
        if [ -x "$script" ]; then
            check_pass "脚本可执行: $script"
        else
            check_warn "脚本无执行权限: $script (运行: chmod +x $script)"
        fi
    else
        check_fail "脚本不存在: $script"
    fi
done

# 7. 网络连接测试
echo ""
echo "7. 检查网络连接..."
if command -v curl &> /dev/null; then
    API_ENDPOINT="https://dashscope.aliyuncs.com"
    HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" --connect-timeout 5 "$API_ENDPOINT" 2>/dev/null)
    if [ "$HTTP_CODE" == "000" ]; then
        check_fail "无法连接到API端点: $API_ENDPOINT"
    else
        check_pass "网络连接正常 (HTTP $HTTP_CODE)"
    fi
else
    check_warn "未安装curl工具，跳过网络检查"
fi

# 总结
echo ""
echo "======================================"
echo "检查总结"
echo "======================================"
echo -e "通过: ${GREEN}$PASS${NC}"
echo -e "失败: ${RED}$FAIL${NC}"
echo ""

if [ $FAIL -eq 0 ]; then
    echo -e "${GREEN}配置检查通过！可以开始批量处理。${NC}"
    echo ""
    echo "下一步："
    echo "1. 测试单份报告: ./run_test.sh \"/path/to/test.docx\""
    echo "2. 开始批量处理: ./run_batch_processor.sh"
    exit 0
else
    echo -e "${RED}发现 $FAIL 个配置问题，请修复后重试。${NC}"
    echo ""
    echo "常见问题："
    echo "- 未设置API密钥: export QWEN_VL_API_KEY='your-key'"
    echo "- 缺少依赖包: pip3 install httpx python-docx structlog"
    echo "- 报告目录不存在: 修改配置文件中的 reports_dir"
    exit 1
fi
