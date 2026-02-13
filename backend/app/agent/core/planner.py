"""
ReAct Agent 规划器 (Planner)

实现两阶段工具加载架构:
1. 第一阶段: LLM仅看工具摘要，选择需要的工具
2. 第二阶段: 按需加载详细schema并构造参数

Token优化: 节省40-50%的token消耗
"""

import json
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime
from app.tools.base.registry import ToolRegistry
from app.agent.context.execution_context import ExecutionContext
from app.services.llm_service import llm_service
from app.utils.llm_response_parser import LLMResponseParser

logger = logging.getLogger(__name__)


class ReActPlanner:
    """
    ReAct规划器: 实现思考-行动-观察循环

    核心特性:
    - 两阶段工具加载 (摘要选择 → 详细构造)
    - 上下文感知的参数构造
    - 智能LLM响应解析
    """

    def __init__(
        self,
        tool_registry: ToolRegistry = None,
        context: Optional[ExecutionContext] = None,
        llm_client=None,
        max_context_turns: int = 3
    ):
        # 如果没有提供 tool_registry，延迟到使用时从 executor 获取
        self._tool_registry = tool_registry
        self.context = context
        self.llm_service = llm_service
        self.max_context_turns = max_context_turns
        self.is_interruption = False  # 中断标志

    @property
    def tool_registry(self):
        """延迟加载 tool_registry，支持从外部注入"""
        if self._tool_registry is not None:
            return self._tool_registry

        # 尝试从全局工具注册表获取
        try:
            from app.agent.tool_adapter import get_react_agent_tool_registry
            return get_react_agent_tool_registry()
        except:
            # 返回空字典作为fallback
            return {}

    async def think_and_action_v2(
        self,
        query: str,
        system_prompt: str,
        user_conversation: str,
        iteration: int,
        latest_observation: Any = None
    ) -> Dict:
        """
        V2版本：思考和行动合并（单次LLM调用）

        用于单步模式的 ReAct 循环，接收已构建好的上下文，直接调用 LLM。

        Args:
            query: 用户查询
            system_prompt: 系统提示词（包含工具摘要）
            user_conversation: 用户对话内容（字符串格式）
            iteration: 当前迭代次数
            latest_observation: 最近的观察结果（可选）

        Returns:
            {
                "thought": "思考过程",
                "reasoning": "推理过程（可选）",
                "action": {
                    "type": "TOOL_CALL" | "TOOL_CALLS",
                    "tool": "工具名称",
                    "args": {...}
                }
            }
        """
        # 构建消息列表
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_conversation}
        ]

        # 调用LLM
        logger.debug(f"[Planner V2] 调用LLM，iteration={iteration}")
        llm_response = await self.llm_service.chat(messages)
        logger.debug(f"[Planner V2] LLM响应: {llm_response[:200]}...")

        # 解析响应 - 使用全局 parser 实例
        from app.utils.llm_response_parser import parser
        parsed_result = parser.parse(llm_response)

        # 检查解析是否成功
        if not parsed_result.get("success") or not parsed_result.get("data"):
            logger.error(f"[Planner V2] 解析失败: {parsed_result.get('error')}")
            return {
                "thought": "无法解析LLM响应",
                "reasoning": parsed_result.get("error", {}).get("error_msg", "LLM返回格式错误"),
                "action": {
                    "type": "FINISH",
                    "tool": "FINISH",
                    "args": {"answer": "抱歉，我无法理解当前的分析需求。"}
                },
                "raw_response": llm_response
            }

        # 提取解析后的数据
        data = parsed_result["data"]

        # 兼容两种格式：
        # 1. 新格式（推荐）：{"thought": "...", "reasoning": "...", "action": {...}}
        # 2. 旧格式：{"thought": "...", "action": "...", "action_input": {...}}

        thought = data.get("thought", "")
        reasoning = data.get("reasoning", "")

        # 检查是否是新格式（直接包含 action 对象）
        if "action" in data and isinstance(data["action"], dict):
            # 新格式：action 已经是完整的对象
            action = data["action"]
        else:
            # 旧格式：需要从 action 和 action_input 构造
            action_input = data.get("action_input", {})
            action_name = data.get("action", "")

            if isinstance(action_input, dict) and "type" in action_input:
                # action_input 本身就是 action 对象
                action = action_input
            elif action_name == "final_answer":
                action = {
                    "type": "FINISH",
                    "tool": "FINISH",
                    "args": {"answer": action_input.get("answer", "")} if isinstance(action_input, dict) else {"answer": str(action_input)}
                }
            else:
                action = {
                    "type": "TOOL_CALL",
                    "tool": action_name,
                    "args": action_input if isinstance(action_input, dict) else {}
                }

        # ========== 两阶段加载：检查是否需要进入第二阶段 ==========
        action_type = action.get("type", "")

        # 提取工具名称和参数
        if "tool" in action:
            tool_name = action["tool"]
            args = action.get("args", {})
        else:
            tool_name = ""
            args = {}

        # 只有 TOOL_CALL 类型且参数为空时才进入第二阶段
        needs_second_stage = (
            action_type == "TOOL_CALL" and
            tool_name and
            tool_name != "FINISH" and
            tool_name != "FINISH_SUMMARY" and
            (not args or args == {} or args is None)
        )

        if needs_second_stage:
            logger.info(f"[Planner V2] 第二阶段：参数构造，tool={tool_name}")

            # 调用第二阶段参数构造
            constructed_params = await self._construct_params_v2(
                tool_name=tool_name,
                query=query,
                user_conversation=user_conversation,
                thought=thought,
                reasoning=reasoning
            )

            if constructed_params:
                # 更新 action 的参数
                action["args"] = constructed_params
                logger.info(f"[Planner V2] 参数构造成功: {list(constructed_params.keys())}")
            else:
                # 参数构造失败，返回错误
                logger.error(f"[Planner V2] 参数构造失败，tool={tool_name}")
                return {
                    "thought": thought,
                    "reasoning": reasoning,
                    "action": {
                        "type": "FINISH",
                        "tool": "FINISH",
                        "args": {"answer": f"无法为工具 {tool_name} 构造参数。"}
                    }
                }

        return {
            "thought": thought,
            "reasoning": reasoning,
            "action": action
        }

    async def _construct_params_v2(
        self,
        tool_name: str,
        query: str,
        user_conversation: str,
        thought: str,
        reasoning: str
    ) -> Optional[Dict]:
        """
        V2版本的参数构造方法（异步）

        专门为 think_and_action_v2 设计，使用消息列表格式

        Args:
            tool_name: 工具名称
            query: 用户查询
            user_conversation: 用户对话内容（第一阶段的）
            thought: 第一阶段的思考内容
            reasoning: 第一阶段的推理内容

        Returns:
            构造的参数字典，失败返回None
        """
        # 1. 获取工具的详细schema
        try:
            from app.tools import create_global_tool_registry
            registry = create_global_tool_registry()
            tool_data = registry._tools.get(tool_name)

            if not tool_data:
                logger.error(f"[Planner V2] 工具不存在: {tool_name}")
                return None

            # 获取工具实例并调用 get_function_schema() 方法
            tool = tool_data.get("tool")
            if tool and hasattr(tool, 'get_function_schema'):
                function_schema = tool.get_function_schema()
                detailed_schema = function_schema.get("parameters", {})
                tool_description = function_schema.get("description", "")
            else:
                # 回退方案：尝试直接从 tool_data 获取
                logger.warning(f"[Planner V2] 工具 {tool_name} 没有 get_function_schema 方法")
                detailed_schema = tool_data.get("input_adapter_rules", {}).get("parameters", {})
                tool_description = tool_data.get("metadata", {}).get("description", "")

            if not detailed_schema or detailed_schema.get("properties") is None:
                logger.warning(f"[Planner V2] 工具 {tool_name} 没有有效的参数定义")
                return None

        except Exception as e:
            logger.error(f"[Planner V2] 获取工具schema失败: {e}")
            return None

        # 2. 构造第二阶段prompt
        schema_text = json.dumps(detailed_schema, indent=2, ensure_ascii=False)

        stage2_prompt = f"""你需要为工具 "{tool_name}" 构造参数。

工具描述: {tool_description}

用户问题: {query}

你的思考: {thought}
推理过程: {reasoning}

对话上下文:
{user_conversation}

工具参数定义:
{schema_text}

请根据上述信息，构造工具的参数。输出格式:
```json
{{
    "thought": "参数构造的思考过程",
    "action": {{
        "type": "TOOL_CALL",
        "tool": "{tool_name}",
        "args": {{
            "参数1": "值1",
            "参数2": "值2"
        }}
    }}
}}
```

注意:
1. 严格遵循参数schema定义
2. 从用户问题中推断合理的参数值
3. 时间参数使用标准格式：YYYY-MM-DD HH:mm:ss
4. 地点参数使用中文城市名称
5. 仅输出JSON，不要额外解释
6. ⚠️ **如果用户问题中的任务无法用当前工具完成（如要求搜索文件，但工具只能处理指定文件），不要强行构造参数，应在thought中说明建议使用其他工具**
   - 搜索文件：使用 bash 工具（Windows: dir /s /b *.docx, Linux: find . -name "*.docx"）
   - 文件系统操作：使用 bash 工具（ls, cd, grep等）
   - Office工具（word_processor/excel_processor/ppt_processor）只能处理已知的文件路径
   - **环境检查**：Office工具仅支持Windows系统，Linux/macOS请使用bash工具或其他方式
"""

        # 3. 调用LLM构造参数
        messages = [
            {"role": "system", "content": "你是一个专业的大气污染溯源分析助手，负责为工具构造参数。"},
            {"role": "user", "content": stage2_prompt}
        ]

        logger.debug(f"[Planner V2] 参数构造阶段 - LLM调用")
        llm_response = await self.llm_service.chat(messages)
        logger.debug(f"[Planner V2] LLM响应: {llm_response[:200]}...")

        # 4. 解析参数
        from app.utils.llm_response_parser import parser
        parsed_result = parser.parse(llm_response)

        if not parsed_result.get("success") or not parsed_result.get("data"):
            logger.error(f"[Planner V2] 参数解析失败: {parsed_result.get('error')}")
            return None

        data = parsed_result["data"]

        # 提取 action.args
        if "action" in data and isinstance(data["action"], dict):
            action_obj = data["action"]
            args = action_obj.get("args", {})
        else:
            # 尝试旧格式
            args = data.get("action_input", {})

        # 验证参数不为空
        if not args or args == {} or args == "null":
            logger.error(f"[Planner V2] 构造的参数为空")
            return None

        return args

    def plan(
        self,
        query: str,
        history: List[Dict] = None,
        available_data: Dict[str, Any] = None
    ) -> Dict:
        """
        制定执行计划

        两阶段流程:
        1. 工具选择阶段: LLM根据摘要选择工具
        2. 参数构造阶段: 加载详细schema并构造参数

        Args:
            query: 用户查询
            history: 历史对话（ReAct循环历史）
            available_data: 可用数据上下文

        Returns:
            {
                "thought": "思考过程",
                "action": "工具名称",
                "action_input": {参数},
                "needs_data": [所需data_id列表]
            }
        """
        history = history or []
        available_data = available_data or {}

        # === 第一阶段: 工具选择 ===
        logger.info("[Planner] === 第一阶段: 工具选择 ===")

        # 1. 获取工具摘要
        tool_summaries = self._get_tool_summaries()

        # 2. 构造第一阶段prompt (仅包含摘要)
        stage1_prompt = self._build_stage1_prompt(
            query=query,
            history=history,
            tool_summaries=tool_summaries,
            available_data=available_data
        )

        # 3. 调用LLM选择工具
        logger.debug(f"[Planner] 工具选择阶段 - LLM调用")
        llm_response = self.llm_service.chat(stage1_prompt)
        logger.debug(f"[Planner] LLM响应: {llm_response[:200]}...")

        # 4. 解析LLM响应
        parsed = LLMResponseParser.parse_tool_call(llm_response)

        if not parsed or "error" in parsed:
            return {
                "thought": "无法解析LLM响应",
                "action": "final_answer",
                "action_input": {"answer": "抱歉，我无法理解当前的分析需求。"},
                "raw_response": llm_response
            }

        # 提取基础信息
        thought = parsed.get("thought", "")
        action = parsed.get("action", "")
        action_input = parsed.get("action_input", {})

        # === 第二阶段: 参数构造 (如果需要) ===
        if action_input is None or action_input == {} or action_input == "null":
            logger.info("[Planner] === 第二阶段: 参数构造 ===")
            logger.debug(f"[Planner] 需要加载详细schema for tool: {action}")

            # 加载schema并构造参数
            constructed_params = self._load_schema_and_construct_params(
                tool_name=action,
                query=query,
                history=history,
                available_data=available_data,
                thought=thought
            )

            if constructed_params:
                action_input = constructed_params
            else:
                # 参数构造失败，返回错误
                return {
                    "thought": thought,
                    "action": "final_answer",
                    "action_input": {"answer": f"无法为工具 {action} 构造参数。"},
                    "raw_response": llm_response
                }

        # 返回最终计划
        return {
            "thought": thought,
            "action": action,
            "action_input": action_input,
            "raw_response": llm_response
        }

    async def stream_user_answer(self, prompt: str):
        """
        流式生成用户答案（异步生成器）

        用于 FINISH_SUMMARY 阶段，生成最终的分析报告。

        Args:
            prompt: 生成答案的提示词

        Yields:
            str: 生成的文本片段
        """
        import httpx

        # 构建消息列表
        messages = [{"role": "user", "content": prompt}]

        # 获取请求配置
        url, headers = self.llm_service._get_request_config()

        # 构建请求payload
        payload = {
            "model": self.llm_service.model,
            "messages": messages,
            "temperature": 0.7,
            "stream": True,
        }

        # 千问3特殊处理：禁用思考模式
        if self.llm_service.provider == "qwen":
            payload["enable_thinking"] = False

        logger.info(f"[Planner] 开始流式生成用户答案，prompt长度: {len(prompt)}")

        try:
            async with httpx.AsyncClient(timeout=600.0) as client:
                async with client.stream("POST", url, headers=headers, json=payload) as response:
                    response.raise_for_status()

                    async for line in response.aiter_lines():
                        if not line:
                            continue

                        # OpenAI / Qwen 兼容接口使用 "data: {...}" 和 "data: [DONE]" 形式
                        if line.startswith("data: "):
                            data_str = line[len("data: ") :].strip()
                            if data_str == "[DONE]":
                                break

                            try:
                                chunk = json.loads(data_str)
                            except Exception:
                                # 非法 JSON 片段直接跳过
                                continue

                            # 兼容不同provider的流式返回格式
                            choices = chunk.get("choices")
                            if not isinstance(choices, list) or not choices:
                                continue

                            first_choice = choices[0]
                            if not isinstance(first_choice, dict):
                                continue

                            # 提取内容片段
                            delta = first_choice.get("delta") or first_choice.get("message") or {}
                            piece = delta.get("content") or ""
                            if piece:
                                yield piece

        except Exception as e:
            logger.error(f"[Planner] 流式生成失败: {e}")
            # 如果流式生成失败，返回错误信息
            yield f"\n\n[生成失败: {str(e)}]"

    def _get_tool_summaries(self) -> List[Dict]:
        """
        获取所有工具的摘要信息（用于第一阶段）

        摘要格式:
        {
            "name": "工具名称",
            "description": "功能描述",
            "category": "工具分类"
        }
        """
        summaries = []
        for tool_name, tool_def in self.tool_registry.list_tools().items():
            summaries.append({
                "name": tool_name,
                "description": tool_def.get("description", ""),
                "category": tool_def.get("category", "general")
            })
        return summaries

    def _build_stage1_prompt(
        self,
        query: str,
        history: List[Dict],
        tool_summaries: List[Dict],
        available_data: Dict
    ) -> str:
        """
        构造第一阶段prompt（工具选择）

        特点:
        - 仅包含工具摘要（不含详细schema）
        - 包含精简的历史上下文
        - 包含可用数据概览
        """
        # 格式化工具摘要
        tools_text = "\n".join([
            f"- {t['name']}: {t['description']} (分类: {t['category']})"
            for t in tool_summaries
        ])

        # 格式化历史记录（最近3轮）
        history_text = ""
        if history:
            recent_history = history[-self.max_context_turns:]
            history_items = []
            for h in recent_history:
                thought = h.get("thought", "")
                action = h.get("action", "")
                obs = h.get("observation", "")
                history_items.append(f"思考: {thought}\n行动: {action}\n观察: {obs[:100]}...")
            history_text = "\n---\n".join(history_items)

        # 格式化可用数据
        data_text = ""
        if available_data:
            data_items = []
            for data_id, info in available_data.items():
                schema = info.get("schema", "unknown")
                count = info.get("record_count", 0)
                data_items.append(f"- {data_id} ({schema}, {count}条记录)")
            data_text = "\n".join(data_items)

        prompt = f"""你是一个智能的大气污染溯源分析助手。请根据用户问题选择合适的工具。

用户问题: {query}

可用工具:
{tools_text}

当前可用数据:
{data_text if data_text else "无"}

历史执行记录:
{history_text if history_text else "无"}

请按照以下格式输出你的决策:
```json
{{
    "thought": "你的思考过程（分析问题需求，选择工具理由）",
    "action": "选择的工具名称",
    "action_input": null
}}
```

注意:
1. 如果需要结束分析，使用 action="final_answer"
2. action_input设为null表示需要后续加载详细参数schema
3. 优先使用已有数据，避免重复查询
4. 仅输出JSON，不要额外解释
"""
        return prompt

    def _load_schema_and_construct_params(
        self,
        tool_name: str,
        query: str,
        history: List[Dict],
        available_data: Dict,
        thought: str
    ) -> Optional[Dict]:
        """
        第二阶段: 加载工具的详细schema并构造参数

        优化策略:
        - 仅加载选中工具的schema
        - 精简历史上下文（提取data_id等关键信息）
        - 聚焦参数构造任务

        Args:
            tool_name: 选中的工具名称
            query: 用户查询
            history: 历史记录
            available_data: 可用数据
            thought: 第一阶段的思考内容

        Returns:
            构造的参数字典，失败返回None
        """
        # 1. 获取工具的详细schema
        tool_def = self.tool_registry.get_tool(tool_name)
        if not tool_def:
            logger.error(f"[Planner] 工具不存在: {tool_name}")
            return None

        detailed_schema = tool_def.get("parameters", {})

        # 2. 提取精简的上下文
        logger.debug(f"[Planner] 上下文压缩: 原始历史轮数={len(history)}")
        relevant_context = self._extract_relevant_context(history)
        logger.debug(f"[Planner] 上下文压缩: 压缩后轮数={len(relevant_context)}")

        # 3. 构造第二阶段prompt
        stage2_prompt = self._build_param_construction_prompt(
            tool_name=tool_name,
            tool_schema=detailed_schema,
            query=query,
            relevant_context=relevant_context,
            available_data=available_data,
            previous_thought=thought
        )

        # 4. 调用LLM构造参数
        logger.debug(f"[Planner] 参数构造阶段 - LLM调用")
        llm_response = self.llm_service.chat(stage2_prompt)
        logger.debug(f"[Planner] LLM响应: {llm_response[:200]}...")

        # 5. 解析参数
        parsed = LLMResponseParser.parse_tool_call(llm_response)

        if not parsed or "error" in parsed:
            logger.error(f"[Planner] 参数解析失败: {parsed}")
            return None

        action_input = parsed.get("action_input", {})

        # 验证参数不为空
        if not action_input or action_input == "null":
            logger.error(f"[Planner] 参数为空")
            return None

        return action_input

    def _extract_relevant_context(self, history: List[Dict]) -> List[Dict]:
        """
        提取上下文信息（保留完整内容）

        策略:
        - 保留最近N轮（默认3轮）
        - 保留完整的对话内容，不做压缩裁剪
        - 确保Office工具等需要上下文信息时能正确工作

        Returns:
            最近N轮的完整历史记录
        """
        if not history:
            return []

        # 保留最近N轮，不做任何压缩
        return history[-self.max_context_turns:]

    def _summarize_observation(self, observation: str) -> str:
        """
        总结观察结果（提取关键信息）

        提取:
        - data_id
        - status
        - record_count
        - 错误信息
        """
        if not observation:
            return ""

        # 尝试解析为JSON
        try:
            obs_data = json.loads(observation)
            summary = {
                "status": obs_data.get("status", "unknown"),
                "data_id": obs_data.get("data_id", ""),
                "record_count": obs_data.get("metadata", {}).get("record_count", 0),
                "error": obs_data.get("error", "")
            }
            return json.dumps(summary, ensure_ascii=False)
        except:
            # 无法解析，返回截断的原始文本
            return observation[:150] + "..."

    def _build_param_construction_prompt(
        self,
        tool_name: str,
        tool_schema: Dict,
        query: str,
        relevant_context: List[Dict],
        available_data: Dict,
        previous_thought: str
    ) -> str:
        """
        构造参数构造阶段的prompt

        特点:
        - 包含详细的参数schema
        - 包含精简的上下文
        - 聚焦参数生成任务
        """
        # 格式化schema
        schema_text = json.dumps(tool_schema, indent=2, ensure_ascii=False)

        # 格式化精简上下文
        context_text = ""
        if relevant_context:
            context_items = []
            for ctx in relevant_context:
                context_items.append(
                    f"思考: {ctx['thought']}\n"
                    f"行动: {ctx['action']}\n"
                    f"观察摘要: {ctx['observation_summary']}"
                )
            context_text = "\n---\n".join(context_items)

        # 格式化可用数据
        data_text = ""
        if available_data:
            data_items = []
            for data_id, info in available_data.items():
                schema = info.get("schema", "unknown")
                count = info.get("record_count", 0)
                data_items.append(f"- {data_id} ({schema}, {count}条记录)")
            data_text = "\n".join(data_items)

        prompt = f"""你需要为工具 "{tool_name}" 构造参数。

用户问题: {query}

你的思考: {previous_thought}

工具参数定义:
{schema_text}

当前可用数据:
{data_text if data_text else "无"}

相关上下文:
{context_text if context_text else "无"}

请根据上述信息，构造工具的参数。输出格式:
```json
{{
    "action_input": {{
        "参数1": "值1",
        "参数2": "值2"
    }}
}}
```

注意:
1. 严格遵循参数schema定义
2. 优先使用可用数据的data_id
3. 推断合理的默认值
4. 仅输出JSON，不要额外解释
"""
        return prompt


# ==================== 历史遗留代码说明 ====================
#
# 以下方法已在架构演进中被替代，已于清理中移除:
#
# 1. _generate_step_summary()
#    - 功能: 生成ReAct步骤摘要
#    - 替代方案: plan()方法中直接构造字典结构
#    - 移除时间: 2024-xx-xx
#
# 2. _extract_json_from_llm()
#    - 功能: 从LLM响应提取JSON
#    - 替代方案: app/utils/llm_response_parser.py 中的 LLMResponseParser
#    - 移除时间: 2024-xx-xx
#
# 3. _format_context_window()
#    - 功能: 简单的上下文窗口限制
#    - 替代方案: _extract_relevant_context() 更智能的上下文压缩
#    - 移除时间: 2024-xx-xx
#
# =========================================================
