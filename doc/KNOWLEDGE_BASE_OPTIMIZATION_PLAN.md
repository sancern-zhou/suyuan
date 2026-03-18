# 知识库检索优化实施方案

> 版本：1.0 | 日期：2024-12 | 状态：待实施

## 概述

本方案针对环保政策和技术规范检索场景，实施两项关键优化：
1. **混合检索（Hybrid Search）**：解决精确匹配问题
2. **Contextual Chunking**：增强分块上下文信息

---

## 一、混合检索（Hybrid Search）实施方案

### 1.1 问题分析

当前纯向量检索在以下场景表现不佳：
- 法规编号查询："DB44/27-2001的排放限值"
- 企业名称查询："广州某某公司的排污许可"
- 条款引用查询："第三十五条规定了什么"

### 1.2 技术方案

采用 **Dense + Sparse 混合检索**，Qdrant 原生支持。

```
检索流程：
┌─────────────────────────────────────────────────────────┐
│                      用户查询                            │
└─────────────────────────────────────────────────────────┘
                           │
              ┌────────────┴────────────┐
              ▼                         ▼
    ┌─────────────────┐       ┌─────────────────┐
    │   Dense 检索     │       │   Sparse 检索   │
    │  (BGE-M3向量)    │       │   (BM25关键词)  │
    └─────────────────┘       └─────────────────┘
              │                         │
              └────────────┬────────────┘
                           ▼
                ┌─────────────────────┐
                │    RRF 融合排序      │
                │ H = (1-α)×S + α×D   │
                └─────────────────────┘
                           │
                           ▼
                ┌─────────────────────┐
                │   Reranker 精排     │
                │  (BGE-Reranker)     │
                └─────────────────────┘
                           │
                           ▼
                    最终结果
```

### 1.3 代码修改

#### 1.3.1 修改 `vector_store.py` - 添加稀疏向量支持

