from app.agent.prompts.report_prompt import build_report_prompt


def test_report_prompt_does_not_inject_city_pollutant_ranking_guidance():
    prompt = build_report_prompt(["analyze_city_pollutant_rankings"])

    assert "analyze_city_pollutant_rankings" not in prompt
    assert "不要使用模型自行排序" not in prompt


def test_report_prompt_explains_when_to_use_agent_workflow_dag():
    prompt = build_report_prompt(["run_agent_workflow"])

    assert "run_agent_workflow" in prompt
    assert "默认通过 `run_agent_workflow` 委托子 Agent" in prompt
    assert "主 Agent 不直接调用单个 `call_sub_agent`" in prompt
    assert "独立 source 节点并行执行" in prompt
    assert "report_analysis_v1" in prompt
    assert "synthesis_task" in prompt
    assert "不得在 DAG 中创建 report 子节点" in prompt
    assert "delivery_tasks" not in prompt


def test_report_prompt_executes_without_legacy_plan_confirmation_flow():
    prompt = build_report_prompt(["run_agent_workflow", "list_skills", "view_skill"])

    assert "缺少关键业务参数时才向用户提问" in prompt
    assert "优先搜索计划模板" not in prompt
    assert "必须先向用户展示查询计划并等待确认" not in prompt
    assert "如果用户满意，询问是否将本次查询计划" not in prompt


def test_report_prompt_requires_a_minimal_dag_even_for_simple_tasks():
    prompt = build_report_prompt(["run_agent_workflow"])

    assert "所有报告生成、更新或撰写任务都使用一次最小可行 DAG" in prompt
    assert "简单任务使用单个 source 节点加 synthesis 节点" in prompt


def test_report_prompt_uses_one_step_report_finalization():
    prompt = build_report_prompt(["create_report_package"])

    assert "最终只调用一次 `create_report_package`" in prompt
    assert "渲染 HTML/Word、执行验收" in prompt
    assert "render_report_package" not in prompt
    assert "validate_report_package" not in prompt


def test_report_prompt_applies_xuchang_audience_and_content_constraints():
    prompt = build_report_prompt(["run_agent_workflow"])

    assert "许昌市生态环境管理用户" in prompt
    assert "按用户角色需求" in prompt
    assert "禁止出现内部接口名、工具名、字段名" in prompt
    assert "不确定性与数据缺口" in prompt
    assert "数据来源、统计时段与口径说明统一放在报告最后" in prompt
