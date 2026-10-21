"""结构化交付工具：子 Agent 通过 submit_result 工具调用交付合规结果信封。

把"最终回复按 result_schema 输出 JSON"的提示词约定升级为函数调用约束：
参数结构即 schema（由节点 result_schema 合成），从根上消灭格式不合规失败。
机制参照 zai-org/ZCode dynamic-workflow 的 ask<T>/submit_result：
类型即 schema、违规按路径定位喂回修复、未调用即未交付。
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from app.tools.base.tool_interface import ToolCategory


def envelope_parameters(result_schema: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """把节点 result_schema 映射为 submit_result 的单个 result 对象参数。"""
    schema = result_schema if isinstance(result_schema, dict) else {}
    properties = schema.get("properties") or {}
    required = list(schema.get("required") or [])
    return {
        "type": "object",
        "properties": {
            "result": {
                "type": "object",
                "description": "结构化结果信封，字段与类型见本定义",
                "properties": properties,
                "required": required,
                "additionalProperties": True,
            }
        },
        "required": ["result"],
    }


class SubmitResultTool:
    """每个专家节点动态构造一次：持有节点 result_schema 并接收结构化交付。"""

    def __init__(self, result_schema: Optional[Dict[str, Any]] = None) -> None:
        self.name = "submit_result"
        self.description = (
            "提交本任务的结构化结果信封。完成分析后必须调用本工具交付；"
            "未调用本工具直接结束视为未完成交付。"
        )
        self.category = ToolCategory.PLANNING
        self.requires_context = False
        self.version = "1.0.0"
        self.function_schema = {
            "name": self.name,
            "description": self.description,
            "parameters": envelope_parameters(result_schema),
        }
        self.submitted_result: Optional[Dict[str, Any]] = None

    async def execute(self, result: Optional[Any] = None, **kwargs: Any) -> Dict[str, Any]:
        if isinstance(result, dict):
            self.submitted_result = result
        else:
            # 模型把信封字段平铺在参数顶层时兜底接收
            flat = {key: value for key, value in kwargs.items() if isinstance(key, str)}
            self.submitted_result = flat or None
        return {
            "status": "success",
            "success": True,
            "result": "结果已提交",
            "data": {},
            "summary": "结构化结果已接收",
        }

    def get_function_schema(self) -> Dict[str, Any]:
        return self.function_schema
