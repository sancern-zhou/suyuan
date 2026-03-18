"""API routes - Conversational Chat Endpoint."""

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional, AsyncGenerator
import json

from app.services.analysis_orchestrator import AnalysisOrchestrator
from app.services.conversation_manager import conversation_manager
from app.services.llm_service import llm_service
from app.models.schemas import ChatRequest, ChatResponse
# from app.utils.data_processing import normalize_city_name  # 已迁移到本地实现
from app.utils.time_utils import normalize_time_param
from config.settings import settings
import structlog

logger = structlog.get_logger()

router = APIRouter()


def normalize_city_name(city: str) -> str:
    """
    Normalize city name by removing '市' suffix.

    Args:
        city: City name (may include 市)

    Returns:
        Normalized city name without 市
    """
    if not city:
        return ""
    return city.replace("市", "").strip()


def generate_dashboard_title(params: dict) -> str:
    """
    根据参数生成动态标题

    格式:
    - 站点维度: 城市+站点名称+污染物指标+溯源分析报告
    - 城市维度: 城市+污染物指标+溯源分析报告
    - 场馆维度: 城市+场馆名称（站点名称）+污染物+溯源分析报告

    Args:
        params: 包含 location, city, pollutant, scale, venue_name 的参数字典

    Returns:
        格式化的标题字符串
    """
    city = params.get("city", "")
    location = params.get("location", "")
    pollutant = params.get("pollutant", "")
    scale = params.get("scale", "station")
    venue_name = params.get("venue_name", "")

    # 城市级别
    if scale == "city":
        return f"{city}{pollutant}溯源分析报告"

    # 站点级别
    if location:
        # 场馆类站点：如果有 venue_name 字段，使用场馆格式
        if venue_name:
            # 场馆格式: 城市+场馆名称（站点名称）+污染物+报告
            return f"{city}{venue_name}（{location}）{pollutant}溯源分析报告"
        else:
            # 普通站点格式: 城市+站点名称+污染物+报告
            return f"{city}{location}{pollutant}溯源分析报告"

    # 默认标题
    return "大气污染溯源分析助手"


class ConfigResponse(BaseModel):
    """Response model for config endpoint."""

    amapPublicKey: Optional[str] = None
    features: dict = {}


@router.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": "air-pollution-traceability-api",
        "version": "1.0.0",
    }


@router.options("/config")
async def config_options():
    """Handle OPTIONS preflight request for /config endpoint."""
    return {}


@router.get("/config")
async def get_config():
    """Get frontend configuration."""
    return ConfigResponse(
        amapPublicKey=settings.amap_public_key,
        features={
            "streaming": True,
            "realtime_progress": True,
        },
    )


