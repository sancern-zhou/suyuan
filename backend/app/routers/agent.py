"""
ReAct Agent API Routes

ReAct Agent 的 REST API 路由
"""

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
import json
import structlog

from app.agent import create_react_agent
from app.agent.session import SessionManager, Session, SessionState

logger = structlog.get_logger()

router = APIRouter(prefix="/api/agent", tags=["agent"])


# ========================================
# Request/Response Models
# ========================================

class AgentAnalyzeRequest(BaseModel):
    """Agent 分析请求"""
    query: str = Field(..., description="用户自然语言查询")
    session_id: Optional[str] = Field(None, description="会话ID（可选，用于会话恢复）")
    enhance_with_history: bool = Field(True, description="是否使用长期记忆增强")
    max_iterations: int = Field(30, ge=1, le=30, description="最大迭代次数")
    plan_mode: bool = Field(False, description="是否使用 ReWOO 规划模式（一次性生成完整计划）")
    mode: Optional[str] = Field(
        "expert",
        description="✅ Agent模式（三模式架构）：'assistant' - 助手模式（办公任务），'expert' - 专家模式（数据分析），'code' - 编程模式（工具开发）"
    )
    assistant_mode: Optional[str] = Field(
        None,
        description="""助手模式（旧版，已弃用，建议使用mode参数）：
        'meteorology-expert' - 气象专家单专家模式
        'quick-tracing-expert' - 快速溯源专家多专家模式
        'data-visualization-expert' - 数据可视化专家单专家模式
        'report-generation-expert' - 报告生成专家（预留）
        'template-report-expert' - 模板报告生成专家（方案B，推荐使用 /api/report/generate-from-template-agent）
        'general-agent' 或 None - 通用Agent单专家模式（支持ReAct循环）"""
    )
    knowledge_base_ids: Optional[List[str]] = Field(
        None,
        description="选中的知识库ID列表，用于检索增强生成"
    )
    enable_reasoning: bool = Field(
        False,
        description="是否启用思考模式（默认False，启用后会显示LLM的推理过程，适用于MiniMax等支持思考模式的模型）"
    )
    is_interruption: bool = Field(
        False,
        description="是否为用户中断后的对话（默认False，用户暂停后继续对话时为True）"
    )
    attachments: Optional[List[dict]] = Field(
        None,
        description="附件列表，包含用户上传的文件信息 [{file_id, name, type, url}]"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "query": "分析广州天河站2025-08-09的O3污染",
                "session_id": None,
                "enhance_with_history": True,
                "max_iterations": 10,
                "plan_mode": False,
                "assistant_mode": "quick-tracing-expert",
                "knowledge_base_ids": ["kb_123", "kb_456"]
            }
        }


class AgentQueryRequest(BaseModel):
    """Agent 简单查询请求（非流式）"""
    query: str = Field(..., description="用户查询")
    max_iterations: int = Field(30, ge=1, le=30, description="最大迭代次数")
    assistant_mode: Optional[str] = Field(
        None,
        description="""助手模式：
        'meteorology-expert' - 气象专家单专家模式
        'quick-tracing-expert' - 快速溯源专家多专家模式
        'data-visualization-expert' - 数据可视化专家单专家模式
        'report-generation-expert' - 报告生成专家（预留，暂未实现）
        'general-agent' 或 None - 通用Agent多专家模式"""
    )

    class Config:
        json_schema_extra = {
            "example": {
                "query": "查询广州今天的天气",
                "max_iterations": 5,
                "assistant_mode": "meteorology-expert"
            }
        }


class AgentQueryResponse(BaseModel):
    """Agent 查询响应"""
    answer: str = Field(..., description="分析答案")
    session_id: str = Field(..., description="会话ID")
    iterations: Optional[int] = Field(None, description="实际迭代次数")
    completed: bool = Field(..., description="是否成功完成")


class ToolInfo(BaseModel):
    """工具信息"""
    name: str
    description: str
    callable: str
    module: str


class ToolListResponse(BaseModel):
    """工具列表响应"""
    tools: List[str]
    count: int


# ========================================
# Global Agent Instances
# ========================================