```python
# backend/app/knowledge_base/vector_store.py

import os
import hashlib
import jieba
from typing import List, Dict, Any, Optional
from collections import Counter
import math
import structlog

logger = structlog.get_logger()


class KnowledgeVectorStore:
    """知识库向量存储封装 - 支持混合检索"""

    def __init__(self):
        self.qdrant_client = None
        self.embedding_model = None
        self._embedding_dim = 1024
        self._sparse_dim = 30000  # BM25稀疏向量维度
        self._init_client()
        self._init_embedding()
        self._init_jieba()

    def _init_jieba(self):
        """初始化jieba分词（用于BM25）"""
        # 加载自定义词典（环保专业术语）
        custom_dict_path = os.getenv("JIEBA_CUSTOM_DICT")
        if custom_dict_path and os.path.exists(custom_dict_path):
            jieba.load_userdict(custom_dict_path)
            logger.info("jieba_custom_dict_loaded", path=custom_dict_path)
        
        # 添加环保常用术语
        env_terms = [
            "PM2.5", "PM10", "VOCs", "NOx", "SO2", "CO", "O3",
            "排放限值", "排污许可", "环评", "总量控制",
            "大气污染", "水污染", "固废", "危废",
            "DB44", "GB", "HJ", "AQI", "IAQI"
        ]
        for term in env_terms:
            jieba.add_word(term)
        
        logger.info("jieba_initialized_with_env_terms")

    def _compute_sparse_vector(self, text: str) -> Dict[int, float]:
        """
        计算BM25稀疏向量
        
        Args:
            text: 输入文本
            
        Returns:
            稀疏向量 {index: weight}
        """
        # 分词
        words = list(jieba.cut(text))
        
        # 计算词频
        word_counts = Counter(words)
        total_words = len(words)
        
        # BM25参数
        k1 = 1.5
        b = 0.75
        avg_dl = 500  # 假设平均文档长度
        
        sparse_vector = {}
        for word, count in word_counts.items():
            if len(word) < 2:  # 跳过单字符
                continue
            
            # 计算TF
            tf = count / total_words
            
            # BM25 TF归一化
            tf_normalized = (tf * (k1 + 1)) / (tf + k1 * (1 - b + b * total_words / avg_dl))
            
            # 使用hash映射到固定维度
            index = hash(word) % self._sparse_dim
            
            # 累加（处理hash冲突）
            if index in sparse_vector:
                sparse_vector[index] += tf_normalized
            else:
                sparse_vector[index] = tf_normalized
        
        return sparse_vector

    async def create_collection(self, collection_name: str) -> bool:
        """
        创建Qdrant Collection（支持混合检索）
        """
        try:
            from qdrant_client.models import (
                Distance, VectorParams, SparseVectorParams, SparseIndexParams
            )

            collections = self.qdrant_client.get_collections().collections
            existing_names = [c.name for c in collections]

            if collection_name in existing_names:
                logger.warning("collection_already_exists", collection=collection_name)
                return True

            # 创建支持混合检索的Collection
            self.qdrant_client.create_collection(
                collection_name=collection_name,
                vectors_config={
                    "dense": VectorParams(
                        size=self._embedding_dim,
                        distance=Distance.COSINE
                    )
                },
                sparse_vectors_config={
                    "sparse": SparseVectorParams(
                        index=SparseIndexParams(on_disk=False)
                    )
                }
            )

            logger.info(
                "collection_created_hybrid",
                collection=collection_name,
                dense_dim=self._embedding_dim,
                sparse_dim=self._sparse_dim
            )
            return True

        except Exception as e:
            logger.error("collection_create_failed", error=str(e))
            raise

    def _add_chunks_sync(
        self,
        collection_name: str,
        chunks: List[Dict[str, Any]],
        metadata: Dict[str, Any]
    ) -> int:
        """同步添加分块（包含稠密和稀疏向量）"""
        if not chunks:
            return 0

        try:
            from qdrant_client.models import PointStruct, SparseVector

            texts = [chunk["content"] for chunk in chunks]
            
            # 批量生成稠密向量
            dense_embeddings = self.embedding_model.encode(
                texts,
                normalize_embeddings=True,
                show_progress_bar=False
            )

            points = []
            for i, (chunk, dense_emb) in enumerate(zip(chunks, dense_embeddings)):
                # 计算稀疏向量
                sparse_vec = self._compute_sparse_vector(chunk["content"])
                
                point_id = self._generate_point_id(
                    metadata.get("document_id", ""),
                    i
                )
                
                points.append(PointStruct(
                    id=point_id,
                    vector={
                        "dense": dense_emb.tolist(),
                        "sparse": SparseVector(
                            indices=list(sparse_vec.keys()),
                            values=list(sparse_vec.values())
                        )
                    },
                    payload={
                        "content": chunk["content"],
                        "chunk_index": i,
                        "chunk_id": chunk.get("id", f"chunk_{i}"),
                        "start_char": chunk.get("start_char"),
                        "end_char": chunk.get("end_char"),
                        "chunk_metadata": chunk.get("metadata", {}),
                        **metadata
                    }
                ))

            # 批量插入
            batch_size = 100
            for i in range(0, len(points), batch_size):
                batch = points[i:i + batch_size]
                self.qdrant_client.upsert(
                    collection_name=collection_name,
                    points=batch
                )

            logger.info(
                "chunks_added_hybrid",
                collection=collection_name,
                chunk_count=len(points)
            )
            return len(points)

        except Exception as e:
            logger.error("chunks_add_failed", error=str(e))
            raise

    async def hybrid_search(
        self,
        collection_name: str,
        query: str,
        top_k: int = 5,
        score_threshold: float = 0.5,
        alpha: float = 0.7,  # Dense权重，0.7表示偏向语义
        filters: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """
        混合检索（Dense + Sparse）
        
        Args:
            collection_name: Collection名称
            query: 查询文本
            top_k: 返回数量
            score_threshold: 相似度阈值
            alpha: Dense向量权重 (0-1)，1=纯语义，0=纯关键词
            filters: 过滤条件
            
        Returns:
            检索结果列表
        """
        try:
            from qdrant_client.models import (
                Filter, FieldCondition, MatchValue,
                SparseVector, Prefetch, FusionQuery, Fusion
            )

            # 生成查询向量
            dense_embedding = self.embedding_model.encode(
                query,
                normalize_embeddings=True
            )
            sparse_vector = self._compute_sparse_vector(query)

            # 构建过滤条件
            qdrant_filter = None
            if filters:
                conditions = [
                    FieldCondition(key=k, match=MatchValue(value=v))
                    for k, v in filters.items()
                ]
                qdrant_filter = Filter(must=conditions)

            # 使用Qdrant的混合检索（RRF融合）
            results = self.qdrant_client.query_points(
                collection_name=collection_name,
                prefetch=[
                    Prefetch(
                        query=dense_embedding.tolist(),
                        using="dense",
                        limit=top_k * 2
                    ),
                    Prefetch(
                        query=SparseVector(
                            indices=list(sparse_vector.keys()),
                            values=list(sparse_vector.values())
                        ),
                        using="sparse",
                        limit=top_k * 2
                    )
                ],
                query=FusionQuery(fusion=Fusion.RRF),
                limit=top_k,
                query_filter=qdrant_filter,
                score_threshold=score_threshold
            )

            # 格式化返回
            formatted_results = []
            for hit in results.points:
                formatted_results.append({
                    "content": hit.payload.get("content"),
                    "score": hit.score,
                    "document_id": hit.payload.get("document_id"),
                    "filename": hit.payload.get("filename"),
                    "chunk_index": hit.payload.get("chunk_index"),
                    "metadata": {
                        k: v for k, v in hit.payload.items()
                        if k not in ["content", "document_id", "filename", "chunk_index"]
                    }
                })

            logger.debug(
                "hybrid_search_completed",
                collection=collection_name,
                query=query[:50],
                result_count=len(formatted_results)
            )
            return formatted_results

        except Exception as e:
            logger.error("hybrid_search_failed", error=str(e))
            # 降级到纯向量检索
            logger.warning("falling_back_to_dense_search")
            return await self.search(
                collection_name, query, top_k, score_threshold, filters
            )
```

