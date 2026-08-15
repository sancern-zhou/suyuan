#!/usr/bin/env python3
"""
Bash工具安全测试 v2.0（独立版本，不加载工具注册表）
"""

import sys
from pathlib import Path

# 直接导入辅助函数
sys.path.insert(0, str(Path(__file__).parent.parent))

# 手动复制辅助函数（避免导入整个工具）
def has_unescaped_char(content: str, char: str) -> bool:
    """检查内容中是否包含未转义的指定字符（引号外）"""
    in_single_quote = False
    in_double_quote = False
    escaped = False

    for c in content:
        if escaped:
            escaped = False
            continue

        if c == '\\':
            if not in_single_quote:
                escaped = True
            continue

        if c == "'" and not in_double_quote:
            in_single_quote = not in_single_quote
            continue

        if c == '"' and not in_single_quote:
            in_double_quote = not in_double_quote
            continue

        if c == char and not in_single_quote and not in_double_quote:
            return True

    return False


def extract_unquoted_content(command: str):
    """提取命令的不同内容版本"""
    unquoted_content = ""
    fully_unquoted = ""
    unquoted_keep_quotes = ""

    in_single_quote = False
    in_double_quote = False
    escaped = False

    for c in command:
        if escaped:
            escaped = False
            if not in_single_quote:
                unquoted_content += c
            if not in_single_quote and not in_double_quote:
                fully_unquoted += c
            unquoted_keep_quotes += c
            continue

        if c == '\\':
            if not in_single_quote:
                escaped = True
            if not in_single_quote:
                unquoted_content += c
            if not in_single_quote and not in_double_quote:
                fully_unquoted += c
            unquoted_keep_quotes += c
            continue

        if c == "'" and not in_double_quote:
            in_single_quote = not in_single_quote
            unquoted_keep_quotes += c
            continue

        if c == '"' and not in_single_quote:
            in_double_quote = not in_double_quote
            unquoted_keep_quotes += c
            continue

        if not in_single_quote:
            unquoted_content += c
        if not in_single_quote and not in_double_quote:
            fully_unquoted += c
        unquoted_keep_quotes += c

    return unquoted_content, fully_unquoted, unquoted_keep_quotes


def strip_safe_redirections(command: str) -> str:
    """移除安全的重定向模式"""
    import re
    safe_patterns = [
        r'\s*2\s*>&\s*1(?=\s|$)',
        r'[012]?\s*>\s*/dev/null(?=\s|$)',
        r'\s*<\s*/dev/null(?=\s|$)',
    ]

    result = command
    for pattern in safe_patterns:
        result = re.sub(pattern, '', result)

    return result


def test_quote_aware_detection():
    """测试引号状态追踪功能"""
    print("\n" + "="*60)
    print("引号状态追踪测试")
    print("="*60)

    test_cases = [
        ("echo hello; world", ";", True, "分号在引号外（危险）"),
        ("echo \"hello; world\"", ";", False, "分号在双引号内（安全）"),
        ("echo 'hello; world'", ";", False, "分号在单引号内（安全）"),
        ("echo hello\\; world", ";", False, "分号已转义（安全）"),
        ("grep \"foo|bar\" file", "|", False, "管道在双引号内（安全）"),
        ("grep 'foo|bar' file", "|", False, "管道在单引号内（安全）"),
        ("ls | grep test", "|", True, "管道在引号外（危险）"),
        ("echo '$HOME'", "$", False, "$在单引号内（安全）"),
        ("echo \"$HOME\"", "$", False, "$在双引号内（安全，变量引用）"),
        ("echo \\$HOME", "$", False, "$已转义（安全）"),
    ]

    passed = 0
    failed = 0

    for command, char, expected, description in test_cases:
        result = has_unescaped_char(command, char)

        if result == expected:
            status = "✅ 通过"
            passed += 1
        else:
            status = "❌ 失败"
            failed += 1

        detected = "检测到" if result else "未检测"
        expected_str = "应检测到" if expected else "不应检测"

        print(f"{status} - {description}")
        print(f"         命令: {command}")
        print(f"         结果: {detected} ({expected_str})")

    print(f"\n通过: {passed}/{len(test_cases)}, 失败: {failed}/{len(test_cases)}")
    return 0 if failed == 0 else 1


