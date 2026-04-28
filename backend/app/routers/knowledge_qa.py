"""
知识问答专家路由（单专家简化版）

专门用于知识库问答场景：
1. 问题拆解（可选）
2. 向量检索召回
3. LLM生成回答
4. 流式返回结果
5. 连续对话历史管理

不使用ReAct流程，直接RAG + LLM
"""

import json
import structlog
import asyncio
import time
from typing import Optional, List
from fastapi import APIRouter, HTTPException, Depends, Header
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.knowledge_base.conversation_store import ConversationStore, get_conversation_store
from app.knowledge_base.models import ConversationSessionStatus

logger = structlog.get_logger()
router = APIRouter(prefix="/api/knowledge-qa", tags=["Knowledge QA"])


# ========================================
# Request/Response Models
# ========================================

class KnowledgeQARequest(BaseModel):
    """知识问答请求"""
    query: str = Field(..., description="用户问题")
    session_id: Optional[str] = Field(None, description="会话ID（可选，用于上下文连贯）")
    knowledge_base_ids: Optional[List[str]] = Field(
        default=None,
        description="指定知识库ID列表（可选，默认使用用户所有可访问的知识库）"
    )
    top_k: int = Field(default=3, ge=1, le=20, description="检索返回的最大结果数")
    score_threshold: Optional[float] = Field(
        default=None,
        ge=0,
        le=1,
        description="检索结果相似度阈值（可选）"
    )
    use_reranker: bool = Field(default=False, description="是否使用Reranker精排（默认关闭以提高速度）")


class ConversationHistoryResponse(BaseModel):
    """对话历史响应"""
    session_id: str
    title: str
    status: str
    total_turns: int
    turns: List[dict]
    created_at: str
    updated_at: str


class SessionListResponse(BaseModel):
    """会话列表响应"""
    sessions: List[dict]
    total: int


class KnowledgeQAResponse(BaseModel):
    """知识问答响应（非流式）"""
    answer: str = Field(..., description="LLM生成的回答")
    session_id: str = Field(..., description="会话ID")
    sources: List[dict] = Field(default=[], description="检索到的知识源")
    elapsed_ms: int = Field(..., description="处理耗时(毫秒)")


# ========================================
# HyDE 假设答案生成函数
# ========================================

async def generate_hypothetical_answer(query: str) -> str:
    """
    使用LLM生成假设答案（HyDE核心步骤）

    HyDE原理：先让LLM生成一个"假设的完美回答"，用这个假设答案去检索
    能获得更好的语义匹配，因为假设答案包含了更丰富的语义信息

    Args:
        query: 用户问题

    Returns:
        假设的完美回答
    """
    from app.services.llm_service import llm_service

    hyde_prompt = f"""你是一位大气环境监测领域的专家。请根据以下关于大气环境监测业务的问题，生成用于向量检索的关键词组。

问题：{query}

要求：
1. 第一组：对原始问题的完整概述（一个完整的短语或句子，保留问题的核心语义和完整信息，不要拆分）
2. 第二组：提取3-4个核心关键词/关键概念（用逗号分隔）

输出格式（直接输出关键词，不要有前缀说明，每组用换行分隔）："""

    try:
        hypothetical_answer = await llm_service.chat(
            messages=[{"role": "user", "content": hyde_prompt}],
            temperature=0.3,  # 低温度，关键词更稳定
            max_tokens=256  # 增加token限制以容纳3组关键词
        )
        logger.info(
            "hyde_generated",
            query=query[:100],
            hyde_keywords=hypothetical_answer.strip()[:200]  # 记录关键词组内容
        )
        return hypothetical_answer
    except Exception as e:
        logger.warning("hyde_generation_failed", error=str(e), query=query[:50])
        # 降级：返回原始问题
        return query


# ========================================
# 知识库检索函数（修复版 - 独立会话 + 超时控制）
# ========================================

