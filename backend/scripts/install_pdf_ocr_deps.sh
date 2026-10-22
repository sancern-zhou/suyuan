#!/bin/bash

# PDF解析工具依赖安装脚本

echo "========================================="
echo "PDF解析工具依赖安装"
echo "========================================="
echo ""

# 检测操作系统
if [[ "$OSTYPE" == "linux-gnu"* ]]; then
    OS="linux"
elif [[ "$OSTYPE" == "darwin"* ]]; then
    OS="macos"
else
    OS="windows"
fi

echo "检测到操作系统: $OS"
echo ""

# 安装Python依赖
echo "========================================="
echo "安装Python依赖..."
echo "========================================="
pip install pdf2image Pillow pdfplumber

if [ $? -ne 0 ]; then
    echo "❌ Python依赖安装失败"
    exit 1
fi

echo "✅ Python依赖安装成功"
echo ""

# 安装系统依赖
echo "========================================="
echo "安装系统依赖..."
echo "========================================="

if [ "$OS" == "linux" ]; then
    echo "安装poppler-utils（Linux）..."
    sudo apt-get update
    sudo apt-get install -y poppler-utils tesseract-ocr libtesseract-dev

    if [ $? -eq 0 ]; then
        echo "✅ 系统依赖安装成功"
    else
        echo "⚠️  系统依赖安装失败，请手动安装"
    fi

elif [ "$OS" == "macos" ]; then
    echo "安装poppler（macOS）..."
    brew install poppler tesseract

    if [ $? -eq 0 ]; then
        echo "✅ 系统依赖安装成功"
    else
        echo "⚠️  系统依赖安装失败，请手动安装"
    fi

else
    echo "Windows系统请手动安装："
    echo "1. 下载poppler-windows: https://github.com/oschwartz10612/poppler-windows/releases/"
    echo "2. 下载Tesseract: https://github.com/UB-Mannheim/tesseract/wiki"
fi

echo ""
echo "========================================="
echo "安装完成！"
echo "========================================="
echo ""
echo "下一步："
echo "1. 运行测试: python tests/test_parse_pdf_tool.py"
echo "2. 查看文档: docs/parse_pdf_dependencies.md"
echo ""
