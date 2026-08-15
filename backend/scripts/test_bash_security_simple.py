"""
Bash工具安全测试（v2.0 - 引号状态追踪）

测试改进后的bash_tool是否：
1. 成功阻止命令注入攻击
2. 减少误报（允许引号内的安全元字符）
"""

import asyncio
import sys
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

# 导入实际的辅助函数
from app.tools.utility.bash_tool import (
    has_unescaped_char,
    extract_unquoted_content,
    strip_safe_redirections,
)


def test_quote_aware_detection():
    """测试引号状态追踪功能"""
    print("\n" + "="*60)
    print("引号状态追踪测试")
    print("="*60)

    test_cases = [
        # (命令, 检测字符, 预期结果, 说明)
        ("echo hello; world", ";", True, "分号在引号外（危险）"),
        ("echo \"hello; world\"", ";", False, "分号在双引号内（安全）"),
        ("echo 'hello; world'", ";", False, "分号在单引号内（安全）"),
        ("echo hello\\; world", ";", False, "分号已转义（安全）"),
        ("grep \"foo|bar\" file", "|", False, "管道在双引号内（安全）"),
        ("grep 'foo|bar' file", "|", False, "管道在单引号内（安全）"),
        ("ls | grep test", "|", True, "管道在引号外（危险）"),
        ("echo '$HOME'", "$", False, "$在单引号内（安全）"),
        ("echo \"$HOME\"", "$", True, "$在双引号内仍有特殊含义（危险）"),
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

    print("\n" + "="*60)
    print("测试结果汇总")
    print("="*60)
    print(f"通过: {passed}/{len(test_cases)}")
    print(f"失败: {failed}/{len(test_cases)}")

    return 0 if failed == 0 else 1


def test_command_injection_prevention():
    """测试命令注入防护"""
    print("\n" + "="*60)
    print("命令注入防护测试")
    print("="*60)

    test_cases = [
        # 命令注入尝试（都应该被阻止）
        ("分号命令注入", "ls; echo 'HACKED'", True),
        ("管道命令注入", "ls | whoami", True),
        ("命令替换$()", "echo $(whoami)", True),
        ("反引号命令替换", "echo `whoami`", True),
        ("AND命令连接", "ls && echo HACKED", True),
        ("OR命令连接", "ls || echo HACKED", True),
        ("输出重定向", "echo test > /tmp/hacked.txt", True),
        ("输入重定向", "cat < /etc/passwd", True),
        ("变量替换", "echo ${HOME}", True),

        # 危险命令（都应该被阻止）
        ("删除系统文件", "rm -rf /", True),
        ("权限提升", "sudo su", True),
        ("关机命令", "shutdown now", True),

        # 安全命令（都应该允许）- 改进版测试
        ("基本命令ls", "ls", False),
        ("基本命令pwd", "pwd", False),
        ("基本命令echo", "echo hello", False),
        ("基本命令cat", "cat file.txt", False),
        ("Python命令", "python --version", False),

        # ✨ 新增：引号内安全元字符（应该允许，这是改进点）
        ("双引号内分号", 'echo "hello; world"', False),
        ("单引号内分号", "echo 'hello; world'", False),
        ("双引号内管道", 'grep "foo|bar" file', False),
        ("单引号内管道", "grep 'foo|bar' file", False),
        ("安全的重定向", "python script.py 2>&1", False),  # 2>&1是安全的
    ]

    passed = 0
    failed = 0

    for name, command, should_be_blocked in test_cases:
        # 使用新的检测逻辑
        command_stripped = command.strip()
        unquoted_content, _, _ = extract_unquoted_content(command_stripped)

        # 检测危险元字符
        is_blocked = False
        error = ""

        # 检测分号
        if has_unescaped_char(unquoted_content, ';'):
            is_blocked = True
            error = "检测到引号外的分号"

        # 检测管道
        if not is_blocked and has_unescaped_char(unquoted_content, '|'):
            is_blocked = True
            error = "检测到引号外的管道"

        # 检测命令替换
        if not is_blocked and ('`' in command_stripped or '$(' in command_stripped):
            is_blocked = True
            error = "检测到命令替换"

        # 检测重定向（排除安全的）
        if not is_blocked:
            safe_command = strip_safe_redirections(command_stripped)
            if has_unescaped_char(safe_command, '>'):
                is_blocked = True
                error = "检测到输出重定向"
            elif has_unescaped_char(safe_command, '<'):
                is_blocked = True
                error = "检测到输入重定向"

        expected_blocked = should_be_blocked

        if is_blocked == expected_blocked:
            status = "✅ 通过"
            passed += 1
        else:
            status = "❌ 失败"
            failed += 1

        block_status = "被阻止" if is_blocked else "允许"
        expected_str = "应被阻止" if should_be_blocked else "应允许"
        print(f"{status} - {name:30} | {block_status:6} ({expected_str})")
        if error:
            print(f"         └─ {error}")

    print("\n" + "="*60)
    print("测试结果汇总")
    print("="*60)
    print(f"通过: {passed}/{len(test_cases)}")
    print(f"失败: {failed}/{len(test_cases)}")

    if failed == 0:
        print("\n✅ 所有安全测试通过！")
        print("\n关键改进点：")
        print("  1. ✅ 引号状态追踪（减少误报）")
        print("  2. ✅ 允许引号内的安全元字符")
        print("  3. ✅ 安全重定向检测（如 2>&1）")
        return 0
    else:
        print(f"\n❌ {failed} 个测试失败，需要继续修复。")
        return 1


def main():
    """运行所有测试"""
    print("\n" + "="*60)
    print("Bash工具安全测试套件 v2.0")
    print("="*60)
    print(f"测试时间: {__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    # 测试1: 引号状态追踪
    result1 = test_quote_aware_detection()

    # 测试2: 命令注入防护
    result2 = test_command_injection_prevention()

    # 总体结果
    print("\n" + "="*60)
    print("总体测试结果")
    print("="*60)
    if result1 == 0 and result2 == 0:
        print("✅ 所有测试通过！Bash工具安全改进成功。")
        return 0
    else:
        print("❌ 部分测试失败，需要继续修复。")
        return 1


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
