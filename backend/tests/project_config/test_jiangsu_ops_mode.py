from app.agent.prompts.prompt_builder import build_react_system_prompt
from app.project_config.loader import load_project_context
from app.tools import create_global_tool_registry
from config.settings import settings


def test_jiangsu_ops_mode_uses_jiangsu_fault_work_order_query_only():
    context = load_project_context("jiangsu-ops")
    tools = context.manifest.backend.agent_mode_tools["ops"]
    override = context.manifest.frontend.agent_mode_overrides["ops"]

    assert override["name"] == "工单审核模式"
    assert override["short_name"] == "工单审核"
    assert "jiangsu_fetch_fault_work_orders" in tools
    assert "jiangsu_fetch_fault_work_order_detail" in tools
    assert "ops_audit_fetch_dataset" not in tools
    assert "ops_audit_run_rules" not in tools
    assert "ops_audit_inspect" not in tools
    assert "execute_ops_sql_query" not in tools
    assert "query_gd_suncere_station_hour_new" not in tools
    assert "query_gd_suncere_station_day_new" not in tools
    assert context.manifest.backend.mode_prompt_files["ops"] == (
        "projects/jiangsu-ops/prompts/ops.md"
    )


def test_jiangsu_ops_mode_loads_project_owned_prompt(monkeypatch):
    monkeypatch.setattr(settings, "project_id", "jiangsu-ops")

    prompt = build_react_system_prompt("ops")

    assert "江苏省工单审核模式智能体" in prompt
    assert "jiangsu_fetch_fault_work_orders" in prompt
    assert "jiangsu_fetch_fault_work_order_detail" in prompt
    assert "不要重新查询同一条件" in prompt
    assert "优先使用直接返回的审核投影" in prompt
    assert "才用 `read_file` 读取附件" in prompt
    assert "ops_audit_fetch_dataset" not in prompt
    assert "query_gd_suncere_station_hour_new" not in prompt


def test_jiangsu_ops_registers_fault_work_order_list_and_detail_tools():
    context = load_project_context("jiangsu-ops")

    registered = create_global_tool_registry(context=context).list_tools()

    assert "jiangsu_fetch_fault_work_orders" in registered
    assert "jiangsu_fetch_fault_work_order_detail" in registered