# 通用Agent实例
multi_expert_agent_instance = create_react_agent(
    with_test_tools=False,
    max_iterations=10
)

# 气象专家模式全局实例
meteorology_expert_agent_instance = create_react_agent(
    with_test_tools=False,
    max_iterations=10,
    max_working_memory=25
)

# 快速溯源专家模式全局实例
quick_tracing_agent_instance = create_react_agent(
    with_test_tools=False,
    max_iterations=8,
    max_working_memory=20
)

# 数据可视化专家模式全局实例
data_viz_agent_instance = create_react_agent(
    with_test_tools=False,
    max_iterations=8,
    max_working_memory=15
)

# 深度溯源专家模式全局实例
deep_tracing_agent_instance = create_react_agent(
    with_test_tools=False,
    max_iterations=15,
    max_working_memory=30
)

logger.info(
    "agent_instances_created",
    multi_expert_tools=len(multi_expert_agent_instance.get_available_tools()),
    meteorology_expert_tools=len(meteorology_expert_agent_instance.get_available_tools()),
    quick_tracing_tools=len(quick_tracing_agent_instance.get_available_tools()),
    deep_tracing_tools=len(deep_tracing_agent_instance.get_available_tools()),
    data_viz_tools=len(data_viz_agent_instance.get_available_tools())
)


# ========================================
# API Endpoints
# ========================================

