"""visual_id 协议契约测试。

钉住不变式：所有 ID 生成器/清洗器的输出必须完整匹配
``app.utils.visual_ids.VISUAL_ID_PATTERN``（[[chart:<id>]] 占位符协议），
后端与前端的占位符匹配正则均以该定义为唯一来源。
历史事故：19 位纳秒 ID 被模型抄错、PM2.5 点号与中文标题进入 ID 导致
Web/App 占位符匹配失败、图表无法渲染。
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.services.image_cache import sanitize_image_id
from app.social.inline_charts import _CHART_REFERENCE
from app.tools.visualization.create_business_chart.renderer import _safe_chart_id
from app.utils.visual_ids import VISUAL_ID_PATTERN, new_visual_id, repair_chart_reference_ids, sanitize_visual_id

_FULL_ID_RE = re.compile(rf"^{VISUAL_ID_PATTERN}$")


def test_short_id_generator_output_matches_protocol():
    for index in range(20):
        assert _FULL_ID_RE.match(new_visual_id("echarts", index))
        assert _FULL_ID_RE.match(new_visual_id("matplotlib"))


def test_sanitize_visual_id_collapses_unsafe_chars():
    assert sanitize_visual_id("generic_pollutant_wind_rose_PM2.5") == "generic_pollutant_wind_rose_PM2.5"
    assert sanitize_visual_id("风速玫瑰图") == ""
    assert sanitize_visual_id("PM$_{2.5}$ 污染物") == "PM_2.5"
    assert sanitize_visual_id("SO$_4^{2-}$") == "SO_4_2"
    assert sanitize_visual_id("///") == ""
    assert len(sanitize_visual_id("x" * 500)) == 100


def test_sanitize_image_id_output_is_protocol_safe():
    nasty_inputs = [
        "PM$_{2.5}$",
        "SO$_4^{2-}$",
        "风速玫瑰图",
        "O$_3$",
        "generic_pollutant_wind_rose_PM2.5",
        "风玫瑰/PM2.5 测试",
        "",
        "///",
        "x" * 500,
    ]
    for value in nasty_inputs:
        assert _FULL_ID_RE.match(sanitize_image_id(value)), value


def test_business_chart_safe_chart_id_matches_protocol():
    for value in ("generic_pollutant_wind_rose_PM2.5", "风速玫瑰", "", "a/b\\c"):
        assert _FULL_ID_RE.match(_safe_chart_id(value)), value


def test_chart_reference_regex_covers_protocol_ids():
    assert _CHART_REFERENCE.search("[[chart:generic_pollutant_wind_rose_PM2.5]]")
    assert _CHART_REFERENCE.search("[[chart:echarts_ab12cd3e4f_0]]")
    # 协议外字符（中文）不应被匹配——生成端已保证不会产生此类 ID
    assert not _CHART_REFERENCE.search("[[chart:风速玫瑰图]]")


def test_repair_chart_reference_ids_fixes_typed_wrong_id():
    """回归：模型把 echarts_hn5yeutr7b_0 抄成 echarts_nyeutr7b_0，图表不渲染。"""
    known = {"echarts_hn5yeutr7b_0", "echarts_hn5yeutrbx_1"}
    text = "结论\n\n[[chart:echarts_nyeutr7b_0]]\n\n要点"
    assert repair_chart_reference_ids(text, known) == "结论\n\n[[chart:echarts_hn5yeutr7b_0]]\n\n要点"


def test_repair_chart_reference_ids_keeps_exact_and_ambiguous():
    known = {"echarts_hn5yeutr7b_0", "echarts_hn5yeutrbx_1"}
    exact = "[[chart:echarts_hn5yeutr7b_0]]"
    assert repair_chart_reference_ids(exact, known) == exact
    # 同前缀多候选时后缀 _0/_1 参与消歧：唯一最近似者胜出
    assert repair_chart_reference_ids("[[chart:echarts_nyeutr7b_0]]", known) == "[[chart:echarts_hn5yeutr7b_0]]"
    # 距离过远不改写
    assert repair_chart_reference_ids("[[chart:echarts_zzzzzzzzzz_9]]", known) == "[[chart:echarts_zzzzzzzzzz_9]]"
    # 真正的同距歧义（两个候选编辑距离相同）不改写
    tie_known = {"echarts_cccx3333_0", "echarts_cccc3333_1"}
    assert repair_chart_reference_ids("[[chart:echarts_cccc3333_0]]", tie_known) == "[[chart:echarts_cccc3333_0]]"


def test_repair_chart_reference_ids_never_crosses_prefix():
    known = {"matplotlib_abc123"}
    assert repair_chart_reference_ids("[[chart:echarts_nyeutr7b_0]]", known) == "[[chart:echarts_nyeutr7b_0]]"


def test_repair_chart_reference_ids_handles_empty_and_no_marker():
    assert repair_chart_reference_ids("plain text", {"echarts_a"}) == "plain text"
    assert repair_chart_reference_ids("[[chart:echarts_a]]", set()) == "[[chart:echarts_a]]"
    assert repair_chart_reference_ids(None, {"echarts_a"}) is None


def test_repair_needs_to_handle_cross_prefix_mangling():
    """回归（2026-10-19）：模型把 echarts_hnccwfa3se_0 抄成 echccwfa3se_0
    （丢 arts_hn，距离 7、前缀变 ech）、把 echarts_hnccwfa41h_1 抄成
    hnccwfa41h_1（丢 echarts_，距离 8、前缀变 hnccwfa41h）——超出现有
    同前缀+距离≤3 修复能力。此类抄错由会话级短别名协议（visual_alias）
    在协议层消除，模糊修复不承担。"""
    known = {"echarts_hnccwfa3se_0", "echarts_hnccwfa41h_1"}
    for marker in ("[[chart:echccwfa3se_0]]", "[[chart:hnccwfa41h_1]]"):
        assert repair_chart_reference_ids(f"图\n{marker}\n文", known) == f"图\n{marker}\n文"


async def test_short_alias_ids_are_protocol_compliant_and_resolvable():
    """别名 chart_N 是 [[chart:<id>]] 协议的合法 ID；解析发生在后端。"""
    from app.agent.runtime.visual_alias import (
        VisualAliasRegistry,
        resolve_chart_alias_markers,
        is_alias_id,
    )

    assert is_alias_id("chart_0")

    registry = VisualAliasRegistry()
    await registry.bind("session_x", ["echarts_hnccwfa3se_0", "echarts_hnccwfa41h_1"])
    text = "图一\n\n[[chart:chart_0]]\n\n图二\n\n[[chart:chart_1]]\n"
    resolved = await resolve_chart_alias_markers(text, "session_x", registry=registry)
    assert "[[chart:echarts_hnccwfa3se_0]]" in resolved
    assert "[[chart:echarts_hnccwfa41h_1]]" in resolved
    assert "chart_0" not in resolved and "chart_1" not in resolved
