"""
ReAct Agent API Routes

ReAct Agent 的 REST API 路由
"""

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from typing import Optional, List
import json
import structlog

from app.agent import create_react_agent

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
    max_iterations: int = Field(10, ge=1, le=20, description="最大迭代次数")
    debug_mode: bool = Field(False, description="是否启用调试模式（会额外返回发送给 LLM 的上下文）")
    plan_mode: bool = Field(False, description="是否使用 ReWOO 规划模式（一次性生成完整计划）")
    assistant_mode: Optional[str] = Field(
        None,
        description="""助手模式：
        'meteorology-expert' - 气象专家单专家模式
        'quick-tracing-expert' - 快速溯源专家多专家模式
        'data-visualization-expert' - 数据可视化专家单专家模式
        'report-generation-expert' - 报告生成专家（预留）
        'template-report-expert' - 模板报告生成专家（方案B，推荐使用 /api/report/generate-from-template-agent）
        'general-agent' 或 None - 通用Agent单专家模式（支持ReAct循环）"""
    )
    precision: str = Field(
        'standard',
        description="EKMA分析精度模式: fast(快速筛查,约18秒), standard(标准分析,约3分钟,默认), full(完整分析,约7-10分钟)"
    )
    knowledge_base_ids: Optional[List[str]] = Field(
        None,
        description="选中的知识库ID列表，用于检索增强生成"
    )
    enable_multi_expert: bool = Field(
        False,
        description="✅ 是否启用多专家系统（默认False，通用Agent使用单专家ReAct模式）"
    )
    enable_reasoning: bool = Field(
        False,
        description="✅ 是否启用思考模式（默认False，启用后会显示LLM的推理过程，适用于MiniMax等支持思考模式的模型）"
    )
    is_interruption: bool = Field(
        False,
        description="✅ 是否为用户中断后的对话（默认False，用户暂停后继续对话时为True）"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "query": "分析广州天河站2025-08-09的O3污染",
                "session_id": None,
                "enhance_with_history": True,
                "max_iterations": 10,
                "debug_mode": False,
                "plan_mode": False,
                "assistant_mode": "quick-tracing-expert",
                "precision": "standard",
                "knowledge_base_ids": ["kb_123", "kb_456"],
                "enable_multi_expert": False
            }
        }


class AgentQueryRequest(BaseModel):
    """Agent 简单查询请求（非流式）"""
    query: str = Field(..., description="用户查询")
    max_iterations: int = Field(10, ge=1, le=20, description="最大迭代次数")
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

# 多专家模式全局实例
multi_expert_agent_instance = create_react_agent(
    with_test_tools=False,  # 使用真实工具
    max_iterations=10,
    enable_multi_expert=True  # 启用多专家系统
)

# 气象专家模式全局实例（单专家，专注气象）
meteorology_expert_agent_instance = create_react_agent(
    with_test_tools=False,  # 使用真实工具
    max_iterations=10,
    enable_multi_expert=False,  # 单专家模式
    max_working_memory=25  # 增加工作记忆容量
)

# 快速溯源专家模式全局实例（多专家协作，专注溯源）
quick_tracing_agent_instance = create_react_agent(
    with_test_tools=False,
    max_iterations=8,  # 快速响应
    enable_multi_expert=True,  # 启用多专家系统
    max_working_memory=20
)

# 数据可视化专家模式全局实例（单专家，专注图表生成）
data_viz_agent_instance = create_react_agent(
    with_test_tools=False,
    max_iterations=8,  # 专注图表，快速响应
    enable_multi_expert=False,  # 单专家模式
    max_working_memory=15  # 适中记忆容量
)

