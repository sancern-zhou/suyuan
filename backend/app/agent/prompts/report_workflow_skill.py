"""分析报告通用工作流技能（专家/报告模式共用提示词片段）。

技能正文：backend/docs/skills/analysis_report_workflow.md
"""

REPORT_WORKFLOW_SKILL_PATH = "backend/docs/skills/analysis_report_workflow.md"

_REPORT_WORKFLOW_SKILL_BODY = [
    "九步流程：明确任务边界（Define）→ 拆解问题结构（Frame）→ 数据获取（Collect）→ "
    "校验与清洗（Validate）→ 分析（Analyze）→ 提炼结论（Synthesize）→ 成稿与可视化（Compose）→ "
    "质检（Review）→ 交付（Deliver）。",
    "流程按需裁剪：正式报告走全程；快问快答只需\"拆解+分析\"两步，直接给结论。"
    "流程是并行迭代的，不是严格瀑布——分析中发现口径或数据问题，回到第 1 步重新对齐后再继续。",
    "工作原则：不编数字、数据和结论可回溯、内部区分事实/推断/建议三种强度、量化优先、"
    "先结论后论证（金字塔结构）。",
    "关键数字必须用 execute_python 或查询工具实际计算并交叉验证（至少两个来源或两种算法），不凭感觉给数；"
    "交付时附数据来源与口径说明、关键假设和局限性。",
]


def report_workflow_skill_section(intro: str) -> str:
    """构建模式特定的分析报告通用工作流提示词片段。

    Args:
        intro: 首段引导语（各模式按自身流程定制衔接方式）。
    """
    header = f"## 分析报告通用工作流（技能）\n\n{intro}"
    body = "\n".join(f"- {item}" for item in _REPORT_WORKFLOW_SKILL_BODY)
    return f"{header}\n{body}"
