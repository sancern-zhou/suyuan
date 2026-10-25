"""ODS 兜底通道契约测试：同步进 guangdong_ods 的表不允许 Agent 查不到。

不变式链：
  sources.yml 声明的每张 ODS 表 => 主契约（contract.txt）或兜底（ods_contract.txt）二选一；
  兜底表必须登记用途（ODS_TABLE_NOTES），生成器缺登记直接失败；
  工具双白名单 = 主契约 + 兜底，两套互斥；兜底表 describe_table 走 guangdong_ods schema。
"""
import sys
from pathlib import Path

import pytest

from app.utils.path_config import resolve_agent_path

_DATA_OPS_SYNC = (Path(__file__).resolve().parents[2]
                  / "projects/guangdong/data-ops/sync")


def _import_fallback_gen():
    sys.path.insert(0, str(_DATA_OPS_SYNC))
    try:
        import gen_ods_fallback_contract
        return gen_ods_fallback_contract
    finally:
        sys.path.pop(0)


@pytest.fixture(scope="module")
def fallback_gen():
    return _import_fallback_gen()


def test_ods_contract_txt_matches_generator(fallback_gen):
    """ods_contract.txt 必须等于 gen_ods_fallback_contract.build_contract() 生成物。"""
    deployed = (resolve_agent_path(
        "backend/app/tools/query/guangdong_ops_sql_query/ods_contract.txt"
    )).read_text(encoding="utf-8")
    assert deployed == fallback_gen.build_contract()


def test_every_synced_table_is_covered_or_fallback(fallback_gen):
    """覆盖率不变式：sources.yml 声明的表不允许存在两边都够不到的 GAP。"""
    declared = set(fallback_gen.synced_logical_tables())
    fallback, covered = fallback_gen.fallback_tables()
    assert declared == set(fallback) | set(covered)
    assert not (set(fallback) & set(covered))


def test_fallback_notes_complete_and_current(fallback_gen):
    """每张兜底表都有用途登记，且登记不包含已不在兜底清单的陈旧表。"""
    tables, _covered = fallback_gen.fallback_tables()
    assert set(fallback_gen.ODS_TABLE_NOTES) == set(tables)


def test_tool_dual_whitelist_disjoint_and_schema_resolution():
    """工具加载双白名单；两套互斥；_schema_of 按层解析 schema。"""
    from app.tools.query.guangdong_ops_sql_query import tool as sql_tool_module

    assert sql_tool_module.ODS_TABLES, "ods_contract.txt 未加载（兜底通道缺失）"
    assert not set(sql_tool_module.MART_TABLES) & set(sql_tool_module.ODS_TABLES)
    assert "guangdong_ods." in sql_tool_module.ODS_SCHEMA_GUIDE

    tool_cls = sql_tool_module.ExecuteGuangdongMartSQLTool
    assert tool_cls._schema_of("mart_work_order_analysis") == "guangdong_mart"
    assert tool_cls._schema_of("rf_m_membraneweighing") == "guangdong_ods"
    assert tool_cls._schema_of("rf_q_pmpressure") == "guangdong_ods"
    assert tool_cls._schema_of("not_a_table") is None

    allowed = set(tool_cls().sql_validator.ALLOWED_TABLES)
    assert "rf_hy_environmenthumidity" in allowed
    assert "sec_checkscore_sxnew" in allowed


def test_layered_datasets_brief_has_summary_and_full_has_guide():
    """契约分层强校验：full 表必有 guide，brief 表必有 summary（生成器同规则）。"""
    sys.path.insert(0, str(_DATA_OPS_SYNC))
    try:
        import gen_tool_contract
    finally:
        sys.path.pop(0)
    docs = {}
    yaml_dir = gen_tool_contract.YAML_DIR
    for fn in sorted(yaml_dir.glob("*.yaml")):
        docs[fn.stem] = gen_tool_contract.load_yaml(str(fn))
    layered = [t for t, d in docs.items() if d.get("detail") == "brief"]
    assert layered, "契约分层未生效：没有任何 detail: brief 表"
    for t, d in docs.items():
        if d.get("detail") == "brief":
            assert d.get("summary"), f"brief 表缺 summary: {t}"
        else:
            assert d.get("guide"), f"full 表缺 guide: {t}"
    # 周检高频表单保持完整字段说明
    for t in ("rf_w_inspection", "rf_w_gaseouscheck_so2", "rf_w_pmcheck"):
        assert docs[t].get("detail") != "brief" and docs[t].get("guide")
