from pathlib import Path

from app.agent.prompts.query_prompt import build_query_prompt

ROOT = Path(__file__).resolve().parents[1]


def test_fixed_business_routing_rules_are_not_hardcoded_in_query_prompt():
    prompt = build_query_prompt(available_tools=[])

    removed_fragments = [
        "广东省内城市和区域数据查询优先使用标准统计报表接口工具",
        "用户问城市统计报表、综合指数、达标率、超标天数、首要污染物比例时",
        "ns_type=2 为新国标",
        "用户查询“珠三角”“非珠三角”“粤东”“粤西”“粤北”“粤东西北”等区域时",
        "168 城市全国排名、排名变化或全国发布数据时",
        "如果用户未指定城市，默认查询广东省 21 个地级市",
    ]

    for fragment in removed_fragments:
        assert fragment not in prompt


def test_query_prompt_keeps_architecture_rules_not_tool_or_ui_details():
    prompt = build_query_prompt(available_tools=[])

    removed_fragments = [
        "PostgreSQL",
        "TimescaleDB",
        "专注于本地 PostgreSQL/TimescaleDB 数据库的结构化查询",
        "## 统计报表查询策略",
        "## 业务规则",
        "## execute_python",
        "## 知识查询",
        "## 语音播报友好回复",
        "结构化数据用 Markdown 表格展示：不超过 30 行",
        "metadata.data_is_complete_for_requested_scope",
        "必须标注数据标准（新 HJ 633-2026 / 旧 HJ 633-2013）、扣沙处理状态",
        "近 3 天使用原始数据",
        "避免在自然语言正文中堆叠过多括号",
        "代码块、JSON metadata、data_id 列表和机器可读字段只放在自然语言正文之后",
        "execute_python 每次调用都是独立环境",
    ]

    for fragment in removed_fragments:
        assert fragment not in prompt

    assert "能力范围由当前项目启用的工具和数据源决定" in prompt
    assert "不知道或缺少依据时直接说明，不编造数据或结论" in prompt
    assert "最终回复先用一到三句话给出可朗读核心结论" in prompt


def test_tool_schema_and_query_memory_own_moved_policy_text():
    sql_tool = (
        ROOT / "app/tools/query/execute_postgres_sql_query/tool.py"
    ).read_text(encoding="utf-8")
    city_report_tool = (
        ROOT / "app/tools/query/query_city_standard_report/tool.py"
    ).read_text(encoding="utf-8")

    # 表目录、字段定位与库路由由工具 schema 承载，不再写进问数提示词
    assert "describe_table" in sql_tool
    assert "bigdata_system" in sql_tool and "sound_data" in sql_tool
    assert "跨库 JOIN" in sql_tool

    assert "综合指数、达标/超标天数、污染物统计浓度、首要污染物、排名" in city_report_tool
    assert "ns_type=2 表示新国标；ns_type=1 表示旧国标" in city_report_tool
