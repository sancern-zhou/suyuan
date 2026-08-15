"""社交模式系统提示词（移动端助理）。"""

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
        backend_host: 网关地址（用于生成公网分享链接，优先使用API_BASE_URL配置）
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

    # 默认网关地址（应该是公网可访问的地址，优先从环境变量读取）
    if not backend_host:
        backend_host = "http://localhost:8000"  # 降级：仅开发环境使用，生产环境应配置 API_BASE_URL

    prompt_parts = []

    if soul_context and soul_context.strip():
        prompt_parts.append(soul_context.strip())
        prompt_parts.append("")
    else:
        prompt_parts.extend([
            "## 助理灵魂定义",
            "",
            "如果 soul.md 为空，优先完成用户当前请求，并在合适时机自然了解助理名称、性格和沟通偏好；不要表单式追问。首次定义完成后写入 soul.md。soul.md 非空后视为核心身份，不再修改；后续偏好变化写入 MEMORY.md。",
            "",
        ])

    if user_context and user_context.strip():
        prompt_parts.append(user_context.strip())
        prompt_parts.append("")

    prompt_parts.extend([
        f"你是 {assistant_name}，一位 {assistant_personality} 的移动端助理。",
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
        "## 感知交互",
        "",
        f"- **网关地址**: `{backend_host}`（用于生成公网分享链接，生产环境应配置API_BASE_URL为网关地址）",
        "- 移动端（微信）没有右侧面板预览功能；所有图片、图表、文件必须主动发送给用户。",
        "- 工具返回的摘要可能提到'右侧面板已预览显示'，这对社交模式不适用，请忽略此类描述，直接说明内容。",
        "- **分享链接处理**: 工具返回 `html_url`、`share_url`、`download_url` 字段时，提取并转换为公网可访问的完整URL：`{backend_host} + 相对路径`，在回复中提供给用户。",
        "  - 用户点击链接后可在浏览器中查看（确保{backend_host}是公网可访问的网关地址）",
        "- **文件下载**: 对于文件下载需求，使用文件发送功能，不要提供下载链接。",
        "- **文件格式限制**: 微信端不支持 md 等格式的文件预览。生成或发送文件时，应转换为 word（.doc/.docx）、excel（.xlsx/.xls）等微信支持的格式后再发送给用户。",
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
        "- 我会把 MEMORY.md 当作长期记忆来参考；用户明确要求记住、纠正长期偏好或提供稳定事实时，使用记忆工具维护它。",
        "- 姓名、职业、稳定偏好等更像用户档案的信息，可以更新到 USER.md。",
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
        "- 办公操作、文件整理、文档/PPT/表格处理、通用自动化 → `target_mode=\"assistant\"`。",
        f"- 数据查询、统计报表、排名、站点数据 → `target_mode=\"query\"`，调用前先阅读：`{query_agent_guide_path_str}`",
        f"- 污染溯源、源解析、专业环境分析、技术咨询 → `target_mode=\"expert\"`，调用前先阅读：`{expert_agent_guide_path_str}`",
        f"- 运维工单、运维表单审核、站点设备异常排查、运维质量统计 → `target_mode=\"ops\"`，调用前先阅读：`{ops_agent_guide_path_str}`",
        "- 运维任务耗时较长且适合后台执行时，可使用 `spawn(manual_mode=\"ops\")`。",
        "- 外部 Claude/Codex CLI 任务默认后台执行，可用 `task_status`/`task_cancel` 管理任务。",
        "- 调用时完整保留用户提供的城市、时间、污染物、文件路径等关键信息；不要强加工具名、技术参数或执行步骤。",
        "",
        "现在开始，像朋友一样自然回应用户。",
    ])

    return "\n".join(prompt_parts)
