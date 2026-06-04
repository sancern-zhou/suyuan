"""
ReAct Agent API Routes

ReAct Agent 的 REST API 路由
"""

from fastapi import APIRouter, HTTPException, Body, Request
from fastapi.responses import StreamingResponse
from pydantic import AliasChoices, BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
import asyncio
import json
import structlog

from app.agent import create_react_agent
from app.agent.session import Session, get_session_manager
from app.agent.runtime.cancellation import cancellation_registry
from app.agent.runtime.steering import steering_registry
from app.agent.runtime.session_advisory_lock import session_advisory_lock
from app.services.llm_service import llm_service

logger = structlog.get_logger()

router = APIRouter(prefix="/api/agent", tags=["agent"])


def _safe_preview(value: Any, max_chars: int = 100) -> str:
    if value is None:
        return "empty"
    if isinstance(value, str):
        return value[:max_chars] if value else "empty"
    try:
        return json.dumps(value, ensure_ascii=False, default=str)[:max_chars]
    except Exception:
        return repr(value)[:max_chars]


# ========================================
# Request/Response Models
# ========================================

class AgentAnalyzeRequest(BaseModel):
    """Agent 分析请求"""
    query: str = Field(..., description="用户自然语言查询")
    session_id: Optional[str] = Field(None, description="会话ID（可选，用于会话恢复）")
    enhance_with_history: bool = Field(True, description="是否使用长期记忆增强")
    max_iterations: int = Field(60, ge=1, le=60, description="最大迭代次数")
    mode: Optional[str] = Field(
        "expert",
        description="✅ Agent模式：'assistant' - 助手模式（办公任务），'expert' - 专家模式（数据分析），'query' - 问数模式（数据查询），'report' - 报告模式（报告生成），'chart' - 图表模式（数据可视化），'ops' - 运维管理模式（工单审核、异常分析）"
    )
    user_id: Optional[str] = Field(None, description="""✅ 用户标识（用于跨会话记忆）
- 如果提供：同一用户在不同session共享记忆
- 如果不提供：每个session独立记忆""")
    assistant_mode: Optional[str] = Field(
        None,
        description="""助手模式（旧版，已弃用，建议使用mode参数）：
        'meteorology-expert' - 气象专家单专家模式
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
    model_tier: Optional[str] = Field(
        None,
        validation_alias=AliasChoices("model_tier", "modelTier"),
        description="模型档位：flash 使用 LLM_FLASH_MODELS 优先级；pro 使用 LLM_PRO_MODELS 优先级"
    )
    skip_auto_followup: bool = Field(
        False,
        validation_alias=AliasChoices("skip_auto_followup", "skipAutoFollowup"),
        description="是否跳过报告模式自动复核钩子，用于自动复核轮防止递归触发"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "query": "分析广州天河站2025-08-09的O3污染",
                "session_id": None,
                "mode": "expert",
                "user_id": "john_doe",
                "enhance_with_history": True,
                "max_iterations": 10,
                "knowledge_base_ids": ["kb_123", "kb_456"]
            }
        }


class AgentQueryRequest(BaseModel):
    """Agent 简单查询请求（非流式）"""
    query: str = Field(..., description="用户查询")
    max_iterations: int = Field(60, ge=1, le=60, description="最大迭代次数")
    session_id: Optional[str] = Field(None, description="会话ID（可选，用于保持会话连续性和记忆）")
    user_identifier: Optional[str] = Field(None, description="用户标识（可选，用于跨会话记忆共享）")
    assistant_mode: Optional[str] = Field(
        None,
        description="""助手模式：
        'meteorology-expert' - 气象专家单专家模式
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


class AgentSteerRequest(BaseModel):
    """执行中用户补充/纠偏输入。"""
    message: str = Field(..., description="追加到当前 active run 的用户输入")


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
    category: str
    status: str
    version: str
    requires_context: bool
    priority: int
    registered_at: Optional[str]
    statistics: Dict[str, Any]
    metadata: Dict[str, Any]
    function_schema: Optional[Dict[str, Any]]
    has_input_adapter: bool
    has_return_schema: bool


class ToolListResponse(BaseModel):
    """工具列表响应"""
    tools: List[Dict[str, Any]]
    count: int


# ========================================
# Global Agent Instances
# ========================================

# 通用Agent实例（使用默认 max_iterations=60）
multi_expert_agent_instance = create_react_agent(
    with_test_tools=False
)

# 气象专家模式全局实例（使用默认 max_iterations=30）
meteorology_expert_agent_instance = create_react_agent(
    with_test_tools=False,
    max_working_memory=25
)

# 数据可视化专家模式全局实例（专注图表，减少迭代）
data_viz_agent_instance = create_react_agent(
    with_test_tools=False,
    max_iterations=8,  # ⚠️ 特殊配置：可视化只需8次
    max_working_memory=15
)

logger.info(
    "agent_instances_created",
    multi_expert_tools=len(multi_expert_agent_instance.get_available_tools()),
    meteorology_expert_tools=len(meteorology_expert_agent_instance.get_available_tools()),
    data_viz_tools=len(data_viz_agent_instance.get_available_tools())
)


# ========================================
# API Endpoints
# ========================================

@router.post("/analyze")
async def analyze_stream(request: AgentAnalyzeRequest, raw_request: Request):
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
    raw_body = await raw_request.json()
    if request.model_tier is None and isinstance(raw_body, dict):
        raw_model_tier = raw_body.get("model_tier") or raw_body.get("modelTier")
        if raw_model_tier:
            request.model_tier = str(raw_model_tier)
        else:
            logger.warning(
                "agent_analyze_model_tier_missing",
                body_keys=sorted(raw_body.keys()),
                session_id=request.session_id,
            )

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
        assistant_mode=request.assistant_mode,
        knowledge_base_ids=request.knowledge_base_ids,
        is_interruption=request.is_interruption,
        model_tier=request.model_tier,
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
        elif request.assistant_mode == 'data-visualization-expert':
            agent = data_viz_agent_instance
            logger.info(
                "使用数据可视化专家模式",
                session_id=request.session_id,
                agent_id=id(agent),
                max_iterations=8
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
            "knowledge_base_ids": request.knowledge_base_ids,
            "enable_reasoning": request.enable_reasoning,
            "is_interruption": request.is_interruption,
            "manual_mode": request.mode,
            "attachments": request.attachments,  # ✅ 传递附件信息
            "user_identifier": request.user_id,  # ✅ 直接传递 user_id，允许 None（None 时使用模式内共享记忆）
            "skip_auto_followup": request.skip_auto_followup
        }

        # 初始化会话管理器（使用全局单例，确保内存缓存一致）
        session_manager = get_session_manager()
        actual_session_id = request.session_id
        conversation_history = []
        collected_data_ids = []
        collected_visuals = []
        seen_visual_ids = set()  # ✅ 用于去重：记录已添加的图表ID

        if not actual_session_id:
            import uuid
            actual_session_id = f"session_{int(datetime.now().timestamp() * 1000)}_{uuid.uuid4().hex[:8]}"
            analyze_kwargs["session_id"] = actual_session_id

        async def event_generator():
            """SSE 事件生成器"""
            nonlocal actual_session_id, conversation_history, collected_data_ids, collected_visuals, seen_visual_ids
            cancel_event = None

            # ✅ 用于统计（不输出日志）
            event_count = 0
            streaming_chunk_count = 0

            # 创建或加载会话
            if actual_session_id:
                session = await session_manager.load_session(actual_session_id)
                if session:
                    session_already_exists = True
                    logger.info(
                        "session_restored",
                        session_id=actual_session_id,
                        has_conversation_history=bool(session.conversation_history),
                        conversation_history_length=len(session.conversation_history) if session.conversation_history else 0,
                        has_data_ids=bool(session.data_ids),
                        data_ids_count=len(session.data_ids) if session.data_ids else 0
                    )
                    conversation_history = session.conversation_history or []

                    # ✅ 不再传递 initial_messages，因为 react_agent._get_or_create_session 会自动从 SessionManager 恢复会话
                    # 避免重复加载历史消息
                else:
                    session_already_exists = False
                    logger.warning(
                        "session_not_found_creating_new",
                        session_id=actual_session_id,
                        hint="SessionManager中未找到该会话，将创建新会话"
                    )
                    session = Session(session_id=actual_session_id, query=request.query)
                    conversation_history = []
            else:
                session_already_exists = False
                session = Session(session_id=actual_session_id, query=request.query)
                conversation_history = []
                logger.info("session_created", session_id=actual_session_id)
                # 更新 analyze_kwargs 中的 session_id
                analyze_kwargs["session_id"] = actual_session_id

            cancel_event = await cancellation_registry.register(actual_session_id)
            analyze_kwargs["cancel_event"] = cancel_event

            # 只保存/刷新会话元数据，不在首个 SSE 事件前同步历史消息。
            # 历史消息在本轮完成或异常时走增量保存，避免 DELETE + INSERT
            # 阻塞用户看到首个响应事件。
            if session_already_exists:
                async def _save_initial_session_metadata() -> None:
                    try:
                        await session_manager.save_session(session, save_messages=False)
                    except Exception as save_err:
                        logger.warning(
                            "initial_session_metadata_save_failed",
                            session_id=actual_session_id,
                            error=str(save_err)
                        )

                asyncio.create_task(_save_initial_session_metadata())
            else:
                await session_manager.save_session(session, save_messages=False)

            # ✅ 添加用户消息到对话历史
            user_message = {
                "type": "user",
                "content": request.query,
                "timestamp": datetime.now().isoformat()
            }
            conversation_history.append(user_message)
            logger.debug("user_message_added", query_preview=request.query[:100])

            try:
                with llm_service.use_model_tier(request.model_tier):
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
                        if event["type"] in ["thought", "tool_use", "tool_result"]:
                            # 创建前端格式的消息
                            event_data = event.get("data", {})

                            # 【验证】检查 tool_result 事件的 data 字段
                            if event["type"] == "tool_result":
                                result = event_data.get("result") or {}
                                logger.info("[tool_result_debug] 验证 event.data 结构",
                                    has_data="data" in event,
                                    data_keys=list(event_data.keys()) if isinstance(event_data, dict) else "not_dict",
                                    has_result="result" in event_data,
                                    result_keys=list(result.keys()) if isinstance(result, dict) else "not_dict",
                                    has_visuals="visuals" in result,
                                    visuals_count=len(result.get("visuals") or [])
                                )

                            frontend_message = {
                                "type": event["type"],
                                "data": event_data,
                                "timestamp": event_data.get("timestamp") if "timestamp" in event_data else None
                            }

                            # 提取 content 字段（前端显示用）
                            if event["type"] == "thought":
                                frontend_message["content"] = event_data.get("thought", "思考中...")
                            elif event["type"] == "tool_use":
                                tool_name = event_data.get("tool_name", "")
                                frontend_message["content"] = f"调用工具: {tool_name}" if tool_name else "执行行动"
                            elif event["type"] == "tool_result":
                                result_data = event_data.get("result", {})
                                if isinstance(result_data, dict):
                                    frontend_message["content"] = (
                                        result_data.get("summary_text")
                                        or _safe_preview(result_data.get("summary"), 500)
                                        or "获得结果"
                                    )
                                else:
                                    frontend_message["content"] = str(result_data)

                            conversation_history.append(frontend_message)
                            # 防御性代码：确保 content 不为 None
                            content = frontend_message.get("content", "")
                            content_preview = _safe_preview(content, 50)
                            logger.debug("conversation_history_appended",
                                        event_type=event["type"],
                                        history_length=len(conversation_history),
                                        content_preview=content_preview)

                        # ✅ streaming_text 事件：流式输出但不保存到历史（由 complete 事件统一保存）
                        elif event["type"] == "streaming_text":
                            # 流式文本直接转发，不保存到对话历史
                            # 等待 complete 事件时再保存完整的最终答案
                            pass

                        elif event["type"] == "synthetic_user_message":
                            event_data = event.get("data") or {}
                            synthetic_message = {
                                "type": "user",
                                "content": event_data.get("content", ""),
                                "timestamp": event_data.get("timestamp", datetime.now().isoformat()),
                                "source": event_data.get("source", "auto_hook"),
                                "hook_name": event_data.get("hook_name")
                            }
                            conversation_history.append(synthetic_message)
                            logger.info(
                                "synthetic_user_message_added",
                                session_id=actual_session_id,
                                hook_name=event_data.get("hook_name"),
                                content_preview=synthetic_message["content"][:100]
                            )

                        # 收集数据ID
                        if event["type"] == "tool_result" and "data" in event:
                            data = event.get("data", {})
                            if "data_id" in data:
                                collected_data_ids.append(data["data_id"])
                            if "data_ids" in data:
                                collected_data_ids.extend(data["data_ids"])

                        # 收集可视化（基于ID去重）
                        if "visuals" in event.get("data", {}):
                            visuals = event["data"]["visuals"]
                            if isinstance(visuals, list):
                                for visual in visuals:
                                    visual_id = visual.get("id")
                                    visual_title = visual.get("title", "")
                                    if visual_id and visual_id not in seen_visual_ids:
                                        logger.info(
                                            "visual_collected",
                                            visual_id=visual_id,
                                            visual_title=visual_title[:50] if visual_title else "",
                                            seen_count=len(seen_visual_ids)
                                        )
                                        collected_visuals.append(visual)
                                        seen_visual_ids.add(visual_id)
                                    elif visual_id and visual_id in seen_visual_ids:
                                        logger.warning(
                                            "visual_duplicate_skipped",
                                            visual_id=visual_id,
                                            visual_title=visual_title[:50] if visual_title else ""
                                        )
                                    elif not visual_id:
                                        # 如果没有ID，也添加（向后兼容）
                                        collected_visuals.append(visual)

                        # ✅ 如果是完成或致命错误，先保存会话（在 yield 之前）
                        if event["type"] == "complete":
                            # ✅ 将本轮生成/读取的 Office 预览元数据附到 complete 事件，避免前端错过
                            # office_document 实时事件后无法打开预览面板。
                            office_documents = agent._session_store.get(
                                actual_session_id, {}
                            ).get("office_documents", [])
                            if office_documents:
                                event.setdefault("data", {})["office_documents"] = office_documents
                                event["data"]["last_office_document"] = office_documents[-1]

                            # ✅ 添加最终答案消息
                            event_data = event.get("data") or {}
                            if event_data.get("answer"):
                                final_message = {
                                    "type": "final",
                                    "content": event_data["answer"],
                                    "data": event_data,
                                    "timestamp": event_data.get("timestamp", datetime.now().isoformat())
                                }

                                # ✅ 将visuals提取到消息顶层，确保能被正确存储和恢复
                                if "visuals" in event_data and isinstance(event_data["visuals"], list):
                                    final_message["visuals"] = event_data["visuals"]

                                conversation_history.append(final_message)
                                logger.debug("response_message_added", answer_preview=event["data"]["answer"][:100])

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

                            # ✅ 将收集的数据存入 _session_store，供 react_agent.py 的 finally 块统一保存
                            if actual_session_id not in agent._session_store:
                                agent._session_store[actual_session_id] = {}

                            agent._session_store[actual_session_id]["collected_data_ids"] = list(set(collected_data_ids))
                            agent._session_store[actual_session_id]["collected_visuals"] = collected_visuals
                            logger.info(
                                "collected_data_stored",
                                session_id=actual_session_id,
                                data_ids_count=len(collected_data_ids),
                                visuals_count=len(collected_visuals)
                            )
                        elif event["type"] in ["incomplete", "fatal_error", "interrupted"]:
                            # ✅ 优化：压缩中间过程，只保留必要信息
                            compressed_history = []
                            for msg in conversation_history:
                                if msg.get("type") in ["user", "final"]:
                                    compressed_history.append(msg)
                                elif msg.get("type") in ["thought", "tool_use", "tool_result"]:
                                    compressed_history.append({
                                        "type": msg.get("type"),
                                        "content": msg.get("content", "")[:200],
                                        "timestamp": msg.get("timestamp")
                                    })
                            session.conversation_history = compressed_history
                            session.data_ids = list(set(collected_data_ids))
                            session.visual_ids = [v.get("id") for v in collected_visuals if v.get("id")]

                            # ✅ 将收集的数据存入 _session_store，供 react_agent.py 的 finally 块统一保存
                            if actual_session_id not in agent._session_store:
                                agent._session_store[actual_session_id] = {}

                            agent._session_store[actual_session_id]["collected_data_ids"] = list(set(collected_data_ids))
                            agent._session_store[actual_session_id]["collected_visuals"] = collected_visuals
                            agent._session_store[actual_session_id]["conversation_history_compressed"] = compressed_history
                            agent._session_store[actual_session_id]["has_error"] = event["type"] != "interrupted"
                            agent._session_store[actual_session_id]["error_type"] = event["type"]
                            if "data" in event and "error" in event["data"]:
                                agent._session_store[actual_session_id]["error_message"] = event["data"].get("error", "Unknown error")
                            if event["type"] == "interrupted":
                                event_data = event.get("data") or {}
                                compressed_history.append({
                                    "type": "interrupted",
                                    "content": event_data.get("reason", "用户已暂停本轮分析"),
                                    "timestamp": datetime.now().isoformat()
                                })
                            await session_manager.save_session(session)

                            logger.info("collected_data_stored_on_error", session_id=actual_session_id, error_type=event["type"])

                        # 将事件序列化为 SSE 格式
                        event_data = json.dumps(event, ensure_ascii=False, default=str)
                        yield f"data: {event_data}\n\n"

                        # 如果是完成或致命错误，结束循环
                        if event["type"] in ["complete", "incomplete", "fatal_error", "interrupted"]:
                            break

            except asyncio.CancelledError:
                if actual_session_id:
                    await cancellation_registry.cancel(actual_session_id)
                    session.conversation_history = conversation_history + [{
                        "type": "interrupted",
                        "content": "客户端已断开，本轮分析已取消",
                        "timestamp": datetime.now().isoformat()
                    }]
                    session.data_ids = list(set(collected_data_ids))
                    session.visual_ids = [v.get("id") for v in collected_visuals if v.get("id")]
                    await session_manager.save_session(session)
                raise
            except Exception as e:
                logger.error(
                    "stream_generation_error",
                    error=str(e),
                    exc_info=True
                )
                # 保存失败会话
                session.conversation_history = conversation_history
                session.data_ids = list(set(collected_data_ids))
                session.error = {
                    "type": "stream_error",
                    "message": str(e),
                    "timestamp": datetime.now().isoformat()
                }
                await session_manager.save_session(session)
                logger.info("session_saved_on_exception", session_id=actual_session_id)

                error_event = {
                    "type": "fatal_error",
                    "data": {
                        "error": str(e),
                        "timestamp": None
                    }
                }
                yield f"data: {json.dumps(error_event, ensure_ascii=False, default=str)}\n\n"
            finally:
                if actual_session_id and cancel_event is not None:
                    await cancellation_registry.unregister(actual_session_id, cancel_event)

        async def locked_event_generator():
            async with session_advisory_lock(actual_session_id):
                async for chunk in event_generator():
                    yield chunk

        return StreamingResponse(
            locked_event_generator(),
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


@router.post("/{session_id}/cancel")
async def cancel_analysis(session_id: str):
    """Cancel an in-flight streaming analysis for a session."""
    cancelled = await cancellation_registry.cancel(session_id)
    return {
        "success": True,
        "cancelled": cancelled,
        "session_id": session_id,
        "message": "已发送取消信号" if cancelled else "没有找到运行中的分析任务",
    }


@router.post("/{session_id}/steer")
async def steer_analysis(session_id: str, request: AgentSteerRequest):
    """Append user steering input to an active steerable run."""
    accepted = await steering_registry.add_input(session_id, request.message)
    return {
        "success": True,
        "accepted": accepted,
        "session_id": session_id,
        "message": "已追加到当前执行任务" if accepted else "没有找到可追加的运行中任务",
    }


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
            session_id=request.session_id,
            user_identifier=request.user_identifier,
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
    获取可用工具列表（包含完整信息）
    """
    try:
        # 从工具注册表获取详细信息
        tools_info = multi_expert_agent_instance.executor.tool_registry.get_tools_info()

        logger.info("agent_tools_listed", count=len(tools_info))

        return ToolListResponse(
            tools=tools_info,
            count=len(tools_info)
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
        # 从工具注册表获取详细信息
        info = multi_expert_agent_instance.executor.tool_registry.get_tool_info(tool_name)

        if not info:
            raise HTTPException(
                status_code=404,
                detail=f"工具不存在: {tool_name}"
            )

        logger.info("tool_info_retrieved", tool_name=tool_name)

        return ToolInfo(**info)

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


@router.patch("/tools/{tool_name}")
async def update_tool_status(tool_name: str, enabled: bool = Body(..., embed=True)):
    """
    更新工具启用/禁用状态

    Args:
        tool_name: 工具名称
        enabled: True=启用, False=禁用
    """
    try:
        registry = multi_expert_agent_instance.executor.tool_registry

        # 检查工具是否存在
        if not registry.get_tool(tool_name):
            raise HTTPException(
                status_code=404,
                detail=f"工具不存在: {tool_name}"
            )

        # 更新工具状态
        success = registry.set_tool_enabled(tool_name, enabled)

        if not success:
            raise HTTPException(
                status_code=500,
                detail=f"更新工具状态失败"
            )

        logger.info(
            "tool_status_updated",
            tool_name=tool_name,
            enabled=enabled
        )

        return {
            "success": True,
            "tool_name": tool_name,
            "enabled": enabled
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "update_tool_status_failed",
            tool_name=tool_name,
            error=str(e),
            exc_info=True
        )
        raise HTTPException(
            status_code=500,
            detail=f"更新工具状态失败: {str(e)}"
        )


@router.get("/tools/categories")
async def get_tools_categories():
    """
    获取所有工具类别
    """
    try:
        registry = multi_expert_agent_instance.executor.tool_registry
        categories = registry.get_categories()

        logger.info("tool_categories_listed", count=len(categories))

        return {
            "categories": categories,
            "count": len(categories)
        }

    except Exception as e:
        logger.error(
            "get_tool_categories_failed",
            error=str(e),
            exc_info=True
        )
        raise HTTPException(
            status_code=500,
            detail=f"获取工具类别失败: {str(e)}"
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
            "data_visualization_expert": {
                "tools_count": len(data_viz_agent_instance.get_available_tools()),
                "max_iterations": data_viz_agent_instance.max_iterations,
                "description": "数据可视化专家模式"
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
