"""
测试 Anthropic 格式修复

验证：
1. tool_result 消息构建
2. 消息历史管理
3. tool_use/tool_result 配对
4. 缺失 tool_result 检测
"""

import asyncio
import json
from app.agent.utils.anthropic_messages import (
    build_tool_result_message,
    detect_missing_tool_results,
    generate_missing_tool_result_messages,
    extract_tool_use_blocks,
    validate_anthropic_message
)


def test_build_tool_result_message():
    """测试 tool_result 消息构建"""
    print("\n=== 测试 tool_result 消息构建 ===")

    # 构建成功的 tool_result
    result = {
        "success": True,
        "data": [{"value": 123}],
        "summary": "测试成功"
    }

    message = build_tool_result_message(
        tool_use_id="toolu_test123",
        result=result,
        is_error=False
    )

    print(f"✓ 成功的 tool_result:")
    print(json.dumps(message, indent=2, ensure_ascii=False))

    # 验证消息格式
    assert validate_anthropic_message(message), "消息格式验证失败"
    assert message["role"] == "user", "角色应为 user"
    assert message["content"][0]["type"] == "tool_result", "content type 应为 tool_result"
    assert message["content"][0]["tool_use_id"] == "toolu_test123", "tool_use_id 不匹配"
    assert message["content"][0]["is_error"] == False, "is_error 应为 False"

    # 构建错误的 tool_result
    error_result = {
        "success": False,
        "error": "测试错误"
    }

    error_message = build_tool_result_message(
        tool_use_id="toolu_error456",
        result=error_result,
        is_error=True
    )

    print(f"\n✓ 错误的 tool_result:")
    print(json.dumps(error_message, indent=2, ensure_ascii=False))

    assert error_message["content"][0]["is_error"] == True, "is_error 应为 True"

    print("\n✅ tool_result 消息构建测试通过")


def test_detect_missing_tool_results():
    """测试缺失 tool_result 检测"""
    print("\n=== 测试缺失 tool_result 检测 ===")

    # 构建测试消息
    messages = [
        {
            "role": "assistant",
            "content": [
                {"type": "text", "text": "我将调用工具"},
                {"type": "tool_use", "id": "toolu_001", "name": "test_tool", "input": {}},
                {"type": "tool_use", "id": "toolu_002", "name": "another_tool", "input": {}}
            ]
        },
        {
            "role": "user",
            "content": [
                {"type": "tool_result", "content": "...", "tool_use_id": "toolu_001", "is_error": False}
            ]
        }
    ]

    missing_ids = detect_missing_tool_results(messages)

    print(f"✓ 缺失的 tool_use_id: {missing_ids}")
    assert "toolu_002" in missing_ids, "应检测到 toolu_002 缺失"
    assert len(missing_ids) == 1, "应只缺失一个 tool_result"

    print("\n✅ 缺失 tool_result 检测测试通过")


def test_generate_missing_tool_result_messages():
    """测试生成缺失的 tool_result 消息"""
    print("\n=== 测试生成缺失的 tool_result 消息 ===")

    assistant_messages = [
        {
            "role": "assistant",
            "content": [
                {"type": "tool_use", "id": "toolu_missing", "name": "test_tool", "input": {}}
            ]
        }
    ]

    missing_messages = generate_missing_tool_result_messages(
        assistant_messages,
        error_message="工具执行超时"
    )

    print(f"✓ 生成的缺失消息数: {len(missing_messages)}")
    print(f"✓ 消息内容:")
    print(json.dumps(missing_messages, indent=2, ensure_ascii=False))

    assert len(missing_messages) == 1, "应生成1条消息"
    assert missing_messages[0]["role"] == "user", "角色应为 user"
    assert missing_messages[0]["content"][0]["tool_use_id"] == "toolu_missing", "tool_use_id 不匹配"
    assert missing_messages[0]["content"][0]["is_error"] == True, "is_error 应为 True"

    print("\n✅ 生成缺失 tool_result 消息测试通过")


