"""Submit a validated result for human review, for any scheduled task."""
from uuid import uuid4

from app.services.task_review import ReviewSubmission, review_visual, submit_review
from app.tools.base.tool_interface import LLMTool, ToolCategory
from app.tools.resource_declarations import resources_for_visuals

# 对话式审核（非计划任务触发）使用的稳定任务标识：同一业务编号只保留一条审核记录，
# 重新提交走版本递增，便于工单审核工作台展示最新研判。
CONVERSATIONAL_REVIEW_TASK_ID = "ops_conversational_review"


class SubmitTaskReviewTool(LLMTool):
    def __init__(self):
        description = "提交已完成分析的结构化结论，生成任务调度中心待人工确认或处置卡片。工单、研判、诊断共用此工具；需要人工确认、处置或归档时均应提交，遵循当前任务的结果要求。comment 必须填写人工复核意见；若模型漏传 comment，工具会用 summary 作为最低限度兜底。同一执行同一业务编号仅提交一次；普通回复不会生成待办。"
        super().__init__(name="submit_task_review", description=description,
                         category=ToolCategory.TASK_MANAGEMENT, requires_context=True,
                         function_schema={"name": "submit_task_review", "description": description,
                                          "parameters": ReviewSubmission.model_json_schema()})

    @staticmethod
    def _conversational_source(context) -> dict:
        """对话式会话没有计划任务上下文时，合成审核来源，使人工确认/归档流程可用。"""
        session_id = str(getattr(context, "session_id", "") or "chat")
        return {
            "task_id": CONVERSATIONAL_REVIEW_TASK_ID,
            "task_name": "对话式工单审核",
            "execution_id": f"chat-{session_id}-{uuid4().hex[:12]}",
            "result_requirements": [],
            "review_subject_bound": False,
            "allow_archived_review_reopen": True,
            "conversational": True,
        }

    async def execute(self, context=None, data_context_manager=None, **kwargs):
        # Runtime dependencies are not fields of the strict review submission schema.
        try:
            source = getattr(context, "scheduled_task_context", None) or {}
            if not source.get("task_id") or not source.get("execution_id"):
                source = {**source, **self._conversational_source(context)}
            # Some model tool calls omit the required comment despite the JSON
            # schema. Keep the hand-off reliable while preserving validation:
            # summary is the only safe, already-validated fallback available.
            submission = dict(kwargs)
            if not str(submission.get("comment") or "").strip() and str(submission.get("summary") or "").strip():
                submission["comment"] = submission["summary"]
            review = submit_review(submission, source)
            visual = review_visual(review)
            # 结果必须是标准 UDF 格式（metadata 齐全）：缺 metadata 会被 tool_adapter
            # 强制转换，转换会在有 visuals 时把 data 置空，ui_command 也就丢了。
            return {"success": True, "status": review["status"],
                    "data": {"review_id": review["review_id"], "version": review["version"]},
                    "metadata": {"generator": self.name},
                    "visuals": [visual], "resources": resources_for_visuals([visual], tool_name=self.name),
                    **self._workbench_ui_command(review),
                    "summary": f"已提交：{review['title']}，等待人工确认或处置。"}
        except ValueError as exc:
            return {"success": False, "status": "failed", "summary": str(exc)}

    @staticmethod
    def _workbench_ui_command(review: dict) -> dict:
        """工单审核且工作台已有证据包条目时，让右侧工作台在会话中自动展开。

        命令放在结果顶层：回放与实时链路都完整保留顶层字段，不依赖 data
        （data 在带 visuals 的标准格式里不保证保留）。
        """
        try:
            from app.services.jiangsu_work_order_review import has_order

            code = str(review.get("subject_id") or "").strip()
            # 工作台条目只由工单审核证据链路创建，存在即说明本次审核属于工单审核。
            if code and has_order(code):
                return {"ui_command": {"type": "open_work_order_review", "working_order_code": code}}
        except Exception:  # noqa: BLE001 - 工作台不可用时静默跳过，不影响审核提交
            pass
        return {}
