"""
Load Data From Memory Tool

工具功能: 让Agent按需读取外部化的大数据
用途: 当Agent需要查看完整数据时,可以通过data_ref加载

data_id格式: schema:v1:hash
例如: 'pmf_result:v1:abc123', 'vocs:v1:def456', 'obm_ofp_result:v1:xyz789'

使用场景:
- Agent在上下文中看到 "data_id: pmf_result:v1:abc123"
- Agent想要查看完整数据内容
- 调用此工具: load_data_from_memory(data_ref="pmf_result:v1:abc123")
"""

from typing import Dict, Any, Optional
import structlog

logger = structlog.get_logger()


class LoadDataFromMemoryTool:
    """
    数据加载工具 - 从外部化存储读取完整数据

    Agent使用说明:
    - 当你在观察结果中看到 "data_id: schema:v1:hash" 时
    - 使用此工具加载完整数据: load_data_from_memory(data_ref="schema:v1:hash")
    - 返回完整的数据内容供你分析

    data_id格式: schema:v1:hash
    例如: 'pmf_result:v1:abc123', 'vocs:v1:def456'
    """

    def __init__(self, memory_manager):
        """
        初始化数据加载工具

        Args:
            memory_manager: HybridMemoryManager实例
        """
        self.memory = memory_manager

    async def execute(self, data_id: str) -> Dict[str, Any]:
        """
        加载外部化的数据

        Args:
            data_id: 数据引用ID (格式: schema:v1:hash)

        Returns:
            {
                "success": bool,
                "data": Any,  # 完整数据
                "summary": str
            }
        """
        logger.info("loading_data_from_memory", data_id=data_id)

        # 从会话记忆中加载数据
        data = self.memory.session.load_data_from_file(data_id)

        if data is None:
            available_refs = list(self.memory.session.data_files.keys())
            logger.warning(
                "data_not_found",
                data_id=data_id,
                available_count=len(available_refs)
            )
            return {
                "success": False,
                "error": f"数据文件不存在: {data_id}",
                "summary": (
                    f"❌ 未找到数据文件 {data_id}\n\n"
                    f"可用data_id列表（{len(available_refs)}个）：\n"
                    + "\n".join([f"  - {ref}" for ref in available_refs[:10]])
                    + ("\n  ..." if len(available_refs) > 10 else "")
                    + "\n\n请使用以上实际data_id，不要使用占位符！"
                ),
                "available_refs": available_refs
            }

        # 生成摘要
        summary = self._generate_summary(data)

        logger.info(
            "data_loaded_successfully",
            data_id=data_id,
            data_size=len(str(data))
        )

        return {
            "success": True,
            "data": data,
            "summary": f"✅ 成功加载数据 {data_id}\n{summary}"
        }

    def _generate_summary(self, data: Any) -> str:
        """生成数据摘要"""
        if isinstance(data, list):
            return f"列表包含 {len(data)} 条记录"
        elif isinstance(data, dict):
            keys = list(data.keys())[:5]
            return f"字典包含键: {', '.join(keys)}"
        elif isinstance(data, str):
            return f"字符串长度: {len(data)}"
        else:
            return f"数据类型: {type(data).__name__}"


def get_function_schema() -> Dict[str, Any]:
    """
    返回工具的Function Calling schema

    供LLM理解工具功能和参数
    """
    return {
        "name": "load_data_from_memory",
        "description": (
            "从外部化存储读取完整数据。\n\n"
            "⚠️ 重要提醒：请使用上下文中实际提供的data_id，不要使用占位符！\n\n"
            "data_id格式：schema:v1:hash（如 'pmf_result:v1:abc123', 'vocs:v1:def456'）\n\n"
            "使用场景：\n"
            "1. 当你在观察结果中看到'data_id: schema:v1:hash'时，使用此工具加载完整数据\n"
            "2. 例如: 如果看到'✅ 任务完成（数据ID：pmf_result:v1:abc123）'，\n"
            "调用 load_data_from_memory(data_id='pmf_result:v1:abc123') 可以获取完整数据\n\n"
            "正确做法：使用观察结果中实际显示的data_id\n\n"
            "如果data_id不存在，工具会返回可用data_id列表供你选择。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "data_id": {
                    "type": "string",
                    "description": (
                        "数据引用ID，格式为 'schema:v1:hash'。"
                        "例如: 'pmf_result:v1:abc123', 'vocs:v1:def456', 'obm_ofp_result:v1:xyz789'。"
                        "通常在观察结果中显示为'data_id: schema:v1:hash'"
                    )
                }
            },
            "required": ["data_id"]
        }
    }


async def load_data_from_memory(
    data_id: str,
    _memory_manager=None
) -> Dict[str, Any]:
    """
    工具适配器函数 - 供tool_adapter调用

    Args:
        data_id: 数据引用ID (格式: schema:v1:hash)
        _memory_manager: 记忆管理器实例(由工具注册时注入)

    Returns:
        工具执行结果
    """
    if _memory_manager is None:
        return {
            "success": False,
            "error": "记忆管理器未初始化",
            "summary": "❌ 内部错误: 记忆管理器未初始化"
        }

    tool = LoadDataFromMemoryTool(_memory_manager)
    return await tool.execute(data_id)
