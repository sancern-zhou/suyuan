"""知识问答模式首轮固定预取：检索证据包直接注入 agent 初始上下文。

设计意图（区别于 agent 自主调 knowledge_qa_workflow）：
用户输入先经过固定检索（本地召回+重排+分块+元数据 + 并发网页摘要），
证据包作为 knowledge_evidence 系统上下文层注入，agent 第一轮即可读证据作答；
只有证据不足时才用工具补查，省掉「规划检索」的 1-2 轮 LLM 往返。

仅在会话首轮执行；追问轮由 agent 按需自行补检索。
"""
from __future__ import annotations

from typing import List, Optional

import structlog

logger = structlog.get_logger()

# 每个命中分块在证据包中的正文字符上限（约 5 块，预算可控）
_MAX_CHUNK_CHARS = 900
_MAX_WEB_CHARS = 1600


def _format_document_read_targets(targets: List[dict]) -> str:
    if not targets:
        return ""
    lines = ["", "### document_read_targets（证据不足时按此精读）"]
    for t in targets[:4]:
        lines.append(
            f"- {t.get('document_name', '')}（knowledge_base_id={t.get('knowledge_base_id')}，"
            f"document_id={t.get('document_id')}），命中块 {t.get('matched_chunk_indices')}；"
            "用 knowledge_document_reader 读相邻块，需全文时 all_chunks"
        )
    return "\n".join(lines)


async def build_first_turn_evidence(
    query: str,
    user_id: Optional[str] = None,
    knowledge_base_ids: Optional[list] = None,
) -> Optional[str]:
    """执行首轮固定检索并格式化为证据包文本；无可用电证证据时返回 None。"""
    from app.api.knowledge_qa import search_knowledge_bases
    from app.tools.workflow.knowledge_qa_workflow import _build_document_read_targets

    results = await search_knowledge_bases(
        query=query,
        user_id=user_id,
        knowledge_base_ids=list(knowledge_base_ids) if knowledge_base_ids else None,
        top_k=5,
        use_reranker="always",
        use_hyde=False,
    )
    local_hits = [r for r in results if r.get("document_id")]
    web = None
    for item in results:
        candidate = (item.get("retrieval_metadata") or {}).get("web_evidence")
        if candidate:
            web = candidate
            break

    web_usable = bool(web and web.get("status") == "ready" and web.get("count"))
    if not local_hits and not web_usable:
        logger.info("knowledge_evidence_empty", query=query[:60])
        return None

    parts: List[str] = [
        "<knowledge_evidence>",
        "## 首轮证据包（系统已在作答前固定预取：本地召回+重排+分块+并发网页摘要一次完成）",
        "- 使用规则：先判断证据是否足以支撑回答——足以支撑时直接回答，不检索、不读全文。",
        "- 证据不足（覆盖缺失、结果冲突、需要跨章节总结或用户明确要求全文）时才继续行动："
        "换关键词调用 knowledge_qa_workflow 补检索，或按 document_read_targets 用 "
        "knowledge_document_reader 精读。是否继续检索由证据充分性决定，不是固定步骤。",
        "",
    ]

    if local_hits:
        parts.append("### 本地知识库命中（按相关度排序）")
        for idx, hit in enumerate(local_hits, 1):
            kb_name = hit.get("knowledge_base_name") or "未知知识库"
            doc_name = hit.get("document_name") or "未知文档"
            score = hit.get("rerank_score")
            score_text = f"{score:.3f}" if isinstance(score, (int, float)) else str(score)
            content = (hit.get("content") or "").strip()[:_MAX_CHUNK_CHARS]
            parts.append(
                f"\n【证据 {idx}】[来源: {kb_name} - {doc_name}] "
                f"(chunk_index={hit.get('chunk_index')}, 相关度={score_text})\n{content}"
            )
        targets_text = _format_document_read_targets(_build_document_read_targets(local_hits))
        if targets_text:
            parts.append(targets_text)

    if web_usable:
        web_text = (web.get("results_text") or "")[:_MAX_WEB_CHARS]
        parts.append(
            "\n### 网页检索补充（仅作线索，不得覆盖本地知识库结论）\n"
            f"来源 {web.get('provider')}，{web.get('count')} 条：\n{web_text}"
        )

    parts.append("</knowledge_evidence>")
    evidence = "\n".join(parts)
    logger.info(
        "knowledge_evidence_prefetch_done",
        query=query[:60],
        local_hits=len(local_hits),
        web_status=(web or {}).get("status"),
        chars=len(evidence),
    )
    return evidence
