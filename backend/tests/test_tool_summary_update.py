"""
测试工具摘要是否正确更新（移除了 replace 操作）
"""

import sys
import os

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.agent.tool_adapter import generate_tool_summaries


def test_word_processor_summary():
    """测试 word_processor 的工具摘要是否正确"""
    print("=" * 80)
    print("测试 word_processor 工具摘要")
    print("=" * 80)

    summary = generate_tool_summaries()

    # 检查是否包含 word_processor
    if "word_processor" in summary:
        print("\n✅ 找到 word_processor 工具")

        # 检查是否提到了 search_and_replace
        if "search_and_replace" in summary:
            print("✅ 提到了 search_and_replace 操作")
        else:
            print("❌ 未提到 search_and_replace 操作")

        # 检查是否仍然提到 replace（应该没有）
        # 注意：要排除 "batch_replace" 的情况
        lines = summary.split("\n")
        for line in lines:
            if "word_processor" in line:
                # 找到 word_processor 所在的行
                print(f"\n📋 word_processor 的摘要行:\n{line.strip()}")

                # 检查是否有 "replace," 或 " replace " (但排除 batch_replace 和 search_and_replace)
                if ", replace," in line or " replace " in line:
                    if "batch_replace" not in line and "search_and_replace" not in line:
                        print("❌ 仍然提到独立的 replace 操作")
                        return False
                    else:
                        print("✅ replace 只出现在 batch_replace 或 search_and_replace 中（正确）")
                else:
                    print("✅ 没有提到独立的 replace 操作")
                break
    else:
        print("\n❌ 未找到 word_processor 工具")


def test_ppt_processor_summary():
    """测试 ppt_processor 的工具摘要是否正确"""
    print("\n" + "=" * 80)
    print("测试 ppt_processor 工具摘要")
    print("=" * 80)

    summary = generate_tool_summaries()

    # 检查是否包含 ppt_processor
    if "ppt_processor" in summary:
        print("\n✅ 找到 ppt_processor 工具")

        # 检查是否提到了 search_and_replace
        if "search_and_replace" in summary:
            print("✅ 提到了 search_and_replace 操作")
        else:
            print("❌ 未提到 search_and_replace 操作")

        # 检查是否仍然提到 replace（应该没有）
        lines = summary.split("\n")
        for line in lines:
            if "ppt_processor" in line:
                # 找到 ppt_processor 所在的行
                print(f"\n📋 ppt_processor 的摘要行:\n{line.strip()}")

                # 检查是否有 "replace," 或 " replace "
                if ", replace," in line or " replace " in line:
                    if "search_and_replace" not in line:
                        print("❌ 仍然提到独立的 replace 操作")
                        return False
                    else:
                        print("✅ replace 只出现在 search_and_replace 中（正确）")
                else:
                    print("✅ 没有提到独立的 replace 操作")
                break
    else:
        print("\n❌ 未找到 ppt_processor 工具")


def main():
    print("\n[START] 测试工具摘要更新\n")

    test_word_processor_summary()
    test_ppt_processor_summary()

    print("\n" + "=" * 80)
    print("[DONE] 测试完成")
    print("=" * 80)


if __name__ == "__main__":
    main()
