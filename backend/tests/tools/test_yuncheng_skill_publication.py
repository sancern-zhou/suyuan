import pytest

from app.tools.utility.skill_management.list_skills_tool import ListSkillsTool
from app.tools.utility.skill_management.view_skill_tool import ViewSkillTool


@pytest.mark.asyncio
async def test_yuncheng_alert_tracing_skill_is_published_as_official_skill():
    listed = await ListSkillsTool().execute(keyword="运城")

    assert listed["success"] is True
    skill_files = {skill["file"] for skill in listed["data"]["skills"]}
    assert any(file.endswith("yuncheng_alert_tracing_skill.md") for file in skill_files)

    viewed = await ViewSkillTool().execute(name="yuncheng_alert_tracing_skill")

    assert viewed["success"] is True
    assert viewed["data"]["is_draft"] is False
    assert "运城市告警溯源分析 Skill" in viewed["data"]["content"]


@pytest.mark.asyncio
async def test_yuncheng_alert_tracing_skill_defines_aqi_and_actionable_field_advice():
    viewed = await ViewSkillTool().execute(name="yuncheng_alert_tracing_skill")

    content = viewed["data"]["content"]
    assert "AQI 小时值" in content
    assert "AQI > 100" in content
    assert "轻度污染" in content
    assert "不等同于单项污染物小时浓度超过 100" in content
    assert "建议时间窗" in content
    assert "核查范围" in content
    assert "现场动作" in content
    assert "补充数据" in content
    assert "升级条件" in content


@pytest.mark.asyncio
async def test_yuncheng_alert_tracing_skill_delegates_to_two_expert_subagents():
    viewed = await ViewSkillTool().execute(name="yuncheng_alert_tracing_skill")
    content = viewed["data"]["content"]

    assert "气象分析专家子 Agent" in content
    assert "常规分析专家子 Agent" in content
    assert "backend/docs/skills/weather_analysis_expert.md" in content
    assert "backend/docs/skills/routine_monitoring_analysis_expert.md" in content
    assert '"expert_type"' in content
    assert '"draft_path"' in content


@pytest.mark.asyncio
async def test_yuncheng_alert_tracing_skill_requires_synchronous_call_sub_agent_and_forbids_spawn():
    viewed = await ViewSkillTool().execute(name="yuncheng_alert_tracing_skill")
    content = viewed["data"]["content"]

    assert "call_sub_agent" in content
    assert "同步" in content
    assert "禁止使用 `spawn`" in content
    assert "不得返回中间状态" in content


@pytest.mark.asyncio
async def test_yuncheng_expert_guides_are_published_official_skills():
    listed = await ListSkillsTool().execute(keyword="气象 常规 专家")

    assert listed["success"] is True
    skill_files = {skill["file"] for skill in listed["data"]["skills"]}
    assert any(file.endswith("weather_analysis_expert.md") for file in skill_files)
    assert any(file.endswith("routine_monitoring_analysis_expert.md") for file in skill_files)

    weather = await ViewSkillTool().execute(name="weather_analysis_expert")
    routine = await ViewSkillTool().execute(name="routine_monitoring_analysis_expert")

    assert weather["success"] is True
    assert routine["success"] is True
    assert "气象分析专家 Skill" in weather["data"]["content"]
    assert "常规监测分析专家 Skill" in routine["data"]["content"]
    for content in (weather["data"]["content"], routine["data"]["content"]):
        assert "业务知识" in content
        assert "分析逻辑" in content
        assert "具体任务" not in content


@pytest.mark.asyncio
async def test_yuncheng_skill_and_experts_require_asset_reading_and_image_drafts():
    main = await ViewSkillTool().execute(name="yuncheng_alert_tracing_skill")
    weather = await ViewSkillTool().execute(name="weather_analysis_expert")
    routine = await ViewSkillTool().execute(name="routine_monitoring_analysis_expert")

    assert main["success"] is True
    assert weather["success"] is True
    assert routine["success"] is True

    main_content = main["data"]["content"]
    weather_content = weather["data"]["content"]
    routine_content = routine["data"]["content"]

    for content in (main_content, weather_content):
        assert "meteorology_history.json" in content
        assert "trajectory_analysis.json" in content
        assert "trajectory.png" in content
        assert "wind_field.png" in content
        assert "forecast_meteorology.json" in content

    for content in (main_content, routine_content):
        assert "target_city_pollutants.json" in content
        assert "nearby_city_pollutants.json" in content
        assert "air_quality_24h_forecast.json" in content
        assert "fire_hotspots_summary.json" in content
        assert "fire_hotspots_map.png" in content

    for content in (weather_content, routine_content):
        assert "必须先读取并分析这些资产" in content
        assert "已阅读资产" in content
        assert "建议插入图片" in content