@router.post("/analyze")
async def analyze_stream(request: AgentAnalyzeRequest):
    """
    流式分析接口（Server-Sent Events）

    实时返回 ReAct Agent 的思考、行动、观察过程。

    **可用工具**:
    - Query Tools (7个):
      - get_air_quality - 空气质量查询
      - get_weather_data - 气象数据查询
      - get_weather_forecast - 天气预报查询
      - get_current_weather - 实时天气查询
      - get_fire_hotspots - 火点数据查询
      - get_dust_data - 扬尘数据查询
      - get_component_data - 组分数据查询（广东省超级站）

    - Analysis Tools (1个):
      - analyze_upwind_enterprises - 上风向企业分析（广东省）

    - Visualization Tools (2个):
      - generate_chart - 智能图表生成（模板库 + LLM）
      - generate_map - 地图生成

    **助手模式**:
    - 'meteorology-expert': 气象专家单专家模式（专注气象 + 默认可视化）
    - 'general-agent' 或 None: 多专家模式（天气+组分+可视化+报告）

    **事件类型**:
    - `start`: 分析开始
    - `thought`: LLM 思考
    - `action`: 行动决策（工具调用或完成）
    - `observation`: 工具执行结果
    - `complete`: 任务成功完成
    - `incomplete`: 达到最大迭代次数
    - `error`: 迭代错误
    - `fatal_error`: 致命错误
    """
    # 针对报告生成专家模式：在进入 ReAct 之前，显式告知 LLM 这是基于已有模板报告的连续对话，
    # 避免其误判为“首次对话、无历史上下文”。
    original_query = request.query
    if request.assistant_mode == "report-generation-expert" and request.session_id:
        request.query = (
            "【报告生成连续对话模式】\n"
            "你正在与用户就之前已经生成的一份基于模板的空气质量报告进行后续对话。\n"
            "该报告的完整 Markdown 内容以及相关数据已经保存在当前会话（session_id="
            f"{request.session_id}）的记忆中，必须把它视为历史上下文的一部分，不要认为这是第一次对话。\n"
            "后续所有用户提问（尤其包含“报告”“表格”“按模板”“修改”“补充”“为什么没按模板输出”等字样）"
            "都应理解为对这份已生成报告的修改、解释或补充，而不是一个全新的独立任务。\n"
            "在思考（Thought）时，请先简要回顾历史报告中与本问题相关的内容（尤其是表格和数据填充情况），"
            "再决定是直接解释/修改，还是需要调用工具获取更多数据。\n"
            f"当前用户的具体问题是：{original_query}"
        )

    logger.info(
        "agent_analyze_request",
        query=request.query[:100],
        session_id=request.session_id,
        max_iterations=request.max_iterations,
        plan_mode=request.plan_mode,
        assistant_mode=request.assistant_mode,
        knowledge_base_ids=request.knowledge_base_ids,
        is_interruption=request.is_interruption,
        mode=request.mode
    )

    try:
        # 根据助手模式选择 Agent
        if request.assistant_mode == 'meteorology-expert':
            agent = meteorology_expert_agent_instance
            logger.info(
                "使用气象专家模式",
                session_id=request.session_id,
                agent_id=id(agent)
            )
        elif request.assistant_mode == 'quick-tracing-expert':
            agent = quick_tracing_agent_instance
            logger.info(
                "使用快速溯源专家模式",
                session_id=request.session_id,
                agent_id=id(agent),
                max_iterations=8
            )
        elif request.assistant_mode == 'data-visualization-expert':
            agent = data_viz_agent_instance
            logger.info(
                "使用数据可视化专家模式",
                session_id=request.session_id,
                agent_id=id(agent),
                max_iterations=8
            )
        elif request.assistant_mode == 'deep-tracing-expert':
            agent = deep_tracing_agent_instance
            logger.info(
                "使用深度溯源专家模式",
                session_id=request.session_id,
                agent_id=id(agent),
                max_iterations=15,
                features=["analyze_trajectory_sources"]
            )
        elif request.assistant_mode == 'report-generation-expert':
            agent = multi_expert_agent_instance
            logger.info(
                "使用报告生成专家模式",
                session_id=request.session_id,
                agent_id=id(agent)
            )
        elif request.assistant_mode == 'template-report-expert':
            raise HTTPException(
                status_code=400,
                detail="模板报告生成请调用 /api/report/generate-from-template-agent（需提供模板内容和时间范围）"
            )
        else:
            # 默认使用通用Agent
            agent = multi_expert_agent_instance
            logger.info(
                "使用通用Agent模式",
                session_id=request.session_id,
                agent_id=id(agent)
            )

        # 构建分析参数
        analyze_kwargs = {
            "user_query": request.query,
            "session_id": request.session_id,
            "enhance_with_history": request.enhance_with_history,
            "max_iterations": request.max_iterations,
            "plan_mode": request.plan_mode,
            "knowledge_base_ids": request.knowledge_base_ids,
            "enable_reasoning": request.enable_reasoning,
            "is_interruption": request.is_interruption,
            "manual_mode": request.mode,
            "attachments": request.attachments  # ✅ 传递附件信息
        }

        # 初始化会话管理器
        session_manager = SessionManager()
        actual_session_id = request.session_id
        conversation_history = []
        collected_data_ids = []
        collected_visuals = []

        async def event_generator():
            """SSE 事件生成器"""
            nonlocal actual_session_id, conversation_history, collected_data_ids, collected_visuals

            # ✅ 用于统计（不输出日志）
            event_count = 0
            streaming_chunk_count = 0

            # 创建或加载会话
            if actual_session_id:
                session = session_manager.load_session(actual_session_id)
                if session:
                    logger.info("session_restored", session_id=actual_session_id)
                    conversation_history = session.conversation_history
                    # ✅ 如果有历史对话，传递给 agent.analyze()
                    if conversation_history:
                        analyze_kwargs["initial_messages"] = conversation_history
                        logger.info(
                            "passing_conversation_history_to_agent",
                            session_id=actual_session_id,
                            message_count=len(conversation_history)
                        )
                else:
                    logger.warning("session_not_found_creating_new", session_id=actual_session_id)
                    session = Session(session_id=actual_session_id, query=request.query)
            else:
                import uuid
                actual_session_id = f"session_{int(datetime.now().timestamp() * 1000)}_{uuid.uuid4().hex[:8]}"
                session = Session(session_id=actual_session_id, query=request.query)
                logger.info("session_created", session_id=actual_session_id)
                # 更新 analyze_kwargs 中的 session_id
                analyze_kwargs["session_id"] = actual_session_id

            # 保存初始会话状态
            session.state = SessionState.ACTIVE
            session_manager.save_session(session)

            # ✅ 添加用户消息到对话历史
            user_message = {
                "type": "user",
                "content": request.query,
                "timestamp": datetime.now().isoformat()
            }
            conversation_history.append(user_message)
            logger.debug("user_message_added", query_preview=request.query[:100])

            try:
                async for event in agent.analyze(**analyze_kwargs):
                    event_count += 1
                    event_type = event.get("type")

                    # ✅ 关闭流式文本事件的所有日志
                    if event_type != "streaming_text":
                        # ✅ 非流式事件：正常记录
                        logger.debug("received_event", event_type=event_type, has_data="data" in event)
                    else:
                        # ✅ 流式事件：静默处理，只统计不输出
                        streaming_chunk_count += 1

                    # 收集对话历史（转换为前端格式，添加 content 字段）
                    if event["type"] in ["thought", "action", "observation"]:
                        # 创建前端格式的消息
                        frontend_message = {
                            "type": event["type"],
                            "data": event.get("data", {}),
                            "timestamp": event.get("data", {}).get("timestamp") if "data" in event else None
                        }

                        # 提取 content 字段（前端显示用）
                        if event["type"] == "thought":
                            frontend_message["content"] = event.get("data", {}).get("thought", "思考中...")
                        elif event["type"] == "action":
                            action_data = event.get("data", {}).get("action", {})
                            tool_name = action_data.get("tool", "")
                            frontend_message["content"] = f"调用工具: {tool_name}" if tool_name else "执行行动"
                        elif event["type"] == "observation":
                            obs_data = event.get("data", {}).get("observation", {})
                            frontend_message["content"] = obs_data.get("summary", "获得结果") if isinstance(obs_data, dict) else str(obs_data)

                        conversation_history.append(frontend_message)
                        logger.debug("conversation_history_appended",
                                    event_type=event["type"],
                                    history_length=len(conversation_history),
                                    content_preview=frontend_message.get("content", "")[:50])

                    # ✅ streaming_text 事件：流式输出但不保存到历史（由 complete 事件统一保存）
                    elif event["type"] == "streaming_text":
                        # 流式文本直接转发，不保存到对话历史
                        # 等待 complete 事件时再保存完整的最终答案
                        pass

                    # 收集数据ID
                    if event["type"] == "observation" and "data" in event:
                        data = event.get("data", {})
                        if "data_id" in data:
                            collected_data_ids.append(data["data_id"])
                        if "data_ids" in data:
                            collected_data_ids.extend(data["data_ids"])

                    # 收集可视化
                    if "visuals" in event.get("data", {}):
                        visuals = event["data"]["visuals"]
                        if isinstance(visuals, list):
                            collected_visuals.extend(visuals)

                    # ✅ 如果是完成或致命错误，先保存会话（在 yield 之前）
                    if event["type"] == "complete":
                        # ✅ 添加最终答案消息
                        if event.get("data", {}).get("answer"):
                            final_message = {
                                "type": "final",
                                "content": event["data"]["answer"],
                                "data": event.get("data", {}),
                                "timestamp": event.get("data", {}).get("timestamp", datetime.now().isoformat())
                            }
                            conversation_history.append(final_message)
                            logger.debug("final_answer_added", answer_preview=event["data"]["answer"][:100])

                        # ✅ 关闭流式统计日志
                        # if streaming_chunk_count > 0:
                        #     logger.info(
                        #         "streaming_statistics",
                        #         session_id=actual_session_id,
                        #         total_events=event_count,
                        #         streaming_chunks=streaming_chunk_count
                        #     )

                        logger.info("saving_session_on_complete",
                                   session_id=actual_session_id,
                                   conversation_history_length=len(conversation_history),
                                   collected_data_ids_count=len(collected_data_ids),
                                   collected_visuals_count=len(collected_visuals))

                        session.state = SessionState.COMPLETED
                        session.completed_at = datetime.now()
                        session.conversation_history = conversation_history
                        session.data_ids = list(set(collected_data_ids))  # 去重
                        session.visual_ids = [v.get("id") for v in collected_visuals if v.get("id")]
                        session_manager.save_session(session)
                        logger.info("session_saved_on_complete", session_id=actual_session_id, data_count=len(session.data_ids))
                    elif event["type"] in ["incomplete", "fatal_error"]:
                        session.state = SessionState.FAILED if event["type"] == "fatal_error" else SessionState.COMPLETED
                        session.conversation_history = conversation_history
                        session.data_ids = list(set(collected_data_ids))
                        session.visual_ids = [v.get("id") for v in collected_visuals if v.get("id")]
                        if "data" in event and "error" in event["data"]:
                            session.error = {
                                "type": event["type"],
                                "message": event["data"].get("error", "Unknown error"),
                                "timestamp": datetime.now().isoformat()
                            }
                        session_manager.save_session(session)
                        logger.info("session_saved_on_error", session_id=actual_session_id, error_type=event["type"])

                    # 将事件序列化为 SSE 格式
                    event_data = json.dumps(event, ensure_ascii=False, default=str)
                    yield f"data: {event_data}\n\n"

                    # 如果是完成或致命错误，结束循环
                    if event["type"] in ["complete", "incomplete", "fatal_error"]:
                        break

            except Exception as e:
                logger.error(
                    "stream_generation_error",
                    error=str(e),
                    exc_info=True
                )
                # 保存失败会话
                session.state = SessionState.FAILED
                session.conversation_history = conversation_history
                session.data_ids = list(set(collected_data_ids))
                session.error = {
                    "type": "stream_error",
                    "message": str(e),
                    "timestamp": datetime.now().isoformat()
                }
                session_manager.save_session(session)
                logger.info("session_saved_on_exception", session_id=actual_session_id)

                error_event = {
                    "type": "fatal_error",
                    "data": {
                        "error": str(e),
                        "timestamp": None
                    }
                }
                yield f"data: {json.dumps(error_event, ensure_ascii=False, default=str)}\n\n"

        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no"
            }
        )

    except Exception as e:
        logger.error(
            "agent_analyze_failed",
            error=str(e),
            exc_info=True
        )
        raise HTTPException(
            status_code=500,
            detail=f"分析失败: {str(e)}"
        )