#### 1.3.2 修改 `service.py` - 使用混合检索

```python
# backend/app/knowledge_base/service.py 中的 search 方法修改

async def search(
    self,
    query: str,
    user_id: Optional[str] = None,
    knowledge_base_ids: Optional[List[str]] = None,
    top_k: int = 5,
    score_threshold: float = 0.5,
    filters: Optional[Dict[str, Any]] = None,
    use_reranker: bool = True,
    use_hybrid: bool = True,  # 新增：是否使用混合检索
    alpha: float = 0.7        # 新增：Dense权重
) -> List[Dict[str, Any]]:
    """
    检索知识库（支持混合检索）
    """
    # ... 获取知识库列表的代码保持不变 ...

    recall_k = top_k * 3 if use_reranker else top_k
    results = []

    async def search_single_kb(kb: KnowledgeBase):
        if use_hybrid:
            # 使用混合检索
            kb_results = await self.vector_store.hybrid_search(
                collection_name=kb.qdrant_collection,
                query=query,
                top_k=recall_k,
                score_threshold=score_threshold,
                alpha=alpha,
                filters=filters
            )
        else:
            # 传统向量检索
            kb_results = await self.vector_store.search(
                collection_name=kb.qdrant_collection,
                query=query,
                top_k=recall_k,
                score_threshold=score_threshold,
                filters=filters
            )
        
        for result in kb_results:
            result["knowledge_base"] = {
                "id": kb.id,
                "name": kb.name,
                "type": kb.kb_type.value
            }
        return kb_results

    all_results = await asyncio.gather(*[search_single_kb(kb) for kb in kbs])
    for kb_results in all_results:
        results.extend(kb_results)

    # Reranker精排
    if use_reranker and len(results) > top_k:
        results = await self._rerank(query, results, top_k)
    else:
        results.sort(key=lambda x: x["score"], reverse=True)
        results = results[:top_k]

    return results
```

### 1.4 环保专业词典

创建自定义分词词典：

```python
# backend/data/jieba_env_dict.txt

# 污染物
PM2.5 100
PM10 100
VOCs 100
非甲烷总烃 100
总悬浮颗粒物 100
可吸入颗粒物 100

# 标准编号
DB44/27 100
GB16297 100
GB13223 100
HJ2.1 100

# 行业术语
排污许可证 100
环境影响评价 100
总量控制 100
达标排放 100
在线监测 100
源解析 100
溯源分析 100
```

---

## 二、Contextual Chunking 实施方案

### 2.1 问题分析

当前LLM分块存在的问题：

**问题1：多segment分块时上下文断裂**
```
长文档 → 拆分为3个segment → 各自调用LLM分块
                              ↓
            Segment 1: 知道是《大气污染防治法》
            Segment 2: 只看到"处罚条款"，不知道是哪个法
            Segment 3: 完全丢失文档信息
```

**问题2：chunk元数据未被利用**
- 已生成 `topic` 和 `type` 元数据
- 未融入chunk内容，检索时无法利用
- chunk脱离文档后，缺少来源信息

### 2.2 优化方案概述

**核心思路**：先生成文档级上下文，再传递给每个segment

