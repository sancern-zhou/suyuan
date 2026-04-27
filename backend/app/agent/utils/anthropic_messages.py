"""
Anthropic Messages API 格式工具

实现标准的 Anthropic Messages API 格式，包括：
- tool_use 和 tool_result 消息构建
- assistant 消息构建（包含 text + tool_use content blocks）
- 消息格式验证
- 缺失 tool_result 检测
- Anthropic 流式事件处理辅助
"""

from typing import Dict, Any, List, Optional, Set
import structlog

logger = structlog.get_logger()


def build_tool_result_message(
    tool_use_id: str,
    result: Dict[str, Any],
    is_error: bool = False
) -> Dict[str, Any]:
    """
    构建 Anthropic 格式的 tool_result 消息

    支持两种 content 格式：
    - 字符串（默认）：将 result 序列化为 JSON 字符串
    - content blocks 列表：当 result 包含 _content_blocks 字段时使用
      例如：[{"type": "text", "text": "..."}, {"type": "image", "source": {...}}]

    Args:
        tool_use_id: 关联的 tool_use.id
        result: 工具执行结果
        is_error: 是否为错误结果

    Returns:
        Anthropic 格式的 tool_result 消息
        {
            "role": "user",
            "content": [
                {
                    "type": "tool_result",
                    "content": "..." | [{"type": "text", ...}],
                    "is_error": False,
                    "tool_use_id": "toolu_xxx"
                }
            ]
        }
    """
    import json

    # 支持富媒体 content blocks（如果 result 显式提供）
    content = result.get("_content_blocks")
    if content is None:
        # 默认：序列化结果为 JSON 字符串
        content = json.dumps(result, ensure_ascii=False, indent=2, default=str)

    return {
        "role": "user",
        "content": [
            {
                "type": "tool_result",
                "content": content,
                "is_error": is_error,
                "tool_use_id": tool_use_id
            }
        ]
    }


def build_assistant_tool_use_message(
    tool_call_id: str,
    tool_name: str,
    tool_input: Dict[str, Any],
    thought_text: str = ""
) -> Dict[str, Any]:
    """构建 Anthropic 格式的 assistant 消息（包含 text + tool_use content blocks）

    在 Anthropic API 中，assistant 的工具调用是通过 content blocks 表达的：
    - text block: LLM 的思考/解释
    - tool_use block: 工具调用

    Args:
        tool_call_id: tool_use content block 的 ID
        tool_name: 工具名称
        tool_input: 工具参数
        thought_text: LLM 的思考文本（可选）

    Returns:
        Anthropic 格式的 assistant 消息
        {
            "role": "assistant",
            "content": [
                {"type": "text", "text": "..."},
                {"type": "tool_use", "id": "toolu_xxx", "name": "tool_name", "input": {...}}
            ]
        }
    """
    content_blocks = []

    if thought_text:
        content_blocks.append({
            "type": "text",
            "text": thought_text
        })

    content_blocks.append({
        "type": "tool_use",
        "id": tool_call_id,
        "name": tool_name,
        "input": tool_input
    })

    return {
        "role": "assistant",
        "content": content_blocks
    }


def build_assistant_text_message(text: str) -> Dict[str, Any]:
    """构建 Anthropic 格式的 assistant 纯文本消息

    Args:
        text: 文本内容

    Returns:
        Anthropic 格式的 assistant 消息
    """
    return {
        "role": "assistant",
        "content": text
    }


def build_text_message(text: str, role: str = "user") -> Dict[str, Any]:
    """
    构建文本消息

    Args:
        text: 消息内容
        role: 角色（user 或 assistant）

    Returns:
        Anthropic 格式的文本消息
    """
    return {
        "role": role,
        "content": text
    }