async def search_knowledge_bases(
    query: str,
    user_id: Optional[str] = None,
    knowledge_base_ids: Optional[List[str]] = None,
    top_k: int = 5,
    score_threshold: Optional[float] = None,
    use_reranker: bool = True,
    use_hyde: bool = False  # 是否使用HyDE
) -> List[dict]:
    """检索知识库并返回相关文档片段（使用独立数据库会话，避免超时）"""
    from app.db.database import async_session
    from sqlalchemy import select
    from app.knowledge_base.models import Document, KnowledgeBase as KBModel, KnowledgeBaseStatus
    from app.knowledge_base.service import KnowledgeBaseService

    # 使用独立会话，检索完成后立即关闭
    async with async_session() as db:
        service = KnowledgeBaseService(db=db)

        # 如果没有指定知识库，自动使用所有可用的知识库
        kb_ids = knowledge_base_ids or []
        if not kb_ids:
            try:
                all_kbs = await service.list_knowledge_bases(
                    user_id=user_id,
                    include_public=True,
                    status=KnowledgeBaseStatus.ACTIVE
                )
                kb_ids = [kb.id for kb in all_kbs]
                logger.info(
                    "auto_selected_all_knowledge_bases",
                    query=query[:50],
                    kb_count=len(kb_ids),
                    kb_ids=kb_ids[:5]  # 只记录前5个
                )
            except Exception as e:
                logger.error("failed_to_list_knowledge_bases", error=str(e))
                return []

            # 如果仍然没有知识库，返回空结果
            if not kb_ids:
                logger.info("no_available_knowledge_bases", query=query[:50])
                return []

        # HyDE优化：当开启精准检索时，生成假设答案用于检索
        search_query = query
        hyde_used = False
        if use_hyde:
            hyde_start = time.time()
            hypothetical_answer = await generate_hypothetical_answer(query)
            search_query = hypothetical_answer
            hyde_elapsed = (time.time() - hyde_start) * 1000
            hyde_used = True
            logger.info(
                "hyde_applied",
                original_query=query[:100],
                hyde_keywords=search_query.strip()[:200],  # 记录用于检索的关键词
                hyde_elapsed_ms=round(hyde_elapsed, 2)
            )

        try:
            results = await asyncio.wait_for(
                service.search(
                    query=search_query,  # 使用原始问题或假设答案
                    user_id=user_id,
                    knowledge_base_ids=kb_ids,
                    top_k=top_k,
                    score_threshold=score_threshold,
                    filters=None,
                    use_reranker=use_reranker
                ),
                timeout=30.0  # 检索超时30秒
            )

            # 格式化结果，添加文档信息
            doc_ids = [r.get("document_id") for r in results if r.get("document_id")]
            docs_map = {}
            if doc_ids:
                doc_result = await db.execute(
                    select(Document).where(Document.id.in_(doc_ids))
                )
                docs_map = {doc.id: doc for doc in doc_result.scalars().all()}

            formatted_results = []
            for r in results:
                doc_id = r.get("document_id")
                kb_info = r.get("knowledge_base", {})
                doc = docs_map.get(doc_id) if doc_id else None

                formatted_results.append({
                    "content": r.get("content", ""),
                    "score": r.get("score", 0),
                    "document_id": doc_id,
                    "document_name": doc.filename if doc else "",
                    "knowledge_base_id": kb_info.get("id"),
                    "knowledge_base_name": kb_info.get("name", ""),
                    "chunk_index": r.get("chunk_index"),
                    "metadata": r.get("metadata", {}),
                    "hyde_used": hyde_used  # 标记是否使用HyDE
                })

            return formatted_results

        except asyncio.TimeoutError:
            logger.warning("knowledge_search_timeout", query=query[:50])
            return []
        except Exception as e:
            logger.error("knowledge_search_failed", error=str(e))
            return []


# ========================================
# 构建RAG Prompt（支持连续对话）
# ========================================

def build_rag_prompt(
    query: str,
    contexts: List[dict],
    conversation_history: str = ""
) -> str:
    """
    构建RAG增强的Prompt

    Args:
        query: 当前用户问题
        contexts: 检索到的参考资料
        conversation_history: 历史对话文本（可选，LLM 会自动理解指代和上下文）
    """
    context_texts = []
    for i, ctx in enumerate(contexts, 1):
        source_info = ""
        if ctx.get("knowledge_base_name"):
            source_info = f"[来源: {ctx['knowledge_base_name']}"
            if ctx.get("document_name"):
                source_info += f" - {ctx['document_name']}"
            source_info += "]"
        elif ctx.get("document_name"):
            source_info = f"[来源: {ctx['document_name']}]"

        context_texts.append(f"""【参考资料 {i}】{source_info}
{ctx.get('content', '')}""")

    context_str = "\n\n".join(context_texts)

    # 构建Prompt
    prompt_parts = []

    # 系统提示
    prompt_parts.append("你是一个专业的知识问答助手，负责回答用户关于大气污染、数据分析等问题。")

    # 连续对话说明
    if conversation_history:
        prompt_parts.append(f"""## 重要：当前是连续对话

=== 对话历史 ===
{conversation_history}
=== 历史结束 ===

**你必须遵守的规则**：
1. 这是连续对话，用户当前问题可能是对上文某个话题的追问
2. 首先根据对话历史理解用户的真实意图，特别是"它/这个/最X/怎么做"等指代
3. **检索到的参考资料仅作为专业知识参考**，如果历史中已有相关信息，优先使用历史的上下文回答
4. 不要重复回答与历史问题相同的内容，追问直接给出答案""")

    # 用户问题
    prompt_parts.append(f"""## 当前问题
{query}""")

    # 参考资料
    if contexts:
        prompt_parts.append(f"""## 参考资料
以下是检索到的相关参考资料（按相关度排序）：

{context_str}""")
        prompt_parts.append("""## 回答要求
1. 优先使用参考资料中的信息进行回答
2. 如果是追问，直接回答问题，不需要重复背景信息
3. 保持回答简洁、准确、专业
4. 如果涉及多个来源的信息，请综合分析后给出答案

## 开始回答""")
    else:
        # 无参考资料时，直接让LLM基于自身知识回答
        prompt_parts.append("""## 回答要求
请直接基于你自己的知识回答用户的问题。
如果问题超出你的知识范围，诚实地说明你不知道，但可以给出合理的推测或建议进一步查询。

## 开始回答""")

    return "\n\n".join(prompt_parts)