```
┌─────────────────────────────────────────────────────────┐
│                      长文档                              │
└─────────────────────────────────────────────────────────┘
                           │
                           ▼
         ┌─────────────────────────────────────┐
         │  Step 1: 文档级上下文生成（1次LLM调用）│
         │  - 标题、类型、主题、关键词           │
         └─────────────────────────────────────┘
                           │
              ┌────────────┼────────────┐
              ▼            ▼            ▼
         Segment 1    Segment 2    Segment 3
              │            │            │
              ▼            ▼            ▼
    ┌─────────────────────────────────────────────────────┐
    │  Step 2: 各segment分块时，携带文档级上下文          │
    │  Prompt: "这是《大气污染防治法》的一部分..."        │
    └─────────────────────────────────────────────────────┘
              │            │            │
              ▼            ▼            ▼
         chunks       chunks       chunks
              │            │            │
              ▼            ▼            ▼
    ┌─────────────────────────────────────────────────────┐
    │  Step 3: 上下文前缀增强                             │
    │  [来源: 大气污染防治法 | 主题: 处罚条款 | ...]      │
    └─────────────────────────────────────────────────────┘
```

### 2.3 技术方案

在存储前为每个chunk添加上下文前缀：

```
原始chunk:
"排放浓度限值为50mg/m³，且排放速率不得超过2.6kg/h"

增强后chunk:
"[来源: 广东省大气污染物排放限值DB44/27-2001 | 主题: 工业锅炉颗粒物排放标准 | 类型: 表格]
排放浓度限值为50mg/m³，且排放速率不得超过2.6kg/h"
```

### 2.4 代码修改

#### 2.4.0 修改 `chunk_with_llm` - 支持文档级上下文传递（关键）

