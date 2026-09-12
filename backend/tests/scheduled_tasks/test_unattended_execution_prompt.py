from app.scheduled_tasks.executor.task_executor import ScheduledTaskExecutor
from app.scheduled_tasks.models import ScheduledTask
from app.tools.agent_tools.call_sub_agent import CallSubAgentTool


def test_scheduled_task_prompt_marks_unattended_execution():
    task = ScheduledTask(
        task_id="ops-weekly-audit",
        name="工单周审",
        description="每周五审核运维工单",
        execution_mode="assistant",
        schedule_type="weekly_custom",
        day_of_week=4,
        hour=9,
        minute=0,
        prompt="审核 2026-08-24 至 2026-08-30 创建的已完成运维工单并生成正式报告。",
    )

    prompt = ScheduledTaskExecutor._build_task_prompt(
        task.prompt,
        task=task,
        execution_id="exec_ops_weekly_audit",
    )

    assert "后台无人值守的定时任务执行" in prompt
    assert "任务名称、任务描述、执行指令、调度和筛选条件均视为用户已提前配置并确认" in prompt
    assert "不要以“请确认”“等待用户确认”“确认后继续”等形式中途结束" in prompt
    assert "必须在本次执行内直接调用并等待工具返回" in prompt


def test_scheduled_parent_context_marks_sub_agent_unattended():
    prompt = CallSubAgentTool()._build_child_request_prompt(
        target_mode="ops",
        goal="逐条复核 review_input.items 并提交结果",
        context="review_input_path: /tmp/review_input.json",
        scheduled_task_context={
            "task_id": "ops-weekly-audit",
            "task_name": "工单周审",
            "execution_id": "exec_ops_weekly_audit",
        },
    )

    assert "后台定时任务执行约束" in prompt
    assert "父任务已经由用户提前配置并确认" in prompt
    assert "不要要求父 Agent 或用户再确认后才继续" in prompt
    assert "在本次子 Agent 执行内直接完成并返回结果" in prompt