# ========================================
# 流式生成回答（支持连续对话）- 真正流式版本
# ========================================

async def generate_streaming_answer(
    query: str,
    contexts: List[dict],
    session_id: str,
    conversation_store: ConversationStore,
    user_id: Optional[str] = None
):
    """
    流式生成回答（支持连续对话历史）- 真正流式输出

    Args:
        query: 用户问题
        contexts: 检索到的参考资料
        session_id: 会话ID
        conversation_store: 对话存储服务
        user_id: 用户ID
    """
    from app.services.llm_service import llm_service

    # 获取对话历史
    turns = await conversation_store.get_recent_turns(session_id, limit=10)
    conversation_history = conversation_store.build_history_for_rag(turns)

    # 构建Prompt（LLM 自己会理解历史和指代）
    prompt = build_rag_prompt(
        query=query,
        contexts=contexts,
        conversation_history=conversation_history
    )

    try:
        # 发送开始事件
        yield f"data: {json.dumps({'type': 'start', 'data': {'session_id': session_id}}, ensure_ascii=False)}\n\n"

        # 使用真正的流式调用，直接yield每个chunk
        import httpx

        url, headers = llm_service._get_request_config()
        payload = {
            "model": llm_service.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.7,
            "stream": True
        }

        # 千问3特殊处理：禁用思考模式
        if llm_service.provider == "qwen":
            payload["enable_thinking"] = False

        full_answer = ""

        async with httpx.AsyncClient(timeout=600.0) as client:
            async with client.stream("POST", url, headers=headers, json=payload) as response:
                response.raise_for_status()

                async for line in response.aiter_lines():
                    if not line:
                        continue

                    # 处理SSE格式
                    if line.startswith("data: "):
                        data_str = line[len("data: "):].strip()
                        if data_str == "[DONE]":
                            break

                        try:
                            chunk = json.loads(data_str)
                            choices = chunk.get("choices", [])
                            if choices:
                                delta = choices[0].get("delta", {}) or choices[0].get("message", {})
                                content = delta.get("content") or ""
                                if content:
                                    full_answer += content
                                    yield f"data: {json.dumps({'type': 'answer_delta', 'data': {'delta': content, 'session_id': session_id}}, ensure_ascii=False)}\n\n"
                        except Exception:
                            continue

        # 发送完成事件（包含sources信息）
        complete_data = {
            'type': 'complete',
            'data': {
                'session_id': session_id,
                'answer': full_answer,
                'sources': contexts,
                'sources_count': len(contexts),
                'timestamp': datetime.now().isoformat()
            }
        }
        yield f"data: {json.dumps(complete_data, ensure_ascii=False, default=str)}\n\n"

        # 保存对话轮次（用户问题）
        await conversation_store.add_turn(
            session_id=session_id,
            role="user",
            content=query,
            query_metadata={"knowledge_base_ids": None, "top_k": len(contexts) if contexts else 0}
        )

        # 保存对话轮次（AI回答）
        await conversation_store.add_turn(
            session_id=session_id,
            role="assistant",
            content=full_answer,
            sources=contexts,
            sources_count=len(contexts)
        )

        logger.info(
            "conversation_turns_saved",
            session_id=session_id,
            user_query_len=len(query),
            answer_len=len(full_answer),
            sources_count=len(contexts)
        )

    except Exception as e:
        logger.error("streaming_answer_failed", error=str(e))
        error_event = {
            'type': 'fatal_error',
            'data': {
                'error': str(e),
                'session_id': session_id
            }
        }
        yield f"data: {json.dumps(error_event, ensure_ascii=False)}\n\n"


