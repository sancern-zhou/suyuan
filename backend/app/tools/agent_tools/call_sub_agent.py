"""
调用子Agent的工具（双向通用）

功能：
- 专家Agent可以调用助手Agent处理办公任务
- 助手Agent可以调用专家Agent处理数据分析
"""

from typing import Dict, Any, Literal, Optional
import structlog

from app.tools.base.tool_interface import LLMTool, ToolCategory

logger = structlog.get_logger()

AgentMode = Literal["assistant", "expert"]


class CallSubAgentTool(LLMTool):
    """
    调用子Agent的工具（双向通用）

    用法：
    - 专家Agent调用助手Agent：call_sub_agent(target_mode="assistant", ...)
    - 助手Agent调用专家Agent：call_sub_agent(target_mode="expert", ...)
    """

    def __init__(
        self,
        memory_manager=None,
        llm_planner=None,
        tool_executor=None
    ):
        # 定义 function_schema
        function_schema = {
            "name": "call_sub_agent",
            "description": "调用另一个Agent模式作为子Agent执行任务",
            "parameters": {
                "type": "object",
                "properties": {
                    "target_mode": {
                        "type": "string",
                        "enum": ["assistant", "expert"],
                        "description": "目标Agent模式（assistant=助手模式，expert=专家模式）"
                    },
                    "task_description": {
                        "type": "string",
                        "description": "任务描述（清晰说明需要子Agent完成什么任务）"
                    },
                    "context_data": {
                        "type": "object",
                        "description": "传递给子Agent的上下文数据（可选）",
                        "default": {}
                    }
                },
                "required": ["target_mode", "task_description"]
            }
        }

        # 初始化基类
        super().__init__(
            name="call_sub_agent",
            description="调用另一个Agent模式作为子Agent执行任务",
            category=ToolCategory.QUERY,  # 归类为查询工具
            function_schema=function_schema,
            version="1.0.0",
            requires_context=True  # ✅ 需要context来获取依赖
        )

        self.memory_manager = memory_manager
        self.llm_planner = llm_planner
        self.tool_executor = tool_executor

    async def execute(
        self,
        context: Optional[Any] = None,  # ✅ context放在第一位
        target_mode: AgentMode = None,
        task_description: str = None,
        context_data: Optional[Dict[str, Any]] = None,
        **kwargs  # ✅ 捕获额外参数
    ) -> Dict[str, Any]:
        """
        执行子Agent调用

        Args:
            context: ExecutionContext（包含memory_manager等依赖）
            target_mode: 目标Agent模式（"assistant" | "expert"）
            task_description: 任务描述
            context_data: 上下文数据

        Returns:
            {
                "status": "success" | "failed",
                "result": "子Agent的执行结果",
                "data": {...},
                "summary": "简要总结"
            }
        """
        # ✅ 参数验证
        if not target_mode:
            return {
                "status": "failed",
                "success": False,
                "result": "缺少必需参数：target_mode",
                "data": {},
                "metadata": {"schema_version": "v2.0", "generator": "call_sub_agent"},
                "summary": "参数验证失败"
            }

        if not task_description:
            return {
                "status": "failed",
                "success": False,
                "result": "缺少必需参数：task_description",
                "data": {},
                "metadata": {"schema_version": "v2.0", "generator": "call_sub_agent"},
                "summary": "参数验证失败"
            }

        try:
            logger.info(
                "calling_sub_agent",
                target_mode=target_mode,
                task=task_description[:100] if task_description else "",
                has_context=context_data is not None
            )

            # ✅ 从context获取依赖（如果工具初始化时没有传递）
            memory_manager = self.memory_manager
            llm_planner = self.llm_planner
            tool_executor = self.tool_executor

            if context and hasattr(context, 'memory_manager'):
                memory_manager = context.memory_manager
                if hasattr(context, 'llm_planner'):
                    llm_planner = context.llm_planner
                if hasattr(context, 'tool_executor'):
                    tool_executor = context.tool_executor

            # 验证必需的依赖
            if not memory_manager:
                raise RuntimeError("memory_manager is required for call_sub_agent")

            # 1. 动态导入（避免循环导入）
            from app.agent.core.loop import ReActLoop
            from app.agent.prompts.prompt_builder import build_react_system_prompt

            # 2. 构建子Agent的系统提示词
            sub_agent_prompt = build_react_system_prompt(mode=target_mode)

            # 3. 创建子Agent实例
            sub_agent_loop = ReActLoop(
                memory_manager=memory_manager,
                llm_planner=llm_planner,
                tool_executor=tool_executor,
                max_iterations=10,  # 限制迭代次数
                stream_enabled=False,  # 子Agent不需要流式输出
                enable_reasoning=False  # 子Agent无需详细reasoning
            )

            # 4. 构建增强的查询（携带上下文）
            enhanced_query = self._build_enhanced_query(
                task_description,
                context_data or {},
                target_mode
            )

            # 5. 执行子Agent
            result_events = []
            async for event in sub_agent_loop.run(
                user_query=enhanced_query,
                manual_mode=target_mode  # 强制使用指定模式
            ):
                result_events.append(event)

            # 6. 提取最终结果
            final_result = self._extract_final_result(result_events)

            logger.info(
                "sub_agent_completed",
                target_mode=target_mode,
                status=final_result["status"],
                iterations=len([e for e in result_events if e.get("type") == "tool_call"])
            )

            return {
                "status": "success",
                "success": True,
                "result": final_result["answer"],
                "data": final_result.get("data", {}),
                "metadata": {
                    "schema_version": "v2.0",
                    "generator": "call_sub_agent",
                    "sub_agent_mode": target_mode,
                    "iterations": len(result_events)
                },
                "summary": f"{self._get_mode_name(target_mode)}已完成任务"
            }

        except Exception as e:
            logger.error(
                "sub_agent_failed",
                target_mode=target_mode,
                error=str(e),
                task=task_description[:100]
            )
            return {
                "status": "failed",
                "success": False,
                "result": f"子Agent执行失败：{str(e)}",
                "data": {},
                "metadata": {
                    "schema_version": "v2.0",
                    "generator": "call_sub_agent"
                },
                "summary": "任务执行失败"
            }

    def _build_enhanced_query(
        self,
        task_description: str,
        context_data: Dict,
        target_mode: str
    ) -> str:
        """构建增强的查询（携带上下文）"""
        query_parts = [task_description]

        if context_data:
            query_parts.append("\n\n【上下文数据】")
            for key, value in context_data.items():
                if isinstance(value, (dict, list)):
                    query_parts.append(f"- {key}: {str(value)[:300]}...")
                else:
                    query_parts.append(f"- {key}: {value}")

        # 根据目标模式添加提示
        if target_mode == "assistant":
            query_parts.append("\n注意：你是作为子Agent被调用，专注完成上述办公任务即可。")
        else:
            query_parts.append("\n注意：你是作为子Agent被调用，专注完成上述数据分析任务即可。")

        return "\n".join(query_parts)

    def _extract_final_result(self, events: list) -> Dict:
        """从事件流中提取最终结果"""
        # 查找agent_finish事件
        for event in reversed(events):
            if event.get("type") == "agent_finish":
                return {
                    "status": "success",
                    "answer": event.get("answer", ""),
                    "data": event.get("data", {})
                }

        # 查找最后一个observation事件
        for event in reversed(events):
            if event.get("type") == "observation":
                return {
                    "status": "success",
                    "answer": event.get("content", ""),
                    "data": event.get("data", {})
                }

        return {
            "status": "failed",
            "answer": "子Agent未返回结果",
            "data": {}
        }

    def _get_mode_name(self, mode: str) -> str:
        """获取模式的友好名称"""
        return "助手Agent" if mode == "assistant" else "专家Agent"