```python
# backend/app/knowledge_base/document_processor.py

async def chunk_with_llm(
    self,
    content: str,
    chunk_size: int = 512,
    filename: str = ""  # 新增：文件名参数
) -> List[Dict[str, Any]]:
    """
    使用本地千问3进行智能分块（支持文档级上下文）
    
    优化点：
    1. 先生成文档级上下文（1次LLM调用）
    2. 将上下文传递给每个segment的分块调用
    3. 确保所有chunk都知道文档全局信息
    """
    if not content.strip():
        return []

    try:
        import asyncio
        
        proxy_url = os.getenv("QWEN3_PROXY_URL", "http://localhost:8088/api")
        
        # ========== 新增：Step 1 - 生成文档级上下文 ==========
        doc_context = await self._generate_doc_context_for_chunking(
            proxy_url=proxy_url,
            content=content,
            filename=filename
        )
        
        logger.info(
            "document_context_generated",
            title=doc_context.get("title", ""),
            doc_type=doc_context.get("doc_type", ""),
            main_topics=doc_context.get("main_topics", [])
        )
        
        # 如果文档过长，先按段落粗分
        if len(content) > LLM_CHUNK_MAX_CHARS:
            segments = self._split_into_segments(content, LLM_CHUNK_MAX_CHARS)
        else:
            segments = [content]

        # 使用信号量限制并发数
        semaphore = asyncio.Semaphore(self.LLM_CHUNK_MAX_CONCURRENT)
        
        async def process_segment(seg_idx: int, segment: str):
            async with semaphore:
                # ========== 关键改动：传递文档上下文 ==========
                chunks = await self._llm_chunk_segment_with_context(
                    proxy_url=proxy_url,
                    segment=segment,
                    chunk_size=chunk_size,
                    doc_context=doc_context,  # 传递文档级上下文
                    segment_index=seg_idx,
                    total_segments=len(segments)
                )
                return (seg_idx, chunks)
        
        # 并发处理所有segments
        tasks = [process_segment(i, seg) for i, seg in enumerate(segments)]
        results = await asyncio.gather(*tasks)
        
        # 按segment顺序合并结果
        results.sort(key=lambda x: x[0])
        
        all_chunks = []
        for seg_idx, chunks in results:
            for chunk in chunks:
                chunk["id"] = f"chunk_{len(all_chunks)}"
                chunk["metadata"]["segment_index"] = seg_idx
                # 将文档级上下文也存入元数据
                chunk["metadata"]["doc_context"] = doc_context
                all_chunks.append(chunk)

        avg_size = sum(len(c["content"]) for c in all_chunks) / len(all_chunks) if all_chunks else 0

        logger.info(
            "document_chunked_with_llm_context",
            chunk_count=len(all_chunks),
            avg_chunk_size=round(avg_size, 1),
            segment_count=len(segments),
            doc_title=doc_context.get("title", "")
        )

        return all_chunks

    except Exception as e:
        logger.error("llm_chunk_failed", error=str(e))
        logger.warning("falling_back_to_sentence_chunking")
        return self._chunk_sync(content, "sentence", chunk_size, chunk_size // 4)


async def _generate_doc_context_for_chunking(
    self,
    proxy_url: str,
    content: str,
    filename: str
) -> Dict[str, Any]:
    """
    生成文档级上下文（用于传递给分块LLM）
    
    只调用1次LLM，分析文档开头和结尾
    """
    import httpx
    
    # 取开头3000字符 + 结尾1000字符
    head = content[:3000]
    tail = content[-1000:] if len(content) > 4000 else ""
    
    sample = f"{head}\n...(中间省略)...\n{tail}" if tail else head
    
    prompt = f"""分析以下文档，提取关键信息用于后续分块。

文件名: {filename}

文档内容（开头和结尾）:
{sample}

请用JSON格式返回：
{{
    "title": "文档完整标题（如：广东省大气污染物排放限值 DB44/27-2001）",
    "doc_type": "文档类型（地方标准/国家标准/法律法规/技术规范/政策文件/研究报告/其他）",
    "issuing_authority": "发布机构（如有）",
    "main_topics": ["主题1", "主题2", "主题3"],
    "structure_hint": "文档结构说明（如：按章节组织/按附录组织/按污染物分类）",
    "keywords": ["关键词1", "关键词2", "关键词3", "关键词4", "关键词5"]
}}"""

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                proxy_url,
                headers={"Content-Type": "application/json"},
                json={
                    "model": "qwen3",
                    "messages": [
                        {"role": "system", "content": "你是文档分析助手，直接返回JSON。"},
                        {"role": "user", "content": prompt}
                    ],
                    "temperature": 0.1
                }
            )
            response.raise_for_status()
            result = response.json()

        result_text = result["choices"][0]["message"]["content"]
        
        json_match = re.search(r'\{[\s\S]*\}', result_text)
        if json_match:
            doc_context = json.loads(json_match.group())
            doc_context["filename"] = filename
            return doc_context
            
    except Exception as e:
        logger.warning("generate_doc_context_failed", error=str(e))
    
    # 降级：基本信息
    return {
        "filename": filename,
        "title": Path(filename).stem if filename else "",
        "doc_type": "",
        "main_topics": [],
        "keywords": []
    }


async def _llm_chunk_segment_with_context(
    self,
    proxy_url: str,
    segment: str,
    chunk_size: int,
    doc_context: Dict[str, Any],
    segment_index: int,
    total_segments: int
) -> List[Dict[str, Any]]:
    """
    对单个segment进行分块（携带文档级上下文）
    
    关键改进：prompt中包含文档标题、类型、主题等全局信息
    """
    import httpx
    
    # 预处理
    segment = self._preprocess_content(segment)
    
    if self._is_toc_content(segment):
        logger.info("skipping_toc_content", content_length=len(segment))
        return []
    
    # 构建文档上下文提示
    doc_title = doc_context.get("title", "")
    doc_type = doc_context.get("doc_type", "")
    main_topics = ", ".join(doc_context.get("main_topics", []))
    keywords = ", ".join(doc_context.get("keywords", []))
    
    context_hint = f"""## 文档信息（重要！请在生成topic时参考）
- 文档标题: {doc_title}
- 文档类型: {doc_type}
- 主要主题: {main_topics}
- 关键词: {keywords}
- 当前位置: 第{segment_index + 1}部分，共{total_segments}部分
"""

    # 优化后的提示词（包含文档上下文）
    prompt = f"""{context_hint}

## 任务
将以下文档片段按语义分块，用于知识库检索。

## 规则
1. 分块大小：500-1500字符，宁大勿小
2. 表格必须完整，与前面的说明文字合并
3. 跳过：纯目录、页眉页脚、版权声明
4. topic要具体：结合上面的文档信息，写明"某某法/标准的某某条款/某某规定"
5. 列表/步骤保持完整

## 输出JSON
{{"chunks":[{{"content":"完整内容","topic":"具体主题（要体现文档名称）","type":"paragraph|table|list"}}]}}

## 文档片段
{segment}"""

    try:
        async with httpx.AsyncClient(timeout=300.0) as client:
            response = await client.post(
                proxy_url,
                headers={"Content-Type": "application/json"},
                json={
                    "model": "qwen3",
                    "messages": [
                        {"role": "system", "content": "你是文档分块助手。直接返回JSON，不要解释。"},
                        {"role": "user", "content": prompt}
                    ],
                    "temperature": 0.1
                }
            )
            response.raise_for_status()
            result = response.json()

        result_text = result["choices"][0]["message"]["content"]
        
        json_match = re.search(r'\{[\s\S]*\}', result_text)
        if json_match:
            parsed = json.loads(json_match.group())
        else:
            return self._fallback_chunk(segment, chunk_size)

        chunks = []
        for i, item in enumerate(parsed.get("chunks", [])):
            chunk_content = item.get("content", "").strip()
            if chunk_content and len(chunk_content) >= 100:
                chunks.append({
                    "id": f"chunk_{i}",
                    "content": chunk_content,
                    "metadata": {
                        "topic": item.get("topic", ""),
                        "type": item.get("type", "paragraph"),
                        "chunking_method": "llm_qwen3_contextual"  # 标记为上下文增强版
                    },
                    "start_char": None,
                    "end_char": None
                })
        
        chunks = self._merge_small_chunks(chunks, min_size=150)
        return chunks if chunks else self._fallback_chunk(segment, chunk_size)

    except Exception as e:
        logger.warning("llm_chunk_segment_with_context_failed", error=str(e))
        return self._fallback_chunk(segment, chunk_size)
```

