"""
Reflexion Handler Module

处理失败分析和智能重试决策的独立模块。
"""
from typing import Dict, Any, List, Optional
import structlog

logger = structlog.get_logger()


class ReflexionHandler:
    """
    Reflexion 反思处理器

    负责：
    1. 分析连续失败的原因
    2. 识别错误模式
    3. 判断可恢复性
    4. 生成改进建议
    """

    def __init__(self, max_reflections: int = 2):
        """
        初始化 Reflexion 处理器

        Args:
            max_reflections: 最大反思次数
        """
        self.max_reflections = max_reflections
        self.reflection_count = 0

    def reset_count(self):
        """重置反思计数器"""
        self.reflection_count = 0

    async def should_early_stop(
        self,
        recent_iterations: List[Dict[str, Any]],
        enable_reflexion: bool = True
    ) -> bool:
        """
        判断是否应该早停（集成 Reflexion 机制）

        Args:
            recent_iterations: 最近的迭代历史
            enable_reflexion: 是否启用 Reflexion

        Returns:
            是否早停
        """
        if not recent_iterations or len(recent_iterations) < 3:
            return False

        # 检查最近3次迭代是否全部失败
        recent_failures = sum(
            1 for it in recent_iterations[-3:]
            if not it.get("observation", {}).get("success", True)
        )

        if recent_failures < 3:
            return False

        # 🔧 新增：检测重复的相同错误（不可恢复模式）
        recent_errors = [
            it.get("observation", {}).get("error", "")
            for it in recent_iterations[-3:]
        ]

        # 检测完全相同的错误连续出现3次
        if len(set(recent_errors)) == 1 and recent_errors[0]:
            logger.warning(
                "detected_identical_repeated_error",
                error=recent_errors[0],
                occurrences=len(recent_errors),
                pattern="unrecoverable"
            )
            # 相同错误重复3次，判定为不可恢复，直接早停
            return True

        # 检测不可恢复的错误模式
        unrecoverable_patterns = [
            "数据格式无法识别",
            "data format unrecognized",
            "模板返回的数据不是有效的",
            "invalid template response",
            "数据引用格式需要先加载",
            "data_ref requires loading"
        ]

        for error in recent_errors:
            if error and any(pattern in error for pattern in unrecoverable_patterns):
                logger.warning(
                    "detected_unrecoverable_error_pattern",
                    error=error,
                    pattern="data_format_issue"
                )
                # 数据格式问题连续出现，直接早停
                return True

        # 集成 Reflexion 机制
        if enable_reflexion and self.reflection_count < self.max_reflections:
            logger.info(
                "reflexion_triggered",
                reflection_count=self.reflection_count,
                max_reflections=self.max_reflections,
                recent_failures=recent_failures
            )

            # 分析失败并决定是否重试
            should_retry = await self._analyze_and_decide_retry(
                recent_iterations[-3:]
            )

            if should_retry:
                self.reflection_count += 1
                logger.info(
                    "reflexion_retry_approved",
                    reflection_count=self.reflection_count,
                    reason="recoverable_error"
                )
                return False  # 继续执行

        # Reflexion 机制判定不可恢复，或已达最大反思次数
        logger.warning(
            "early_stop_condition_met",
            recent_failures=recent_failures,
            reflection_exhausted=self.reflection_count >= self.max_reflections
        )
        return True

    async def _analyze_and_decide_retry(
        self,
        failed_iterations: List[Dict[str, Any]]
    ) -> bool:
        """
        使用 Reflexion 机制分析失败并决定是否重试

        Args:
            failed_iterations: 最近失败的迭代

        Returns:
            是否应该重试
        """
        try:
            from app.services.llm_service import llm_service

            # 分析失败原因
            failure_analysis = self._analyze_failures(failed_iterations)

            # 构建反思提示词
            reflection_prompt = f"""
你是一个能够自我反思和改进的AI Agent。请分析最近的执行失败并判断是否值得重试。

## 最近的失败情况

{failure_analysis}

## 反思任务

请分析：
1. **根本原因**: 为什么连续失败？是参数问题、工具问题还是数据问题？
2. **可恢复性**: 这些失败是否可以通过调整策略解决？
3. **重试建议**: 如果重试，应该如何调整方法？

请按以下格式输出：

**失败原因**: [简要说明根本原因]
**可恢复**: [是/否]
**改进策略**: [如果可恢复，说明具体改进措施]

注意：
- 如果是数据不存在、权限错误等不可恢复错误，回答"否"
- 如果是参数传递错误、工具选择不当等，回答"是"
"""

            # 调用 LLM 进行反思
            response = await llm_service.chat(
                messages=[{"role": "user", "content": reflection_prompt}],
                temperature=0.3
            )

            # 解析反思结果
            is_recoverable = "可恢复**: 是" in response or "可恢复**: Yes" in response.lower()

            if is_recoverable:
                logger.info(
                    "reflexion_analysis_complete",
                    is_recoverable=is_recoverable,
                    response_preview=response[:200]
                )

            return is_recoverable

        except Exception as e:
            logger.error(
                "reflexion_analysis_failed",
                error=str(e),
                exc_info=True
            )
            # Reflexion 失败时，保守策略：不重试
            return False

    def _analyze_failures(
        self,
        failed_iterations: List[Dict[str, Any]]
    ) -> str:
        """
        分析失败的迭代并生成摘要

        Args:
            failed_iterations: 失败的迭代列表

        Returns:
            失败分析文本
        """
        analysis_lines = []

        for i, iteration in enumerate(failed_iterations, 1):
            # 跳过None或非字典元素
            if not iteration or not isinstance(iteration, dict):
                continue

            action = iteration.get("action", {})
            observation = iteration.get("observation", {})

            tool_name = action.get("tool", "Unknown")
            error = observation.get("error", observation.get("summary", "Unknown error"))

            analysis_lines.append(
                f"失败 {i}: 工具 {tool_name} - {error}"
            )

        # 识别错误模式
        errors = [
            it.get("observation", {}).get("error", "")
            for it in failed_iterations if it and isinstance(it, dict)
        ]

        patterns = []
        if errors and any("参数" in e or "argument" in e.lower() for e in errors if e):
            patterns.append("参数传递错误")
        if errors and any("not found" in e.lower() or "不存在" in e for e in errors if e):
            patterns.append("数据不存在")
        if errors and any("timeout" in e.lower() or "超时" in e for e in errors if e):
            patterns.append("请求超时")

        if patterns:
            analysis_lines.append(f"\n错误模式: {', '.join(patterns)}")

        return "\n".join(analysis_lines)

    def get_reflection_context(self, response: str) -> Dict[str, Any]:
        """
        生成反思上下文（供记忆系统使用）

        Args:
            response: LLM 反思响应

        Returns:
            反思上下文字典
        """
        return {
            "thought": f"[Reflexion 反思] {response}",
            "action": {"type": "REFLECTION", "analysis": response},
            "observation": {
                "success": True,
                "summary": "完成失败分析和改进建议"
            }
        }

    async def detect_repetitive_patterns(
        self,
        recent_iterations: List[Dict[str, Any]]
    ) -> bool:
        """
        检测重复执行模式（主动反思用）

        Args:
            recent_iterations: 最近的迭代历史

        Returns:
            是否检测到重复模式
        """
        if len(recent_iterations) < 4:
            return False

        # 检测是否重复调用相同工具
        recent_tools = [
            it.get("action", {}).get("tool")
            for it in recent_iterations[-4:]
            if it.get("action", {}).get("type") == "TOOL_CALL"
        ]

        if len(recent_tools) >= 3:
            # 统计工具使用频率
            from collections import Counter
            tool_counts = Counter(recent_tools)
            most_common = tool_counts.most_common(1)[0]

            # 如果某个工具被重复调用3次或以上
            if most_common[1] >= 3:
                logger.info(
                    "detected_repetitive_tool",
                    tool=most_common[0],
                    count=most_common[1],
                    total_tools=len(recent_tools)
                )
                return True

        return False

    async def generate_proactive_insight(
        self,
        recent_iterations: List[Dict[str, Any]],
        current_query: str
    ) -> Dict[str, Any]:
        """
        主动生成反思洞察（而非被动应对失败）

        Args:
            recent_iterations: 最近的迭代历史
            current_query: 当前查询

        Returns:
            反思洞察字典
        """
        try:
            from app.services.llm_service import llm_service

            # 分析执行模式
            pattern_analysis = self._analyze_execution_pattern(recent_iterations)

            # 构建反思提示词
            reflection_prompt = f"""
作为专业的大气污染溯源分析专家，请基于执行模式提供战略洞察：

当前查询: {current_query}

执行模式分析: {pattern_analysis}

请分析：
1. **策略有效性**: 当前方法是否高效？有何改进空间？
2. **数据充足性**: 数据获取是否充分？是否需要调整？
3. **工具选择**: 工具选择是否合理？有更好的替代方案吗？
4. **风险预警**: 基于当前模式，可能遇到什么问题？

请以JSON格式输出：
{{
    "insight": "关键发现和洞察",
    "recommendation": "具体改进建议",
    "warning": "潜在风险提醒",
    "confidence": "信心度(0-1)"
}}

注意：这是主动反思，不需要等待失败发生。
"""

            # 🔧 改进：调用LLM并捕获JSON解析错误
            try:
                response = await llm_service.call_llm_with_json_response(reflection_prompt)

                # 验证响应格式
                if not isinstance(response, dict):
                    logger.warning(
                        "proactive_reflexion_invalid_response_type",
                        response_type=type(response).__name__
                    )
                    raise ValueError("LLM返回非字典类型")

                # 提取字段（带默认值）
                insight = response.get("insight", "执行模式正常")
                recommendation = response.get("recommendation", "继续保持当前策略")
                warning = response.get("warning", "无明显风险")
                confidence = response.get("confidence", 0.7)

                # 确保confidence是数值类型
                if not isinstance(confidence, (int, float)):
                    try:
                        confidence = float(confidence)
                    except (ValueError, TypeError):
                        confidence = 0.7

            except (ValueError, TypeError, KeyError) as json_err:
                # JSON解析失败或格式错误，使用默认值
                logger.warning(
                    "proactive_reflexion_json_parse_failed",
                    error=str(json_err),
                    error_type=type(json_err).__name__
                )
                insight = "反思生成部分成功"
                recommendation = "继续当前策略，注意监控执行效果"
                warning = "JSON解析失败，使用默认洞察"
                confidence = 0.5

            return {
                "insight": insight,
                "recommendation": recommendation,
                "warning": warning,
                "confidence": confidence,
                "pattern": pattern_analysis
            }

        except Exception as e:
            logger.error(
                "proactive_reflexion_failed",
                error=str(e),
                error_type=type(e).__name__,
                exc_info=True
            )
            return {
                "insight": "反思生成失败",
                "recommendation": "继续当前策略",
                "warning": "无",
                "confidence": 0.0,
                "pattern": "分析失败"
            }

    def _analyze_execution_pattern(
        self,
        iterations: List[Dict[str, Any]]
    ) -> str:
        """
        分析执行模式

        Args:
            iterations: 迭代列表

        Returns:
            模式分析文本
        """
        patterns = []

        # 分析工具调用频率
        tools_used = [
            it.get("action", {}).get("tool")
            for it in iterations
            if it.get("action", {}).get("type") == "TOOL_CALL"
        ]

        if tools_used:
            from collections import Counter
            tool_counts = Counter(tools_used)
            most_common = tool_counts.most_common(1)[0]
            patterns.append(f"主要工具: {most_common[0]} (使用{most_common[1]}次)")

        # 分析数据获取 vs 分析的比例
        data_tools = [t for t in tools_used if t and (t.startswith("get_") or "weather" in t or "quality" in t)]
        analysis_tools = [t for t in tools_used if t and ("analyze" in t or "calculate" in t)]

        patterns.append(f"数据获取工具: {len(data_tools)}次")
        patterns.append(f"分析工具: {len(analysis_tools)}次")

        # 分析成功/失败率
        successes = sum(
            1 for it in iterations
            if it.get("observation", {}).get("success", True)
        )
        if iterations:
            patterns.append(f"成功率: {successes}/{len(iterations)} ({successes/len(iterations)*100:.1f}%)")
        else:
            patterns.append("成功率: N/A (无迭代数据)")

        return "; ".join(patterns)

    async def should_trigger_proactive_reflexion(
        self,
        recent_iterations: List[Dict[str, Any]],
        iteration_count: int
    ) -> bool:
        """
        判断是否应该触发主动反思

        Args:
            recent_iterations: 最近的迭代
            iteration_count: 当前迭代次数

        Returns:
            是否触发
        """
        # 每2次迭代触发一次主动反思
        if iteration_count % 2 == 0 and iteration_count > 0:
            # 检测重复模式
            if await self.detect_repetitive_patterns(recent_iterations):
                return True

            # 检测数据获取不充分
            data_tools = sum(
                1 for it in recent_iterations[-2:]
                if it.get("action", {}).get("tool", "").startswith("get_")
            )
            if data_tools == 0 and iteration_count >= 4:
                return True

        return False

    async def handle_input_adaptation_error(
        self,
        error: Dict[str, Any],
        tool_name: str,
        raw_args: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        处理输入适配错误并生成智能重试建议

        Args:
            error: 适配错误信息
            tool_name: 工具名称
            raw_args: 原始参数

        Returns:
            重试建议
        """
        try:
            logger.info(
                "handling_input_adaptation_error",
                tool_name=tool_name,
                error_type=error.get("type"),
                missing_fields=error.get("missing_fields", [])
            )

            # 错误类型分类
            error_type = error.get("type", "unknown")
            missing_fields = error.get("missing_fields", [])

            # 生成重试建议
            suggestions = []

            # 1. 缺失字段处理
            if error_type == "missing_required_fields" and missing_fields:
                for field in missing_fields:
                    suggestion = self._generate_field_suggestion(field, tool_name)
                    if suggestion:
                        suggestions.append(suggestion)

            # 2. 工具特定建议
            tool_suggestion = self._get_tool_specific_suggestion(tool_name, missing_fields)
            if tool_suggestion:
                suggestions.append(tool_suggestion)

            # 3. 通用建议
            if not suggestions:
                suggestions.append("请检查参数完整性并确保所有必需字段都已提供")

            # 构建重试建议
            retry_suggestion = {
                "type": "input_adaptation_retry",
                "should_retry": True,
                "error_type": error_type,
                "missing_fields": missing_fields,
                "suggestions": suggestions,
                "corrected_args": error.get("suggested_call", {}).get("args", raw_args),
                "examples": error.get("suggested_call", {}).get("examples", {}),
                "notes": error.get("suggested_call", {}).get("notes", "")
            }

            logger.info(
                "input_adaptation_retry_generated",
                tool_name=tool_name,
                suggestions_count=len(suggestions)
            )

            return retry_suggestion

        except Exception as e:
            logger.error(
                "handle_input_adaptation_error_failed",
                tool_name=tool_name,
                error=str(e),
                exc_info=True
            )
            return {
                "type": "input_adaptation_retry",
                "should_retry": False,
                "error": "生成重试建议失败",
                "original_error": error
            }

    def _generate_field_suggestion(self, field: str, tool_name: str) -> Optional[str]:
        """
        为特定字段生成建议

        Args:
            field: 字段名
            tool_name: 工具名称

        Returns:
            建议文本
        """
        suggestions_map = {
            "location": "请提供具体地点，如'广州'、'天河站'等",
            "pollutant": "请指定污染物类型，如'PM2.5'、'O3'、'NO2'等",
            "start_time": "请提供开始时间，格式：YYYY-MM-DD HH:MM:SS",
            "end_time": "请提供结束时间，格式：YYYY-MM-DD HH:MM:SS",
            "time_range": "请提供时间范围，如'2025-01-01 到 2025-01-02'",
            "search_range_km": "请提供搜索半径（公里），如'5.0'",
            "station_name": "请提供监测站点名称",
            "city": "请提供城市名称"
        }

        return suggestions_map.get(field)

    def _get_tool_specific_suggestion(
        self,
        tool_name: str,
        missing_fields: List[str]
    ) -> Optional[str]:
        """
        获取工具特定建议

        Args:
            tool_name: 工具名称
            missing_fields: 缺失字段

        Returns:
            建议文本
        """
        tool_suggestions = {
            "get_weather_data": "天气数据查询需要：地点、时间范围",
            "get_air_quality": "空气质量查询需要：地点、污染物、时间范围",
            "get_vocs_components": "VOCs查询需要：地点、时间范围",
            "analyze_upwind_enterprises": "上风向分析需要：地点、时间范围、搜索半径",
            "calculate_pmf": "PMF分析需要：地点、组分数据",
        }

        base_suggestion = tool_suggestions.get(tool_name)
        if not base_suggestion:
            return None

        if missing_fields:
            missing_str = ", ".join(missing_fields[:3])  # 只显示前3个
            return f"{base_suggestion}。当前缺少：{missing_str}"

        return base_suggestion

    def should_use_response_normalizer(self, error: Dict[str, Any]) -> bool:
        """
        判断是否应该使用ResponseNormalizer重试

        Args:
            error: 错误信息

        Returns:
            是否应该使用ResponseNormalizer
        """
        error_type = error.get("type", "")

        # 特定错误类型应该尝试ResponseNormalizer
        use_normalizer_types = [
            "unrecognized_response_format",
            "invalid_action_from_llm"
        ]

        return error_type in use_normalizer_types or "format" in str(error).lower()

    def generate_reflexion_prompt_for_input_error(
        self,
        error: Dict[str, Any],
        tool_name: str,
        raw_args: Dict[str, Any]
    ) -> str:
        """
        生成用于输入错误的Reflexion提示词

        Args:
            error: 错误信息
            tool_name: 工具名称
            raw_args: 原始参数

        Returns:
            反思提示词
        """
        missing_fields = error.get("missing_fields", [])
        expected_schema = error.get("expected_schema", {})

        prompt = f"""
你是一个专业的AI Agent，正在分析输入参数问题。

## 当前情况
工具: {tool_name}
错误: {error.get('error', '未知错误')}
缺失字段: {missing_fields}

## 参数分析
提供的参数: {list(raw_args.keys())}
期望的Schema: {expected_schema}

## 反思任务
请分析：
1. **参数问题**: 为什么LLM没有提供完整的参数？
2. **改进方法**: 如何让LLM提供正确的参数？
3. **重试策略**: 下次调用应该如何指导LLM？

请提供具体的改进建议。
"""

        return prompt
