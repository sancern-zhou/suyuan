"""客户端来源标记（client_channel）契约测试。

请求入口经 runtime_metadata 透传 client_channel（web/app），上下文构建器
渲染 <client_channel> 层，模式提示词据此做端侧差异分支（App 静态图、精简回复）。
"""
from unittest.mock import Mock

from app.agent.context.context_builder import SimplifiedContextBuilder
from app.agent.prompts.chart_prompt import build_chart_prompt
from app.agent.prompts.knowledge_prompt import build_knowledge_prompt
from app.agent.prompts.query_prompt import build_query_prompt
from app.agent.prompts.tool_registry import get_tools_by_mode


def _builder(client_channel):
    builder = SimplifiedContextBuilder(Mock(), Mock(), {})
    builder.current_mode = "query"
    builder.client_channel = client_channel
    return builder


def test_app_channel_is_marked_in_platform_policy_layer():
    layer = _builder("app")._build_platform_policy_prompt()
    assert "<client_channel>" in layer
    assert "App 端（Android 手机客户端）" in layer


def test_web_channel_is_marked_in_platform_policy_layer():
    layer = _builder("web")._build_platform_policy_prompt()
    assert "<client_channel>" in layer
    assert "Web 端（桌面浏览器）" in layer


def test_missing_channel_renders_no_client_marker():
    layer = _builder(None)._build_platform_policy_prompt()
    assert "<client_channel>" not in layer


def test_query_prompt_branches_chart_form_by_channel():
    prompt = build_query_prompt([])
    # Web 契约句保留；App 端与专家模式一致，用 Python 直绘静态图
    assert "问数绘图以 `execute_echarts_python`（ECharts 交互图）为主" in prompt
    assert "App 端（client_channel 为 app）" in prompt
    assert "`execute_python`（Matplotlib/Seaborn）绘制 PNG 静态图" in prompt
    assert "不产出 ECharts 交互图资源" in prompt
    assert "render_chart_to_image" not in prompt


def test_mode_prompts_state_app_has_no_side_panel():
    for prompt in (build_query_prompt([]), build_knowledge_prompt([])):
        assert "App 端没有 Web 端的右侧面板" in prompt
        assert "适当精简" in prompt


def test_chart_prompt_branches_output_form_without_tool_names():
    prompt = build_chart_prompt([])
    assert "App 端" in prompt and "PNG" in prompt
    for tool_name in ("execute_echarts_python", "render_chart_to_image", "execute_python", "read_file"):
        assert tool_name not in prompt


def test_static_render_tool_stays_out_of_chart_mode_whitelists():
    # App 端静态图由 execute_python 直绘（已在白名单），不引入 ECharts 转 PNG 的渲染工具
    assert "render_chart_to_image" not in get_tools_by_mode("query")
    assert "render_chart_to_image" not in get_tools_by_mode("chart")
    assert "execute_python" in get_tools_by_mode("query")
    assert "execute_python" in get_tools_by_mode("chart")