#### 2.4.1 修改 `document_processor.py` - 上下文前缀增强

```python
# backend/app/knowledge_base/document_processor.py

# 在 chunk_with_llm 方法后添加新方法

def enhance_chunks_with_context(
    self,
    chunks: List[Dict[str, Any]],
    document_context: Dict[str, str]
) -> List[Dict[str, Any]]:
    """
    为分块添加上下文信息（Contextual Chunking）
    
    Args:
        chunks: 分块列表
        document_context: 文档上下文信息
            - filename: 文件名
            - title: 文档标题（可选）
            - doc_type: 文档类型（可选）
            - summary: 文档摘要（可选）
    
    Returns:
        增强后的分块列表
    """
    enhanced_chunks = []
    
    for chunk in chunks:
        # 提取chunk元数据
        metadata = chunk.get("metadata", {})
        topic = metadata.get("topic", "")
        chunk_type = metadata.get("type", "paragraph")
        
        # 构建上下文前缀
        context_parts = []
        
        # 1. 文档来源
        filename = document_context.get("filename", "")
        if filename:
            # 清理文件名（去除扩展名和路径）
            clean_name = Path(filename).stem
            context_parts.append(f"来源: {clean_name}")
        
        # 2. 文档标题（如果有）
        title = document_context.get("title", "")
        if title and title != clean_name:
            context_parts.append(f"标题: {title}")
        
        # 3. 主题（LLM生成的）
        if topic:
            context_parts.append(f"主题: {topic}")
        
        # 4. 内容类型
        type_map = {
            "paragraph": "正文",
            "table": "表格",
            "list": "列表",
            "header": "标题",
            "code": "代码"
        }
        type_label = type_map.get(chunk_type, chunk_type)
        context_parts.append(f"类型: {type_label}")
        
        # 构建上下文字符串
        context_str = " | ".join(context_parts)
        context_prefix = f"[{context_str}]\n"
        
        # 创建增强后的chunk
        enhanced_chunk = chunk.copy()
        enhanced_chunk["content"] = context_prefix + chunk["content"]
        enhanced_chunk["original_content"] = chunk["content"]  # 保留原始内容
        enhanced_chunk["context_prefix"] = context_prefix
        
        enhanced_chunks.append(enhanced_chunk)
    
    logger.info(
        "chunks_enhanced_with_context",
        chunk_count=len(enhanced_chunks),
        sample_context=enhanced_chunks[0]["context_prefix"] if enhanced_chunks else ""
    )
    
    return enhanced_chunks


async def generate_document_context(
    self,
    content: str,
    filename: str
) -> Dict[str, str]:
    """
    使用LLM生成文档级上下文信息
    
    Args:
        content: 文档内容（前2000字符用于分析）
        filename: 文件名
        
    Returns:
        文档上下文信息
    """
    import httpx
    
    proxy_url = os.getenv("QWEN3_PROXY_URL", "http://localhost:8088/api")
    
    # 截取文档开头用于分析
    sample_content = content[:2000]
    
    prompt = f"""分析以下文档，提取关键信息：

文件名: {filename}
文档开头:
{sample_content}

请用JSON格式返回：
{{
    "title": "文档完整标题",
    "doc_type": "文档类型（如：地方标准/国家标准/技术规范/政策文件/研究报告）",
    "summary": "一句话概述文档主要内容（不超过50字）",
    "keywords": ["关键词1", "关键词2", "关键词3"]
}}"""

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                proxy_url,
                headers={"Content-Type": "application/json"},
                json={
                    "model": "qwen3",
                    "messages": [
                        {"role": "system", "content": "你是文档分析助手，直接返回JSON。"},
                        {"role": "user", "content": prompt}
                    ],
                    "temperature": 0.1
                }
            )
            response.raise_for_status()
            result = response.json()

        result_text = result["choices"][0]["message"]["content"]
        
        # 提取JSON
        json_match = re.search(r'\{[\s\S]*\}', result_text)
        if json_match:
            doc_context = json.loads(json_match.group())
            doc_context["filename"] = filename
            return doc_context
            
    except Exception as e:
        logger.warning("generate_document_context_failed", error=str(e))
    
    # 降级：使用文件名作为基本信息
    return {
        "filename": filename,
        "title": Path(filename).stem,
        "doc_type": "",
        "summary": ""
    }
```

