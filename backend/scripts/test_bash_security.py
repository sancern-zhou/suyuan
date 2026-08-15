"""
Bash工具安全测试

测试修复后的bash_tool是否能够防止命令注入攻击
"""

import asyncio
import sys
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.tools.utility.bash_tool import BashTool


async def test_command_injection_prevention():
    """测试命令注入防护"""
    print("\n" + "="*60)
    print("Bash工具安全测试（命令注入防护）")
    print("="*60)

    tool = BashTool()
    test_cases = [
        # 命令注入尝试
        ("命令注入: 分号", "ls; echo 'HACKED'", False),
        ("命令注入: 管道", "ls | whoami", False),
        ("命令注入: 命令替换", "echo $(whoami)", False),
        ("命令注入: 反引号", "echo `whoami`", False),
        ("命令注入: AND连接", "ls && echo HACKED", False),
        ("命令注入: OR连接", "ls || echo HACKED", False),
        ("命令注入: 重定向", "echo test > /tmp/hacked.txt", False),
        ("命令注入: 变量替换", "echo ${HOME}", False),

        # 危险命令
        ("危险命令: rm -rf /", "rm -rf /", False),
        ("危险命令: sudo", "sudo su", False),

        # 安全命令（应该允许）
        ("安全命令: ls", "ls", True),
        ("安全命令: cat", "cat README.md", True),
        ("安全命令: python", "python --version", True),
    ]

    passed = 0
    failed = 0

    for name, command, should_succeed in test_cases:
        print(f"\n测试: {name}")
        print(f"命令: {command}")

        result = await tool.execute(command=command)

        is_blocked = not result.get("success", False)
        expected_blocked = not should_succeed

        if is_blocked == expected_blocked:
            print(f"✅ 通过 - {'被正确阻止' if is_blocked else '正确允许'}")
            if not result.get("success"):
                error = result.get("error", "未知错误")
                print(f"   错误信息: {error[:100]}")
            passed += 1
        else:
            print(f"❌ 失败 - {'应该被阻止但允许了' if should_succeed else '应该允许但被阻止了'}")
            print(f"   结果: {result}")
            failed += 1

    # 汇总
    print("\n" + "="*60)
    print("测试结果汇总")
    print("="*60)
    print(f"通过: {passed}/{len(test_cases)}")
    print(f"失败: {failed}/{len(test_cases)}")

    if failed == 0:
        print("\n✅ 所有安全测试通过！bash工具已成功防止命令注入攻击。")
        return 0
    else:
        print(f"\n❌ {failed} 个测试失败，需要继续修复。")
        return 1


async def test_safe_command_execution():
    """测试安全命令是否能正常执行"""
    print("\n" + "="*60)
    print("Bash工具功能测试（安全命令执行）")
    print("="*60)

    tool = BashTool()
    test_cases = [
        ("基本命令: pwd", "pwd"),
        ("基本命令: echo", "echo hello"),
        ("文件命令: ls", "ls -la"),
        ("Python命令", "python --version"),
    ]

    passed = 0
    failed = 0

    for name, command in test_cases:
        print(f"\n测试: {name}")
        print(f"命令: {command}")

        result = await tool.execute(command=command)

        if result.get("success"):
            print(f"✅ 通过 - 命令执行成功")
            stdout = result.get("data", {}).get("stdout", "")
            if stdout:
                print(f"   输出: {stdout[:100]}...")
            passed += 1
        else:
            print(f"❌ 失败 - 命令执行失败")
            print(f"   错误: {result.get('error', '未知错误')}")
            failed += 1

    print("\n" + "="*60)
    print("测试结果汇总")
    print("="*60)
    print(f"通过: {passed}/{len(test_cases)}")
    print(f"失败: {failed}/{len(test_cases)}")

    return 0 if failed == 0 else 1


async def main():
    """运行所有测试"""
    print("\n" + "="*60)
    print("Bash工具安全测试套件")
    print("="*60)
    print(f"测试时间: {__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    # 测试1: 命令注入防护
    result1 = await test_command_injection_prevention()

    # 测试2: 安全命令执行
    result2 = await test_safe_command_execution()

    # 总体结果
    print("\n" + "="*60)
    print("总体测试结果")
    print("="*60)
    if result1 == 0 and result2 == 0:
        print("✅ 所有测试通过！Bash工具安全修复成功。")
        return 0
    else:
        print("❌ 部分测试失败，需要继续修复。")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
