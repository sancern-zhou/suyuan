"""Expert deliberation-only ReAct prompts."""

from __future__ import annotations

from typing import List, Optional


def build_deliberation_meteorology_prompt(
    available_tools: List[str],
    memory_context: Optional[str] = None,
    memory_file_path: Optional[str] = None,
) -> str:
    return (
        "你是会商场景内部使用的气象会商专家，专注气象扩散、轨迹传输、上风向企业和气象数据补证。"
        "只基于事实账本和工具 Observation 判断；最终回答必须服从用户消息中的 JSON schema。"
        f"\n当前模式工具数：{len(available_tools)}。"
    )


def build_deliberation_chemistry_prompt(
    available_tools: List[str],
    memory_context: Optional[str] = None,
    memory_file_path: Optional[str] = None,
) -> str:
    return (
        "你是会商场景内部使用的化学会商专家，专注组分数据、PMF源解析、组分重构和二次生成补证。"
        "不得在缺少 PMF 或组分证据时写精确贡献比例；最终回答必须服从用户消息中的 JSON schema。"
        f"\n当前模式工具数：{len(available_tools)}。"
    )


def build_deliberation_reviewer_prompt(
    available_tools: List[str],
    memory_context: Optional[str] = None,
    memory_file_path: Optional[str] = None,
) -> str:
    return (
        "你是会商场景内部使用的会商审查员，专注审查事实链、证据充分性和禁写结论。"
        "重点识别无事实编号、无工具 Observation 或过度因果推断的结论；最终回答必须服从用户消息中的 JSON schema。"
        f"\n当前模式工具数：{len(available_tools)}。"
    )
