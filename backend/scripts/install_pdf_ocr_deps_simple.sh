#!/bin/bash
# PDF解析工具依赖快速安装脚本
# 使用方法: bash install_pdf_ocr_deps_simple.sh

echo "========================================="
echo "PDF解析工具依赖快速安装"
echo "========================================="
echo ""

# 激活conda环境
echo "激活conda环境: backend_py311"
source /root/miniconda3/etc/profile.d/conda.sh
conda activate backend_py311

if [ $? -ne 0 ]; then
    echo "❌ 无法激活conda环境"
    exit 1
fi

echo "✅ Conda环境已激活"
echo "当前Python: $(which python)"
echo ""

# 安装Python依赖
echo "========================================="
echo "安装Python依赖..."
echo "========================================="

pip install pdf2image Pillow pdfplumber

if [ $? -eq 0 ]; then
    echo "✅ Python依赖安装成功"
else
    echo "❌ Python依赖安装失败"
    exit 1
fi

echo ""

# 检查系统依赖
echo "========================================="
echo "检查系统依赖..."
echo "========================================="

if command -v pdftoppm &> /dev/null; then
    echo "✅ poppler-utils 已安装"
else
    echo "❌ poppler-utils 未安装"
    echo ""
    echo "请手动安装poppler-utils:"
    echo "  Linux/Ubuntu: sudo apt-get install poppler-utils"
    echo "  macOS: brew install poppler"
    echo "  Windows: 下载并安装 poppler-windows"
    echo "           https://github.com/oschwartz10612/poppler-windows/releases/"
fi

echo ""
echo "========================================="
echo "安装完成！"
echo "========================================="
echo ""
echo "验证安装:"
echo "  python check_pdf_ocr_deps.py"
echo ""
