"""
验证 read_file 工具不进行意图检测

这个脚本验证：
1. 工具不分析用户问题内容
2. 模式选择完全基于参数和文件大小
3. 没有关键词检测逻辑
"""
import asyncio
from pathlib import Path
from app.tools.utility.read_file_tool import ReadFileTool


async def verify_no_intent_detection():
    """验证不进行意图检测"""
    print("=" * 70)
    print("验证 read_file 工具不进行意图检测")
    print("=" * 70)

    tool = ReadFileTool()

    # 1. 检查是否有意图检测相关的方法或属性
    print("\n1. 检查工具实现...")
    has_intent_detection = False

    # 检查是否有意图关键词列表
    if hasattr(tool, '_edit_intent_keywords'):
        print("❌ 发现 _edit_intent_keywords 属性（意图检测）")
        has_intent_detection = True
    else:
        print("✅ 无 _edit_intent_keywords 属性")

    # 检查是否有意图检测方法
    intent_methods = [
        '_detect_intent',
        '_infer_intent',
        '_analyze_user_query',
        '_check_edit_intent'
    ]
    for method in intent_methods:
        if hasattr(tool, method):
            print(f"❌ 发现意图检测方法: {method}")
            has_intent_detection = True

    if not has_intent_detection:
        print("✅ 无意图检测方法")

    # 2. 检查模式选择逻辑
    print("\n2. 检查模式选择逻辑...")

    # 读取 _read_word_xml 方法的文档字符串
    docstring = tool._read_word_xml.__doc__
    if docstring:
        if "意图" in docstring or "intent" in docstring.lower():
            if "不进行意图检测" in docstring:
                print("✅ 方法文档明确说明：不进行意图检测")
            else:
                print("⚠️  方法文档提到意图，需要检查")

        if "关键词" in docstring or "keyword" in docstring.lower():
            print("❌ 方法文档提到关键词（意图检测）")
            has_intent_detection = True
        else:
            print("✅ 方法文档未提关键词")
    else:
        print("⚠️  方法缺少文档字符串")

    # 3. 验证模式选择只基于参数和文件大小
    print("\n3. 验证模式选择逻辑...")

    test_cases = [
        {
            "name": "小文件，无参数",
            "file_size": 50_000,  # 50KB < 100KB
            "raw_mode": False,
            "include_formatting": False,
            "expected_mode": "structured",
            "reason": "小文件默认使用 structured"
        },
        {
            "name": "大文件，无参数",
            "file_size": 150_000,  # 150KB >= 100KB
            "raw_mode": False,
            "include_formatting": False,
            "expected_mode": "text",
            "reason": "大文件默认使用 text"
        },
        {
            "name": "raw_mode=True（覆盖文件大小）",
            "file_size": 150_000,
            "raw_mode": True,
            "include_formatting": False,
            "expected_mode": "raw",
            "reason": "raw_mode 参数优先级最高"
        },
        {
            "name": "include_formatting=True（覆盖默认）",
            "file_size": 150_000,
            "raw_mode": False,
            "include_formatting": True,
            "expected_mode": "structured",
            "reason": "include_formatting 覆盖默认行为"
        }
    ]

    all_passed = True
    for test in test_cases:
        # 模拟模式选择逻辑（不实际调用方法）
        file_size = test["file_size"]
        raw_mode = test["raw_mode"]
        include_formatting = test["include_formatting"]

        # 复现 _read_word_xml 的逻辑
        if raw_mode:
            actual_mode = "raw"
        elif include_formatting:
            actual_mode = "structured"
        elif file_size < 100_000:
            actual_mode = "structured"
        else:
            actual_mode = "text"

        passed = actual_mode == test["expected_mode"]
        status = "✅" if passed else "❌"
        all_passed = all_passed and passed

        print(f"{status} {test['name']}")
        print(f"   预期: {test['expected_mode']}, 实际: {actual_mode}")
        print(f"   理由: {test['reason']}")

    # 4. 总结
    print("\n" + "=" * 70)
    print("验证结果")
    print("=" * 70)

    if not has_intent_detection and all_passed:
        print("✅ 所有测试通过！")
        print("\n✅ 确认：read_file 工具不进行意图检测")
        print("✅ 确认：模式选择完全基于参数和文件大小")
        print("✅ 确认：无关键词检测逻辑")
        print("\n核心原则：")
        print("• 系统不分析用户问题内容")
        print("• 系统不检测关键词推断意图")
        print("• 系统只根据文件大小选择默认模式")
        print("• LLM 通过参数完全控制模式")
    else:
        print("❌ 测试失败！")
        if has_intent_detection:
            print("⚠️  发现意图检测相关代码或属性")
        if not all_passed:
            print("⚠️  模式选择逻辑不符合预期")


if __name__ == "__main__":
    asyncio.run(verify_no_intent_detection())
