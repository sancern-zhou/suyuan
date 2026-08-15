#!/bin/bash
# 批量处理臭氧垂直报告 - 快速启动脚本

# 设置脚本目录
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

# 检查环境变量
if [ -z "$QWEN_VL_API_KEY" ]; then
    echo "错误：未设置 QWEN_VL_API_KEY 环境变量"
    echo "请先设置：export QWEN_VL_API_KEY='your-api-key'"
    exit 1
fi

# 检查配置文件
if [ ! -f "batch_ozone_config.json" ]; then
    echo "错误：配置文件不存在：batch_ozone_config.json"
    exit 1
fi

# 检查报告目录
REPORTS_DIR=$(python3 -c "import json; print(json.load(open('batch_ozone_config.json'))['reports_dir'])")
if [ ! -d "$REPORTS_DIR" ]; then
    echo "错误：报告目录不存在：$REPORTS_DIR"
    echo "请修改 batch_ozone_config.json 中的 reports_dir 路径"
    exit 1
fi

# 显示配置信息
echo "======================================"
echo "臭氧垂直报告批量处理"
echo "======================================"
echo "报告目录：$REPORTS_DIR"
echo "开始时间：$(date '+%Y-%m-%d %H:%M:%S')"
echo "======================================"
echo ""

# 运行处理脚本
python3 batch_ozone_report_processor.py

# 检查执行结果
if [ $? -eq 0 ]; then
    echo ""
    echo "======================================"
    echo "处理完成！"
    echo "======================================"
    echo "查看报告：cat batch_ozone_report_processor_report.json"
    echo "查看进度：cat batch_ozone_report_processor_progress.json"
    echo "======================================"
else
    echo ""
    echo "处理失败，请查看日志"
    exit 1
fi
