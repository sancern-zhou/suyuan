@echo off
REM PDF解析工具依赖安装脚本（Windows）

echo =========================================
echo PDF解析工具依赖安装
echo =========================================
echo.

REM 安装Python依赖
echo =========================================
echo 安装Python依赖...
echo =========================================
pip install pdf2image Pillow pdfplumber

if errorlevel 1 (
    echo ❌ Python依赖安装失败
    pause
    exit /b 1
)

echo ✅ Python依赖安装成功
echo.

REM Windows系统依赖
echo =========================================
echo Windows系统请手动安装以下依赖：
echo =========================================
echo.
echo 1. poppler-windows（必需）
echo    下载地址: https://github.com/oschwartz10612/poppler-windows/releases/
echo    解压后将bin目录添加到PATH环境变量
echo.
echo 2. Tesseract OCR（可选）
echo    下载地址: https://github.com/UB-Mannheim/tesseract/wiki
echo    安装后配置环境变量 TESSERACT_CMD
echo.

REM 配置环境变量提示
echo =========================================
echo 配置.env文件（可选）
echo =========================================
echo.
echo 如果需要使用Tesseract OCR，请在 backend/.env 文件中添加：
echo TESSERACT_CMD=D:\Tesseract-OCR\tesseract.exe
echo.

echo =========================================
echo 安装完成！
echo =========================================
echo.
echo 下一步：
echo 1. 手动安装poppler和Tesseract（见上方说明）
echo 2. 运行测试: python tests\test_parse_pdf_tool.py
echo 3. 查看文档: docs\parse_pdf_dependencies.md
echo.
pause