@router.post("/query", response_model=AgentQueryResponse)
async def simple_query(request: AgentQueryRequest):
    """
    简单查询接口（非流式）

    适用于不需要实时进度的简单查询。
    """
    logger.info(
        "agent_query_request",
        query=request.query[:100],
        max_iterations=request.max_iterations
    )

    try:
        # 默认使用多专家协作模式（兼容无assistant_mode参数的情况）
        agent = multi_expert_agent_instance
        assistant_mode = 'general-agent'  # 默认模式

        # 根据助手模式选择 Agent（使用全局实例以保持会话连续性）
        if hasattr(request, 'assistant_mode') and request.assistant_mode:
            if request.assistant_mode == 'meteorology-expert':
                agent = meteorology_expert_agent_instance
                assistant_mode = 'meteorology-expert'
                logger.info(
                    "使用气象专家模式",
                    agent_id=id(agent)
                )
            elif request.assistant_mode == 'quick-tracing-expert':
                agent = quick_tracing_agent_instance
                assistant_mode = 'quick-tracing-expert'
                logger.info(
                    "使用快速溯源专家模式",
                    agent_id=id(agent),
                    max_iterations=8
                )
            elif request.assistant_mode == 'data-visualization-expert':
                agent = data_viz_agent_instance
                assistant_mode = 'data-visualization-expert'
                logger.info(
                    "使用数据可视化专家模式",
                    agent_id=id(agent),
                    max_iterations=8
                )
            elif request.assistant_mode == 'report-generation-expert':
                raise HTTPException(
                    status_code=501,
                    detail="报告生成专家尚未实现，敬请期待"
                )

        logger.info(
            "agent_query_with_assistant_mode",
            assistant_mode=assistant_mode,
            agent_id=id(agent)
        )

        # 收集结果
        answer = ""
        session_id = ""
        iterations = 0
        completed = False

        async for event in agent.analyze(
            request.query,
            max_iterations=request.max_iterations
        ):
            if event["type"] == "start":
                session_id = event["data"].get("session_id", "")

            elif event["type"] == "complete":
                answer = event["data"].get("answer", "")
                iterations = event["data"].get("iterations", 0)
                completed = True
                break

            elif event["type"] == "incomplete":
                answer = event["data"].get("answer", "")
                iterations = event["data"].get("iterations", 0)
                completed = False
                break

            elif event["type"] == "fatal_error":
                raise HTTPException(
                    status_code=500,
                    detail=event["data"].get("error", "未知错误")
                )

        return AgentQueryResponse(
            answer=answer,
            session_id=session_id,
            iterations=iterations,
            completed=completed
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "agent_query_failed",
            error=str(e),
            exc_info=True
        )
        raise HTTPException(
            status_code=500,
            detail=f"查询失败: {str(e)}"
        )


