#!/bin/bash
# 多微信账号支持测试脚本

echo "========================================="
echo "多微信账号支持测试"
echo "========================================="
echo ""

# 颜色定义
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${YELLOW}1. 检查后端服务...${NC}"
if curl -s http://localhost:8000/api/social/accounts > /dev/null 2>&1; then
    echo -e "${GREEN}✓ 后端服务运行中${NC}"
else
    echo -e "${RED}✗ 后端服务未启动${NC}"
    echo "请先启动后端: cd backend && python -m uvicorn app.main:app --reload"
    exit 1
fi

echo ""
echo -e "${YELLOW}2. 检查前端服务...${NC}"
if curl -s http://localhost:5174 > /dev/null 2>&1; then
    echo -e "${GREEN}✓ 前端服务运行中${NC}"
else
    echo -e "${RED}✗ 前端服务未启动${NC}"
    echo "请先启动前端: cd frontend && npm run dev"
    exit 1
fi

echo ""
echo -e "${YELLOW}3. 检查配置文件...${NC}"
if [ -f "config/social_config.yaml" ]; then
    echo -e "${GREEN}✓ 配置文件存在${NC}"
else
    echo -e "${RED}✗ 配置文件不存在${NC}"
    echo "请确保 config/social_config.yaml 存在"
fi

echo ""
echo -e "${YELLOW}4. 测试API接口...${NC}"
echo "获取账号列表..."
RESPONSE=$(curl -s http://localhost:8000/api/social/accounts)
echo "响应: $RESPONSE"

echo ""
echo -e "${YELLOW}5. 检查状态目录...${NC}"
if [ -d "backend_data_registry/social/weixin" ]; then
    echo -e "${GREEN}✓ 状态目录存在${NC}"
    echo "账号目录:"
    ls -la backend_data_registry/social/weixin/ 2>/dev/null || echo "  （暂无账号）"
else
    echo -e "${YELLOW}⚠ 状态目录不存在（首次运行正常）${NC}"
fi

echo ""
echo "========================================="
echo -e "${GREEN}测试完成！${NC}"
echo "========================================="
echo ""
echo "接下来可以："
echo "1. 访问前端管理页面: http://localhost:5174/social-accounts"
echo "2. 创建新账号并测试登录"
echo "3. 查看后端日志了解详细信息"
echo ""
echo "如有问题，请查看："
echo "- 后端日志: 终端输出"
echo "- 完成总结: MULTI_WEIXIN_COMPLETION_SUMMARY.md"
echo "- 设计文档: backend/docs/multi_weixin_accounts_design.md"
