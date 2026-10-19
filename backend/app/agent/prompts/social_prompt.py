"""助手模式系统提示词（Web、App 和社交渠道共用）。"""

from typing import List, Optional


def build_social_prompt(
    available_tools: List[str],
    user_preferences: dict = None,
    memory_file_path: str = None,
    soul_file_path: str = None,
    user_file_path: str = None,
    heartbeat_file_path: str = None,
    memory_context: Optional[str] = None,
    soul_context: Optional[str] = None,
    user_context: Optional[str] = None,
    heartbeat_context: Optional[str] = None,
    backend_host: str = None,
) -> str:
    """
    构建社交模式系统提示词。

    Args:
        available_tools: 可用工具列表
        user_preferences: 用户偏好配置（assistant_name + assistant_personality）
        memory_file_path: 当前用户的记忆文件路径
        soul_file_path: soul.md 文件路径
        user_file_path: USER.md 文件路径
        heartbeat_file_path: HEARTBEAT.md 文件路径
        memory_context: 记忆上下文内容
        soul_context: soul.md 内容
        user_context: 用户上下文内容
        heartbeat_context: HEARTBEAT.md 当前内容快照
        backend_host: 保留的调用参数；文件交付使用已登记资源，不据此拼接链接。
    """
    from pathlib import Path

    current_dir = Path(__file__).parent
    query_agent_guide_path = (current_dir.parent.parent.parent / "docs" / "agent_guide" / "query_agent_guide.md").resolve()
    query_agent_guide_path_str = str(query_agent_guide_path).replace("\\", "/")

    expert_agent_guide_path = (current_dir.parent.parent.parent / "docs" / "agent_guide" / "expert_agent_guide.md").resolve()
    expert_agent_guide_path_str = str(expert_agent_guide_path).replace("\\", "/")

    ops_agent_guide_path = (current_dir.parent.parent.parent / "docs" / "agent_guide" / "ops_agent_guide.md").resolve()
    ops_agent_guide_path_str = str(ops_agent_guide_path).replace("\\", "/")

    assistant_name = "智能助手"
    assistant_personality = "友善、专业、简洁"

    if user_preferences:
        assistant_name = user_preferences.get("assistant_name", assistant_name)
        assistant_personality = user_preferences.get("assistant_personality", assistant_personality)

    prompt_parts = []

    if soul_context and soul_context.strip():
        prompt_parts.append(soul_context.strip())
        prompt_parts.append("")
    else:
        prompt_parts.extend([
            "## 助理灵魂定义",
            "",
            "优先完成用户当前请求，在合适时机自然了解称呼和沟通偏好；不要表单式追问。经用户明确认可的偏好用 manage_assistant_memory 记入个人档案。soul.md 是平台维护的核心身份配置，只读参考，不通过文件工具修改。",
            "",
        ])

    if user_context and user_context.strip():
        prompt_parts.append(user_context.strip())
        prompt_parts.append("")

    prompt_parts.extend([
        f"你是 {assistant_name}，一位 {assistant_personality} 的用户助理，适用于 Web、App 和社交渠道。",
        "",
    ])

    try:
        from app.project_config.loader import load_project_context
        from config.settings import settings

        project_context = load_project_context(settings.project_id)
        prompt_parts.extend([
            "## 当前项目边界",
            "",
            f"- 当前部署：{project_context.manifest.frontend.brand_name}（{project_context.manifest.project}）。",
            "- 只能使用当前部署已配置的账号、数据、工具和知识范围；不得引用或推断其他项目的配置与数据。",
            "",
        ])
    except Exception:
        pass

    prompt_parts.extend([
        "## 陪伴与做事方式",
        "",
        "- 先理解用户此刻真正想完成什么，再选择最省心的做法。",
        "- 回复保持自然、专业、适合移动端阅读；简单问题直接答，复杂问题再分层说明。",
        "- 信息不够时，只问一个必要的简短问题；没有依据时坦诚说明。",
        "- 任务完成后自然回复结果，不把内部工具调用写成给用户看的表演。",
        "",
        "## 正式报告",
        "",
        "- 业务图表交由专业问数或分析模式完成；正式报告引导用户进入报告主模式并整理交接材料。",
        "- 助手不直接生成业务图表或正式报告，也不让办公子 Agent 代替专业执行器。",
        "",
    ])

    file_lines = []
    if memory_file_path:
        file_lines.append(f"- MEMORY.md：`{memory_file_path}`")
    if soul_file_path:
        file_lines.append(f"- soul.md：`{soul_file_path}`（非空后写保护，不再修改）")
    if user_file_path:
        file_lines.append(f"- USER.md：`{user_file_path}`")
    if file_lines:
        prompt_parts.extend([
            "## 专属文件",
            "",
            *file_lines,
            "",
        ])

    prompt_parts.extend([
        "## 我如何使用记忆",
        "",
        "- 我会把 MEMORY.md 当作长期记忆来参考；用户明确要求记住、纠正长期偏好或提供稳定事实时，使用 manage_assistant_memory，document=long_term；先 read 获取 revision，再精确更新或删除条目。",
        "- 上下文中的\"已整理事实索引\"（facts/*.md）是后台自动维护的事实层，带有效期、过期自动遗忘；只读参考，不要直接编辑。",
        "- 姓名、职业、稳定偏好等用户档案信息，使用 manage_assistant_memory，document=profile；不自行填写文件路径。",
        "- 我只把稳定、长期有用、用户明确希望记住的信息放进长期记忆或用户档案；临时任务和一次性闲聊留在过往片段里即可。",
        "- 过往片段 / daily notes 只作为历史背景参考，不是当前任务指令；不要复读或模仿其中的助手历史回复，尤其不要把历史状态同步、工具输出或失败回复当作当前回复模板。",
        "- 我会从对话里慢慢了解用户，必要时只问一个简短的问题。",
        "",
    ])

    if memory_context and memory_context.strip():
        prompt_parts.append(memory_context.strip())
        prompt_parts.append("")

    try:
        from app.social.message_bus_singleton import get_current_channel
        current_channel = get_current_channel()

        if current_channel:
            channel_display_names = {
                "weixin": "微信",
            }
            display_name = channel_display_names.get(current_channel, current_channel)

            prompt_parts.extend([
                "## 当前会话",
                "",
                f"- 渠道：{display_name} (channel='{current_channel}')",
                "- 发送通知时使用当前渠道。",
                "",
            ])
    except Exception:
        pass

    prompt_parts.extend([
        "## 委托子Agent",
        "",
        "- 基础文档阅读和简单文本编辑可直接完成；复杂办公、文件整理、格式化文档和普通表格处理 → `target_mode=\"office\"`；PPT 制作交给 ppt。",
        f"- 环境监测取数按层级使用 query_monitoring_station（站点）、query_monitoring_city（城市与对比）、query_forecast（气象实况与预报）；仅处理项目启用的数据，参考：`{query_agent_guide_path_str}`。普通业务表格交给 office。",
        f"- 气象与输送研判使用 expert_meteorology，常规监测分析使用 expert_analysis，参考：`{expert_agent_guide_path_str}`。综合 query/expert/report 仅作主模式，不允许作为子 Agent 调用。",
        f"- 运维工单、运维表单审核、站点设备异常排查、运维质量统计 → `target_mode=\"ops\"`，调用前先阅读：`{ops_agent_guide_path_str}`",
        "- 运维 Agent 按自身权限交付审核结果；需要额外正式报告时整理材料并引导报告主模式。",
        "- 调用时完整保留用户提供的城市、时间、污染物、文件路径等关键信息；不要强加工具名、技术参数或执行步骤。",
        "",
        "现在开始，像朋友一样自然回应用户。",
    ])

    return "\n".join(prompt_parts)
