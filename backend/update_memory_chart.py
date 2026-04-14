#!/usr/bin/env python3
"""
Update MEMORY.md with chart interaction preferences

This script adds the new "图表交互偏好" section to the user preferences.
Run with: python update_memory_chart.py
"""

import os

MEMORY_FILE = "/home/xckj/suyuan/backend_data_registry/memory/chart/MEMORY.md"

# Read the current content
with open(MEMORY_FILE, 'r', encoding='utf-8') as f:
    content = f.read()

# Check if already updated
if "图表交互偏好" in content:
    print("MEMORY.md already contains the chart interaction preferences.")
    print("No update needed.")
    exit(0)

# Find the "用户偏好" section and add the new entries
old_section = """## 用户偏好
- 时间基准：使用ISO 8601格式（如'2026-01-01T00:00:00'）
- 数据查询：明确指定站点和时间范围
- 图表设计：偏好时序图展示多污染物浓度变化
- 图表设计：偏好极坐标系图表展示风向与污染物关系
- 图表设计：偏好平滑渐变效果的风玫瑰图，避免扇区划分"""

new_section = """## 用户偏好
- 时间基准：使用ISO 8601格式（如'2026-01-01T00:00:00'）
- 数据查询：明确指定站点和时间范围
- 图表设计：偏好时序图展示多污染物浓度变化
- 图表设计：偏好极坐标系图表展示风向与污染物关系
- 图表设计：偏好平滑渐变效果的风玫瑰图，避免扇区划分
- **图表交互偏好**：
  - 生成报告时：优先选择平滑静态图（matplotlib contourf）
  - 数据探索时：优先选择交互式图表（ECharts polar + heatmap）
  - 极坐标图：特别强调需要平滑渐变效果，无扇区边界"""

# Replace the old section with the new one
updated_content = content.replace(old_section, new_section)

# Write back to the file
with open(MEMORY_FILE, 'w', encoding='utf-8') as f:
    f.write(updated_content)

print("MEMORY.md updated successfully!")
print("Added '图表交互偏好' section to user preferences.")