# ========================================
# API Endpoints（简化版）
# ========================================

@router.post("/stream")
async def knowledge_qa_stream(
    request: KnowledgeQARequest,
    db: AsyncSession = Depends(get_db)
):
    """
    知识问答流式接口（推荐使用）

    流程：
    1. 接收用户问题
    2. 获取或创建会话
    3. 检索知识库获取相关文档（RAG）
    4. 将问题+检索结果+历史发送给LLM
    5. 流式返回LLM回答
    6. 保存对话轮次

    **事件类型**:
    - `start`: 问答开始
    - `answer_delta`: 回答内容增量
    - `complete`: 问答完成（包含sources）
    - `fatal_error`: 致命错误
    """
    start_time = time.time()

    # 获取用户ID（从请求头）
    user_id = None  # 实际应从请求头获取，如：x-user-id

    # 获取或创建会话
    conversation_store = await get_conversation_store(db)
    session_id, existing_turns, is_new = await conversation_store.get_or_create_session(
        session_id=request.session_id,
        user_id=user_id,
        knowledge_base_ids=request.knowledge_base_ids,
        first_query=request.query
    )

    logger.info(
        "knowledge_qa_request",
        query=request.query[:100],
        session_id=session_id,
        is_new_session=is_new,
        existing_turns=len(existing_turns),
        knowledge_base_ids=request.knowledge_base_ids,
        top_k=request.top_k
    )

    try:
        # Step 1: HyDE + 检索知识库（使用独立会话，超时控制）
        # HyDE始终启用，精准检索控制是否重排序
        search_start = time.time()

        contexts = await search_knowledge_bases(
            query=request.query,
            user_id=user_id,
            knowledge_base_ids=request.knowledge_base_ids,
            top_k=request.top_k,
            score_threshold=request.score_threshold,
            use_reranker=request.use_reranker,
            use_hyde=True  # 始终启用HyDE
        )

        search_elapsed = (time.time() - search_start) * 1000
        logger.info(
            "knowledge_search_completed",
            results_count=len(contexts),
            elapsed_ms=round(search_elapsed, 2)
        )

        # Step 2: 流式生成回答（传入conversation_store）
        # 如果没有检索到结果，仍让LLM基于自身知识回答
        async def event_generator():
            try:
                async for event in generate_streaming_answer(
                    query=request.query,
                    contexts=contexts,
                    session_id=session_id,
                    conversation_store=conversation_store,
                    user_id=user_id
                ):
                    yield event
            except Exception as e:
                logger.error("event_generation_failed", error=str(e))
                error_event = {
                    'type': 'fatal_error',
                    'data': {
                        'error': str(e),
                        'session_id': session_id
                    }
                }
                yield f"data: {json.dumps(error_event, ensure_ascii=False)}\n\n"

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
        logger.error("knowledge_qa_failed", error=str(e), exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"知识问答失败: {str(e)}"
        )


@router.post("", response_model=KnowledgeQAResponse)
async def knowledge_qa_non_stream(request: KnowledgeQARequest):
    """
    知识问答非流式接口（简化版）

    流程：
    1. 检索知识库
    2. LLM生成回答
    3. 返回完整结果
    """
    start_time = time.time()

    # 获取用户ID
    user_id = None

    # 生成会话ID
    session_id = request.session_id or f"kqa_{int(time.time() * 1000)}"

    try:
        # 检索知识库（HyDE始终启用，精准检索控制是否重排序）
        contexts = await search_knowledge_bases(
            query=request.query,
            user_id=user_id,
            knowledge_base_ids=request.knowledge_base_ids,
            top_k=request.top_k,
            score_threshold=request.score_threshold,
            use_reranker=request.use_reranker,
            use_hyde=True  # 始终启用HyDE
        )

        # 构建Prompt
        prompt = build_rag_prompt(request.query, contexts)

        # 调用LLM生成回答
        from app.services.llm_service import llm_service
        answer = await llm_service.chat(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
            max_tokens=4096
        )

        elapsed_ms = round((time.time() - start_time) * 1000, 2)

        # 格式化来源
        sources = []
        for ctx in contexts:
            sources.append({
                "content": ctx.get("content", "")[:200] + "...",
                "source": ctx.get("knowledge_base_name", "") + "/" + ctx.get("document_name", ""),
                "score": ctx.get("score", 0)
            })

        return KnowledgeQAResponse(
            answer=answer or "抱歉，我没有找到相关的信息来回答您的问题。",
            session_id=session_id,
            sources=sources,
            elapsed_ms=elapsed_ms
        )

    except Exception as e:
        logger.error("knowledge_qa_non_stream_failed", error=str(e))
        raise HTTPException(
            status_code=500,
            detail=f"知识问答失败: {str(e)}"
        )


