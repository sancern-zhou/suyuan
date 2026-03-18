#!/bin/bash
# Linux系统类型检测脚本

echo "========== Linux系统信息检测 =========="
echo ""

# 1. 检测系统发行版
echo "1. 系统发行版信息:"
if [ -f /etc/os-release ]; then
    . /etc/os-release
    echo "   发行版: $NAME"
    echo "   版本: $VERSION"
    echo "   ID: $ID"
    echo "   ID_LIKE: $ID_LIKE"
elif [ -f /etc/redhat-release ]; then
    echo "   $(cat /etc/redhat-release)"
elif [ -f /etc/debian_version ]; then
    echo "   Debian Version: $(cat /etc/debian_version)"
else
    echo "   未知系统"
fi

echo ""

# 2. 检测系统架构
echo "2. 系统架构:"
echo "   $(uname -m)"

echo ""

# 3. 检测内核版本
echo "3. 内核版本:"
echo "   $(uname -r)"

echo ""

# 4. 检查已安装的ODBC驱动
echo "4. 已安装的ODBC驱动:"
odbcinst -q -d 2>/dev/null
if [ $? -ne 0 ]; then
    echo "   未找到odbcinst命令或未安装驱动"
fi

echo ""

# 5. 检查unixODBC是否安装
echo "5. unixODBC安装状态:"
if command -v odbcinst &> /dev/null; then
    echo "   unixODBC已安装: $(odbcinst --version)"
else
    echo "   unixODBC未安装"
fi

echo ""

# 6. 检查SQL Server驱动
echo "6. SQL Server ODBC驱动状态:"
if odbcinst -q -d | grep -i "sql server" > /dev/null 2>&1; then
    echo "   已安装的SQL Server驱动:"
    odbcinst -q -d | grep -i "sql server"
else
    echo "   未安装SQL Server ODBC驱动"
fi

echo ""
echo "========== 检测完成 =========="
