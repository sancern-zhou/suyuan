"""简单验证 word_processor 提示词"""
from app.agent.tool_adapter import get_tool_summaries

summaries = get_tool_summaries()

# 保存到文件
with open('word_processor_prompt.txt', 'w', encoding='utf-8') as f:
    f.write(summaries)

# 提取 word_processor 部分
lines = summaries.split('\n')
start_idx = None
for i, line in enumerate(lines):
    if 'word_processor' in line:
        start_idx = i
        break

if start_idx:
    print("Found word_processor at line", start_idx)
    print("\n=== word_processor section (15 lines) ===")
    for line in lines[start_idx:start_idx+15]:
        print(line)
else:
    print("word_processor NOT FOUND")

print("\n=== Key checks ===")
text = summaries[start_idx:start_idx+1000] if start_idx else ""
print("Contains best practices:", "【insert最佳实践】" in text)
print("No args:null:", "args: null" not in text)
print("Contains example:", "operation" in text and "insert" in text)
