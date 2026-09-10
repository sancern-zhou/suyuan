"""Submit a validated result for human review, for any scheduled task."""
from app.services.task_review import ReviewSubmission, submit_review, review_visual
from app.tools.base.tool_interface import LLMTool, ToolCategory
from app.tools.resource_declarations import resources_for_visuals


class SubmitTaskReviewTool(LLMTool):
    def __init__(self):
        description = "提交已完成分析的结构化结论，生成任务调度中心待人工确认或处置卡片。工单、研判、诊断共用此工具；需要人工确认、处置或归档时均应提交，遵循当前任务的结果要求。同一执行同一业务编号仅提交一次；普通回复不会生成待办。"
        super().__init__(name="submit_task_review", description=description,
                         category=ToolCategory.TASK_MANAGEMENT, requires_context=True,
                         function_schema={"name": "submit_task_review", "description": description,
                                          "parameters": ReviewSubmission.model_json_schema()})

    async def execute(self, context=None, **kwargs):
        try:
            source = getattr(context, "scheduled_task_context", None) or {}
            review = submit_review(kwargs, source)
            visual = review_visual(review)
            return {"success": True, "status": review["status"],
                    "data": {"review_id": review["review_id"], "version": review["version"]},
                    "visuals": [visual], "resources": resources_for_visuals([visual], tool_name=self.name),
                    "summary": f"已提交：{review['title']}，等待人工确认或处置。"}
        except ValueError as exc:
            return {"success": False, "status": "failed", "summary": str(exc)}