@router.get("/health")
async def knowledge_qa_health():
    """健康检查"""
    return {
        "status": "healthy",
        "service": "knowledge-qa-expert",
        "description": "知识问答专家服务 - 基于RAG的智能问答系统"
    }


# ========================================
# 会话管理 API
# ========================================

@router.get("/history/{session_id}")
async def get_conversation_history(
    session_id: str,
    db: AsyncSession = Depends(get_db)
):
    """
    获取对话历史

    返回会话的所有对话轮次
    """
    conversation_store = await get_conversation_store(db)
    session = await conversation_store.get_session(session_id)

    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")

    turns = await conversation_store.get_all_turns(session_id)

    return {
        "session_id": session.id,
        "title": session.title,
        "status": session.status.value,
        "total_turns": session.total_turns,
        "turns": [
            {
                "turn_index": turn.turn_index,
                "role": turn.role,
                "content": turn.content,
                "sources": turn.sources,
                "sources_count": turn.sources_count,
                "created_at": turn.created_at.isoformat()
            }
            for turn in turns
        ],
        "created_at": session.created_at.isoformat(),
        "updated_at": session.updated_at.isoformat()
    }


@router.get("/history/{session_id}/recent")
async def get_recent_turns(
    session_id: str,
    limit: int = 10,
    db: AsyncSession = Depends(get_db)
):
    """
    获取最近的对话轮次

    Args:
        session_id: 会话ID
        limit: 返回数量（默认10）
    """
    conversation_store = await get_conversation_store(db)
    turns = await conversation_store.get_recent_turns(session_id, limit=limit)

    return {
        "session_id": session_id,
        "turns": [
            {
                "turn_index": turn.turn_index,
                "role": turn.role,
                "content": turn.content,
                "sources": turn.sources,
                "sources_count": turn.sources_count,
                "created_at": turn.created_at.isoformat()
            }
            for turn in turns
        ]
    }


@router.delete("/history/{session_id}")
async def delete_conversation_session(
    session_id: str,
    db: AsyncSession = Depends(get_db)
):
    """
    删除会话

    级联删除所有对话轮次
    """
    conversation_store = await get_conversation_store(db)
    success = await conversation_store.delete_session(session_id)

    if not success:
        raise HTTPException(status_code=404, detail="会话不存在")

    return {"message": "会话已删除", "session_id": session_id}


@router.post("/history/{session_id}/archive")
async def archive_conversation_session(
    session_id: str,
    db: AsyncSession = Depends(get_db)
):
    """
    归档会话
    """
    conversation_store = await get_conversation_store(db)
    success = await conversation_store.archive_session(session_id)

    if not success:
        raise HTTPException(status_code=404, detail="会话不存在")

    return {"message": "会话已归档", "session_id": session_id}


@router.get("/history/list")
async def list_user_sessions(
    status: Optional[str] = None,
    limit: int = 20,
    offset: int = 0,
    user_id: Optional[str] = None,
    db: AsyncSession = Depends(get_db)
):
    """
    列出用户的会话

    Args:
        status: 状态过滤 (active/archived/expired)
        limit: 返回数量
        offset: 偏移量
        user_id: 用户ID（从请求头获取）
    """
    # 从请求头获取用户ID
    user_id = user_id or None

    conversation_store = await get_conversation_store(db)

    # 解析状态
    status_filter = None
    if status:
        try:
            status_filter = ConversationSessionStatus(status)
        except ValueError:
            raise HTTPException(status_code=400, detail="无效的状态值")

    sessions = await conversation_store.list_user_sessions(
        user_id=user_id,
        status=status_filter,
        limit=limit,
        offset=offset
    )

    return {
        "sessions": [
            {
                "session_id": s.id,
                "title": s.title,
                "status": s.status.value,
                "total_turns": s.total_turns,
                "last_query": s.last_query,
                "created_at": s.created_at.isoformat(),
                "updated_at": s.updated_at.isoformat()
            }
            for s in sessions
        ],
        "total": len(sessions)
    }