def extract_tool_use_blocks(assistant_message: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    从 assistant 消息中提取 tool_use blocks

    Args:
        assistant_message: Assistant 消息

    Returns:
        tool_use blocks 列表
    """
    content = assistant_message.get("content", [])

    if isinstance(content, str):
        return []

    return [
        block for block in content
        if isinstance(block, dict) and block.get("type") == "tool_use"
    ]


def detect_missing_tool_results(messages: List[Dict[str, Any]]) -> Set[str]:
    """
    检测缺失的 tool_result

    Args:
        messages: 消息列表

    Returns:
        缺失的 tool_use_id 集合
    """
    tool_use_ids: Set[str] = set()
    tool_result_ids: Set[str] = set()

    for msg in messages:
        role = msg.get("role")

        if role == "assistant":
            # 提取 tool_use blocks
            content = msg.get("content", [])
            if isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "tool_use":
                        tool_use_ids.add(block.get("id", ""))

        elif role == "user":
            # 提取 tool_result blocks
            content = msg.get("content", [])
            if isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "tool_result":
                        tool_result_ids.add(block.get("tool_use_id", ""))

    # 返回缺失的 tool_use_id
    missing_ids = tool_use_ids - tool_result_ids

    if missing_ids:
        logger.warning(
            "anthropic_missing_tool_results_detected",
            missing_count=len(missing_ids),
            missing_ids=list(missing_ids)
        )

    return missing_ids


def generate_missing_tool_result_messages(
    assistant_messages: List[Dict[str, Any]],
    error_message: str = "工具执行被中断"
) -> List[Dict[str, Any]]:
    """
    为缺失的 tool_result 生成错误消息

    Args:
        assistant_messages: Assistant 消息列表
        error_message: 错误消息

    Returns:
        tool_result 消息列表
    """
    messages = []

    for assistant_msg in assistant_messages:
        tool_use_blocks = extract_tool_use_blocks(assistant_msg)

        for tool_use in tool_use_blocks:
            tool_use_id = tool_use.get("id", "")
            if not tool_use_id:
                continue

            messages.append({
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "content": error_message,
                        "is_error": True,
                        "tool_use_id": tool_use_id
                    }
                ]
            })

    if messages:
        logger.info(
            "anthropic_generated_missing_tool_results",
            count=len(messages),
            error_message=error_message
        )

    return messages


def validate_anthropic_message(message: Dict[str, Any]) -> bool:
    """
    验证消息是否符合 Anthropic 格式

    Args:
        message: 消息对象

    Returns:
        是否有效
    """
    role = message.get("role")
    if role not in ("user", "assistant"):
        return False

    content = message.get("content")
    if not content:
        return False

    # content 可以是字符串或列表
    if isinstance(content, str):
        return True

    if isinstance(content, list):
        for block in content:
            if not isinstance(block, dict):
                return False

            block_type = block.get("type")
            if block_type not in ("text", "tool_use", "tool_result", "image", "thinking"):
                return False

        return True

    return False


def normalize_message_to_anthropic(message: Dict[str, Any]) -> Dict[str, Any]:
    """
    将 suyuan 内部消息格式转换为 Anthropic 格式

    Args:
        message: suyuan 内部消息

    Returns:
        Anthropic 格式消息
    """
    role = message.get("role", "user")

    # 如果已经是 Anthropic 格式，直接返回
    if validate_anthropic_message(message):
        return message

    # 转换 suyuan 格式
    content = message.get("content", "")

    # 如果 content 已经是列表（content blocks），保持不变
    if isinstance(content, list):
        return message

    # 否则包装为文本消息
    return {
        "role": role,
        "content": content
    }


def extract_text_from_content(content: Any) -> str:
    """
    从 content 中提取文本内容

    Args:
        content: content 字段（可以是字符串或列表）

    Returns:
        提取的文本
    """
    if isinstance(content, str):
        return content

    if isinstance(content, list):
        texts = []
        for block in content:
            if isinstance(block, dict):
                block_type = block.get("type")

                if block_type == "text":
                    texts.append(block.get("text", ""))
                elif block_type == "tool_result":
                    result_content = block.get("content", "")
                    texts.append(f"[工具结果] {result_content}")
                elif block_type == "tool_use":
                    tool_name = block.get("name", "")
                    texts.append(f"[调用工具] {tool_name}")

        return "\n\n".join(texts)

    return str(content)


def format_messages_for_anthropic_api(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    格式化消息列表以符合 Anthropic API 要求

    Args:
        messages: 原始消息列表

    Returns:
        格式化后的消息列表
    """
    formatted = []

    for msg in messages:
        normalized = normalize_message_to_anthropic(msg)

        # 验证格式
        if not validate_anthropic_message(normalized):
            logger.warning(
                "anthropic_invalid_message_skipped",
                role=msg.get("role"),
                content_type=type(msg.get("content"))
            )
            continue

        formatted.append(normalized)

    return formatted