@router.post("/chat")
async def chat_with_context(request: ChatRequest):
    """
    Conversational chat endpoint with context memory.

    Supports multi-turn conversations with:
    - Intent classification (NEW_ANALYSIS, FOLLOW_UP_QUESTION, etc.)
    - Parameter accumulation across turns
    - Friendly clarification prompts when info is missing
    - Follow-up questions about analysis results
    - **Streaming support** for real-time analysis progress

    Flow:
    1. Get or create session
    2. Classify intent and extract parameters
    3. Route based on intent:
       - NEW_ANALYSIS: Start analysis if ready (streaming), else ask for clarification
       - FOLLOW_UP_QUESTION: Answer based on stored analysis results
       - CLARIFICATION_RESPONSE: Merge params and check if ready
       - GENERAL_CHAT: Provide general assistance
    """
    logger.info("chat_request_received", message=request.message[:100], session_id=request.session_id, stream=request.stream)

    # 统一使用流式响应（所有客户端均使用SSE流）
    return StreamingResponse(
        generate_chat_stream(request),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


async def generate_chat_stream(request: ChatRequest) -> AsyncGenerator[str, None]:
    """
    生成会话式对话的流式响应

    支持：
    - 会话记忆和参数累积
    - 意图分类
    - 实时分析进度推送（利用orchestrator.analyze_streaming）
    """
    # Get or create session
    session = conversation_manager.get_or_create_session(request.session_id)

    # DEBUG: Log session info
    print(f"\n{'='*80}")
    print(f"【Session Info】")
    print(f"{'='*80}")
    print(f"Request session_id: {request.session_id}")
    print(f"Actual session_id: {session.session_id}")
    print(f"Session state: {session.state}")
    print(f"Has analysis_result: {session.analysis_result is not None}")
    if session.analysis_result:
        print(f"Analysis result keys: {list(session.analysis_result.keys())}")
    print(f"Extracted params: {session.extracted_params}")
    print(f"History messages: {len(session.history)}")
    print(f"{'='*80}\n")

    # Add user message to history
    session.add_message("user", request.message)

    try:
        # Step 1: Send session info
        yield f"data: {json.dumps({'type': 'session', 'session_id': session.session_id}, ensure_ascii=False)}\n\n"

        # Step 2: Intent classification (removed unnecessary message)

        # Get conversation context
        context = session.get_context()

        # DEBUG: Log session state before LLM call
        logger.info("DEBUG_session_state_before_llm",
                    session_id=session.session_id,
                    has_analysis_result=bool(session.analysis_result),
                    analysis_result_keys=list(session.analysis_result.keys()) if session.analysis_result else None,
                    extracted_params=session.extracted_params,
                    context_has_analysis=context.get("has_analysis_result", False))

        # Combined parameter extraction and intent classification
        llm_result = await llm_service.extract_parameters_and_classify_intent(
            message=request.message,
            context=context
        )

        # DEBUG: Log LLM result
        logger.info("DEBUG_llm_result",
                    intent=llm_result.get("intent"),
                    can_proceed=llm_result.get("can_proceed"),
                    has_analysis_in_context=context.get("has_analysis_result", False))

        intent = llm_result.get("intent", "NEW_ANALYSIS")
        extracted_params = llm_result.get("extracted_params", {})
        missing_params = llm_result.get("missing_params", [])
        clarification_prompt = llm_result.get("clarification_prompt", "")
        can_proceed = llm_result.get("can_proceed", False)

        logger.info(
            "intent_classified",
            session_id=session.session_id,
            intent=intent,
            can_proceed=can_proceed
        )

        # Intent classification message removed - frontend will display friendly progress

        # Update session parameters
        session.update_parameters(extracted_params)

        # Normalize parameters
        if session.extracted_params.get("city"):
            session.extracted_params["city"] = normalize_city_name(session.extracted_params["city"])
        if session.extracted_params.get("start_time"):
            session.extracted_params["start_time"] = normalize_time_param(
                session.extracted_params["start_time"], is_end_time=False
            )
        if session.extracted_params.get("end_time"):
            session.extracted_params["end_time"] = normalize_time_param(
                session.extracted_params["end_time"], is_end_time=True
            )

        # Route based on intent
        if intent in ["NEW_ANALYSIS", "CLARIFICATION_RESPONSE"]:
            # DEBUG: Log readiness check
            is_ready = session.is_ready_for_analysis()
            missing = session.get_missing_parameters()

            print(f"\n{'='*80}")
            print(f"【Readiness Check】")
            print(f"{'='*80}")
            print(f"can_proceed (from LLM): {can_proceed}")
            print(f"is_ready_for_analysis(): {is_ready}")
            print(f"missing_parameters: {missing}")
            print(f"session.extracted_params: {session.extracted_params}")
            print(f"scale: {session.extracted_params.get('scale')}")
            print(f"{'='*80}\n")

            if can_proceed and is_ready:
                # All parameters ready - start streaming analysis
                session.state = "ANALYZING"

                # Confirmation message removed - frontend will show progress

                # Create query from parameters
                query = f"分析{session.extracted_params['city'] or ''}{session.extracted_params['location']}{session.extracted_params['start_time']}至{session.extracted_params['end_time']}的{session.extracted_params['pollutant']}污染情况"

                # 发送参数提取完成事件（用于前端标题更新）
                params_for_frontend = {
                    "location": session.extracted_params.get('location'),
                    "city": session.extracted_params.get('city'),
                    "pollutant": session.extracted_params.get('pollutant'),
                    "start_time": session.extracted_params.get('start_time'),
                    "end_time": session.extracted_params.get('end_time'),
                    "scale": session.extracted_params.get('scale'),
                    "venue_name": session.extracted_params.get('venue_name'),  # 添加场馆名称字段
                }
                yield f"data: {json.dumps({'type': 'step', 'step': 'extract_params', 'status': 'success', 'data': params_for_frontend, 'message': '✅ 参数提取成功'}, ensure_ascii=False)}\n\n"

                # 生成并发送动态标题
                dashboard_title = generate_dashboard_title(params_for_frontend)
                yield f"data: {json.dumps({'type': 'title', 'title': dashboard_title}, ensure_ascii=False)}\n\n"
                logger.info("dashboard_title_generated", title=dashboard_title, params=params_for_frontend)

                # Stream analysis using orchestrator
                orchestrator = AnalysisOrchestrator()
                async for event in orchestrator.analyze_streaming(query):
                    # Forward events from orchestrator to client
                    event_type = event.get('event', 'unknown')

                    if event_type == 'step':
                        yield f"data: {json.dumps({'type': 'step', 'step': event['step'], 'status': event['status'], 'message': event['message']}, ensure_ascii=False)}\n\n"

                    elif event_type == 'module_complete':
                        yield f"data: {json.dumps({'type': 'result', 'module': event['module'], 'data': event['data']}, ensure_ascii=False)}\n\n"

                    elif event_type == 'kpi':
                        yield f"data: {json.dumps({'type': 'result', 'module': 'kpi_summary', 'data': event['data']}, ensure_ascii=False)}\n\n"

                    elif event_type == 'done':
                        # DEBUG: Log what we received from orchestrator
                        print(f"\n{'='*80}")
                        print(f"【Done Event Received】")
                        print(f"{'='*80}")
                        print(f"Session ID: {session.session_id}")
                        print(f"Event has data: {bool(event.get('data'))}")
                        if event.get('data'):
                            print(f"Data keys: {list(event.get('data').keys())}")
                            print(f"Data size: {len(str(event.get('data')))} bytes")
                        print(f"Before storage - session.analysis_result is None: {session.analysis_result is None}")
                        print(f"{'='*80}\n")

                        logger.info("DEBUG_done_event_received",
                                    has_data=bool(event.get('data')),
                                    data_keys=list(event.get('data', {}).keys()) if isinstance(event.get('data'), dict) else None)

                        # Store result in session
                        session.set_analysis_result(event['data'])

                        print(f"\n{'='*80}")
                        print(f"【After Storage】")
                        print(f"{'='*80}")
                        print(f"Session ID: {session.session_id}")
                        print(f"session.analysis_result is None: {session.analysis_result is None}")
                        if session.analysis_result:
                            print(f"Stored keys: {list(session.analysis_result.keys())}")
                        print(f"Session state: {session.state}")
                        print(f"{'='*80}\n")

                        # DEBUG: Log what we're sending to client
                        response_data = {'type': 'done', 'success': True, 'data': event['data'], 'message': '✅ 分析完成！'}
                        logger.info("DEBUG_sending_to_client",
                                    response_keys=list(response_data.keys()),
                                    has_data_field=bool(response_data.get('data')))

                        yield f"data: {json.dumps(response_data, ensure_ascii=False)}\n\n"

                        # ✅ 关键修复：发送done事件后立即结束流
                        logger.info("chat_stream_ending", session_id=session.session_id, message="Stream ending after done event")
                        return  # 结束生成器，关闭SSE连接

                    elif event_type == 'error':
                        yield f"data: {json.dumps({'type': 'error', 'message': event['error']}, ensure_ascii=False)}\n\n"
                        session.state = "INITIAL"
                        return

            else:
                # Missing parameters - ask for clarification
                session.state = "COLLECTING_PARAMS"

                # Generate scale-aware default message
                scale = session.extracted_params.get("scale", "station")
                if scale == "city":
                    default_message = "请提供完整的分析信息（城市名称、污染物类型、时间范围）。"
                else:
                    default_message = "请提供完整的分析信息（站点名称、污染物类型、时间范围）。"

                response_message = clarification_prompt or default_message

                session.add_message("ai", response_message)

                yield f"data: {json.dumps({'type': 'message', 'message': response_message}, ensure_ascii=False)}\n\n"
                yield f"data: {json.dumps({'type': 'done', 'success': False, 'missing_params': missing_params}, ensure_ascii=False)}\n\n"

        elif intent == "FOLLOW_UP_QUESTION":
            if not session.analysis_result:
                response_message = "您还没有进行任何分析。请先提供站点、污染物和时间信息以开始分析。"
                session.add_message("ai", response_message)
                yield f"data: {json.dumps({'type': 'message', 'message': response_message}, ensure_ascii=False)}\n\n"
                yield f"data: {json.dumps({'type': 'done', 'success': True}, ensure_ascii=False)}\n\n"
            else:
                # Use LLM to answer based on analysis result
                yield f"data: {json.dumps({'type': 'step', 'step': 'answering_question', 'status': 'start', 'message': '正在基于分析结果回答您的问题...'}, ensure_ascii=False)}\n\n"

                response_message = await llm_service.answer_followup_question(
                    question=request.message,
                    analysis_result=session.analysis_result,
                    context=context
                )

                session.add_message("ai", response_message)
                yield f"data: {json.dumps({'type': 'message', 'message': response_message}, ensure_ascii=False)}\n\n"
                yield f"data: {json.dumps({'type': 'done', 'success': True}, ensure_ascii=False)}\n\n"

        else:
            # 未知意图，默认当做FOLLOW_UP_QUESTION处理
            logger.warning("unknown_intent", intent=intent, message=request.message[:50])
            if session.analysis_result:
                response_message = await llm_service.answer_followup_question(
                    question=request.message,
                    analysis_result=session.analysis_result,
                    context=context
                )
            else:
                response_message = "抱歉，我不太理解您的意思。请告诉我要分析的站点名称、污染物类型和时间范围。"

            session.add_message("ai", response_message)
            yield f"data: {json.dumps({'type': 'message', 'message': response_message}, ensure_ascii=False)}\n\n"
            yield f"data: {json.dumps({'type': 'done', 'success': True}, ensure_ascii=False)}\n\n"

    except Exception as e:
        logger.error("chat_streaming_failed", session_id=session.session_id, error=str(e), exc_info=True)
        yield f"data: {json.dumps({'type': 'error', 'message': f'处理失败: {str(e)}'}, ensure_ascii=False)}\n\n"




@router.options("/chat")
async def chat_options():
    """Handle OPTIONS preflight request for /chat endpoint."""
    return {}
