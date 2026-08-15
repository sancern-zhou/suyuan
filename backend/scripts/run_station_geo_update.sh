#!/bin/bash
# 站点地理信息更新工具 - 快速启动脚本

set -e  # 遇到错误立即退出

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
CONFIG_DIR="$PROJECT_ROOT/config"

echo "================================"
echo "站点地理信息更新工具"
echo "================================"
echo ""

# 检查 Python 环境
if ! command -v python3 &> /dev/null; then
    echo "错误: 未找到 python3 命令"
    exit 1
fi

# 检查依赖
echo "检查依赖..."
python3 -c "import pyodbc, structlog" 2>/dev/null || {
    echo "错误: 缺少必要的依赖包"
    echo "请运行: pip install pyodbc structlog"
    exit 1
}
echo "依赖检查通过 ✓"
echo ""

# 检查配置文件
if [ ! -f "$CONFIG_DIR/station_district_results_with_type_id.json" ]; then
    echo "错误: 未找到配置文件 station_district_results_with_type_id.json"
    exit 1
fi
echo "配置文件检查通过 ✓"
echo ""

# 菜单选择
echo "请选择操作："
echo "1) 测试单个城市的匹配情况（推荐先执行）"
echo "2) 执行全量更新"
echo "3) 验证更新结果"
echo "4) 完整流程（测试+更新+验证）"
echo "5) 退出"
echo ""
read -p "请输入选项 (1-5): " choice

case $choice in
    1)
        echo ""
        read -p "请输入要测试的城市名称（如：广州）: " city_name
        if [ -z "$city_name" ]; then
            echo "错误: 城市名称不能为空"
            exit 1
        fi
        echo ""
        echo "测试城市: $city_name"
        echo "================================"
        cd "$SCRIPT_DIR"
        python3 test_city_matching.py "$city_name"
        ;;
    2)
        echo ""
        echo "执行全量更新..."
        echo "================================"
        cd "$SCRIPT_DIR"
        python3 update_station_geo_info.py
        echo ""
        echo "更新完成！"
        echo "输出文件: $CONFIG_DIR/station_district_results_with_type_id_updated.json"
        ;;
    3)
        echo ""
        echo "验证更新结果..."
        echo "================================"
        cd "$SCRIPT_DIR"
        python3 validate_station_geo_update.py
        echo ""
        echo "验证完成！"
        echo "验证报告: $CONFIG_DIR/station_geo_update_report.txt"
        ;;
    4)
        echo ""
        echo "执行完整流程..."
        echo "================================"
        echo ""
        echo "[步骤 1/3] 测试单个城市..."
        read -p "请输入要测试的城市名称（如：广州，直接回车跳过）: " city_name
        echo ""
        if [ -n "$city_name" ]; then
            cd "$SCRIPT_DIR"
            python3 test_city_matching.py "$city_name"
            echo ""
        fi

        echo "[步骤 2/3] 执行全量更新..."
        cd "$SCRIPT_DIR"
        python3 update_station_geo_info.py
        echo ""

        echo "[步骤 3/3] 验证更新结果..."
        cd "$SCRIPT_DIR"
        python3 validate_station_geo_update.py
        echo ""

        echo "================================"
        echo "完整流程执行完成！"
        echo ""
        echo "输出文件："
        echo "  - 更新后的JSON: $CONFIG_DIR/station_district_results_with_type_id_updated.json"
        echo "  - 验证报告: $CONFIG_DIR/station_geo_update_report.txt"
        echo "  - 未匹配站点: $CONFIG_DIR/station_district_results_with_type_id_updated_unmatched.json"
        echo ""
        echo "下一步："
        echo "  1. 查看验证报告"
        echo "  2. 检查未匹配站点列表（如果有）"
        echo "  3. 确认无误后替换原文件"
        echo "================================"
        ;;
    5)
        echo "退出"
        exit 0
        ;;
    *)
        echo "错误: 无效的选项"
        exit 1
        ;;
esac

echo ""
