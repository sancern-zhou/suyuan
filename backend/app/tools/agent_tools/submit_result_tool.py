"""结构化交付工具：子 Agent 通过 submit_result 工具调用交付合规结果信封。

把"最终回复按 result_schema 输出 JSON"的提示词约定升级为函数调用约束：
参数结构即 schema（由节点 result_schema 合成），从根上消灭格式不合规失败。
机制参照 zai-org/ZCode dynamic-workflow 的 ask<T>/submit_result：
类型即 schema、违规按路径定位喂回修复、未调用即未交付。

2026-11-05 提交时校验前移：schema 违规与 deliverables 文件机械核对在
execute 内即时执行（与 call_sub_agent 事后校验同源同语义）。校验失败的
提交返回 success=False——runtime 终止判定（_submitted_result_from_records）
跳过失败提交，错误作为 observation 回给子 Agent 在剩余预算内轮内修复，
不再等到子会话结束后才发现交付无效（qingyuan-oct DAG 失败教训：子 Agent
收到"结果已提交"假象，节点却因占位路径判死）。
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from app.agent.workflow.protocol import validate_result_schema
from app.agent.workflow.resource_contract import validate_deliverable_entries
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


def json_safe_envelope(value: Any) -> Optional[Dict[str, Any]]:
    """信封唯一准入契约：从这里交付的结果永远是 JSON 可序列化对象。

    信封的全部下游（agent_runtime 交付边界、call_sub_agent final_result、
    workflow result_envelope）都会对其 json.dumps——契约在唯一生产点建立
    一次，而不是让每个下游各自加 default=str 兜底。混入不可序列化对象时
    按保守策略降级为字符串表示，保证交付边界永不因序列化失败废掉节点。
    """
    if not isinstance(value, dict):
        return None
    try:
        json.dumps(value, ensure_ascii=False)
        return value
    except (TypeError, ValueError):
        return json.loads(json.dumps(value, ensure_ascii=False, default=str))


class SubmitResultTool:
    """每个专家节点动态构造一次：持有节点 result_schema 并接收结构化交付。"""

    def __init__(self, result_schema: Optional[Dict[str, Any]] = None) -> None:
        self.name = "submit_result"
        self.description = (
            "提交本任务的结构化结果信封。完成分析后必须调用本工具交付；"
            "未调用本工具直接结束视为未完成交付。"
            "提交时会即时校验：信封字段须满足结果协议，deliverables[].path "
            "必须指向本轮实际保存的真实文件（禁止占位路径），声明 fields 时"
            "仅限 csv/json 且字段须与文件实际内容一致，不符合会被打回并附具体违规项。"
        )
        self.category = ToolCategory.PLANNING
        self.requires_context = False
        self.version = "1.0.0"
        self.result_schema = result_schema if isinstance(result_schema, dict) else {}
        self.function_schema = {
            "name": self.name,
            "description": self.description,
            "parameters": envelope_parameters(self.result_schema),
        }
        self.submitted_result: Optional[Dict[str, Any]] = None

    def __call__(self, *args: Any, **kwargs: Any):
        # executor 直接调用 registry 里的值（await tool_func(...)）；
        # 裸实例注册（call_sub_agent/_inject_submit_result）需要可调用形态，
        # 否则报 'SubmitResultTool' object is not callable，交付信封丢失。
        return self.execute(*args, **kwargs)

    def _envelope_violations(self, envelope: Any) -> List[Dict[str, str]]:
        """提交时校验：与 call_sub_agent 事后校验同源（schema + deliverables 机械核对）。"""
        if not isinstance(envelope, dict):
            return [{"path": "$", "expected": "object result envelope", "got": "missing"}]
        violations = validate_result_schema(envelope, self.result_schema)
        return violations + validate_deliverable_entries(envelope.get("deliverables"))

    async def execute(self, result: Optional[Any] = None, **kwargs: Any) -> Dict[str, Any]:
        if isinstance(result, dict):
            envelope = json_safe_envelope(result)
        else:
            # 模型把信封字段平铺在参数顶层时兜底接收。
            # executor 会注入 __execution_context 等双下划线关键字参数，
            # 它们不是模型产出，剔除（曾混进信封导致交付边界序列化崩溃）。
            flat = {
                key: value
                for key, value in kwargs.items()
                if isinstance(key, str) and not key.startswith("__")
            }
            envelope = json_safe_envelope(flat) if flat else None

        violations = self._envelope_violations(envelope)
        if violations:
            # success=False：runtime 终止判定跳过失败提交，循环继续；
            # 错误明细随 observation 回给子 Agent 轮内修复，不写入
            # submitted_result（未通过校验不视为已交付）。
            detail = "\n".join(
                f"- {item.get('path')}: expected {item.get('expected')}, got {item.get('got')}"
                for item in violations[:10]
            )
            return {
                "status": "validation_failed",
                "success": False,
                "result": (
                    "结构化结果未通过提交校验，请只修正下列违规项后重新调用 submit_result"
                    "（其余字段保持不变，不要重新执行分析）：\n" + detail
                ),
                "data": {"validation_errors": violations, "submitted_result": envelope},
                "summary": f"提交校验失败（{len(violations)} 项），修正后重新提交",
            }

        self.submitted_result = envelope
        return {
            "status": "success",
            "success": True,
            "result": "结果已提交",
            # 回传结构化信封：runtime 据此把 submit_result 视为终止动作，
            # 父 Agent 也可直接从 tool_result 提取（不依赖事件命名）。
            "data": {"submitted_result": self.submitted_result},
            "summary": "结构化结果已接收",
        }

    def get_function_schema(self) -> Dict[str, Any]:
        return self.function_schema
