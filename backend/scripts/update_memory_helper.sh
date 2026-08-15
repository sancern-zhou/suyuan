#!/bin/bash
# Helper script to update MEMORY.md with chart interaction preferences
# Usage: sudo bash update_memory_helper.sh

MEMORY_FILE="/home/xckj/suyuan/backend_data_registry/memory/chart/MEMORY.md"
BACKUP_FILE="/home/xckj/suyuan/backend_data_registry/memory/chart/MEMORY.md.backup"
UPDATED_FILE="/home/xckj/suyuan/backend/MEMORY.md.updated"

echo "Updating MEMORY.md with chart interaction preferences..."

# Backup the original file
cp "$MEMORY_FILE" "$BACKUP_FILE"
echo "✓ Backup created at $BACKUP_FILE"

# Copy the updated file
cp "$UPDATED_FILE" "$MEMORY_FILE"
echo "✓ MEMORY.md updated successfully"

# Set proper permissions
chmod 644 "$MEMORY_FILE"
echo "✓ Permissions set to 644"

echo ""
echo "Update complete! The following changes were made:"
echo "  - Added '图表交互偏好' section to user preferences"
echo "  - Added dual-mode support note to historical conclusions"
echo ""
echo "If you need to revert, run: sudo cp $BACKUP_FILE $MEMORY_FILE"
