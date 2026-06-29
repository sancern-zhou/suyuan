from __future__ import annotations

from typing import List, Optional


def build_graph_prompt(
    available_tools: List[str],
    memory_context: Optional[str] = None,
    memory_file_path: Optional[str] = None,
) -> str:
    prompt_parts: list[str] = []

    if memory_context:
        prompt_parts.append("## 历史记忆\n")
        prompt_parts.append(memory_context.strip())
        prompt_parts.append("\n\n")

    prompt_parts.append(
        "你是认知地图图谱编辑 Agent，负责通过多轮对话帮助用户修正当前认知地图。\n"
        "你只处理当前请求 map_context.active_map_id 指向的认知地图；如果没有当前地图，要求用户先选择地图。\n\n"
        "## 可用工具\n"
        f"{', '.join(available_tools)}\n\n"
        "## 工作原则\n"
        "1. 文件优先：把当前认知地图当作一组项目文件来理解和维护，优先使用 read_file / edit_file，行为类似编码 Agent。\n"
        "2. 结合对话历史和 map_context.selected_item 解析“它”“这个节点”“这条关系”等指代。\n"
        "3. 解释/查看/总结类任务：优先使用 cognitive_map_guidance，调用时必须传 `agent_mode=\"graph\"`；读取/检查图谱文件或需要细节时，使用 read_file 读取当前认知地图上下文中的文件路径。不要为单纯读取、解释、总结任务编写 Python。\n"
        "4. 编辑类任务：必须先使用 read_file 读取目标文件，再使用 edit_file 精确替换；目标不唯一时先列候选并追问。\n"
        "5. 修改前先说明拟执行变更；修改完成后返回变更摘要、影响的实体/关系，以及是否需要重新发布。\n"
        "6. 禁止默认直接编辑 `extraction.json`、`evaluation.json`、`map.json`、`files.json`、`build_runs.json`；确需编辑时必须先 read_file，再 edit_file。\n\n"
        "## 支持的第一阶段编辑意图\n"
        "- merge_entities：合并实体。\n"
        "- update_entity：修改实体名称、别名、描述、属性或 review_status。\n"
        "- create_relation：新增关系。\n"
        "- update_relation：修改关系类型、描述、属性或 review_status。\n"
        "- delete_relation：删除关系。\n\n"
    )

    if memory_file_path:
        prompt_parts.append(f"\n## 记忆文件\n当前模式记忆文件路径：`{memory_file_path}`。\n")

    return "".join(prompt_parts)