#### 2.4.2 修改 `service.py` - 在处理流程中应用增强

```python
# backend/app/knowledge_base/service.py

async def _process_document(
    self,
    doc: Document,
    kb: KnowledgeBase,
    chunking_strategy: str = "llm",
    chunk_size: int = 800,
    chunk_overlap: int = 100
):
    """处理文档：解析、分块、上下文增强、向量化"""
    doc_id = doc.id
    doc_file_path = doc.file_path
    doc_filename = doc.filename
    doc_file_size = doc.file_size
    doc_extra_metadata = dict(doc.extra_metadata) if doc.extra_metadata else {}
    
    kb_id = kb.id
    kb_collection = kb.qdrant_collection

    try:
        # 1. 解析文档
        content = await self.processor.parse(doc_file_path)

        # 2. 生成文档级上下文（新增）
        doc_context = await self.processor.generate_document_context(
            content=content,
            filename=doc_filename
        )
        
        # 保存文档上下文到元数据
        doc_extra_metadata["document_context"] = doc_context

        # 3. 分块
        chunks = await self.processor.chunk(
            content=content,
            strategy=chunking_strategy,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap
        )

        # 4. 上下文增强（新增）
        chunks = self.processor.enhance_chunks_with_context(
            chunks=chunks,
            document_context=doc_context
        )

        # 5. 向量化并存储
        chunk_count = await self.vector_store.add_chunks(
            collection_name=kb_collection,
            chunks=chunks,
            metadata={
                "document_id": doc_id,
                "filename": doc_filename,
                "knowledge_base_id": kb_id,
                "doc_title": doc_context.get("title", ""),
                "doc_type": doc_context.get("doc_type", ""),
                **doc_extra_metadata
            }
        )

        # ... 后续状态更新代码保持不变 ...
```

### 2.4 检索时的处理

由于上下文前缀已融入content，检索时自动受益：
- 向量检索：embedding包含上下文信息，语义更准确
- 关键词检索：可匹配文档标题、标准号等
- 返回结果：用户看到完整的来源信息

---

## 三、数据迁移方案

### 3.1 存量数据处理

对于已存在的知识库数据，需要重新处理：

```python
# backend/scripts/migrate_to_hybrid.py

import asyncio
from app.knowledge_base.service import KnowledgeBaseService
from app.db.database import async_session

async def migrate_knowledge_base(kb_id: str):
    """迁移单个知识库到混合检索格式"""
    async with async_session() as db:
        service = KnowledgeBaseService(db=db)
        
        # 1. 获取知识库
        kb = await service.get_knowledge_base(kb_id)
        if not kb:
            print(f"Knowledge base not found: {kb_id}")
            return
        
        # 2. 获取所有文档
        docs = await service.list_documents(kb_id)
        
        # 3. 删除旧Collection
        old_collection = kb.qdrant_collection
        await service.vector_store.delete_collection(old_collection)
        
        # 4. 创建新Collection（支持混合检索）
        await service.vector_store.create_collection(old_collection)
        
        # 5. 重新处理每个文档
        for doc in docs:
            if doc.status.value == "completed" and doc.file_path:
                try:
                    await service._process_document(
                        doc=doc,
                        kb=kb,
                        chunking_strategy="llm",
                        chunk_size=800,
                        chunk_overlap=100
                    )
                    print(f"Migrated: {doc.filename}")
                except Exception as e:
                    print(f"Failed: {doc.filename} - {e}")

if __name__ == "__main__":
    import sys
    kb_id = sys.argv[1] if len(sys.argv) > 1 else None
    if kb_id:
        asyncio.run(migrate_knowledge_base(kb_id))
    else:
        print("Usage: python migrate_to_hybrid.py <kb_id>")
```

