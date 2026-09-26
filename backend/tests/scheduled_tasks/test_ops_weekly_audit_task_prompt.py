from app.tools.scheduled_tasks.create_scheduled_task import (
    OPS_WEEKLY_AUDIT_EXECUTION_MODE,
    OPS_WEEKLY_AUDIT_TASK_PROMPT,
)


def test_ops_weekly_audit_task_prompt_uses_direct_audit_outputs():
    assert OPS_WEEKLY_AUDIT_EXECUTION_MODE == "ops"
    assert "作为当前运维 Agent 直接完整执行任务" in OPS_WEEKLY_AUDIT_TASK_PROMPT
    assert "不调用 call_sub_agent" in OPS_WEEKLY_AUDIT_TASK_PROMPT
    assert 'call_sub_agent(target_mode="ops")' not in OPS_WEEKLY_AUDIT_TASK_PROMPT
    assert "ops_audit_fetch_dataset" in OPS_WEEKLY_AUDIT_TASK_PROMPT
    assert "按 execution_id 自动隔离" in OPS_WEEKLY_AUDIT_TASK_PROMPT
    assert "不要指定 output_dir" in OPS_WEEKLY_AUDIT_TASK_PROMPT
    assert "ops_audit_run_rules 会直接生成" in OPS_WEEKLY_AUDIT_TASK_PROMPT
    assert "final_issue_list_path" in OPS_WEEKLY_AUDIT_TASK_PROMPT
    assert "report_input_path" in OPS_WEEKLY_AUDIT_TASK_PROMPT
    assert "pending_review_count" in OPS_WEEKLY_AUDIT_TASK_PROMPT
    assert "按审核报告规范生成并交付 HTML/Word 报告" in OPS_WEEKLY_AUDIT_TASK_PROMPT
    assert "create_report_package" not in OPS_WEEKLY_AUDIT_TASK_PROMPT
    assert "render_report_package" not in OPS_WEEKLY_AUDIT_TASK_PROMPT
    assert "validate_report_package" not in OPS_WEEKLY_AUDIT_TASK_PROMPT
    assert "不得再调用子 Agent 做全量主观审核" in OPS_WEEKLY_AUDIT_TASK_PROMPT
    assert "不得调用已移除的 ops_audit_submit_review" in OPS_WEEKLY_AUDIT_TASK_PROMPT
    assert "reviewed_issue_list_path" not in OPS_WEEKLY_AUDIT_TASK_PROMPT
