#!/bin/bash
# 清理 HEARTBEAT.md 文件

HEARTBEAT_DIR="backend_data_registry/social/heartbeat"
BACKUP_FILE="${HEARTBEAT_DIR}/HEARTBEAT.md.bak"
NEW_FILE="${HEARTBEAT_DIR}/HEARTBEAT.md.new"
TARGET_FILE="${HEARTBEAT_DIR}/HEARTBEAT.md"

echo "正在清理 HEARTBEAT.md 文件..."

# 备份原文件
echo "1. 备份原文件..."
sudo cp "${TARGET_FILE}" "${BACKUP_FILE}"
if [ $? -eq 0 ]; then
    echo "   备份成功: ${BACKUP_FILE}"
else
    echo "   备份失败"
    exit 1
fi

# 替换为清洁版本
echo "2. 替换为清洁版本..."
sudo cp "${NEW_FILE}" "${TARGET_FILE}"
if [ $? -eq 0 ]; then
    echo "   替换成功"
else
    echo "   替换失败"
    exit 1
fi

# 设置正确的权限
echo "3. 设置文件权限..."
sudo chmod 644 "${TARGET_FILE}"
sudo chown root:root "${TARGET_FILE}"

# 显示新文件内容
echo ""
echo "清理完成！新文件内容："
echo "=================================="
cat "${TARGET_FILE}"
echo "=================================="
echo ""
echo "统计信息："
echo "- 原文件行数: $(wc -l < "${BACKUP_FILE}")"
echo "- 新文件行数: $(wc -l < "${TARGET_FILE}")"
echo "- 备份文件: ${BACKUP_FILE}"
