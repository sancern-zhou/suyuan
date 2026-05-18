#!/bin/bash
# 路径迁移修复脚本
# 用于修复 chart_image_renderer/tool.py 和迁移数据

echo "===== 路径迁移修复脚本 ====="

# 步骤1：修复 chart_image_renderer/tool.py（需要root权限）
echo "步骤1：修复 chart_image_renderer/tool.py ..."
sudo sed -i 's|OUTPUT_DIR = Path("/home/xckj/suyuan/backend_data_registry/chart_images")|# ✅ 使用统一路径配置\nfrom app.utils.path_config import get_chart_images_dir\nOUTPUT_DIR = get_chart_images_dir()|' /home/xckj/suyuan/backend/app/tools/visualization/chart_image_renderer/tool.py

if [ $? -eq 0 ]; then
    echo "✅ chart_image_renderer/tool.py 修复成功"
else
    echo "❌ chart_image_renderer/tool.py 修复失败"
fi

# 步骤2：验证所有路径已修复
echo ""
echo "步骤2：验证修复结果..."
REMAINING=$(grep -r "suyuan/backend_data_registry" /home/xckj/suyuan/backend/app --include="*.py" | wc -l)
echo "剩余未修复路径数：$REMAINING"

if [ "$REMAINING" -eq 0 ]; then
    echo "✅ 所有路径已修复完成"
else
    echo "⚠️ 仍有 $REMAINING 处未修复"
    grep -rn "suyuan/backend_data_registry" /home/xckj/suyuan/backend/app --include="*.py"
fi

# 步骤3：迁移旧数据到新目录
echo ""
echo "步骤3：迁移旧数据到新目录..."
OLD_DIR="/home/xckj/suyuan/backend_data_registry"
NEW_DIR="/home/xckj/suyuan/backend/backend_data_registry"

if [ -d "$OLD_DIR" ]; then
    echo "发现旧目录：$OLD_DIR"
    echo "开始迁移数据..."

    # 使用 rsync 同步数据（保留权限、时间戳等）
    rsync -av --progress "$OLD_DIR/" "$NEW_DIR/"

    if [ $? -eq 0 ]; then
        echo "✅ 数据迁移成功"
    else
        echo "❌ 数据迁移失败"
        exit 1
    fi

    # 备份旧目录
    echo ""
    echo "备份旧目录..."
    mv "$OLD_DIR" "${OLD_DIR}_old_$(date +%Y%m%d_%H%M%S)"

    if [ $? -eq 0 ]; then
        echo "✅ 旧目录已备份"
    else
        echo "⚠️ 旧目录备份失败，请手动处理"
    fi
else
    echo "⚠️ 旧目录不存在，无需迁移"
fi

# 步骤4：创建验证脚本
echo ""
echo "步骤4：创建验证脚本..."
cat > /tmp/verify_paths.py << 'EOF'
#!/usr/bin/env python3
"""验证路径配置是否正确"""
from pathlib import Path

# 检查新目录
NEW_DIR = Path("/home/xckj/suyuan/backend/backend_data_registry")
print(f"新目录存在: {NEW_DIR.exists()}")
print(f"新目录内容: {list(NEW_DIR.iterdir())[:5]}")

# 检查旧目录
OLD_DIR = Path("/home/xckj/suyuan/backend_data_registry")
print(f"旧目录存在: {OLD_DIR.exists()}")

# 测试 path_config
try:
    from backend.app.utils.path_config import (
        get_data_registry,
        get_memory_dir,
        get_reports_dir
    )
    print(f"\npath_config 测试:")
    print(f"  data_registry: {get_data_registry()}")
    print(f"  memory_dir: {get_memory_dir()}")
    print(f"  reports_dir: {get_reports_dir()}")
    print("✅ path_config 配置正确")
except Exception as e:
    print(f"❌ path_config 测试失败: {e}")
EOF

python3 /tmp/verify_paths.py

echo ""
echo "===== 修复完成 ====="
echo "请重启后端服务让修改生效："
echo "  cd /home/xckj/suyuan/backend && python -m uvicorn app.main:app --reload"
