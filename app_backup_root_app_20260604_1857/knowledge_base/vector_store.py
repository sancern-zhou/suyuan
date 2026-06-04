"""
知识库向量存储封装

封装Qdrant向量数据库操作，支持：
- Collection创建/删除
- 向量化存储
- 语义检索（Dense）
- 混合检索（Dense + Sparse BM25）
- 按文档删除
"""

import os
import hashlib
from typing import List, Dict, Any, Optional
from collections import Counter
import structlog

logger = structlog.get_logger()


class KnowledgeVectorStore:
    """知识库向量存储封装，支持混合检索"""

    def __init__(self):
        self.qdrant_client = None
        self.embedding_model = None
        self._embedding_dim = 1024  # bge-m3维度
        self._sparse_dim = 30000    # BM25稀疏向量维度
        self._jieba_initialized = False
        self._init_client()
        self._init_embedding()
        self._init_jieba()

    def _init_client(self):
        """初始化Qdrant客户端"""
        try:
            from qdrant_client import QdrantClient

            host = os.getenv("QDRANT_HOST", "localhost")
            port = int(os.getenv("QDRANT_PORT", 6333))
            api_key = os.getenv("QDRANT_API_KEY")
            # 是否使用HTTPS（默认False，使用HTTP）
            use_https = os.getenv("QDRANT_HTTPS", "false").lower() == "true"

            # 构建URL
            protocol = "https" if use_https else "http"
            url = f"{protocol}://{host}:{port}"

            # 超时设置（秒）
            timeout = int(os.getenv("QDRANT_TIMEOUT", "300"))  # 默认5分钟
            
            # 支持API Key认证
            if api_key:
                self.qdrant_client = QdrantClient(
                    url=url,
                    api_key=api_key,
                    timeout=timeout
                )
            else:
                self.qdrant_client = QdrantClient(
                    url=url,
                    timeout=timeout
                )

            logger.info(
                "qdrant_client_initialized",
                url=url,
                auth="api_key" if api_key else "none"
            )
        except Exception as e:
            logger.error("qdrant_client_init_failed", error=str(e))
            raise

    def _init_embedding(self):
        """初始化bge-m3 Embedding模型"""
        try:
            from sentence_transformers import SentenceTransformer

            # 优先使用环境变量中的本地模型路径
            local_path = os.getenv("BGE_M3_MODEL_PATH")

            # 如果环境变量未设置或路径不存在，自动检测项目目录下的 models 文件夹
            if not local_path or not os.path.exists(local_path):
                # 获取当前文件所在目录（backend/app/knowledge_base/）
                current_dir = os.path.dirname(os.path.abspath(__file__))
                # 项目根目录 (backend/)
                project_root = os.path.dirname(os.path.dirname(current_dir))
                # models 目录（使用 bge-m3-model 目录）
                local_path = os.path.join(project_root, "models", "bge-m3-model")

            if local_path and os.path.exists(local_path):
                logger.info("loading_bge_m3_from_local", path=local_path)
                self.embedding_model = SentenceTransformer(local_path)
            else:
                # 回退到在线下载
                logger.info("loading_bge_m3_from_hub")
                self.embedding_model = SentenceTransformer("BAAI/bge-m3")
            
            logger.info("bge_m3_model_loaded")

            # 验证维度
            test_embedding = self.embedding_model.encode("test", normalize_embeddings=True)
            self._embedding_dim = len(test_embedding)
            logger.info("embedding_model_ready", dim=self._embedding_dim)

        except Exception as e:
            logger.error("embedding_model_init_failed", error=str(e))
            raise

    def _init_jieba(self):
        """初始化jieba分词器，加载环保专业词典"""
        try:
            import jieba
            
            # 加载自定义词典
            dict_path = os.getenv("JIEBA_ENV_DICT_PATH")
            if dict_path and os.path.exists(dict_path):
                jieba.load_userdict(dict_path)
                logger.info("jieba_custom_dict_loaded", path=dict_path)
            
            # 添加常用环保专业术语
            env_terms = [
                # 污染物
                "PM2.5", "PM10", "O3", "NOx", "SO2", "CO", "VOCs",
                "臭氧", "氮氧化物", "二氧化硫", "一氧化碳", "挥发性有机物",
                # 标准号
                "GB3095", "HJ663", "HJ664", "HJ644", "DB44",
                # 环保术语
                "源解析", "PMF", "OBM", "EKMA", "敏感性分析",
                "排放清单", "大气污染", "空气质量", "AQI", "IAQI",
                "机动车尾气", "工业排放", "扬尘污染", "光化学反应",
                "边界层", "逆温层", "气象条件", "环境监测"
            ]
            for term in env_terms:
                jieba.add_word(term)
            
            self._jieba_initialized = True
            logger.info("jieba_initialized_with_env_terms")
            
        except Exception as e:
            logger.warning("jieba_init_failed", error=str(e))
            self._jieba_initialized = False

    def _compute_sparse_vector(self, text: str) -> Dict[int, float]:
        """
        计算BM25稀疏向量
        
        Args:
            text: 输入文本
            
        Returns:
            稀疏向量 {index: weight}
        """
        if not self._jieba_initialized:
            return {}
        
        try:
            import jieba
            
            # 分词
            words = list(jieba.cut(text))
            
            # 计算词频
            word_counts = Counter(words)
            total_words = len(words)
            
            if total_words == 0:
                return {}
            
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
            
        except Exception as e:
            logger.warning("sparse_vector_compute_failed", error=str(e))
            return {}

    async def create_collection(self, collection_name: str, enable_hybrid: bool = True) -> bool:
        """
        创建Qdrant Collection，支持混合检索

        Args:
            collection_name: Collection名称
            enable_hybrid: 是否启用混合检索（稠密+稀疏向量）

        Returns:
            是否创建成功
        """
        try:
            from qdrant_client.models import Distance, VectorParams

            # 检查是否已存在
            collections = self.qdrant_client.get_collections().collections
            existing_names = [c.name for c in collections]

            if collection_name in existing_names:
                logger.warning(
                    "collection_already_exists",
                    collection=collection_name
                )
                return True

            if enable_hybrid and self._jieba_initialized:
                # 创建支持混合检索的Collection
                from qdrant_client.models import SparseVectorParams, SparseIndexParams
                
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
            else:
                # 创建仅支持稠密向量的Collection（向后兼容）
                self.qdrant_client.create_collection(
                    collection_name=collection_name,
                    vectors_config=VectorParams(
                        size=self._embedding_dim,
                        distance=Distance.COSINE
                    )
                )
                logger.info(
                    "collection_created_dense_only",
                    collection=collection_name,
                    vector_size=self._embedding_dim
                )
            
            return True

        except Exception as e:
            logger.error(
                "collection_create_failed",
                collection=collection_name,
                error=str(e)
            )
            raise

    async def delete_collection(self, collection_name: str) -> bool:
        """
        删除Qdrant Collection

        Args:
            collection_name: Collection名称

        Returns:
            是否删除成功
        """
        try:
            self.qdrant_client.delete_collection(collection_name)
            logger.info("collection_deleted", collection=collection_name)
            return True
        except Exception as e:
            logger.error(
                "collection_delete_failed",
                collection=collection_name,
                error=str(e)
            )
            return False

    async def add_chunks(
        self,
        collection_name: str,
        chunks: List[Dict[str, Any]],
        metadata: Dict[str, Any],
        enable_hybrid: bool = True
    ) -> int:
        """
        添加文档分块到向量库

        Args:
            collection_name: Collection名称
            chunks: 分块列表 [{"id": str, "content": str, "metadata": dict}, ...]
            metadata: 公共元数据（document_id, filename等）
            enable_hybrid: 是否启用混合向量（稠密+稀疏）

        Returns:
            添加的向量数量
        """
        import asyncio
        return await asyncio.to_thread(
            self._add_chunks_sync, collection_name, chunks, metadata, enable_hybrid
        )

    def _add_chunks_sync(
        self,
        collection_name: str,
        chunks: List[Dict[str, Any]],
        metadata: Dict[str, Any],
        enable_hybrid: bool = True
    ) -> int:
        """同步添加分块（支持混合向量）"""
        if not chunks:
            return 0

        try:
            from qdrant_client.models import PointStruct

            # 批量生成稠密embedding
            texts = [chunk["content"] for chunk in chunks]
            embeddings = self.embedding_model.encode(
                texts,
                normalize_embeddings=True,
                show_progress_bar=False
            )

            # 判断是否使用混合向量
            use_hybrid = enable_hybrid and self._jieba_initialized

            # 构建点
            points = []
            for i, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
                point_id = self._generate_point_id(
                    metadata.get("document_id", ""),
                    i
                )
                
                if use_hybrid:
                    # 混合向量模式：稠密+稀疏
                    from qdrant_client.models import SparseVector
                    sparse_vec = self._compute_sparse_vector(chunk["content"])
                    
                    points.append(PointStruct(
                        id=point_id,
                        vector={
                            "dense": embedding.tolist(),
                            "sparse": SparseVector(
                                indices=list(sparse_vec.keys()),
                                values=list(sparse_vec.values())
                            ) if sparse_vec else SparseVector(indices=[], values=[])
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
                else:
                    # 仅稠密向量模式（向后兼容）
                    points.append(PointStruct(
                        id=point_id,
                        vector=embedding.tolist(),
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

            # 批量插入（分批避免超时）
            batch_size = 100
            for i in range(0, len(points), batch_size):
                batch = points[i:i + batch_size]
                self.qdrant_client.upsert(
                    collection_name=collection_name,
                    points=batch
                )

            logger.info(
                "chunks_added",
                collection=collection_name,
                chunk_count=len(points),
                document_id=metadata.get("document_id")
            )
            return len(points)

        except Exception as e:
            logger.error(
                "chunks_add_failed",
                collection=collection_name,
                error=str(e)
            )
            raise

    async def search(
        self,
        collection_name: str,
        query: str,
        top_k: int = 5,
        score_threshold: float = 0.5,
        filters: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """
        向量检索

        Args:
            collection_name: Collection名称
            query: 查询文本
            top_k: 返回数量
            score_threshold: 相似度阈值
            filters: 过滤条件

        Returns:
            检索结果列表
        """
        try:
            # 生成查询向量
            query_embedding = self.embedding_model.encode(
                query,
                normalize_embeddings=True
            )

            # 构建过滤条件
            qdrant_filter = None
            if filters:
                from qdrant_client.models import Filter, FieldCondition, MatchValue
                conditions = [
                    FieldCondition(key=k, match=MatchValue(value=v))
                    for k, v in filters.items()
                ]
                qdrant_filter = Filter(must=conditions)

            # 检索
            results = self.qdrant_client.search(
                collection_name=collection_name,
                query_vector=query_embedding.tolist(),
                limit=top_k,
                score_threshold=score_threshold,
                query_filter=qdrant_filter
            )

            # 格式化返回
            formatted_results = []
            for hit in results:
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
                "search_completed",
                collection=collection_name,
                query_length=len(query),
                result_count=len(formatted_results)
            )
            return formatted_results

        except Exception as e:
            logger.error(
                "search_failed",
                collection=collection_name,
                error=str(e)
            )
            raise

    async def hybrid_search(
        self,
        collection_name: str,
        query: str,
        top_k: int = 5,
        score_threshold: float = 0.5,
        alpha: float = 0.7,
        filters: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """
        混合检索（Dense + Sparse BM25）
        
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
        # 如果jieba未初始化，降级到纯向量检索
        if not self._jieba_initialized:
            logger.warning("hybrid_search_fallback_no_jieba")
            return await self.search(
                collection_name, query, top_k, score_threshold, filters
            )
        
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
                        ) if sparse_vector else SparseVector(indices=[], values=[]),
                        using="sparse",
                        limit=top_k * 2
                    )
                ],
                query=FusionQuery(fusion=Fusion.RRF),
                limit=top_k,
                query_filter=qdrant_filter
            )

            # 格式化返回
            formatted_results = []
            for hit in results.points:
                score = hit.score if hit.score else 0.0
                if score >= score_threshold:
                    formatted_results.append({
                        "content": hit.payload.get("content"),
                        "score": score,
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

    async def delete_by_document(
        self,
        collection_name: str,
        document_id: str
    ) -> bool:
        """
        删除文档的所有向量

        Args:
            collection_name: Collection名称
            document_id: 文档ID

        Returns:
            是否删除成功
        """
        try:
            from qdrant_client.models import Filter, FieldCondition, MatchValue

            self.qdrant_client.delete(
                collection_name=collection_name,
                points_selector=Filter(
                    must=[FieldCondition(
                        key="document_id",
                        match=MatchValue(value=document_id)
                    )]
                )
            )

            logger.info(
                "document_vectors_deleted",
                collection=collection_name,
                document_id=document_id
            )
            return True

        except Exception as e:
            logger.error(
                "document_vectors_delete_failed",
                collection=collection_name,
                document_id=document_id,
                error=str(e)
            )
            return False

    async def get_collection_info(self, collection_name: str) -> Optional[Dict[str, Any]]:
        """
        获取Collection信息

        Args:
            collection_name: Collection名称

        Returns:
            Collection信息字典，不存在则返回None
        """
        try:
            info = self.qdrant_client.get_collection(collection_name)
            return {
                "name": collection_name,
                "vectors_count": info.vectors_count,
                "points_count": info.points_count,
                "status": info.status.value
            }
        except Exception:
            return None

    def _generate_point_id(self, document_id: str, chunk_index: int) -> int:
        """
        生成唯一的点ID

        Args:
            document_id: 文档ID
            chunk_index: 分块索引

        Returns:
            整数ID
        """
        # 使用MD5哈希生成稳定的整数ID
        hash_input = f"{document_id}_{chunk_index}"
        hash_hex = hashlib.md5(hash_input.encode()).hexdigest()
        # 取前16位转为整数（避免超出范围）
        return int(hash_hex[:16], 16)
