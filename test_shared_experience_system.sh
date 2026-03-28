#!/bin/bash

# Agent共享经验库系统测试脚本

echo "========================================="
echo "Agent共享经验库系统测试"
echo "========================================="
echo ""

# 1. 测试文件是否存在
echo "1. 检查共享经验文件..."
if [ -f "backend_data_registry/social/shared/SHARED_EXPERIENCES.md" ]; then
    echo "   ✓ 共享经验文件存在"
    echo "   当前经验数：$(grep -c '^## 经验' backend_data_registry/social/shared/SHARED_EXPERIENCES.md)"
else
    echo "   ✗ 共享经验文件不存在"
    exit 1
fi

echo ""

# 2. 测试辅助函数
echo "2. 测试辅助函数..."
cd backend
python3 << 'EOF'
import sys
sys.path.insert(0, '.')

from app.social.shared_experience_utils import (
    generate_anonymous_id,
    parse_shared_experiences,
    get_next_experience_id,
    update_experience_stats,
    search_experiences_by_keywords
)

# 测试匿名ID生成
anon_id = generate_anonymous_id("test_user")
print(f"   ✓ 匿名ID生成: {anon_id}")

# 测试解析
exps = parse_shared_experiences("../backend_data_registry/social/shared/SHARED_EXPERIENCES.md")
print(f"   ✓ 解析经验数: {len(exps)}")

if exps:
    print(f"   ✓ 第一条经验: {exps[0]['id']} - {exps[0]['stars']}星 - {exps[0]['usage_count']}次使用")

# 测试获取下一个ID
next_id = get_next_experience_id("../backend_data_registry/social/shared/SHARED_EXPERIENCES.md")
print(f"   ✓ 下一个经验ID: {next_id}")

# 测试搜索
results = search_experiences_by_keywords("../backend_data_registry/social/shared/SHARED_EXPERIENCES.md", ["VOCs", "PMF"])
print(f"   ✓ 搜索'VOCs PMF': 找到{len(results)}条结果")

EOF
cd ..
echo ""

# 3. 测试grep搜索
echo "3. 测试grep工具搜索..."
if grep -q "VOCs" backend_data_registry/social/shared/SHARED_EXPERIENCES.md; then
    echo "   ✓ grep搜索'VOCs'成功"
else
    echo "   ✗ grep搜索失败"
fi

echo ""

# 4. 测试单元测试
echo "4. 运行单元测试..."
cd backend
python -m pytest tests/test_shared_experience_utils.py -v --tb=short -q
TEST_RESULT=$?
cd ..

echo ""
echo "========================================="
if [ $TEST_RESULT -eq 0 ]; then
    echo "✓ 所有测试通过"
else
    echo "✗ 部分测试失败"
fi
echo "========================================="
