"""
测试真实的失败案例
"""
import sys
import os
import json

# 设置UTF-8编码输出
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app.utils.llm_response_parser import LLMResponseParser

# 从日志中提取的真实失败案例
real_failure = '''{
  "thought": "用户询问当前工作目录（D:\\\\溯源）是否包含"报告模板"目录。历史记录显示，我们之前使用了`dir /ad`命令列出了目录结构，但输出被截断了，只显示了部分内容。为了准确回答用户的问题，我需要执行一个更具体的命令来检查是否存在名为"报告模板"的子目录。",
  "reasoning": "用户的问题是一个关于文件系统结构的简单查询。我需要检查D:\\\\溯源目录下是否存在"报告模板"子目录。我可以使用`dir`命令配合通配符或直接检查特定目录名。考虑到Windows命令行，最直接的方法是使用`dir /ad "D:\\\\溯源\\\\报告模板"`来检查该目录是否存在。如果命令成功且有输出，则说明目录存在；如果命令失败或没有输出，则说明目录不存在。这不需要调用任何大气环境分析工具，只需要使用系统命令（bash工具）即可。",
  "action": {
    "type": "TOOL_CALL",
    "tool": "bash",
    "args": {
      "command": "dir /ad \\"D:\\\\溯源\\\\报告模板\\"",
    }
  }
}'''

print("="*80)
print("真实失败案例测试")
print("="*80)

print("\n原始内容:")
print(real_failure[:400])

# 步骤1：验证原始JSON是否有效
print("\n" + "="*80)
print("步骤1：验证原始JSON格式")
print("="*80)

try:
    data = json.loads(real_failure)
    print("✅ 原始JSON有效！")
    print(f"数据键: {list(data.keys())}")
except json.JSONDecodeError as e:
    print(f"❌ 原始JSON无效: {e}")
    print(f"错误位置: line {e.lineno}, column {e.colno}")
    print(f"错误字符: position {e.pos}")

    # 显示错误位置附近的内容
    if e.pos is not None:
        start = max(0, e.pos - 30)
        end = min(len(real_failure), e.pos + 30)
        print(f"\n错误位置附近:")
        print(real_failure[start:end])
        print(" " * (e.pos - start) + "^")

# 步骤2：使用json-repair修复
print("\n" + "="*80)
print("步骤2：使用json-repair修复")
print("="*80)

from json_repair import repair_json

repaired = repair_json(real_failure)
print(f"修复后长度: {len(repaired)} (原始: {len(real_failure)})")

try:
    data = json.loads(repaired)
    print("✅ 修复后JSON有效！")
    print(f"数据键: {list(data.keys())}")
except json.JSONDecodeError as e:
    print(f"❌ 修复后仍然无效: {e}")

# 步骤3：使用LLMResponseParser
print("\n" + "="*80)
print("步骤3：使用LLMResponseParser完整解析")
print("="*80)

parser = LLMResponseParser()
result = parser.parse(real_failure)

print(f"解析成功: {result['success']}")

if result['success']:
    print("✅ 解析成功！")
    print(f"数据键: {list(result['data'].keys())}")
    if 'action' in result['data']:
        action = result['data']['action']
        print(f"工具: {action.get('tool')}")
        print(f"命令: {action.get('args', {}).get('command')}")
else:
    print("❌ 解析失败")
    if result.get('error'):
        error = result['error']
        print(f"错误类型: {error.get('error_type')}")
        print(f"错误消息: {error.get('error_msg')}")

# 步骤4：检查具体问题
print("\n" + "="*80)
print("步骤4：分析具体问题")
print("="*80)

# 检查JSON结构
print("检查JSON结构完整性:")

# 计算括号
open_braces = real_failure.count('{')
close_braces = real_failure.count('}')
print(f"左括号 {{ : {open_braces}")
print(f"右括号 }} : {close_braces}")
print(f"括号匹配: {'✅ 是' if open_braces == close_braces else '❌ 否'}")

# 检查引号
quotes = real_failure.count('"')
print(f"双引号数量: {quotes}")
print(f"引号成对: {'✅ 是' if quotes % 2 == 0 else '❌ 否（奇数个引号）'}")

# 检查是否被截断
print(f"\n字符串结尾:")
print(repr(real_failure[-100:]))

if 'command' in real_failure:
    print("\n⚠️ 问题发现：'command' 字段存在但值可能不完整")
    # 查找 command 字段
    cmd_start = real_failure.find('"command":')
    if cmd_start != -1:
        cmd_section = real_failure[cmd_start:cmd_start+200]
        print(f"command字段附近: {cmd_section}")
