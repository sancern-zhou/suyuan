#!/bin/bash

# 大气污染溯源分析系统 - 数据库初始化脚本 (Linux/macOS)

echo "========================================"
echo "大气污染溯源分析系统"
echo "数据库初始化脚本"
echo "========================================"
echo

SERVER="180.184.30.94"
USERNAME="sa"
PASSWORD="#Ph981,6J2bOkWYT7p?5slH$I~g_0itR"
DATABASE="AirPollutionAnalysis"
SCRIPT_FILE="init_history_table_complete.sql"

echo "数据库服务器: $SERVER"
echo "数据库名称: $DATABASE"
echo "SQL脚本: $SCRIPT_FILE"
echo

# 检查 sqlcmd 工具
echo "正在检查 sqlcmd 工具..."
if ! command -v sqlcmd &> /dev/null; then
    echo "[错误] 未找到 sqlcmd 工具！"
    echo
    echo "请安装 SQL Server 命令行工具："
    echo "macOS: brew install msodbcsql17 mssql-tools"
    echo "Linux: https://docs.microsoft.com/en-us/sql/linux/sql-server-linux-setup-tools"
    echo
    exit 1
fi
echo "[✓] sqlcmd 工具已安装"
echo

# 检查脚本文件
echo "正在检查脚本文件..."
if [ ! -f "$SCRIPT_FILE" ]; then
    echo "[错误] 未找到脚本文件: $SCRIPT_FILE"
    echo "请确保脚本文件在当前目录下"
    exit 1
fi
echo "[✓] 脚本文件存在"
echo

echo "========================================"
echo "开始执行数据库初始化..."
echo "========================================"
echo

# 执行 SQL 脚本
sqlcmd -S "$SERVER" -U "$USERNAME" -P "$PASSWORD" -i "$SCRIPT_FILE" -o init_output.log

if [ $? -eq 0 ]; then
    echo
    echo "========================================"
    echo "[成功] 数据库初始化完成！"
    echo "========================================"
    echo
    echo "日志文件: init_output.log"
    echo
    echo "下一步操作："
    echo "1. 查看日志文件确认无错误"
    echo "2. 配置 backend/.env 文件"
    echo "3. 安装 Python 依赖: pip install pyodbc aioodbc"
    echo "4. 运行测试: python test_history_db.py"
    echo
    echo "=========================================="
    echo "执行日志："
    echo "=========================================="
    cat init_output.log
else
    echo
    echo "========================================"
    echo "[失败] 数据库初始化失败！"
    echo "========================================"
    echo
    echo "错误代码: $?"
    echo "请检查日志文件: init_output.log"
    echo
    if [ -f init_output.log ]; then
        echo "=========================================="
        echo "错误日志："
        echo "=========================================="
        cat init_output.log
    fi
    exit 1
fi

echo