### 3.2 增量数据

新上传的文档自动使用新流程，无需额外处理。

---

## 四、配置与环境变量

```bash
# .env 新增配置

# 混合检索
HYBRID_SEARCH_ENABLED=true
HYBRID_SEARCH_ALPHA=0.7  # Dense权重，0.7偏向语义

# Jieba分词
JIEBA_CUSTOM_DICT=./data/jieba_env_dict.txt

# 上下文增强
CONTEXTUAL_CHUNKING_ENABLED=true
```

---

## 五、测试验证

### 5.1 混合检索测试用例

```python
# tests/test_hybrid_search.py

import pytest

@pytest.mark.asyncio
async def test_exact_match_standard_number():
    """测试精确匹配：标准编号"""
    query = "DB44/27-2001的颗粒物排放限值"
    results = await service.search(query, use_hybrid=True)
    
    # 应该匹配到包含该标准号的文档
    assert any("DB44/27" in r["content"] for r in results)

@pytest.mark.asyncio
async def test_semantic_match():
    """测试语义匹配：概念查询"""
    query = "工厂烟囱排放的废气如何达标"
    results = await service.search(query, use_hybrid=True)
    
    # 应该匹配到排放标准相关内容
    assert len(results) > 0

@pytest.mark.asyncio
async def test_hybrid_vs_pure_vector():
    """对比混合检索与纯向量检索"""
    query = "HJ2.1环评导则"
    
    hybrid_results = await service.search(query, use_hybrid=True)
    vector_results = await service.search(query, use_hybrid=False)
    
    # 混合检索应该在精确查询上表现更好
    hybrid_has_match = any("HJ2.1" in r["content"] for r in hybrid_results)
    vector_has_match = any("HJ2.1" in r["content"] for r in vector_results)
    
    assert hybrid_has_match  # 混合检索必须能匹配
```

### 5.2 上下文增强测试

```python
@pytest.mark.asyncio
async def test_contextual_chunk_format():
    """测试上下文增强格式"""
    chunks = await processor.chunk_with_llm(sample_content)
    enhanced = processor.enhance_chunks_with_context(
        chunks, 
        {"filename": "DB44_27-2001.pdf", "title": "广东省大气污染物排放限值"}
    )
    
    # 检查上下文前缀
    first_chunk = enhanced[0]
    assert first_chunk["content"].startswith("[")
    assert "来源:" in first_chunk["content"]
    assert "主题:" in first_chunk["content"]
```

---

## 六、预期效果

| 指标 | 优化前 | 优化后 | 提升 |
|------|--------|--------|------|
| 精确查询准确率 | ~60% | ~90% | +30% |
| 语义查询准确率 | ~75% | ~80% | +5% |
| 上下文完整性 | 低 | 高 | 显著 |
| 来源可追溯性 | 无 | 有 | 新增 |

---

## 七、实施计划

| 阶段 | 时间 | 任务 | 产出 |
|------|------|------|------|
| **Phase 1** | 第1-2天 | 实现混合检索核心代码 | vector_store.py |
| **Phase 2** | 第3天 | 实现上下文增强 | document_processor.py |
| **Phase 3** | 第4天 | 服务层集成 | service.py |
| **Phase 4** | 第5天 | 测试与调优 | 测试报告 |
| **Phase 5** | 第6-7天 | 数据迁移（可选） | 迁移完成 |

---

## 八、回滚方案

如果新功能出现问题，可通过配置快速回滚：

```python
# 回滚到纯向量检索
use_hybrid=False

# 回滚到无上下文增强
# 在service.py中注释掉enhance_chunks_with_context调用
```

---

## 附录：依赖更新

```bash
# requirements.txt 新增
jieba>=0.42.1  # 中文分词
```

Qdrant版本要求：>= 1.7.0（支持Sparse Vector和Prefetch）
