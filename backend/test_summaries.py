"""测试 Office 工具摘要生成"""
import sys
sys.path.insert(0, 'D:/溯源/backend')

from app.agent.tool_adapter_backup import get_tool_summaries

# 获取工具摘要
summaries = get_tool_summaries()

# 查找 Office 工具
lines = summaries.split('\n')
for i, line in enumerate(lines):
    if 'processor' in line.lower():
        # 打印当前行和下一行
        print(line)
        if i + 1 < len(lines):
            print(lines[i + 1])
        print('---')