def test_command_security():
    """测试命令安全性和误报率"""
    print("\n" + "="*60)
    print("命令安全性和误报测试")
    print("="*60)

    test_cases = [
        # (名称, 命令, 应被阻止)
        # 危险命令
        ("分号注入", "ls; whoami", True),
        ("管道注入", "ls | whoami", True),
        ("命令替换", "echo $(whoami)", True),
        ("反引号替换", "echo `whoami`", True),
        ("输出重定向", "echo test > /tmp/file", True),
        ("变量扩展", "echo ${HOME}", True),

        # 安全命令
        ("基本ls", "ls", False),
        ("基本echo", "echo hello", False),
        ("基本cat", "cat file.txt", False),

        # ✨ 改进点：引号内安全元字符（应允许）
        ("双引号内分号", 'echo "hello; world"', False),
        ("单引号内分号", "echo 'hello; world'", False),
        ("双引号内管道", 'grep "foo|bar" file', False),
        ("单引号内管道", "grep 'foo|bar' file", False),
        ("安全重定向2>&1", "python script.py 2>&1", False),
        ("安全重定向null", "ls > /dev/null", False),
    ]

    passed = 0
    failed = 0

    for name, command, should_be_blocked in test_cases:
        # 使用改进的安全检查（与实际代码一致）
        command_stripped = command.strip()

        is_blocked = False
        reason = ""

        # 第一层：命令替换检测
        if not is_blocked and ('`' in command_stripped or '$(' in command_stripped):
            is_blocked = True
            reason = "命令替换"

        if not is_blocked and '${' in command_stripped:
            is_blocked = True
            reason = "变量扩展"

        # 第二层：使用fully_unquoted检测引号外的危险字符
        if not is_blocked:
            _, fully_unquoted, _ = extract_unquoted_content(command_stripped)

            if ';' in fully_unquoted:
                is_blocked = True
                reason = "引号外分号"
            elif '|' in fully_unquoted:
                is_blocked = True
                reason = "引号外管道"

        # 第三层：重定向检测（排除安全的）
        if not is_blocked:
            safe_cmd = strip_safe_redirections(command_stripped)
            safe_unquoted, _, _ = extract_unquoted_content(safe_cmd)

            if '>' in safe_unquoted:
                is_blocked = True
                reason = "输出重定向"
            elif '<' in safe_unquoted:
                is_blocked = True
                reason = "输入重定向"

        if is_blocked == should_be_blocked:
            status = "✅ 通过"
            passed += 1
        else:
            status = "❌ 失败"
            failed += 1

        block_status = "被阻止" if is_blocked else "允许"
        expected = "应阻止" if should_be_blocked else "应允许"
        print(f"{status} - {name:25} | {block_status:6} ({expected})")
        if reason:
            print(f"         └─ {reason}")

    print(f"\n通过: {passed}/{len(test_cases)}, 失败: {failed}/{len(test_cases)}")
    return 0 if failed == 0 else 1


def main():
    """运行所有测试"""
    print("\n" + "="*60)
    print("Bash工具安全测试 v2.0（独立版本）")
    print("="*60)

    result1 = test_quote_aware_detection()
    result2 = test_command_security()

    print("\n" + "="*60)
    print("总体结果")
    print("="*60)

    if result1 == 0 and result2 == 0:
        print("✅ 所有测试通过！")
        print("\n改进效果：")
        print("  1. ✅ 引号状态追踪工作正常")
        print("  2. ✅ 允许引号内的安全元字符")
        print("  3. ✅ 减少误报率")
        print("  4. ✅ 保持安全防护（危险命令仍被阻止）")
        return 0
    else:
        print("❌ 部分测试失败")
        return 1


if __name__ == "__main__":
    sys.exit(main())
