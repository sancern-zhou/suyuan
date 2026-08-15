#!/bin/bash
# 知识库索引优化快速脚本

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "=================================================="
echo "  知识库Collection索引优化工具"
echo "=================================================="
echo ""
echo "请选择模式："
echo "  1) 检查所有知识库（不执行重建）"
echo "  2) 交互式重建（需要确认）"
echo "  3) 强制重建（跳过确认）"
echo ""
read -p "请输入选项 [1-3]: " choice

case $choice in
  1)
    echo ""
    echo "🔍 检查模式..."
    python optimize_all_knowledge_bases.py --dry-run
    ;;
  2)
    echo ""
    echo "🔧 交互式重建模式..."
    python optimize_all_knowledge_bases.py
    ;;
  3)
    echo ""
    echo "⚡ 强制重建模式..."
    echo "警告：将跳过所有确认提示！"
    read -p "确认继续？ [yes/no]: " confirm
    if [[ $confirm == "yes" || $confirm == "y" ]]; then
        python optimize_all_knowledge_bases.py --force
    else
        echo "已取消"
        exit 0
    fi
    ;;
  *)
    echo "无效选项"
    exit 1
    ;;
esac

echo ""
echo "完成！"
