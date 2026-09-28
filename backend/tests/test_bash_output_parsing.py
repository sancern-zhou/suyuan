"""
测试bash工具输出的解析
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


def test_bash_output_parsing():
    """测试bash工具输出的解析"""
    parser = LLMResponseParser()

    print("="*80)
    print("Bash工具输出解析测试")
    print("="*80)

    # 从日志中提取的真实bash输出
    bash_output = '''{
  "status": "success",
  "success": true,
  "data": {
    "stdout": " 驱动器 D 中的卷没有标签。\n 卷的序列号是 C24D-A6FD\n\n D:\\溯源 的目录\n\n2026/02/06  17:06    <DIR>          .\n2026/02/07  23:41    <DIR>          ..\n2026/01/28  11:38    <DIR>          .claude\n2025/12/16  14:41    <DIR>          .cursor\n2026/02/08  01:27    <DIR>          .git\n2025/12/23  12:04    <DIR>          .github\n2025/11/10  12:54    <DIR>          .pytest_cache\n2025/10/23  19:28    <DIR>          .venv5\n2025/12/03  19:04    <DIR>          .vscode\n2026/02/08  10:42    <DIR>          backend\n2025/12/29  20:44    <DIR>          backend_data_registry\n2025/12/09  23:45    <DIR>          data\n2025/12/25  11:01    <DIR>          doc\n2026/02/08  12:52    <DIR>          docs\n2025/12/28  23:04    <DIR>          D?tmp\n2025/11/07  13:43    <DIR>          D?溯源frontendsrc\n2025/11/07  13:50    <DIR>          D?溯源frontendsrccomponentsvisualization\n2026/02/08  01:17    <DIR>          frontend\n2025/12/04  12:08    <DIR>          hub\n2025/12/18  12:01",
    "stderr": "",
    "exit_code": 0,
    "command": "dir /ad 2>nul || echo 'No subdirectories found'",
    "working_directory": "D:\\溯源"
  },
  "metadata": {
    "tool_name": "bash",
    "timeout": 30,
    "stdout_truncated": false,
    "stderr_truncated": false
  },
  "summary": "✅ 命令执行成功: dir /ad 2>nul || echo 'No subdirectories found'\n输出:  驱动器 D 中的卷没有标签。\n 卷的序列号是 C24D-A6FD\n\n D:\\溯源 的目录\n\n2026/02/06  17:06    <DIR>          .\n2026/02/07  23:..."
  }
}'''

    print("\n原始内容（包含bash输出）:")
    print("长度:", len(bash_output))

    # 检查这个JSON是否有效
    print("\n" + "="*80)
    print("步骤1：验证原始JSON格式")
    print("="*80)

    try:
        data = json.loads(bash_output)
        print("✅ 原始JSON有效！")
        print(f"数据键: {list(data.keys())}")
    except json.JSONDecodeError as e:
        print(f"❌ 原始JSON无效: {e}")
        print(f"错误位置: line {e.lineno}, column {e.colno}, char {e.pos}")

        # 显示错误位置附近的内容
        if e.pos is not None:
            start = max(0, e.pos - 50)
            end = min(len(bash_output), e.pos + 50)
            print(f"\n错误位置附近:")
            print(repr(bash_output[start:end]))
            print(" " * (e.pos - start) + "^")

    # 步骤2：检查特殊字符
    print("\n" + "="*80)
    print("步骤2：检查特殊字符")
    print("="*80)

    # 查找所有非ASCII字符
    special_chars = []
    for i, char in enumerate(bash_output):
        if ord(char) > 127:
            special_chars.append((i, char, hex(ord(char)), repr(char)))

    print(f"非ASCII字符数量: {len(special_chars)}")
    if special_chars[:20]:  # 只显示前20个
        print("\n前20个非ASCII字符:")
        for pos, char, hex_val, repr_val in special_chars[:20]:
            context_start = max(0, pos - 10)
            context_end = min(len(bash_output), pos + 10)
            print(f"  位置 {pos:4d}: {char} (U+{hex_val[2:]}) {repr_val}")
            print(f"    上下文: {repr(bash_output[context_start:context_end])}")

    # 查找特殊模式
    print("\n特殊模式检查:")
    print(f"包含 'D?tmp': {'D?tmp' in bash_output}")
    print(f"包含 'D?溯源': {'D?溯源' in bash_output}")
    print(f"包含 'D?溯源frontend': {'D?溯源frontend' in bash_output}")

    # 检查引号平衡
    print(f"\n引号统计:")
    print(f"双引号数量: {bash_output.count('"')}")
    print(f"是否成对: {'是' if bash_output.count('"') % 2 == 0 else '否'}")

    # 检查括号平衡
    open_braces = bash_output.count('{')
    close_braces = bash_output.count('}')
    print(f"\n括号统计:")
    print(f"左括号 {{ : {open_braces}")
    print(f"右括号 }} : {close_braces}")
    print(f"括号匹配: {'是' if open_braces == close_braces else '否'}")

    # 步骤3：测试解析器
    print("\n" + "="*80)
    print("步骤3：使用LLMResponseParser解析")
    print("="*80)

    result = parser.parse(bash_output)
    print(f"解析成功: {result['success']}")

    if result['success']:
        print("✅ 解析成功！")
        print(f"数据键: {list(result['data'].keys())}")
    else:
        print("❌ 解析失败")
        if result.get('error'):
            error = result['error']
            print(f"错误类型: {error.get('error_type')}")
            print(f"错误消息: {error.get('error_msg')}")
            print(f"尝试的策略: {error.get('strategies_tried')}")


if __name__ == "__main__":
    test_bash_output_parsing()
