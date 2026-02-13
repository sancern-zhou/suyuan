"""
测试 Office 工具的提示词是否正确生成
"""
import sys
import os

# 添加项目路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app.agent.tool_adapter import get_tool_summaries


def test_word_processor_prompt():
    """测试 word_processor 工具的提示词"""
    print("=" * 80)
    print("测试 word_processor 工具提示词生成")
    print("=" * 80)

    # 获取工具摘要
    summaries = get_tool_summaries()

    # 打印查询工具部分
    print("\n【查询工具部分】")
    print("=" * 80)

    # 提取 word_processor 相关行
    lines = summaries.split('\n')
    word_processor_lines = []
    in_word_processor = False

    for i, line in enumerate(lines):
        if 'word_processor' in line:
            in_word_processor = True
        if in_word_processor:
            word_processor_lines.append(line)
            # 如果遇到下一个工具，停止
            if i > 0 and '• ' in line and 'word_processor' not in line:
                break

    print('\n'.join(word_processor_lines))

    # 验证关键内容
    print("\n" + "=" * 80)
    print("验证关键内容")
    print("=" * 80)

    full_text = '\n'.join(word_processor_lines)

    checks = {
        "contains_operations": "read(读取)" in full_text,
        "contains_insert": "insert(插入)" in full_text,
        "contains_example": '{"path' in full_text,
        "contains_best_practice_title": "【insert最佳实践】" in full_text,
        "contains_bp1": "position=\"end\"" in full_text,
        "contains_bp2": "target需精确匹配" in full_text,
        "contains_bp3": "建议先read" in full_text,
        "contains_bp4": "search_and_replace" in full_text,
        "contains_full_example": "operation" in full_text and "insert" in full_text,
        "no_secondary_loading": "args: null" not in full_text and "先请求详细参数" not in full_text,
        "contains_windows": "仅Windows" in full_text
    }

    for check_name, result in checks.items():
        status = "[PASS]" if result else "[FAIL]"
        print(f"{status} {check_name}: {'Yes' if result else 'No'}")

    all_passed = all(checks.values())

    print("\n" + "=" * 80)
    if all_passed:
        print("[SUCCESS] All checks passed! word_processor prompt updated correctly")
    else:
        print("[FAILED] Some checks failed, please review the prompt content")
    print("=" * 80)

    return all_passed


if __name__ == "__main__":
    success = test_word_processor_prompt()
    sys.exit(0 if success else 1)