# 深度溯源专家模式全局实例（多专家协作，深度分析）
# 特点：使用analyze_trajectory_sources + calculate_obm_full_chemistry
deep_tracing_agent_instance = create_react_agent(
    with_test_tools=False,
    max_iterations=15,  # 深度分析需要更多迭代
    enable_multi_expert=True,  # 启用多专家系统
    max_working_memory=30  # 增加记忆容量（深度分析数据量大）
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
        debug_mode=request.debug_mode,
        plan_mode=request.plan_mode,
        assistant_mode=request.assistant_mode,
        precision=request.precision,
        knowledge_base_ids=request.knowledge_base_ids,
        is_interruption=request.is_interruption  # ✅ 记录中断标志
    )

    try:
        # 根据助手模式和 enable_multi_expert 参数选择 Agent
        if request.assistant_mode == 'meteorology-expert':
            # 气象专家模式：单专家，专注气象
            agent = meteorology_expert_agent_instance
            logger.info(
                "使用气象专家单专家模式",
                session_id=request.session_id,
                enable_multi_expert=False,
                agent_id=id(agent)
            )
        elif request.assistant_mode == 'quick-tracing-expert':
            # 快速溯源专家模式：多专家协作，专注溯源
            agent = quick_tracing_agent_instance
            logger.info(
                "使用快速溯源专家模式",
                session_id=request.session_id,
                enable_multi_expert=True,
                agent_id=id(agent),
                max_iterations=8
            )
        elif request.assistant_mode == 'data-visualization-expert':
            # 数据可视化专家模式：单专家，专注图表
            agent = data_viz_agent_instance
            logger.info(
                "使用数据可视化专家模式",
                session_id=request.session_id,
                enable_multi_expert=False,
                agent_id=id(agent),
                max_iterations=8
            )
        elif request.assistant_mode == 'deep-tracing-expert':
            # 深度溯源专家模式：多专家协作，HYSPLIT轨迹+源清单+RACM2化学机理
            agent = deep_tracing_agent_instance
            # 深度溯源模式默认使用 full 精度
            if request.precision == 'standard':
                request.precision = 'full'
            logger.info(
                "使用深度溯源专家模式",
                session_id=request.session_id,
                enable_multi_expert=True,
                agent_id=id(agent),
                max_iterations=15,
                precision=request.precision,
                features=["analyze_trajectory_sources", "calculate_obm_full_chemistry"]
            )
        elif request.assistant_mode == 'report-generation-expert':
            # 报告生成专家模式：
            # - 复用多专家Agent实例 multi_expert_agent_instance，确保与模板报告/溯源流水线共享会话记忆；
            # - 但在本模式下通过 enable_multi_expert=False 走单专家 ReAct 循环（在下方 analyze_kwargs 中控制）。
            agent = multi_expert_agent_instance
            logger.info(
                "使用报告生成专家模式（单专家ReAct，复用multi_expert_agent_instance）",
                session_id=request.session_id,
                agent_id=id(agent)
            )
        elif request.assistant_mode == 'template-report-expert':
            # 模板报告生成专家：推荐使用 /api/report/generate-from-template-agent 以携带模板内容
            raise HTTPException(
                status_code=400,
                detail="模板报告生成请调用 /api/report/generate-from-template-agent（需提供模板内容和时间范围）"
            )
        elif request.enable_multi_expert:
            # ✅ 通用Agent多专家模式（显式启用）
            agent = multi_expert_agent_instance
            logger.info(
                "使用通用Agent多专家协作模式",
                session_id=request.session_id,
                enable_multi_expert=True,
                agent_id=id(agent)
            )
        else:
            # ✅ 通用Agent单专家模式（默认）：支持真正的ReAct循环
            agent = meteorology_expert_agent_instance  # 复用气象专家的单专家实例
            logger.info(
                "使用通用Agent单专家ReAct模式",
                session_id=request.session_id,
                enable_multi_expert=False,
                agent_id=id(agent),
                mode="真正的ReAct循环：思考→行动→观察"
            )

        # 验证precision有效性
        if request.precision not in ['fast', 'standard', 'full']:
            request.precision = 'standard'

        # ✅ 决定是否传递 enable_multi_expert 参数
        # 快速溯源、深度溯源和部分单专家模式使用实例的默认设置，不被前端参数覆盖
        should_pass_multi_expert_param = (
            request.assistant_mode in ['meteorology-expert', 'data-visualization-expert', 'report-generation-expert'] or
            request.assistant_mode is None or
            request.assistant_mode == 'general-agent'
        )

        # 构建分析参数
        analyze_kwargs = {
            "user_query": request.query,
            "session_id": request.session_id,
            "enhance_with_history": request.enhance_with_history,
            "max_iterations": request.max_iterations,
            "debug_mode": request.debug_mode,
            "plan_mode": request.plan_mode,
            "precision": request.precision,  # EKMA分析精度模式 (fast/standard/full)
            "knowledge_base_ids": request.knowledge_base_ids,  # 知识库ID列表
            "enable_reasoning": request.enable_reasoning,  # ✅ 思考模式开关（是否显示LLM推理过程）
            "is_interruption": request.is_interruption  # ✅ 中断标志（用户暂停后继续对话）
        }

        # ✅ 只有在需要时才传递 enable_multi_expert 参数
        if should_pass_multi_expert_param:
            analyze_kwargs["enable_multi_expert"] = request.enable_multi_expert

        async def event_generator():
            """SSE 事件生成器"""
            try:
                async for event in agent.analyze(**analyze_kwargs):
                    # 将事件序列化为 SSE 格式
                    event_data = json.dumps(event, ensure_ascii=False, default=str)
                    yield f"data: {event_data}\n\n"

                    # 如果是完成或致命错误，发送结束信号
                    if event["type"] in ["complete", "incomplete", "fatal_error"]:
                        break

            except Exception as e:
                logger.error(
                    "stream_generation_error",
                    error=str(e),
                    exc_info=True
                )
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
                    "使用气象专家单专家模式",
                    enable_multi_expert=False,
                    agent_id=id(agent)
                )
            elif request.assistant_mode == 'quick-tracing-expert':
                agent = quick_tracing_agent_instance
                assistant_mode = 'quick-tracing-expert'
                logger.info(
                    "使用快速溯源专家模式",
                    enable_multi_expert=True,
                    agent_id=id(agent),
                    max_iterations=8
                )
            elif request.assistant_mode == 'data-visualization-expert':
                agent = data_viz_agent_instance
                assistant_mode = 'data-visualization-expert'
                logger.info(
                    "使用数据可视化专家模式",
                    enable_multi_expert=False,
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
            agent_id=id(agent),
            enable_multi_expert=agent.enable_multi_expert
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
                "enable_multi_expert": multi_expert_agent_instance.enable_multi_expert,
                "description": "通用多专家协作模式"
            },
            "meteorology_expert": {
                "tools_count": len(meteorology_expert_agent_instance.get_available_tools()),
                "max_iterations": meteorology_expert_agent_instance.max_iterations,
                "enable_multi_expert": meteorology_expert_agent_instance.enable_multi_expert,
                "description": "气象专家单专家模式"
            },
            "quick_tracing_expert": {
                "tools_count": len(quick_tracing_agent_instance.get_available_tools()),
                "max_iterations": quick_tracing_agent_instance.max_iterations,
                "enable_multi_expert": quick_tracing_agent_instance.enable_multi_expert,
                "description": "快速溯源专家多专家模式"
            },
            "data_visualization_expert": {
                "tools_count": len(data_viz_agent_instance.get_available_tools()),
                "max_iterations": data_viz_agent_instance.max_iterations,
                "enable_multi_expert": data_viz_agent_instance.enable_multi_expert,
                "description": "数据可视化专家单专家模式"
            },
            "deep_tracing_expert": {
                "tools_count": len(deep_tracing_agent_instance.get_available_tools()),
                "max_iterations": deep_tracing_agent_instance.max_iterations,
                "enable_multi_expert": deep_tracing_agent_instance.enable_multi_expert,
                "description": "深度溯源专家多专家模式（HYSPLIT轨迹+源清单+RACM2化学机理）"
            },
            "report_generation_expert": {
                "tools_count": 0,
                "max_iterations": 0,
                "enable_multi_expert": False,
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