def test_extract_tool_use_blocks():
    """测试提取 tool_use blocks"""
    print("\n=== 测试提取 tool_use blocks ===")

    assistant_message = {
        "role": "assistant",
        "content": [
            {"type": "text", "text": "我将调用工具"},
            {"type": "tool_use", "id": "toolu_001", "name": "test_tool", "input": {"arg1": "value1"}},
            {"type": "tool_use", "id": "toolu_002", "name": "another_tool", "input": {"arg2": "value2"}}
        ]
    }

    tool_use_blocks = extract_tool_use_blocks(assistant_message)

    print(f"✓ 提取的 tool_use blocks 数量: {len(tool_use_blocks)}")
    print(f"✓ tool_use blocks:")
    for block in tool_use_blocks:
        print(f"  - {block['name']}: {block['id']}")

    assert len(tool_use_blocks) == 2, "应提取2个 tool_use blocks"
    assert tool_use_blocks[0]["id"] == "toolu_001", "第一个 tool_use id 不匹配"
    assert tool_use_blocks[1]["name"] == "another_tool", "第二个 tool_use name 不匹配"

    print("\n✅ 提取 tool_use blocks 测试通过")


def test_validate_anthropic_message():
    """测试 Anthropic 消息验证"""
    print("\n=== 测试 Anthropic 消息验证 ===")

    # 有效的文本消息
    valid_text_message = {
        "role": "user",
        "content": "测试消息"
    }

    assert validate_anthropic_message(valid_text_message), "文本消息验证失败"
    print("✓ 文本消息验证通过")

    # 有效的 tool_result 消息
    valid_tool_result_message = {
        "role": "user",
        "content": [
            {"type": "tool_result", "content": "...", "tool_use_id": "toolu_001", "is_error": False}
        ]
    }

    assert validate_anthropic_message(valid_tool_result_message), "tool_result 消息验证失败"
    print("✓ tool_result 消息验证通过")

    # 有效的 tool_use 消息
    valid_tool_use_message = {
        "role": "assistant",
        "content": [
            {"type": "tool_use", "id": "toolu_001", "name": "test_tool", "input": {}}
        ]
    }

    assert validate_anthropic_message(valid_tool_use_message), "tool_use 消息验证失败"
    print("✓ tool_use 消息验证通过")

    # 无效的消息（缺少 role）
    invalid_message = {
        "content": "测试"
    }

    assert not validate_anthropic_message(invalid_message), "无效消息应验证失败"
    print("✓ 无效消息验证正确拒绝")

    print("\n✅ Anthropic 消息验证测试通过")


def test_full_workflow():
    """测试完整工作流"""
    print("\n=== 测试完整工作流 ===")

    # 模拟对话历史
    messages = []

    # 1. Assistant 调用工具
    assistant_message = {
        "role": "assistant",
        "content": [
            {"type": "tool_use", "id": "toolu_001", "name": "get_weather", "input": {"city": "北京"}}
        ]
    }
    messages.append(assistant_message)

    # 2. 检测缺失的 tool_result
    missing_ids = detect_missing_tool_results(messages)
    print(f"✓ 检测到缺失的 tool_use_id: {missing_ids}")
    assert "toolu_001" in missing_ids

    # 3. 生成 tool_result
    result = {
        "success": True,
        "data": {"temperature": 25, "weather": "晴"},
        "summary": "北京天气：晴，温度25℃"
    }

    tool_result_message = build_tool_result_message(
        tool_use_id="toolu_001",
        result=result,
        is_error=False
    )
    messages.append(tool_result_message)

    # 4. 再次检测，应无缺失
    missing_ids_after = detect_missing_tool_results(messages)
    print(f"✓ 添加 tool_result 后缺失的 tool_use_id: {missing_ids_after}")
    assert len(missing_ids_after) == 0, "添加 tool_result 后不应有缺失"

    print("\n✅ 完整工作流测试通过")


def main():
    """运行所有测试"""
    print("\n" + "=" * 60)
    print("开始测试 Anthropic 格式修复")
    print("=" * 60)

    try:
        test_build_tool_result_message()
        test_detect_missing_tool_results()
        test_generate_missing_tool_result_messages()
        test_extract_tool_use_blocks()
        test_validate_anthropic_message()
        test_full_workflow()

        print("\n" + "=" * 60)
        print("✅ 所有测试通过！")
        print("=" * 60)

    except AssertionError as e:
        print(f"\n❌ 测试失败: {e}")
        raise
    except Exception as e:
        print(f"\n❌ 测试出错: {e}")
        raise


if __name__ == "__main__":
    main()
