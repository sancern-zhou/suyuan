"""
修复 tool_adapter.py 的缩进问题
"""
import re

# 读取文件
with open('app/agent/tool_adapter.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# 找到需要修复的行（677-685行）
# 将这些行的缩进增加4个空格，使其在函数内部
fixed_lines = []
for i, line in enumerate(lines):
    line_num = i + 1
    if 677 <= line_num <= 685:
        # 增加缩进
        if line.strip():  # 非空行
            fixed_lines.append('    ' + line)
        else:
            fixed_lines.append(line)
    else:
        fixed_lines.append(line)

# 写回文件
with open('app/agent/tool_adapter.py', 'w', encoding='utf-8') as f:
    f.writelines(fixed_lines)

print("缩进修复完成")
