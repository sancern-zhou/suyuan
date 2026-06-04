"""
Active Memory Retriever - 最小版

基于关键词的分层记忆召回，不依赖向量库。

召回策略：
1. daily notes 相关：在 memory/YYYY-MM-DD.md 中搜索日志型上下文
2. 预算控制：限制召回的 token 数量
"""

import os
import re
from typing import List, Dict, Optional, Any
import structlog

logger = structlog.get_logger(__name__)


class ActiveMemoryRetriever:
    """
    最小版历史会话召回器

    使用关键词匹配从 memory/*.md 中召回历史会话片段。
    MEMORY.md 不在这里召回；社交模式会完整注入用户隔离的长期记忆。
    """

    def __init__(
        self,
        max_tokens: Optional[int] = None,
        max_facts: int = 20,
        keyword_weight: float = 1.0,
        recency_weight: float = 0.5
    ):
        """
        初始化召回器

        Args:
            max_tokens: 最大召回 token 数（默认从环境变量读取，默认 2000）
            max_facts: 最多召回的事实数量（默认 20）
            keyword_weight: 关键词匹配权重（默认 1.0）
            recency_weight: 时间衰减权重（默认 0.5）
        """
        if max_tokens is None:
            max_tokens = int(os.getenv("ACTIVE_MEMORY_MAX_TOKENS", "2000"))

        self.max_tokens = max_tokens
        self.max_facts = max_facts
        self.keyword_weight = keyword_weight
        self.recency_weight = recency_weight

        logger.info(
            "active_memory_retriever_initialized",
            max_tokens=max_tokens,
            max_facts=max_facts,
            keyword_weight=keyword_weight,
            recency_weight=recency_weight
        )

    def retrieve(
        self,
        memory_store: Any,
        query: str,
        recent_messages: List[Dict] = []
    ) -> str:
        """
        从记忆存储中召回历史会话片段

        Args:
            memory_store: ImprovedMemoryStore 实例
            query: 用户查询
            recent_messages: 最近的对话历史（可选）

        Returns:
            召回的历史会话内容（格式化的 Markdown）
        """
        try:
            # 提取查询关键词
            keywords = self._extract_keywords(query, recent_messages)

            if not keywords:
                # 如果没有提取到关键词，返回空（不注入任何记忆）
                logger.debug("no_keywords_extracted", query=query)
                return ""

            # 只搜索 daily notes。MEMORY.md 由社交模式完整注入。
            relevant_facts = self._search_daily_notes(memory_store, keywords)

            if not relevant_facts:
                logger.debug("no_relevant_facts_found", keywords=keywords)
                return ""

            if self.max_tokens <= self._estimate_tokens(self._history_context_header()):
                logger.debug(
                    "history_context_budget_too_small",
                    max_tokens=self.max_tokens,
                )
                return ""

            # 按 token 预算限制召回内容
            limited_facts = self._limit_by_tokens(
                relevant_facts,
                self.max_tokens
            )

            # 格式化为 Markdown
            result = self._format_memory_context(limited_facts)

            logger.info(
                "historical_conversation_memory_retrieved",
                keywords=keywords,
                total_facts=len(relevant_facts),
                retrieved_facts=len(limited_facts),
                estimated_tokens=self._estimate_tokens(result)
            )

            return result

        except Exception as e:
            logger.error(
                "failed_to_retrieve_historical_conversation_memory",
                error=str(e),
                exc_info=True
            )
            return ""

    def _extract_keywords(
        self,
        query: str,
        recent_messages: List[Dict] = []
    ) -> List[str]:
        """
        从查询和历史消息中提取关键词

        策略：
        1. 提取查询中的中文词汇（2-4字）
        2. 提取查询中的英文单词
        3. 从最近3条消息中补充关键词
        4. 去重并过滤停用词
        """
        keywords = []
        seen_keywords = set()

        def add_keyword(value: str) -> None:
            if value and value not in seen_keywords:
                keywords.append(value)
                seen_keywords.add(value)

        # 英文单词和污染物指标优先保留，避免被中文 ngram 截断。
        english_pattern = re.compile(r'\b[a-zA-Z]{3,}\b')
        english_words = english_pattern.findall(query)
        for word in english_words:
            add_keyword(word.lower())

        # 污染物/指标常见写法，如 PM2.5、O3、NO2
        metric_pattern = re.compile(r'\b[a-zA-Z]{1,4}\d(?:\.\d)?\b')
        metric_words = metric_pattern.findall(query)
        for word in metric_words:
            add_keyword(word.upper())

        # 简单的中文分词（按连续中文片段 + 2-4 字滑窗扩展）
        chinese_pattern = re.compile(r'[\u4e00-\u9fa5]{2,4}')
        chinese_words = chinese_pattern.findall(query)
        for word in chinese_words:
            add_keyword(word)
        for word in self._expand_chinese_keywords(chinese_words):
            add_keyword(word)

        # 从历史消息中补充（最多3条）
        for msg in recent_messages[-3:]:
            content = msg.get("content", "")
            if isinstance(content, str):
                chinese_words = chinese_pattern.findall(content)
                for word in chinese_words[:5]:
                    add_keyword(word)
                for word in self._expand_chinese_keywords(chinese_words[:5]):
                    add_keyword(word)

        # 简单停用词过滤
        stopwords = {
            "的", "了", "是", "在", "我", "你", "他", "她", "它",
            "这", "那", "有", "没有", "不", "也", "都", "就", "还",
            "the", "a", "an", "is", "are", "was", "were", "be",
            "have", "has", "had", "do", "does", "did", "will", "would"
        }
        keywords = [k for k in keywords if k not in stopwords and len(k) >= 2]

        return list(keywords)[:10]  # 最多10个关键词

    def _expand_chinese_keywords(self, words: List[str]) -> List[str]:
        """把较长中文片段展开成短 ngram，提升关键词召回率。"""
        expanded = []
        for word in words:
            if len(word) <= 2:
                continue
            for width in (4, 3, 2):
                if len(word) <= width:
                    continue
                for index in range(0, len(word) - width + 1):
                    expanded.append(word[index:index + width])
        return expanded

    def _search_relevant_facts(
        self,
        memory_content: str,
        keywords: List[str],
        source: str = "MEMORY.md"
    ) -> List[Dict]:
        """
        在 MEMORY.md 中搜索包含关键词的事实

        Returns:
            事实列表，每个事实包含 {content, score, line_number}
        """
        facts = []
        lines = memory_content.split('\n')

        for line_num, line in enumerate(lines, 1):
            line = line.strip()
            if not line or line.startswith('#'):
                continue

            # 计算匹配分数
            score = 0.0
            for keyword in keywords:
                if keyword.lower() in line.lower():
                    score += self.keyword_weight

            if score > 0:
                facts.append({
                    "content": line,
                    "score": score,
                    "line_number": line_num,
                    "source": source
                })

        # 按分数排序（降序）
        facts.sort(key=lambda x: x["score"], reverse=True)

        return facts[:self.max_facts]

    def _search_daily_notes(
        self,
        memory_store: Any,
        keywords: List[str]
    ) -> List[Dict]:
        """在 memory/YYYY-MM-DD.md 中搜索相关上下文。"""
        if not hasattr(memory_store, "search_daily_notes"):
            return []

        facts = []
        seen = set()

        for keyword in keywords:
            try:
                results = memory_store.search_daily_notes(keyword, limit=3)
            except Exception as e:
                logger.warning(
                    "daily_note_search_failed",
                    keyword=keyword,
                    error=str(e)
                )
                continue

            for result in results:
                context = str(result.get("context") or result.get("match") or "").strip()
                if not context or context in seen:
                    continue

                seen.add(context)
                score = 0.0
                lowered = context.lower()
                for candidate in keywords:
                    if candidate.lower() in lowered:
                        score += self.keyword_weight

                facts.append({
                    "content": self._compact_context(context),
                    "score": score + self.recency_weight,
                    "line_number": result.get("line_number", 0),
                    "source": result.get("source", "memory/*.md")
                })

                if len(facts) >= self.max_facts:
                    return facts

        facts.sort(key=lambda x: x["score"], reverse=True)
        return facts[:self.max_facts]

    def _compact_context(self, context: str) -> str:
        """压缩 daily note 多行上下文，适合注入 prompt。"""
        lines = [line.strip() for line in context.splitlines() if line.strip()]
        return " / ".join(lines)

    def _limit_by_tokens(
        self,
        facts: List[Dict],
        max_tokens: int
    ) -> List[Dict]:
        """
        按 token 预算限制召回内容

        简单估算：1个中文字符 ≈ 1.5 tokens，1个英文单词 ≈ 1 token
        """
        limited_facts = []
        current_tokens = 0

        for fact in facts:
            fact_tokens = self._estimate_tokens(fact["content"])

            if current_tokens + fact_tokens <= max_tokens:
                limited_facts.append(fact)
                current_tokens += fact_tokens
            else:
                break

        return limited_facts

    def _estimate_tokens(self, text: str) -> int:
        """
        估算文本的 token 数量

        简单策略：
        - 中文字符 × 1.5
        - 英文字母 / 4
        - 标点符号 × 0.5
        """
        chinese_chars = len(re.findall(r'[\u4e00-\u9fa5]', text))
        english_chars = len(re.findall(r'[a-zA-Z]', text))
        punctuation = len(re.findall(r'[^\w\s]', text))

        return int(chinese_chars * 1.5 + english_chars / 4 + punctuation * 0.5)

    def _format_memory_context(self, facts: List[Dict]) -> str:
        """
        格式化召回的记忆为 Markdown
        """
        if not facts:
            return ""

        lines = [
            "## 我想起的过往片段\n",
            self._history_context_header()
        ]

        for fact in facts:
            source = fact.get("source", "memory")
            lines.append(f"- [{source}] {fact['content']}")

        return "\n".join(lines) + "\n"

    def _history_context_header(self) -> str:
        return (
            "下面是我从这个用户过去的对话里想起的一些片段。"
            "它们可能有助于理解背景，但我会以用户此刻说的话为准；"
            "如果过去的信息和当前表达不一致，我会优先相信当前这次对话。\n"
        )


def build_social_memory_context(
    memory_store: Any,
    query: str,
    recent_messages: Optional[List[Dict]] = None,
    retriever: Optional[ActiveMemoryRetriever] = None,
) -> str:
    """Build social-mode memory context.

    Social mode injects the current user's full MEMORY.md first, then appends
    clearly-labeled historical conversation snippets from daily notes.
    """
    sections = []

    if hasattr(memory_store, "get_memory_context"):
        memory_context = memory_store.get_memory_context()
    elif hasattr(memory_store, "read_long_term"):
        long_term = memory_store.read_long_term()
        memory_context = f"## 长期记忆\n{long_term}" if long_term.strip() else ""
    else:
        memory_context = ""

    if memory_context and memory_context.strip():
        sections.append(memory_context.strip())

    history_retriever = retriever or ActiveMemoryRetriever()
    history_context = history_retriever.retrieve(
        memory_store=memory_store,
        query=query,
        recent_messages=recent_messages or [],
    )
    if history_context and history_context.strip():
        sections.append(history_context.strip())

    return "\n\n".join(sections)
