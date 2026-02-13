"""
Working Memory - Layer 1

工作记忆层，保留最近的完整迭代历史。

策略：
- 保留最新10条完整迭代（详细记录）
- 第11次时，压缩前10条为摘要，保留11条（1条详细）
- 第12-20次：继续添加至10条详细记录
- 第21次时，压缩11-20条为摘要，保留21条（1条详细）
- 之后每10次触发一次压缩，保持10条详细记录恒定
- 压缩后的摘要保存在SessionMemory中，可供LLM查询
- 内存使用量恒定：最多10条详细记录
- 关键改进：LLM压缩时会保留完整的data_id信息
"""

from typing import List, Dict, Any, Optional
from datetime import datetime
import json
import structlog

logger = structlog.get_logger()


# 自定义JSON编码器：处理datetime对象和Pydantic模型
def json_serializer(obj):
    """处理datetime对象和Pydantic模型的JSON序列化"""
    if isinstance(obj, datetime):
        return obj.isoformat()
    # 支持Pydantic模型的序列化
    if hasattr(obj, 'dict') and callable(getattr(obj, 'dict')):
        try:
            return obj.dict()
        except Exception:
            pass
    # 处理其他不可序列化的对象
    return str(obj)  # 使用字符串表示，避免抛出错误


class WorkingMemory:
    """
    工作记忆 - 保留最近的完整迭代

    特点：
    - 高优先级：始终在 LLM 上下文的最前面
    - 完整信息：包含完整的 Thought/Action/Observation（最新20条）
    - 批量压缩：第11次压缩前10条，保留11-20条；第21次压缩11-20条，保留21-30条
    - 智能遗忘：压缩后的摘要保存在SessionMemory，可被LLM查询
    - 内存恒定：最多保持20条详细记录，避免内存泄漏
    - data_id保留：LLM压缩时强制保留关键data_id引用
    """

    def __init__(
        self,
        max_iterations: int = 10,  # 恒定保留10条详细记录
        batch_compress_threshold: int = 11,  # 第11次时触发首次压缩
        compress_batch_size: int = 10,  # 每次压缩10条
        max_context_chars: int = 50000,  # 大幅增加字符限制
        max_context_threshold: int = 160000  # 160K tokens阈值
    ):
        """
        初始化工作记忆

        Args:
            max_iterations: 恒定保留的详细迭代次数（默认10）
            batch_compress_threshold: 批量压缩阈值（第11次触发首次压缩）
            compress_batch_size: 每次压缩的迭代数（默认10）
            max_context_chars: 最大上下文字符数
            max_context_threshold: 最大上下文token数阈值（默认160K）
        """
        self.max_iterations = max_iterations
        self.batch_compress_threshold = batch_compress_threshold
        self.compress_batch_size = compress_batch_size
        self.max_context_chars = max_context_chars
        self.max_context_threshold = max_context_threshold
        self.iterations: List[Dict[str, Any]] = []
        self.compression_count = 0  # 压缩次数计数

        # Import token budget manager
        try:
            from app.utils.token_budget import token_budget_manager
            self.token_budget = token_budget_manager
            self.use_token_budget = True
            logger.debug("working_memory_using_token_budget",
                       max_context_tokens=self.token_budget.max_context_tokens)
        except ImportError:
            self.token_budget = None
            self.use_token_budget = False
            logger.warning("working_memory_token_budget_unavailable")

    def add_iteration(
        self,
        thought: str,
        action: Dict[str, Any],
        observation: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """
        添加新的迭代记录

        Args:
            thought: LLM 的思考过程
            action: 执行的动作（TOOL_CALL 或 FINISH）
            observation: 观察结果

        Returns:
            如果发生批量压缩，返回被压缩的迭代列表；否则返回空列表
        """
        # 构造迭代记录
        iteration = {
            "thought": thought,
            "action": action,
            "observation": observation,
            "timestamp": datetime.now().isoformat()
        }

        self.iterations.append(iteration)

        logger.debug(
            "working_memory_add",
            total=len(self.iterations),
            max_iterations=self.max_iterations,
            batch_threshold=self.batch_compress_threshold,
            max_context_chars=self.max_context_chars
        )

        # 检查是否需要压缩
        should_compress = False
        compress_reason = ""

        # 策略1: 达到批次压缩阈值
        if len(self.iterations) >= self.batch_compress_threshold:
            should_compress = True
            compress_reason = f"iterations_count_{len(self.iterations)}"
        else:
            # 策略2: 上下文token数超限（160K阈值保护）
            try:
                current_context = self.get_context_for_llm()
                context_tokens = self.token_budget.count_tokens(current_context) if self.use_token_budget else len(current_context) // 3

                # 检查是否超过160K tokens
                MAX_CONTEXT_THRESHOLD = 160000  # 160K tokens
                if context_tokens > MAX_CONTEXT_THRESHOLD:
                    should_compress = True
                    compress_reason = f"token_threshold_exceeded_{context_tokens}tokens"
                    logger.warning(
                        "token_threshold_trigger_compress",
                        context_tokens=context_tokens,
                        threshold=MAX_CONTEXT_THRESHOLD,
                        overflow=context_tokens - MAX_CONTEXT_THRESHOLD
                    )
                # 策略3: 字符数超限（备用）
                elif len(current_context) > self.max_context_chars:
                    should_compress = True
                    compress_reason = f"context_too_long_{len(current_context)}chars"
                    logger.info(
                        "context_too_long_trigger_compress",
                        context_chars=len(current_context),
                        max_chars=self.max_context_chars
                    )
            except Exception as e:
                logger.warning(
                    "context_check_failed",
                    error=str(e)
                )
                # 如果检查上下文失败，不触发压缩

        # 执行压缩
        if should_compress:
            # 压缩前 compress_batch_size 条记录
            batch_to_compress = self.iterations[:self.compress_batch_size]

            # 保留记录策略
            if "context_too_long" in compress_reason or "token_threshold_exceeded" in compress_reason:
                # 特殊情况：上下文超限，需要保留更多记录确保连续性
                # 根据压缩次数动态调整保留数量
                preserve_count = min(10, 5 + self.compression_count)
                self.iterations = self.iterations[-preserve_count:] if len(self.iterations) >= preserve_count else self.iterations
                remaining_count = len(self.iterations)

                # 动态调整压缩频率：如果经常触发token阈值，增加压缩频率
                if "token_threshold_exceeded" in compress_reason:
                    self.compression_count += 1
                    # 每触发3次token阈值压缩，提前下次压缩时机
                    if self.compression_count % 3 == 0:
                        old_threshold = self.batch_compress_threshold
                        self.batch_compress_threshold = max(6, self.batch_compress_threshold - 1)
                        logger.warning(
                            "dynamic_compression_adjustment",
                            reason="Frequent token threshold violations",
                            old_threshold=old_threshold,
                            new_threshold=self.batch_compress_threshold,
                            compression_count=self.compression_count
                        )

                logger.warning(
                    "context_too_long_compression_strategy_updated",
                    reason="Preserving more context for continuous dialogue",
                    remaining_count=remaining_count,
                    preserve_count=preserve_count,
                    compression_count=self.compression_count
                )
            else:
                # 正常情况：保留后 max_iterations 条记录
                self.iterations = self.iterations[-self.max_iterations:]
                remaining_count = len(self.iterations)

            logger.debug(
                "working_memory_batch_compress",
                compressed_count=len(batch_to_compress),
                remaining_count=remaining_count,
                batch_size=self.compress_batch_size,
                max_iterations=self.max_iterations,
                reason=compress_reason,
                compression_count=self.compression_count
            )
            return batch_to_compress  # 返回要压缩的批次

        return []  # 不需要压缩

    def get_context_for_llm(self, include_raw_data: bool = False) -> str:
        """
        格式化为 LLM 可读的上下文（Claude Code 风格：丰富信息 + 智能压缩）

        Args:
            include_raw_data: 是否包含原始数据（而非仅data_ref和采样数据）

        Returns:
            格式化的上下文字符串
        """
        if not self.iterations:
            return "这是第一次思考，没有历史记录。"

        context_parts = ["=== ReAct 执行历史 ===\n"]

        for i, iter_data in enumerate(self.iterations, 1):
            # ✅ 修复：检查是否是图表观察结果（action.type == "CHART_GENERATED"）
            action = iter_data.get("action", {})
            observation = iter_data.get("observation", {})

            if action.get("type") == "CHART_GENERATED":
                context_parts.append(f"\n## 图表结果 {i}")
                # ✅ 修复：从observation中提取字段，不是从iter_data顶层
                context_parts.append(f"\n**图表信息**:\n{observation.get('summary', '图表已生成')}")
                context_parts.append(f"\n**图表ID**: {observation.get('chart_id', 'N/A')}")
                context_parts.append(f"\n**图表类型**: {observation.get('chart_type', 'N/A')}")
                context_parts.append(f"\n**图表标题**: {observation.get('chart_title', 'N/A')}")
                if observation.get('data_id'):
                    context_parts.append(f"\n**数据引用**: {observation['data_id']}")
                context_parts.append(f"\n**生成工具**: {observation.get('source_tool', 'N/A')}")
                context_parts.append(f"\n**生成时间**: {iter_data.get('timestamp', 'N/A')}")
                continue

            context_parts.append(f"\n## 步骤 {i}")
            context_parts.append(f"\n**思考 (Thought)**:\n{iter_data['thought']}")

            # 格式化 Action
            action = iter_data['action']
            if action['type'] == 'TOOL_CALL':
                context_parts.append(f"\n**行动 (Action)**:\n调用工具 `{action['tool']}`")
                args = action.get('args', {})
                if args:
                    # 格式化参数（关键信息不省略）
                    args_str = json.dumps(args, ensure_ascii=False, indent=2, default=json_serializer)
                    context_parts.append(f"\n参数:\n```json\n{args_str}\n```")
            elif action['type'] == 'TOOL_CALLS':
                # 处理并行工具调用
                tools = action.get('tools', [])
                context_parts.append(f"\n**行动 (Action)**:\n并行调用 {len(tools)} 个工具:")
                for idx, tool_call in enumerate(tools, 1):
                    tool_name = tool_call.get('tool', 'unknown')
                    context_parts.append(f"\n  {idx}. `{tool_name}`")
                    args = tool_call.get('args', {})
                    if args:
                        args_str = json.dumps(args, ensure_ascii=False, indent=2, default=json_serializer)
                        context_parts.append(f"\n     参数: ```json\n{args_str}\n```")
            elif action['type'] == 'FINISH':
                context_parts.append(f"\n**行动 (Action)**:\n完成任务")

            # 格式化 Observation（简化版本，因为主要格式化在 loop.py 中完成）
            obs = iter_data['observation']
            # 只显示摘要，因为完整内容已经在 loop.py:_format_observation 中格式化并存入 SessionMemory
            summary = obs.get('summary', '执行完成')
            success = obs.get('success', True)
            status = '成功' if success else '失败'

            obs_str = f"**状态**: {status}"
            if summary:
                obs_str += f"\n**摘要**: {summary}"

            # 如果有 data_ref，显示数据引用
            if 'data_ref' in obs:
                obs_str += f"\n**数据引用**: `{obs['data_ref']}`"

            context_parts.append(f"\n**观察 (Observation)**:\n{obs_str}")

        context = "\n".join(context_parts)

        # ✅ 移除Token预算截断 - 仅监控，不截断
        # 完全依赖160K阈值保护 + 批量压缩 + 动态调整
        if self.use_token_budget and self.token_budget:
            context_tokens = self.token_budget.count_tokens(context)

            # 仅监控和记录，不执行截断
            if context_tokens > 50000:
                logger.info(
                    "context_size_monitoring",
                    context_tokens=context_tokens,
                    warning_threshold=50000,
                    ultimate_threshold=160000,
                    overflow=context_tokens - 50000,
                    message="上下文较大但未截断，依赖160K阈值终极保护"
                )

            # 记录详细统计信息
            logger.debug(
                "context_stats",
                context_tokens=context_tokens,
                context_chars=len(context),
                iterations_count=len(self.iterations),
                compression_count=self.compression_count
            )
        else:
            # Token预算不可用时记录警告
            logger.warning(
                "token_budget_unavailable",
                context_chars=len(context),
                message="Token预算管理不可用，完全依赖160K阈值保护"
            )

        return context

    def _extract_executions_summary(self, context: str) -> str:
        """提取执行摘要，保留关键结果"""
        lines = context.split('\n')
        summary_lines = []

        # 保留观察结果中的成功数据和关键信息
        in_observation = False
        for line in lines:
            if "**观察 (Observation)**" in line:
                in_observation = True
                summary_lines.append("\n=== 关键执行结果摘要 ===")
                continue

            if in_observation:
                # 保留数据预览和关键结果
                if any(keyword in line for keyword in ["成功", "[OK]", "数据", "records", "源贡献", "贡献率", "浓度"]):
                    if len(summary_lines) < 50:  # 最多保留50行关键结果
                        summary_lines.append(line)
                elif line.startswith("## "):  # 遇到新步骤，停止
                    break

        return "\n".join(summary_lines) if summary_lines else context[-2000:]  # 如果没有提取到，返回最后2000字符

    def _format_data_preview(self, data: Any, max_tokens: int = 30000) -> str:
        """
        格式化数据预览（智能截断 based on token budget）

        使用Token预算管理，优先显示更多数据，而非固定3条。

        Args:
            data: 数据对象
            max_tokens: 最大token数（默认30000，满足复杂分析需求）

        Returns:
            数据预览字符串（智能截断）
        """
        import json
        from datetime import datetime

        # ✅ Import token budget manager
        try:
            from app.utils.token_budget import token_budget_manager
            use_token_budget = True
        except ImportError:
            # Fallback: use character-based truncation
            use_token_budget = False

        if isinstance(data, list):
            # 列表：智能显示，最大化数据量
            if len(data) == 0:
                return "空列表"

            # ✅ 使用Token预算管理：逐条添加，直到超出预算
            if use_token_budget:
                preview_items = []
                current_tokens = 0

                for item in data:
                    item_str = json.dumps(item, ensure_ascii=False, default=json_serializer)
                    item_tokens = token_budget_manager.count_tokens(item_str)

                    if current_tokens + item_tokens > max_tokens:
                        # 超出预算，停止添加
                        break

                    preview_items.append(item)
                    current_tokens += item_tokens

                # 至少显示1条
                if not preview_items and data:
                    preview_items = data[:1]

                preview_str = json.dumps(preview_items, ensure_ascii=False, indent=2, default=json_serializer)

                if len(preview_items) < len(data):
                    return (
                        f"{preview_str}\n"
                        f"... （共 {len(data)} 条记录，已显示前 {len(preview_items)} 条，"
                        f"约 {current_tokens} tokens）"
                    )
                else:
                    return preview_str
            else:
                # Fallback：从20条提高到100条
                preview_items = data[:100]
                preview_str = json.dumps(preview_items, ensure_ascii=False, indent=2, default=json_serializer)

                if len(data) > 100:
                    return f"{preview_str}\n... （共 {len(data)} 条记录）"
                else:
                    return preview_str

        elif isinstance(data, dict):
            # 字典：显示所有键值（但值可能被截断）
            if not data:
                return "空字典"

            preview_str = json.dumps(data, ensure_ascii=False, indent=2, default=json_serializer)

            # ✅ 使用Token预算管理
            if use_token_budget:
                tokens = token_budget_manager.count_tokens(preview_str)
                if tokens > max_tokens:
                    # 截断至目标tokens
                    truncated = token_budget_manager._truncate_to_tokens(preview_str, max_tokens)
                    return f"{truncated}\n... （字典数据已截断，约 {max_tokens} tokens）"
                else:
                    return preview_str
            else:
                # Fallback：字符截断
                if len(preview_str) > 2000:  # 提高到2000字符（之前500）
                    return preview_str[:2000] + "\n... （数据已截断）"
                else:
                    return preview_str

        elif isinstance(data, str):
            # 字符串：截断显示
            if use_token_budget:
                tokens = token_budget_manager.count_tokens(data)
                if tokens > max_tokens:
                    truncated = token_budget_manager._truncate_to_tokens(data, max_tokens)
                    return f"{truncated}\n... （已截断至 {max_tokens} tokens）"
                else:
                    return data
            else:
                if len(data) > 2000:  # 提高到2000字符
                    return data[:2000] + "... （已截断）"
                else:
                    return data

        else:
            # 其他类型：转为字符串
            str_data = str(data)
            if use_token_budget:
                tokens = token_budget_manager.count_tokens(str_data)
                if tokens > max_tokens:
                    return token_budget_manager._truncate_to_tokens(str_data, max_tokens)
                else:
                    return str_data
            else:
                return str_data[:2000]

    def estimate_tokens(self) -> int:
        """
        估算当前上下文的 token 数量（使用 Token 预算管理器）

        Returns:
            估算的 token 数
        """
        if self.use_token_budget and self.token_budget:
            context = self.get_context_for_llm()
            return self.token_budget.count_tokens(context)
        else:
            # Fallback: 粗略估算
            context = self.get_context_for_llm()
            return len(context) // 3

    def clear(self):
        """清空工作记忆"""
        self.iterations.clear()
        logger.info("working_memory_cleared")

    def get_iterations(self) -> List[Dict[str, Any]]:
        """
        获取所有迭代记录

        Returns:
            迭代记录列表
        """
        return self.iterations.copy()

    def __len__(self) -> int:
        """返回当前迭代数量"""
        return len(self.iterations)

    def add_chart_observation(self, chart_info: Dict[str, Any]) -> None:
        """
        添加图表观察结果到工作记忆

        Args:
            chart_info: 图表信息字典，包含chart_id、chart_type、chart_title、summary等
        """
        # 构建图表观察记录 - 使用标准ReAct迭代格式
        chart_observation = {
            "thought": f"图表已生成：{chart_info.get('chart_title', '无标题')}",
            "action": {
                "type": "CHART_GENERATED",
                "tool": chart_info.get("source_tool", "smart_chart_generator"),
                "chart_id": chart_info.get("chart_id", "未知图表"),
                "chart_type": chart_info.get("chart_type", "unknown")
            },
            "observation": {
                "success": True,
                "summary": chart_info.get("summary", "图表已生成"),
                "chart_id": chart_info.get("chart_id", "未知图表"),
                "chart_type": chart_info.get("chart_type", "unknown"),
                "chart_title": chart_info.get("chart_title", "无标题"),
                "data_id": chart_info.get("data_id"),
                "source_tool": chart_info.get("source_tool", "未知工具"),
                "has_chart": True
            },
            "timestamp": datetime.now().isoformat()
        }

        # 添加到迭代列表中
        self.iterations.append(chart_observation)

        logger.info(
            "working_memory_chart_added",
            chart_id=chart_info.get("chart_id"),
            chart_type=chart_info.get("chart_type"),
            total_iterations=len(self.iterations)
        )

        # 检查是否需要压缩（保持原有逻辑）
        if len(self.iterations) > self.max_iterations + 5:  # 超过5条就压缩
            # 压缩最旧的非图表记录，保留图表记录
            non_chart_iterations = [it for it in self.iterations if it.get("action", {}).get("type") != "CHART_GENERATED"]
            chart_iterations = [it for it in self.iterations if it.get("action", {}).get("type") == "CHART_GENERATED"]

            # 保留最新的max_iterations条记录，其中优先保留图表记录
            if len(non_chart_iterations) > self.max_iterations:
                # 压缩部分非图表记录
                self.iterations = non_chart_iterations[-self.max_iterations:] + chart_iterations[-2:]
            else:
                # 非图表记录不多，只保留图表记录
                self.iterations = non_chart_iterations + chart_iterations[-self.max_iterations:]

            logger.info(
                "working_memory_chart_compressed",
                remaining_iterations=len(self.iterations)
            )

    def __repr__(self) -> str:
        return f"<WorkingMemory iterations={len(self.iterations)}/{self.max_iterations}>"