@router.get("/tools", response_model=ToolListResponse)
async def list_tools():
    """
    获取可用工具列表
    """
    try:
        # 优先返回多专家模式的工具列表（更完整）
        tools = multi_expert_agent_instance.get_available_tools()

        logger.info("agent_tools_listed", count=len(tools))

        return ToolListResponse(
            tools=tools,
            count=len(tools)
        )

    except Exception as e:
        logger.error(
            "list_tools_failed",
            error=str(e),
            exc_info=True
        )
        raise HTTPException(
            status_code=500,
            detail=f"获取工具列表失败: {str(e)}"
        )


@router.get("/tools/{tool_name}", response_model=ToolInfo)
async def get_tool_info(tool_name: str):
    """
    获取特定工具的详细信息
    """
    try:
        # 优先从多专家模式实例获取工具信息
        info = multi_expert_agent_instance.get_tool_info(tool_name)

        if not info:
            # 如果多专家模式没有该工具，尝试从气象专家模式获取
            info = meteorology_expert_agent_instance.get_tool_info(tool_name)

        if not info:
            raise HTTPException(
                status_code=404,
                detail=f"工具不存在: {tool_name}"
            )

        logger.info("tool_info_retrieved", tool_name=tool_name)

        return ToolInfo(
            name=info["name"],
            description=info.get("doc", "无描述"),
            callable=info["callable"],
            module=info["module"]
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "get_tool_info_failed",
            tool_name=tool_name,
            error=str(e),
            exc_info=True
        )
        raise HTTPException(
            status_code=500,
            detail=f"获取工具信息失败: {str(e)}"
        )