def test_yuncheng_task_prompt_requires_expert_subagent_drafts():
    prompt = (
        __import__("pathlib")
        .Path("config/task_lists/yuncheng_alert_tracing_assistant_prompt.md")
        .read_text(encoding="utf-8")
    )

    assert "调用 expert 模式子 Agent" in prompt
    assert "气象分析专家" in prompt
    assert "常规分析专家" in prompt
    assert "expert_type" in prompt
    assert "draft_path" in prompt
    assert "读取两个专家草稿" in prompt


def test_yuncheng_task_prompt_keeps_wechat_push_in_social_mode():
    prompt = (
        __import__("pathlib")
        .Path("config/task_lists/yuncheng_alert_tracing_assistant_prompt.md")
        .read_text(encoding="utf-8")
    )

    assert "社交模式定时任务" in prompt
    assert "告警 JSON" in prompt
    assert "助手模式" in prompt
    assert "社交模式收到回复后推送报告给微信用户" in prompt
    assert "微信推送告警摘要和 Word 附件" not in prompt
    assert "从 manifest 和证据目录中整理实际存在的资产路径" not in prompt
    assert "air_quality_24h_forecast.json" not in prompt
    assert "fire_hotspots_map.png" not in prompt


@pytest.mark.asyncio
async def test_yuncheng_skill_defines_direct_assistant_event_contract():
    viewed = await ViewSkillTool().execute(name="yuncheng_alert_tracing_skill")
    content = viewed["data"]["content"]

    assert "事件任务使用助手模式直接执行本 skill" in content
    assert "告警状态为 `has_alert=true` 且 `status=pending_trace`" in content
    assert "调用专家子 Agent 分析" in content
    assert "生成报告、Word 文件和微信摘要" in content
    assert '"broadcast"' in content
    assert '"message"' in content
    assert '"media"' in content
    assert "事件任务服务负责广播" in content
    assert "不直接调用微信、广播或通知工具" in content
    assert "社交模式收到回复后推送" not in content
    assert "调用助手模式执行本 skill" not in content


@pytest.mark.asyncio
async def test_yuncheng_skill_requires_asset_time_aware_business_timeline():
    viewed = await ViewSkillTool().execute(name="yuncheng_alert_tracing_skill")

    assert viewed["success"] is True
    content = viewed["data"]["content"]
    for phrase in (
        "污染过程时间线",
        "目标城市小时数据作为主时间轴",
        "实际有效时次",
        "不强行对齐",
        "告警前背景",
        "告警触发时刻",
        "未来数小时趋势",
        "变化—同期情况—业务意义",
    ):
        assert phrase in content
    assert "关键变化看板" not in content
    assert "## 天气与传输影响" not in content


@pytest.mark.asyncio
async def test_yuncheng_skill_keeps_timeline_business_facing():
    viewed = await ViewSkillTool().execute(name="yuncheng_alert_tracing_skill")

    content = viewed["data"]["content"]
    for phrase in (
        "图片紧跟其对应的时间节点",
        "有效时次",
        "起报时间",
        "预报时效",
        "执行时段",
        "无法确认有效时次",
    ):
        assert phrase in content
    for forbidden in ("证据强度", "置信度", "假设竞争"):
        assert forbidden not in content


@pytest.mark.asyncio
async def test_yuncheng_experts_return_time_ordered_business_drafts():
    weather = await ViewSkillTool().execute(name="weather_analysis_expert")
    routine = await ViewSkillTool().execute(name="routine_monitoring_analysis_expert")

    for viewed in (weather, routine):
        content = viewed["data"]["content"]
        assert "按实际时间顺序" in content
        assert "实际有效时次" in content
        assert "建议挂接的时间节点" in content

    assert "轨迹受体时刻" in weather["data"]["content"]
    assert "起报时间和预报时效" in weather["data"]["content"]
    assert "目标城市小时数据作为主时间轴" in routine["data"]["content"]
    assert "污染变化、周边情况和业务关注点" in routine["data"]["content"]


def test_yuncheng_task_prompt_requires_timeline_integration():
    prompt = (
        __import__("pathlib")
        .Path("config/task_lists/yuncheng_alert_tracing_assistant_prompt.md")
        .read_text(encoding="utf-8")
    )

    for phrase in (
        "目标城市小时数据作为主时间轴",
        "读取所有资产的实际有效时次",
        "不强行对齐",
        "污染过程时间线",
        "变化—同期情况—业务意义",
        "图片紧跟其对应的时间节点",
    ):
        assert phrase in prompt
