"""渐进发现上报工具（report_finding，对齐 ZCode dynamic-workflow 的 report）。

工作流节点子 Agent 在执行中把关键中间结论按条上报：决定性数值、口径决策、
异常情况。发现即时落 coordinator journal（`node.finding`）并随快照推给前端
实时可见；节点失败时已上报的发现进入 salvage，不随节点倒下丢失（对齐
ZCode："一个死在第 12 个 ask 上的 run 仍做完了 11 个 ask 的活，捞回它正是
report 存在的理由"）。

与 submit_result 的关系：submit_result 是交付终态（结构化信封），
report_finding 是过程遥测（有界列表、去重、超限拒绝而非静默截断）。
"""

from __future__ import annotations

from typing import Any, Callable, Dict, Optional

from app.tools.base.tool_interface import ToolCategory

# 与 coordinator 的边界一致：每节点条数、单条长度（coordinator 侧最终裁剪）
MAX_FINDINGS_PER_NODE = 20
MAX_CONTENT_CHARS = 1000


class ReportFindingTool:
    """每个子 Agent 节点动态构造一次：持有任务标识并向上报 observer。"""

    def __init__(
        self,
        *,
        task_id: str,
        on_finding: Optional[Callable[[Dict[str, Any]], Any]] = None,
        max_findings: int = MAX_FINDINGS_PER_NODE,
    ) -> None:
        self.name = "report_finding"
        self.description = (
            "上报一条关键中间发现（执行中随时可调用）。只报决定性内容："
            "关键数值/占比、口径或范围决策、数据异常与缺失。不要上报过程"
            "流水（正在做什么、调了什么工具）。发现会实时展示给用户，节点"
            "失败后仍会被保留。"
        )
        self.category = ToolCategory.PLANNING
        self.requires_context = False
        self.version = "1.0.0"
        self.function_schema = {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "type": "object",
                "properties": {
                    "content": {
                        "type": "string",
                        "description": "一条完整的发现陈述，含具体数值与口径（不超过 1000 字）",
                    },
                    "tag": {
                        "type": "string",
                        "description": "简短分类标签，如 数值/口径/异常/缺口（可选）",
                    },
                },
                "required": ["content"],
            },
        }
        self.task_id = task_id
        self.on_finding = on_finding
        self.max_findings = max(1, int(max_findings))
        self.reported = 0

    def __call__(self, *args: Any, **kwargs: Any):
        # executor 直接 await registry 里的值；裸实例必须可调用（同 SubmitResultTool）
        return self.execute(*args, **kwargs)

    def get_function_schema(self) -> Dict[str, Any]:
        return self.function_schema

    async def execute(
        self, content: Optional[str] = None, tag: Optional[str] = None, **kwargs: Any
    ) -> Dict[str, Any]:
        text = str(content or "").strip()
        if self.reported >= self.max_findings:
            return {
                "status": "success",
                "success": True,
                "result": f"发现条数已达上限（{self.max_findings}），本条未上报。请把剩余内容合并进最终结果交付。",
                "data": {"reported": self.reported, "accepted": False, "reason": "budget_exhausted"},
                "summary": "发现上报次数已达上限",
            }
        if not text:
            return {
                "status": "failed",
                "success": False,
                "result": "report_finding 需要 content 参数",
                "data": {},
                "summary": "发现内容为空",
            }
        self.reported += 1
        info = {
            "task_id": self.task_id,
            "content": text[:MAX_CONTENT_CHARS],
            "tag": str(tag or "").strip()[:40] or None,
        }
        if self.on_finding is not None:
            try:
                result = self.on_finding(info)
                if hasattr(result, "__await__"):
                    await result
            except Exception:  # noqa: BLE001 - 观察者异常不影响执行
                pass
        return {
            "status": "success",
            "success": True,
            "result": f"发现 #{self.reported} 已上报，将实时展示给用户并在节点失败时保留。",
            "data": {"reported": self.reported, "accepted": True},
            "summary": "发现已上报",
        }