@router.get("/health")
async def agent_health():
    """
    Agent 健康检查
    """
    return {
        "status": "healthy",
        "agent_type": "ReAct Agent",
        "instances": {
            "multi_expert": {
                "tools_count": len(multi_expert_agent_instance.get_available_tools()),
                "max_iterations": multi_expert_agent_instance.max_iterations,
                "description": "通用Agent模式"
            },
            "meteorology_expert": {
                "tools_count": len(meteorology_expert_agent_instance.get_available_tools()),
                "max_iterations": meteorology_expert_agent_instance.max_iterations,
                "description": "气象专家模式"
            },
            "quick_tracing_expert": {
                "tools_count": len(quick_tracing_agent_instance.get_available_tools()),
                "max_iterations": quick_tracing_agent_instance.max_iterations,
                "description": "快速溯源专家模式"
            },
            "data_visualization_expert": {
                "tools_count": len(data_viz_agent_instance.get_available_tools()),
                "max_iterations": data_viz_agent_instance.max_iterations,
                "description": "数据可视化专家模式"
            },
            "deep_tracing_expert": {
                "tools_count": len(deep_tracing_agent_instance.get_available_tools()),
                "max_iterations": deep_tracing_agent_instance.max_iterations,
                "description": "深度溯源专家模式（HYSPLIT轨迹+源清单+RACM2化学机理）"
            },
            "report_generation_expert": {
                "tools_count": 0,
                "max_iterations": 0,
                "description": "报告生成专家（预留，暂未实现）"
            }
        }
    }


# ========================================
# TODO: 会话管理接口（可选）
# ========================================

# @router.get("/sessions/{session_id}")
# async def get_session_status(session_id: str):
#     """获取会话状态"""
#     pass
#
# @router.delete("/sessions/{session_id}")
# async def delete_session(session_id: str):
#     """删除会话"""
#     pass
