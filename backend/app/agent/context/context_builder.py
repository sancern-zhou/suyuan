"""
简化的上下文构建器

按照提示词结构分为两部分：
1. 系统提示词：模式提示词 + 记忆/社交档案
2. 用户对话内容：仅当前轮状态提示和当前查询

对话历史由 Anthropic 原生 messages 单独传递，不能再格式化成文本重复注入。
"""

from typing import Dict, Any, List, Optional
import json
import structlog
from datetime import datetime

from ..memory.context_compressor import ContextCompressor
from ...utils.token_budget import token_budget_manager

logger = structlog.get_logger()


class SimplifiedContextBuilder:
    """
    简化的上下文构建器

    核心职责：
    1. 构建系统提示词（固定部分）
    2. 构建当前轮用户消息（动态部分）
    3. 超过80%阈值时触发LLM压缩

    注意：
    - conversation_history 会以结构化 messages 传给 LLM。
    - 不要把 conversation_history 转成 "## 对话历史" 文本塞进 user message，
      否则 tool_use/tool_result 会重复进入上下文。
    """

    def __init__(self, llm_client, memory_manager, tool_registry=None):
        """
        初始化简化的上下文构建器

        Args:
            llm_client: LLM客户端（用于压缩）
            memory_manager: HybridMemoryManager实例
            tool_registry: 工具注册表（可选）
        """
        self.llm_client = llm_client
        self.memory = memory_manager
        self.tool_registry = tool_registry
        self.compressor = ContextCompressor(llm_client)

        # Token配置
        self.max_context_tokens = token_budget_manager.max_context_tokens
        self.safety_buffer = token_budget_manager.safety_buffer
        self.compression_threshold = 0.8  # 80%阈值

        # ✅ 新增：当前模式（默认expert）
        self.current_mode = "expert"

        # ✅ 新增：记忆上下文内容（从快照获取，用于系统提示词注入）
        self.memory_context = None

        # ✅ 新增：用户记忆文件路径（仅social模式使用）
        self.memory_file_path = None

        # ✅ 新增：用户偏好配置（仅social模式使用）
        self.user_preferences = None

        # ✅ 新增：用户上下文内容（从USER.md获取，仅social模式使用）
        self.user_context = None

        # ✅ 新增：soul上下文内容（从soul.md获取，仅social模式使用）
        self.soul_context = None

        # ✅ 新增：soul文件路径（仅social模式使用）
        self.soul_file_path = None

        # ✅ 新增：USER文件路径（仅social模式使用）
        self.user_file_path = None

        # ✅ 新增：HEARTBEAT文件路径（仅social模式使用）
        self.heartbeat_file_path = None

        # ✅ 新增：HEARTBEAT文件内容快照（仅social模式使用）
        self.heartbeat_context = None

        # 图表模式 draw.io 画板上下文，仅 chart 模式允许注入。
        self.board_context = None

        # 问数模式地图交互上下文，仅 query 模式允许注入。
        self.map_context = None

        # 当前逻辑会话的共享资源投影。此字段不受模式隔离策略清理。
        self.session_resource_context = None

        # 知识库图谱上下文，由 Agent 入口按 graph 模式绑定注入。

        logger.info(
            "context_builder_initialized",
            max_context=self.max_context_tokens,
            safety_buffer=self.safety_buffer,
            compression_threshold=f"{self.compression_threshold*100}%"
        )

    async def build_for_thought_action(
        self,
        query: str,
        iteration: int,
        latest_observation: str = "",
        conversation_history: Optional[List[Dict[str, Any]]] = None,
        mode: str = "expert",  # ✅ 新增：Agent模式
        is_interruption: bool = False  # ✅ 新增：中断标志
    ) -> Dict[str, Any]:
        """
        为 Thought + Action 构建完整上下文

        Args:
            query: 用户查询
            iteration: 当前迭代次数
            latest_observation: 最新观察结果（可选）
            conversation_history: 对话历史（可选，LLM消息格式）
            mode: Agent模式（"assistant" | "expert"）

        Returns:
            {
                "system_prompt": str,      # 系统提示词（固定）
                "user_conversation": str,   # 用户对话内容（动态）
                "tokens": {
                    "system": int,
                    "user": int,
                    "total": int,
                    "compressed": bool
                }
            }
        """
        # 设置当前模式
        self.current_mode = mode
        self._apply_mode_context_policy(mode)

        # ✅ 调试日志：检查查询是否包含记忆
        has_memory_in_query = "长期记忆" in query and "记忆文件路径" in query
        if has_memory_in_query:
            logger.debug(
                "query_contains_memory",
                query_length=len(query),
                memory_marker_found="长期记忆" in query,
                file_path_marker_found="记忆文件路径" in query,
                query_preview=query[:300]
            )

        # 1. 构建系统提示词（固定部分）
        system_prompt = self._build_system_prompt()
        system_tokens = token_budget_manager.count_tokens(system_prompt)

        # 2. 构建用户对话内容（动态部分）
        user_conversation = self._build_user_conversation(
            query=query,
            iteration=iteration,
            latest_observation=latest_observation,
            conversation_history=conversation_history,
            is_interruption=is_interruption  # ✅ 传递中断标志
        )
        user_tokens = token_budget_manager.count_tokens(user_conversation)
        history_tokens = self._estimate_messages_tokens(conversation_history)

        # 3. 计算总token（包含结构化历史的估算）
        total_tokens = system_tokens + user_tokens + history_tokens
        max_allowed = int(self.max_context_tokens * self.compression_threshold)

        logger.info(
            "context_built",
            mode=mode,  # ✅ 记录模式
            system_tokens=system_tokens,
            user_tokens=user_tokens,
            history_tokens=history_tokens,
            total_tokens=total_tokens,
            max_allowed=max_allowed,
            usage_ratio=f"{total_tokens/self.max_context_tokens*100:.1f}%"
        )

        # 4. 判断是否需要压缩
        compressed = False
        if total_tokens > max_allowed:
            logger.warning(
                "context_exceeds_threshold_compression_needed",
                total_tokens=total_tokens,
                max_allowed=max_allowed,
                overflow=total_tokens - max_allowed,
                overflow_ratio=f"{(total_tokens/max_allowed - 1)*100:.1f}%"
            )

            # ✅ 修复：直接压缩 conversation_history 并持久化到 session
            compressed_history = await self._compress_and_persist_history(conversation_history)

            # 用压缩后的历史重新构建 user_conversation
            user_conversation = self._build_user_conversation(
                query=query,
                iteration=iteration,
                latest_observation=latest_observation,
                conversation_history=compressed_history,
                is_interruption=is_interruption
            )
            user_tokens_after = token_budget_manager.count_tokens(user_conversation)
            history_tokens_after = self._estimate_messages_tokens(compressed_history)

            logger.info(
                "user_conversation_compressed",
                before_tokens=user_tokens,
                after_tokens=user_tokens_after,
                history_tokens_before=history_tokens,
                history_tokens_after=history_tokens_after,
                compression_ratio=f"{(1 - user_tokens_after/user_tokens)*100:.1f}%",
                history_length_before=len(conversation_history) if conversation_history else 0,
                history_length_after=len(compressed_history) if compressed_history else 0
            )

            compressed = True
            user_tokens = user_tokens_after
            history_tokens = history_tokens_after

        return {
            "system_prompt": system_prompt,
            "user_conversation": user_conversation,
            "tokens": {
                "system": system_tokens,
                "user": user_tokens,
                "history": history_tokens,
                "total": system_tokens + user_tokens + history_tokens,
                "compressed": compressed
            }
        }

    def _build_system_prompt(self) -> str:
        """
        构建系统提示词（固定部分）

        包括：
        1. 根据模式选择的系统提示词（assistant or expert）
        2. 记忆上下文（从快照获取，直接注入）
        3. 用户上下文（从USER.md获取，仅social模式）
        4. 回退到简单工具列表（旧版本兼容）
        """
        # ✅ 使用新的提示词构建器，传递记忆上下文、soul上下文和用户上下文
        from ..prompts.prompt_builder import build_react_system_prompt
        from config.settings import settings

        # 仅social模式需要backend_host（使用公网可访问的网关地址）
        backend_host = None
        if self.current_mode == "social":
            # 优先使用 api_base_url（网关地址，如 http://219.135.180.51:56041）
            # 其次使用 signed_media_base_url（公网后端地址）
            # 最后使用 backend_host（本地地址，仅开发环境）
            backend_host = settings.api_base_url or settings.signed_media_base_url or settings.backend_host

        mode_prompt = build_react_system_prompt(
            mode=self.current_mode,
            available_tools=(
                list(self.tool_registry.keys())
                if self.current_mode == "custom" and isinstance(self.tool_registry, dict)
                else None
            ),
            user_preferences=self.user_preferences,  # ✅ 传递用户偏好（仅social模式使用）
            memory_file_path=self.memory_file_path,  # ✅ 传递记忆文件路径（仅social模式使用）
            soul_file_path=self.soul_file_path,  # ✅ 传递 soul.md 文件路径
            user_file_path=self.user_file_path,  # ✅ 传递 USER.md 文件路径
            heartbeat_file_path=self.heartbeat_file_path,  # ✅ 传递 HEARTBEAT.md 文件路径
            memory_context=self.memory_context,  # ✅ 传递记忆上下文内容（MEMORY.md）
            soul_context=self.soul_context,  # ✅ 传递 soul.md 内容
            user_context=self.user_context,  # ✅ 传递用户上下文内容（USER.md）
            heartbeat_context=self.heartbeat_context,  # ✅ 传递 HEARTBEAT.md 当前内容
            backend_host=backend_host,  # ✅ 传递网关地址（仅social模式使用）
            board_context=self.board_context if self.current_mode == "chart" else None,
        )
        sections = [mode_prompt.rstrip()]
        if self.session_resource_context:
            sections.append(
                "<session_resources>\n"
                + self.session_resource_context.strip()
                + "\n</session_resources>"
            )
        if self.current_mode == "query" and self.map_context:
            sections.append(
                "## Agentic GIS 视觉交互说明\n"
                "- 当前请求可能包含前端地图交互上下文，见用户消息中的“当前地图交互上下文”。\n"
                "- 如需改变用户所见，优先调用 `visual_interaction` 生成 `map_program`，不要只用自然语言描述地图变化。\n"
                "- 地图事件代表用户已在 GIS 中完成的操作，例如框选、视图变化、图层开关；分析时应把它当作当前对话状态。\n"
                "- `map_program_executed` / `map_program_failed` 是前端执行回执；只有回执中 `layer_rendered` 且 feature_count > 0 的图层，才能视为已经真实显示。"
            )
        if self.current_mode == "graph" and self.map_context:
            sections.append(
                "## 知识库图谱编辑上下文\n"
                "- 当前请求来自知识库图谱详情面板的对话编辑入口。\n"
                "- 用户可能用“这个节点”“这条关系”“刚才那个实体”等表达指代，优先结合用户消息中的“当前知识库图谱上下文”。\n"
                "- 修改图谱时使用知识库图谱工具和 API，所有操作限定在当前 knowledge_base_id。"
            )
        sections.append(self._build_runtime_metadata_prompt())
        sections.append(self._build_agent_control_prompt())
        return "\n\n".join(section for section in sections if section)

    def _build_runtime_metadata_prompt(self) -> str:
        """Build system-only runtime metadata used for temporal reasoning."""
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        return (
            "<runtime_metadata>\n"
            f"系统参考时间: {current_time}\n"
            "</runtime_metadata>"
        )

    def _build_agent_control_prompt(self) -> str:
        """Build system-level loop control rules for every agent mode."""
        return (
            "<agent_control>\n"
            "每轮开始前，我先整理眼前的对话、工具结果和刚刚完成的动作，判断用户这件事是否已经可以交代清楚。\n"
            "如果现有信息已经足够，就直接给出自然、明确的回复；如果用户问“刚才在做什么”，优先依据真实对话历史和工具结果回顾。\n"
            "需要补信息时，再安静地调用合适的工具；同一份仍然有效的结果已经拿到后，就继续使用它，不在原地反复查询。\n"
            "</agent_control>"
        )

    def _apply_mode_context_policy(self, mode: str) -> None:
        """Enforce mode-specific context boundaries.

        social:
            May inject MEMORY.md, SOUL.md, USER.md and HEARTBEAT.md metadata/content.
        all other modes:
            May inject only the mode memory document. Social profile files are
            explicitly cleared even if an upstream caller accidentally sets them.
        """
        if mode == "social":
            self.board_context = None
            self.map_context = None
            return

        if any([
            self.user_preferences,
            self.user_context,
            self.soul_context,
            self.soul_file_path,
            self.user_file_path,
            self.heartbeat_file_path,
            self.heartbeat_context,
        ]):
            logger.warning(
                "non_social_context_stripped",
                mode=mode,
                had_user_preferences=self.user_preferences is not None,
                had_user_context=self.user_context is not None,
                had_soul_context=self.soul_context is not None,
                had_soul_file_path=self.soul_file_path is not None,
                had_user_file_path=self.user_file_path is not None,
                had_heartbeat_file_path=self.heartbeat_file_path is not None,
                had_heartbeat_context=self.heartbeat_context is not None,
            )

        self.user_preferences = None
        self.user_context = None
        self.soul_context = None
        self.soul_file_path = None
        self.user_file_path = None
        self.heartbeat_file_path = None
        self.heartbeat_context = None

        if mode != "chart" and self.board_context is not None:
            logger.warning(
                "non_chart_board_context_stripped",
                mode=mode,
            )
            self.board_context = None

        if mode not in {"query", "graph"} and self.map_context is not None:
            logger.warning(
                "mode_without_map_context_stripped",
                mode=mode,
            )
            self.map_context = None

    def _estimate_messages_tokens(self, conversation_history: Optional[List[Dict[str, Any]]]) -> int:
        """Best-effort token estimate for structured message history."""
        if not conversation_history:
            return 0
        try:
            return token_budget_manager.count_tokens(
                json.dumps(conversation_history, ensure_ascii=False, default=str)
            )
        except Exception:
            return 0

    def _get_simple_tool_list(self) -> str:
        """获取简单工具列表（回退方案）"""
        if not self.tool_registry:
            return "**可用工具**：工具加载失败"

        tool_names = list(self.tool_registry.keys())
        return f"**可用工具**：{', '.join(tool_names[:20])}..."

    def _build_board_selection_user_summary(self) -> str:
        """Build a compact current-turn summary for chart board selection."""
        if self.current_mode != "chart" or not isinstance(self.board_context, dict):
            return ""

        selected_cells = (
            self.board_context.get("selected_cells")
            or self.board_context.get("selectedCells")
            or []
        )
        if not isinstance(selected_cells, list) or not selected_cells:
            return ""

        lines = [
            "## 当前画板选中状态",
            f"当前已选中 {len(selected_cells)} 个元素。",
        ]

        for index, cell in enumerate(selected_cells[:5], start=1):
            if not isinstance(cell, dict):
                lines.append(f"{index}. {cell}")
                continue

            cell_id = cell.get("id") or cell.get("cell_id") or cell.get("cellId") or "unknown"
            value = cell.get("value") or cell.get("label") or ""
            cell_type = "edge" if cell.get("edge") else "vertex" if cell.get("vertex") else "cell"
            geometry = cell.get("geometry") if isinstance(cell.get("geometry"), dict) else {}
            geometry_text = ""
            if geometry:
                geometry_text = (
                    f" geometry=(x={geometry.get('x')}, y={geometry.get('y')}, "
                    f"w={geometry.get('width')}, h={geometry.get('height')})"
                )

            label_text = f" value={value}" if value else ""
            lines.append(f"{index}. id={cell_id} type={cell_type}{label_text}{geometry_text}")

        if len(selected_cells) > 5:
            lines.append(f"...另有 {len(selected_cells) - 5} 个选中元素，详见系统提示词 selected_cells JSON。")

        return "\n".join(lines)

    def _build_map_context_user_summary(self) -> str:
        """Build a compact current-turn summary for query-mode GIS interactions."""
        if self.current_mode != "query" or not isinstance(self.map_context, dict):
            return ""

        events = self.map_context.get("events") or []
        if not isinstance(events, list) or not events:
            return ""

        current_program = self.map_context.get("current_program")
        program_id = ""
        if isinstance(current_program, dict):
            program_id = current_program.get("program_id") or current_program.get("id") or ""

        lines = ["## 当前地图交互上下文"]
        if program_id:
            lines.append(f"当前地图程序: {program_id}")
        session_id = self.map_context.get("session_id")
        if session_id:
            lines.append(f"地图会话: {session_id}")

        for index, event in enumerate(events[-5:], start=1):
            if not isinstance(event, dict):
                lines.append(f"{index}. {event}")
                continue

            event_name = event.get("event") or event.get("type") or "unknown"
            active_layers = event.get("active_layers") or event.get("activeLayers") or []
            geometry = event.get("geometry") if isinstance(event.get("geometry"), dict) else None
            view = event.get("map_view") or event.get("view")
            view = view if isinstance(view, dict) else None
            receipt = event.get("receipt") if isinstance(event.get("receipt"), dict) else None

            details = [f"event={event_name}"]
            if active_layers:
                details.append(f"active_layers={json.dumps(active_layers, ensure_ascii=False)}")
            if geometry:
                details.append(f"geometry_type={geometry.get('type')}")
            if view:
                center = view.get("center")
                zoom = view.get("zoom")
                details.append(f"view=center:{center}, zoom:{zoom}")
            if receipt:
                receipt_program = receipt.get("program_id") or ""
                receipt_status = receipt.get("status") or ""
                if receipt_program:
                    details.append(f"receipt_program={receipt_program}")
                if receipt_status:
                    details.append(f"receipt_status={receipt_status}")
                layers = receipt.get("layers") or []
                if isinstance(layers, list) and layers:
                    layer_summaries = []
                    for layer in layers[:20]:
                        if not isinstance(layer, dict):
                            continue
                        layer_summary = f"{layer.get('layer_id')}:{layer.get('status')}:{layer.get('feature_count', 0)}"
                        data_id = layer.get("data_id")
                        if data_id:
                            layer_summary = f"{layer_summary}:data_id={data_id}"
                        layer_summaries.append(layer_summary)
                    if layer_summaries:
                        details.append(f"receipt_layers={json.dumps(layer_summaries, ensure_ascii=False)}")
                    if len(layers) > 20:
                        details.append(f"receipt_layers_omitted={len(layers) - 20}")
                errors = receipt.get("errors") or []
                if isinstance(errors, list) and errors:
                    details.append(f"receipt_errors={json.dumps(errors[:3], ensure_ascii=False)}")

            lines.append(f"{index}. " + " ".join(details))

        if len(events) > 5:
            lines.append(f"...另有 {len(events) - 5} 条地图事件未展开。")

        return "\n".join(lines)

    def _build_graph_map_context_user_summary(self) -> str:
        """Build a compact current-turn summary for knowledge-base graph editing."""
        if self.current_mode != "graph" or not isinstance(self.map_context, dict):
            return ""

        knowledge_base_id = self.map_context.get("knowledge_base_id")
        if not knowledge_base_id:
            return "## 当前知识库图谱上下文\n未收到 knowledge_base_id；请先在知识库面板选择知识库。"

        lines = ["## 当前知识库图谱上下文", f"knowledge_base_id={knowledge_base_id}"]
        lines.append("图谱事实通过知识库图谱子资源查询和修改，不读取独立 JSON 文件。")

        selected_item = self.map_context.get("selected_item")
        if isinstance(selected_item, dict):
            item_kind = selected_item.get("kind") or "unknown"
            item_id = selected_item.get("id") or selected_item.get("entity_id") or selected_item.get("relation_id") or ""
            item_name = selected_item.get("name") or selected_item.get("label") or ""
            lines.append(f"selected_item kind={item_kind} id={item_id} name={item_name}")

        visible_entity_ids = self.map_context.get("visible_entity_ids") or []
        visible_relation_ids = self.map_context.get("visible_relation_ids") or []
        if isinstance(visible_entity_ids, list):
            lines.append(f"visible_entity_ids={len(visible_entity_ids)}")
        if isinstance(visible_relation_ids, list):
            lines.append(f"visible_relation_ids={len(visible_relation_ids)}")

        entity_count = self.map_context.get("entity_count")
        relation_count = self.map_context.get("relation_count")
        if entity_count is not None:
            lines.append(f"entity_count={entity_count}")
        if relation_count is not None:
            lines.append(f"relation_count={relation_count}")

        return "\n".join(lines)

    def _build_user_conversation(
        self,
        query: str,
        iteration: int,
        latest_observation: str,
        conversation_history: Optional[List[Dict[str, Any]]],
        is_interruption: bool = False  # ✅ 新增：中断标志
    ) -> str:
        """
        构建当前轮用户消息（动态部分）

        包括：
        1. 当前查询
        2. 当前运行状态
        3. 必要的附件提示

        Args:
            query: 用户查询
            iteration: 当前迭代次数
            latest_observation: 最新观察结果
            conversation_history: 结构化对话历史（仅用于判断是否为后续迭代，不在此处展开）
            is_interruption: 是否为用户中断后的对话

        Returns:
            用户对话内容字符串
        """
        # ✅ 调试日志：检查查询是否包含记忆
        has_memory_in_query = "长期记忆" in query and "用户问题：" in query
        if has_memory_in_query:
            # 提取记忆部分用于日志预览
            memory_preview = ""
            if "用户问题：" in query:
                memory_part = query.split("用户问题：")[0].strip()
                memory_preview = memory_part[:200]

            logger.info(
                "user_conversation_contains_memory",
                query_length=len(query),
                contains_memory_marker="长期记忆" in query,
                contains_user_question_marker="用户问题：" in query,
                memory_part_preview=memory_preview,
                will_add_to_status_section=True  # ✅ 确认会添加到状态部分
            )

        sections = []

        if not conversation_history:
            logger.warning("context_builder_no_conversation_history", iteration=iteration)

        # ✅ 检测记忆增强内容
        has_memory_enhancement = "长期记忆" in query and "用户问题：" in query
        has_attachments = "**用户上传的附件**" in query
        memory_section = ""
        user_question_section = ""
        attachment_section = ""
        current_input_section = f"## 当前进行的任务\n{query}\n"

        if has_memory_enhancement:
            # 提取记忆部分（在"用户问题："之前）
            if "用户问题：" in query:
                parts = query.split("用户问题：", 1)
                memory_part = parts[0].strip()
                # 提取用户问题和附件信息（在"用户问题："之后的所有内容）
                user_question_and_attachments = parts[1].strip() if len(parts) > 1 else ""
                memory_section = f"\n\n{memory_part}\n\n"

                # ✅ 分离用户问题和附件信息
                if "**用户上传的附件**" in user_question_and_attachments:
                    question_parts = user_question_and_attachments.split("**用户上传的附件**", 1)
                    user_question_section = f"\n\n{question_parts[0].strip()}\n\n"
                    attachment_section = f"\n\n**用户上传的附件**{question_parts[1]}"
                else:
                    user_question_section = f"\n\n{user_question_and_attachments}\n\n"

                # ✅ 调试日志：确认用户问题和附件信息
                logger.debug(
                    "user_question_section_extracted",
                    section_length=len(user_question_section),
                    has_attachments="**用户上传的附件**" in user_question_section,
                    preview=user_question_section[:200]
                )
        elif has_attachments:
            # ✅ 没有记忆增强但有附件（直接从query中提取）
            if "**用户上传的附件**" in query:
                parts = query.split("**用户上传的附件**", 1)
                user_question_section = f"\n\n{parts[0].strip()}\n\n"
                attachment_section = f"\n\n**用户上传的附件**{parts[1]}"
                logger.debug(
                    "attachment_section_extracted_without_memory",
                    user_question_length=len(user_question_section),
                    attachment_length=len(attachment_section),
                    preview=attachment_section[:200]
                )

        if has_memory_enhancement or has_attachments:
            current_input_section = (
                "## 当前进行的任务\n"
                f"{memory_section}"
                f"{user_question_section}"
                f"{attachment_section}"
            )

        if conversation_history:
            # 已有对话历史：结构化 history 已通过 messages 单独传递。
            # 此处不重复展开工具调用、工具结果或通用控制规则。

            board_selection_summary = self._build_board_selection_user_summary()
            if board_selection_summary:
                sections.append(board_selection_summary)
            map_context_summary = self._build_map_context_user_summary()
            if map_context_summary:
                sections.append(map_context_summary)
            graph_map_context_summary = self._build_graph_map_context_user_summary()
            if graph_map_context_summary:
                sections.append(graph_map_context_summary)

            # 当前用户消息不再预写入 conversation_history。第 1 轮需要在
            # 最后一条 user message 中表达本轮输入；后续轮次 history 已包含。
            if iteration == 1:
                sections.append(current_input_section)

            # ✅ 调试日志：确认记忆和用户问题内容已添加
            if has_memory_enhancement or has_attachments:
                logger.debug(
                    "context_added_to_status",
                    memory_length=len(memory_section),
                    user_question_length=len(user_question_section),
                    attachment_length=len(attachment_section),
                    has_memory=has_memory_enhancement,
                    has_attachments=has_attachments,
                    iteration=iteration
                )
        else:
            # 首次迭代：显示完整查询
            board_selection_summary = self._build_board_selection_user_summary()
            if board_selection_summary:
                sections.append(board_selection_summary)
            map_context_summary = self._build_map_context_user_summary()
            if map_context_summary:
                sections.append(map_context_summary)
            graph_map_context_summary = self._build_graph_map_context_user_summary()
            if graph_map_context_summary:
                sections.append(graph_map_context_summary)
            sections.append(current_input_section)

        # 3. 最新观察结果（仅当conversation_history为空时添加，避免重复）
        # conversation_history已包含所有历史对话，包括完整的observation数据
        # latest_observation通常已经包含在conversation_history的最后一条助手消息中
        if latest_observation and not conversation_history:
            sections.append(f"## 最新观察结果\n{latest_observation}")

        return "\n\n".join(sections)

    async def _compress_and_persist_history(self, conversation_history: Optional[List[Dict[str, Any]]]) -> Optional[List[Dict[str, Any]]]:
        """
        压缩对话历史并持久化到 session

        ✅ 修复：压缩后直接写回 session.conversation_history，避免下次迭代重新处理完整历史

        Args:
            conversation_history: 原始对话历史（LLM消息格式）

        Returns:
            压缩后的对话历史
        """
        if not conversation_history:
            return None

        try:
            # 使用 LLM 压缩对话历史
            compressed_messages = await self.compressor.compress(
                conversation_history,
                force=True,
                force_reason="context_tokens_exceeded"
            )

            # ✅ 关键修复：将压缩后的消息写回 session
            self.memory.session.update_messages(compressed_messages)
            await self._save_llm_compact_state(
                compressed_messages,
                reason="context_tokens_exceeded",
            )

            logger.info(
                "conversation_history_persisted",
                original_count=len(conversation_history),
                compressed_count=len(compressed_messages),
                session_id=self.memory.session_id
            )

            return compressed_messages

        except Exception as e:
            logger.error("llm_compression_failed", error=str(e))
            # 降级策略：简单截断，保留最近的消息
            fallback_count = max(10, len(conversation_history) // 2)
            truncated = conversation_history[-fallback_count:]

            # 即使降级也要写回 session
            self.memory.session.update_messages(truncated)
            await self._save_llm_compact_state(
                truncated,
                reason="context_tokens_exceeded_fallback_truncate",
            )

            logger.warning(
                "conversation_history_truncated_fallback",
                original_count=len(conversation_history),
                truncated_count=len(truncated)
            )

            return truncated

    async def _save_llm_compact_state(
        self,
        messages: List[Dict[str, Any]],
        *,
        reason: str,
    ) -> None:
        source_until_sequence = getattr(
            self.memory.session,
            "llm_source_until_sequence",
            None,
        )
        if not isinstance(source_until_sequence, int):
            logger.warning(
                "llm_compact_state_not_persisted_missing_source_boundary",
                session_id=self.memory.session_id,
                mode=self.current_mode,
                reason=reason,
            )
            return

        try:
            from app.agent.session.session_resolver import save_llm_compact_state_for_mode

            persisted = await save_llm_compact_state_for_mode(
                self.memory.session_id,
                messages,
                mode=self.current_mode,
                source_until_sequence=source_until_sequence,
                token_estimate=self._estimate_messages_tokens(messages),
                reason=reason,
            )
            logger.info(
                "llm_compact_state_persisted",
                session_id=self.memory.session_id,
                mode=self.current_mode,
                source_until_sequence=source_until_sequence,
                message_count=len(messages),
                persisted=persisted,
            )
        except Exception as exc:
            logger.error(
                "llm_compact_state_persist_failed",
                session_id=self.memory.session_id,
                mode=self.current_mode,
                error=str(exc),
            )

    def _simple_truncate(self, text: str) -> str:
        """
        简单截断（降级策略）

        按段落截断，保留最近的内容

        Args:
            text: 输入文本

        Returns:
            截断后的文本
        """
        target_tokens = int(self.max_context_tokens * 0.6)
        return token_budget_manager._truncate_to_tokens(text, target_tokens)
