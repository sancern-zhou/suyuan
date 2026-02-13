"""
调试JSON内容
"""

import json

# 真实的失败案例
real_case = r'''{
  "thought": "用户需要在当前工作目录D:\溯源中搜索一个具体的Word文档文件"2025年臭氧垂直报告7-ok - 副本.docx"。这是一个文件搜索任务，需要使用bash工具来执行搜索命令。"
}'''

print("原始内容:")
print(real_case)
print("\n" + "="*80 + "\n")

# 尝试解析
try:
    data = json.loads(real_case)
    print("解析成功:")
    print(data)
except json.JSONDecodeError as e:
    print(f"解析失败: {e}")
    print(f"\n错误位置: line {e.lineno}, column {e.colno}, char {e.pos}")

    # 显示错误位置附近的内容
    if e.pos is not None:
        start = max(0, e.pos - 20)
        end = min(len(real_case), e.pos + 20)
        print(f"\n错误位置附近的内容:")
        print(repr(real_case[start:end]))
        print(" " * (e.pos - start) + "^")

# 分析字符串内容
print("\n" + "="*80)
print("分析字符串中的引号:")
print("="*80)

# 查找所有的引号
quote_positions = []
for i, char in enumerate(real_case):
    if char == '"':
        quote_positions.append((i, char))

print(f"共找到 {len(quote_positions)} 个引号:")
for pos, char in quote_positions[:20]:  # 只显示前20个
    start = max(0, pos - 10)
    end = min(len(real_case), pos + 10)
    print(f"位置 {pos:3d}: ...{repr(real_case[start:end])}...")
