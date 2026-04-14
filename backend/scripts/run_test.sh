#!/bin/bash
# 测试单份报告处理 - 快速启动脚本

# 设置脚本目录
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

# 检查参数
if [ -z "$1" ]; then
    echo "用法：./run_test.sh <报告文件路径>"
    echo "示例：./run_test.sh /path/to/2022年1月1日臭氧垂直.docx"
    exit 1
fi

TEST_FILE="$1"

# 检查文件是否存在
if [ ! -f "$TEST_FILE" ]; then
    echo "错误：文件不存在：$TEST_FILE"
    exit 1
fi

# 检查环境变量
if [ -z "$QWEN_VL_API_KEY" ]; then
    echo "警告：未设置 QWEN_VL_API_KEY 环境变量"
    echo "请先设置：export QWEN_VL_API_KEY='your-api-key'"
fi

# 显示测试信息
echo "======================================"
echo "测试单份报告处理"
echo "======================================"
echo "测试文件：$TEST_FILE"
echo "开始时间：$(date '+%Y-%m-%d %H:%M:%S')"
echo "======================================"
echo ""

# 运行测试脚本
python3 test_single_report.py --file "$TEST_FILE"

# 检查执行结果
if [ $? -eq 0 ]; then
    echo ""
    echo "======================================"
    echo "测试完成！"
    echo "======================================"
    echo "查看报告：cat test_report.json"
    echo "查看输出：ls -la test_output/"
    echo "======================================"
else
    echo ""
    echo "测试失败，请查看日志"
    exit 1
fi
