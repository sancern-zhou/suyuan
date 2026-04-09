"""
调用子Agent的工具（双向通用）

功能：
- 专家Agent可以调用助手Agent处理办公任务
- 助手Agent可以调用专家Agent处理数据分析
- Social Agent可以调用专家Agent进行数据分析

Session支持：
- 支持session_id参数实现连续对话
- 不传session_id则创建新session并返回
- 传入session_id则继续已有对话
"""

from typing import Dict, Any, Literal, Optional, List
import structlog
from datetime import datetime

from app.tools.base.tool_interface import LLMTool, ToolCategory
from app.agent.session.session_manager import get_session_manager
from app.agent.session.models import Session

logger = structlog.get_logger()

# 获取全局session管理器
session_manager = get_session_manager()

# ⚠️ 支持6种模式：assistant, expert, code, query, report, social
AgentMode = Literal["assistant", "expert", "code", "query", "report", "social"]


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
            "description": "调用另一个Agent模式作为子Agent执行任务（支持session连续对话）",
            "parameters": {
                "type": "object",
                "properties": {
                    "target_mode": {
                        "type": "string",
                        "enum": ["assistant", "expert", "code", "query", "report", "social"],
                        "description": "目标Agent模式（assistant=助手, expert=专家, social=社交, query=问数, report=报告, code=编程）"
                    },
                    "task_description": {
                        "type": "string",
                        "description": "任务描述（清晰说明需要子Agent完成什么任务）"
                    },
                    "context_data": {
                        "type": "object",
                        "description": "传递给子Agent的上下文数据（可选）",
                        "default": {}
                    },
                    "session_id": {
                        "type": "string",
                        "description": "子Agent会话ID（可选）：传入则继续已有对话，不传则创建新会话。返回值中会包含此session_id可用于后续继续对话"
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
        session_id: Optional[str] = None,  # ✅ 新增：session_id参数
        **kwargs  # ✅ 捕获额外参数
    ) -> Dict[str, Any]:
        """
        执行子Agent调用（支持session连续对话）

        Args:
            context: ExecutionContext（包含memory_manager等依赖）
            target_mode: 目标Agent模式（"assistant" | "expert"）
            task_description: 任务描述
            context_data: 上下文数据
            session_id: 可选，子Agent会话ID（传入则继续已有对话）

        Returns:
            {
                "status": "success" | "failed",
                "result": "子Agent的执行结果",
                "data": {...},
                "metadata": {
                    "session_id": "xxx",  # ✅ 返回session_id供父Agent使用
                    "is_new_session": true/false
                },
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
            # 获取父Agent模式
            parent_mode = self._get_parent_mode(context)

            logger.info(
                "calling_sub_agent",
                parent_mode=parent_mode,
                target_mode=target_mode,
                task=task_description[:100] if task_description else "",
                has_context=context_data is not None,
                session_id=session_id,
                is_continuation=session_id is not None
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

            # ✅ 1. Session处理：确定session_id和对话历史
            conversation_history = []
            is_new_session = False

            if session_id:
                # 继续已有session
                session = session_manager.get_session(session_id)
                if not session:
                    return {
                        "status": "failed",
                        "success": False,
                        "result": f"Session不存在或已过期: {session_id}",
                        "data": {},
                        "metadata": {"schema_version": "v2.0", "generator": "call_sub_agent"},
                        "summary": "Session不存在"
                    }
                # 验证session匹配
                if session.child_mode != target_mode:
                    return {
                        "status": "failed",
                        "success": False,
                        "result": f"Session模式不匹配：期望{session.child_mode}，实际{target_mode}",
                        "data": {},
                        "metadata": {"schema_version": "v2.0", "generator": "call_sub_agent"},
                        "summary": "Session模式不匹配"
                    }
                conversation_history = session.conversation_history
                logger.info(f"继续子Agent session: {session_id}, 历史消息数: {len(conversation_history)}")
            else:
                # 创建新session
                session_id = self._generate_session_id(parent_mode, target_mode)
                is_new_session = True
                logger.info(f"创建新子Agent session: {session_id}")

            # 2. 动态导入（避免循环导入）
            from app.agent.core.loop import ReActLoop
            from app.agent.prompts.prompt_builder import build_react_system_prompt

            # 3. 构建子Agent的系统提示词
            sub_agent_prompt = build_react_system_prompt(mode=target_mode)

            # 4. 创建子Agent实例（不限制迭代次数，由子Agent自行决定）
            sub_agent_loop = ReActLoop(
                memory_manager=memory_manager,
                llm_planner=llm_planner,
                tool_executor=tool_executor,
                stream_enabled=False,  # 子Agent不需要流式输出
                enable_reasoning=False  # 子Agent无需详细reasoning
            )

            # 5. 构建增强的查询（携带上下文）
            enhanced_query = self._build_enhanced_query(
                task_description,
                context_data or {},
                target_mode
            )

            # 6. 执行子Agent（传入对话历史）
            result_events = []
            async for event in sub_agent_loop.run(
                user_query=enhanced_query,
                manual_mode=target_mode,  # 强制使用指定模式
                initial_messages=conversation_history if conversation_history else None  # ✅ 传入历史
            ):
                result_events.append(event)

            # 7. 提取最终结果
            final_result = self._extract_final_result(result_events)

            logger.info(
                "sub_agent_completed",
                target_mode=target_mode,
                status=final_result["status"],
                iterations=len([e for e in result_events if e.get("type") == "tool_call"]),
                session_id=session_id
            )

            # 提取结构化数据（data_ids、chart_urls、statistics、tool_calls）
            structured_data = {
                "data_ids": self._extract_data_ids(result_events),
                "chart_urls": self._extract_chart_urls(result_events),
                "statistics": self._extract_statistics(result_events),
                "tool_calls": self._extract_tool_calls(result_events)
            }

            # ✅ 8. 保存/更新session
            self._update_session(
                session_id=session_id,
                parent_mode=parent_mode,
                child_mode=target_mode,
                user_query=task_description,
                assistant_answer=final_result["answer"],
                result_events=result_events
            )

            return {
                "status": "success",
                "success": True,
                "result": final_result["answer"],
                "data": structured_data,
                "metadata": {
                    "schema_version": "v2.0",
                    "generator": "call_sub_agent",
                    "sub_agent_mode": target_mode,
                    "iterations": len(result_events),
                    "data_ids_count": len(structured_data["data_ids"]),
                    "chart_urls_count": len(structured_data["chart_urls"]),
                    # ✅ 返回session_id给父Agent
                    "session_id": session_id,
                    "is_new_session": is_new_session
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
        mode_hints = {
            "assistant": "注意：你是作为子Agent被调用，专注完成上述办公任务即可。",
            "expert": "注意：你是作为子Agent被调用，专注完成上述数据分析任务即可。",
            "social": "注意：你是作为子Agent被调用，专注完成上述社交平台任务即可。",
            "query": "注意：你是作为子Agent被调用，专注完成上述数据查询任务即可。",
            "report": "注意：你是作为子Agent被调用，专注完成上述报告生成任务即可。",
            "code": "注意：你是作为子Agent被调用，专注完成上述编程任务即可。",
        }
        query_parts.append(f"\n{mode_hints.get(target_mode, '')}")

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
        mode_names = {
            "assistant": "助手Agent",
            "expert": "专家Agent",
            "social": "社交Agent",
            "query": "问数Agent",
            "report": "报告Agent",
            "code": "编程Agent",
        }
        return mode_names.get(mode, mode)

    def _extract_data_ids(self, events: list) -> list:
        """从事件流中提取所有data_id"""
        data_ids = []
        for event in events:
            # 从observation中提取
            if event.get("type") == "observation":
                if "data_id" in event:
                    data_ids.append(event["data_id"])
                # 从data字段中提取
                if "data" in event and isinstance(event["data"], dict):
                    if "data_id" in event["data"]:
                        data_ids.append(event["data"]["data_id"])
                    # 从data字段中的data_ids数组提取
                    if "data_ids" in event["data"] and isinstance(event["data"]["data_ids"], list):
                        data_ids.extend(event["data"]["data_ids"])
        return list(set(data_ids))  # 去重

    def _extract_chart_urls(self, events: list) -> list:
        """从事件流中提取所有图表URL"""
        chart_urls = []
        for event in events:
            if event.get("type") == "observation":
                # 从markdown_image中提取
                content = event.get("content", "")
                if "![" in content:
                    import re
                    urls = re.findall(r'\(/api/image/[^\)]+\)', content)
                    chart_urls.extend([url[1:-1] for url in urls])
                # 从visuals字段中提取
                if "visuals" in event and isinstance(event["visuals"], list):
                    for visual in event["visuals"]:
                        if isinstance(visual, dict):
                            if "payload" in visual and isinstance(visual["payload"], dict):
                                if "image_url" in visual["payload"]:
                                    chart_urls.append(visual["payload"]["image_url"])
                # 从data字段中的chart_urls数组提取
                if "data" in event and isinstance(event["data"], dict):
                    if "chart_urls" in event["data"] and isinstance(event["data"]["chart_urls"], list):
                        chart_urls.extend(event["data"]["chart_urls"])
        return list(set(chart_urls))  # 去重

    def _extract_statistics(self, events: list) -> dict:
        """从事件流中提取统计摘要"""
        statistics = {}
        for event in events:
            if event.get("type") == "observation":
                # 从result字段提取统计信息
                if "result" in event and isinstance(event["result"], dict):
                    for city, data in event["result"].items():
                        if isinstance(data, dict):
                            # 提取关键统计指标
                            stats = {
                                "composite_index": data.get("composite_index"),
                                "exceed_days": data.get("exceed_days") or data.get("total_exceed_days"),
                                "compliance_rate": data.get("compliance_rate"),
                                "statistical_concentrations": data.get("statistical_concentrations")
                            }
                            # 过滤None值
                            statistics[city] = {k: v for k, v in stats.items() if v is not None}
                # 从data字段中的statistics提取
                if "data" in event and isinstance(event["data"], dict):
                    if "statistics" in event["data"] and isinstance(event["data"]["statistics"], dict):
                        statistics.update(event["data"]["statistics"])
        return statistics

    def _extract_tool_calls(self, events: list) -> list:
        """从事件流中提取工具调用记录"""
        tool_calls = []
        for event in events:
            if event.get("type") == "tool_call":
                tool_calls.append({
                    "tool": event.get("generator", event.get("tool", "")),
                    "args": event.get("args", {})
                })
        return tool_calls

    def _get_parent_mode(self, context: Optional[Any]) -> str:
        """从context获取父Agent模式"""
        if context and hasattr(context, 'manual_mode'):
            return context.manual_mode
        # 尝试从memory_manager获取
        if context and hasattr(context, 'memory_manager'):
            mm = context.memory_manager
            if hasattr(mm, 'mode'):
                return mm.mode
        return "social"  # 默认社交模式

    def _generate_session_id(self, parent_mode: str, child_mode: str) -> str:
        """生成子Agent session_id"""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        return f"{parent_mode}__to__{child_mode}__{timestamp}"

    def _update_session(
        self,
        session_id: str,
        parent_mode: str,
        child_mode: str,
        user_query: str,
        assistant_answer: str,
        result_events: List[Dict]
    ):
        """更新子Agent session"""
        # 加载或创建session
        session = session_manager.get_session(session_id)

        if not session:
            # 创建新session
            session = Session(
                session_id=session_id,
                query=user_query,
                parent_mode=parent_mode,
                child_mode=child_mode,
                is_sub_agent_session=True
            )

        # 添加对话历史
        session.conversation_history.append({
            "role": "user",
            "content": user_query,
            "timestamp": datetime.now().isoformat()
        })
        session.conversation_history.append({
            "role": "assistant",
            "content": assistant_answer,
            "timestamp": datetime.now().isoformat()
        })

        # 提取并添加data_ids和visual_ids
        data_ids = self._extract_data_ids(result_events)
        visual_ids = self._extract_visual_ids(result_events)

        # 去重后添加
        existing_data_ids = set(session.data_ids)
        for data_id in data_ids:
            if data_id not in existing_data_ids:
                session.data_ids.append(data_id)

        existing_visual_ids = set(session.visual_ids)
        for visual_id in visual_ids:
            if visual_id not in existing_visual_ids:
                session.visual_ids.append(visual_id)

        # 保存session（更新时间戳）
        session_manager.save_session(session, update_timestamp=True)

        logger.info(
            "session_updated",
            session_id=session_id,
            conversation_length=len(session.conversation_history),
            data_count=len(session.data_ids),
            visual_count=len(session.visual_ids)
        )

    def _extract_visual_ids(self, events: list) -> list:
        """从事件流中提取visual_ids"""
        visual_ids = []
        for event in events:
            if event.get("type") == "observation":
                # 从visuals字段中提取
                if "visuals" in event and isinstance(event["visuals"], list):
                    for visual in event["visuals"]:
                        if isinstance(visual, dict) and "id" in visual:
                            visual_ids.append(visual["id"])
                # 从data字段中的visuals提取
                if "data" in event and isinstance(event["data"], dict):
                    if "visuals" in event["data"] and isinstance(event["data"]["visuals"], list):
                        for visual in event["data"]["visuals"]:
                            if isinstance(visual, dict) and "id" in visual:
                                visual_ids.append(visual["id"])
        return list(set(visual_ids))  # 去重
