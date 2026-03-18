# 知识库集成设计方案

## 1. 概述

### 1.1 设计目标

在现有ReAct Agent架构中集成知识库系统，实现：

1. **知识库检索工具**：作为ReAct工作流中的检索节点，支持RAG增强
2. **前端知识库选择**：用户可选择启用的知识库参与分析
3. **知识库管理界面**：支持用户创建、管理和维护知识库
4. **多租户权限隔离**：支持公共知识库和个人知识库

### 1.2 知识库类型

| 类型 | 说明 | 可见性 | 管理权限 |
|------|------|--------|----------|
| **公共知识库** | 系统级共享知识库，所有用户可检索 | 全体用户 | 仅管理员 |
| **个人知识库** | 用户私有知识库，仅本人可见 | 仅创建者 | 创建者本人 |

**典型场景**：
- **公共知识库**：大气污染防治政策法规、排放标准、行业技术规范、通用分析案例
- **个人知识库**：用户上传的企业资料、历史分析报告、个人研究文档

### 1.3 技术选型

| 组件 | 技术方案 | 说明 |
|------|---------|------|
| 文档解析 | Unstructured | 支持50+格式，自动清洗 |
| 分块策略 | LlamaIndex | 语义分块，灵活配置 |
| 向量存储 | Qdrant (已有) | 复用现有基础设施 |
| Embedding | BAAI/bge-m3 | 中英双语，8192 token上下文 |
| Reranker | BAAI/bge-reranker-v2-m3 | 精排重排序，提升召回质量 |

---

## 2. 系统架构

### 2.1 整体架构图

```
┌─────────────────────────────────────────────────────────────────────┐
│                           前端 (Vue 3)                               │
├─────────────────────────────────────────────────────────────────────┤
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────────┐  │
│  │ AssistantSidebar│  │  InputBox       │  │ KnowledgeBaseManager│  │
│  │ + 知识库选择器   │  │  + 知识库开关    │  │ (新增管理页面)       │  │
│  └────────┬────────┘  └────────┬────────┘  └──────────┬──────────┘  │
└───────────┼────────────────────┼─────────────────────┼──────────────┘
            │                    │                     │
            ▼                    ▼                     ▼
┌─────────────────────────────────────────────────────────────────────┐
│                           后端 API                                   │
├─────────────────────────────────────────────────────────────────────┤
│  /api/analyze (已有)          /api/knowledge-base/* (新增)           │
│  + knowledge_base_ids参数      - CRUD操作                            │
│                                - 文档上传/解析                        │
└────────────────────────────────┬────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────────┐
│                        ReAct Agent 核心                              │
├─────────────────────────────────────────────────────────────────────┤
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │                    ExpertRouterV3                            │    │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐        │    │
│  │  │ Weather  │ │Component │ │   Viz    │ │  Report  │        │    │
│  │  │ Executor │ │ Executor │ │ Executor │ │ Executor │        │    │
│  │  └──────────┘ └──────────┘ └──────────┘ └──────────┘        │    │
│  └─────────────────────────────────────────────────────────────┘    │
│                                 │                                    │
│                                 ▼                                    │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │                    Tool Registry                             │    │
│  │  ┌────────────────────────────────────────────────────────┐ │    │
│  │  │ knowledge_base_search (新增)                            │ │    │
│  │  │ - 接收: query, knowledge_base_ids                       │ │    │
│  │  │ - 返回: 相关文档片段 + 元数据                            │ │    │
│  │  └────────────────────────────────────────────────────────┘ │    │
│  │  ┌────────────────────────────────────────────────────────┐ │    │
│  │  │ 其他工具 (get_weather_data, calculate_pmf, ...)        │ │    │
│  │  └────────────────────────────────────────────────────────┘ │    │
│  └─────────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────────┐
│                        存储层                                        │
├─────────────────────────────────────────────────────────────────────┤
│  ┌─────────────────────┐  ┌─────────────────────────────────────┐   │
│  │ PostgreSQL          │  │ Qdrant (已有)                        │   │
│  │ - 知识库元数据       │  │ - 文档向量存储                       │   │
│  │ - 文档信息          │  │ - Collection per 知识库              │   │
│  │ - 用户权限          │  │ - 语义检索                           │   │
│  └─────────────────────┘  └─────────────────────────────────────┘   │
│                                                                      │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │ 文件存储 (本地/OSS)                                          │    │
│  │ - 原始文档存储                                               │    │
│  │ - 解析后的分块缓存                                           │    │
│  └─────────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────────┘
```

### 2.2 知识库权限架构

```
┌─────────────────────────────────────────────────────────────────────┐
│                         知识库权限模型                                │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │                    公共知识库 (Public)                         │   │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐         │   │
│  │  │ 排放标准 │ │ 政策法规 │ │ 技术规范 │ │ 通用案例 │         │   │
│  │  └──────────┘ └──────────┘ └──────────┘ └──────────┘         │   │
│  │  可见性: 全体用户 | 管理权限: 系统管理员                       │   │
│  └──────────────────────────────────────────────────────────────┘   │
│                                                                      │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │                    个人知识库 (Private)                        │   │
│  │  ┌─────────────────┐  ┌─────────────────┐                     │   │
│  │  │ 用户A的知识库    │  │ 用户B的知识库    │  ...               │   │
│  │  │ - 企业资料      │  │ - 研究文档      │                     │   │
│  │  │ - 历史报告      │  │ - 个人笔记      │                     │   │
│  │  └─────────────────┘  └─────────────────┘                     │   │
│  │  可见性: 仅创建者 | 管理权限: 创建者本人                        │   │
│  └──────────────────────────────────────────────────────────────┘   │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

### 2.3 数据流

```
用户上传文档
     │
     ▼
┌─────────────┐
│ Unstructured│ ← 文档解析 (PDF/Word/Excel/HTML...)
└──────┬──────┘
       │
       ▼
┌─────────────┐
│ LlamaIndex  │ ← 智能分块 (语义/句子/Markdown/混合)
└──────┬──────┘
       │
       ▼
┌─────────────┐
│ bge-m3      │ ← 向量化 (中英双语Embedding)
└──────┬──────┘
       │
       ▼
┌─────────────┐
│   Qdrant    │ ← 向量存储
└─────────────┘

检索流程:
┌─────────────┐
│ 用户查询    │
└──────┬──────┘
       │
       ▼
┌─────────────┐
│ 向量召回    │ ← 多路召回 (top_k * 3)
└──────┬──────┘
       │
       ▼
┌─────────────┐
│ Reranker    │ ← BGE-Reranker精排重排序
└──────┬──────┘
       │
       ▼
┌─────────────┐
│ 返回Top-K   │ ← 最终结果
└─────────────┘
```

---

## 3. 后端设计

### 3.1 目录结构

```
backend/app/
├── knowledge_base/                    # 新增：知识库模块
│   ├── __init__.py
│   ├── models.py                      # 数据模型
│   ├── schemas.py                     # Pydantic模式
│   ├── service.py                     # 业务逻辑
│   ├── document_processor.py          # 文档处理器
│   ├── chunking_strategies.py         # 分块策略
│   └── vector_store.py                # 向量存储封装
├── tools/
│   └── knowledge/                     # 新增：知识库工具
│       └── search_knowledge_base/
│           ├── __init__.py
│           └── tool.py                # 知识库检索工具
└── api/
    └── knowledge_base_routes.py       # 新增：知识库API
```

### 3.2 数据模型

```python
# backend/app/knowledge_base/models.py

from sqlalchemy import Column, String, DateTime, Integer, JSON, ForeignKey, Text, Enum, Boolean
from sqlalchemy.orm import relationship
from datetime import datetime
import enum

class KnowledgeBaseStatus(enum.Enum):
    ACTIVE = "active"
    BUILDING = "building"
    FAILED = "failed"
    ARCHIVED = "archived"

class KnowledgeBaseType(enum.Enum):
    """知识库类型"""
    PUBLIC = "public"    # 公共知识库：所有用户可见
    PRIVATE = "private"  # 个人知识库：仅创建者可见

class DocumentStatus(enum.Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"

class ChunkingStrategy(enum.Enum):
    """分块策略"""
    SEMANTIC = "semantic"    # 语义分块（慢但精准）
    SENTENCE = "sentence"    # 句子分块（快）
    MARKDOWN = "markdown"    # Markdown标题分块
    HYBRID = "hybrid"        # 混合：先按标题，再按句子

class KnowledgeBase(Base):
    """知识库"""
    __tablename__ = "knowledge_bases"

    id = Column(String(36), primary_key=True)
    name = Column(String(128), nullable=False)
    description = Column(Text)

    # 类型和权限
    kb_type = Column(Enum(KnowledgeBaseType), default=KnowledgeBaseType.PRIVATE)
    owner_id = Column(String(36), nullable=True)  # 公共知识库为null，个人知识库为user_id
    is_default = Column(Boolean, default=False)   # 是否默认启用

    # 配置
    embedding_model = Column(String(64), default="BAAI/bge-m3")
    chunking_strategy = Column(Enum(ChunkingStrategy), default=ChunkingStrategy.SENTENCE)
    chunk_size = Column(Integer, default=256)     # 减小默认值，提升检索精度
    chunk_overlap = Column(Integer, default=64)   # 增加重叠，避免信息丢失

    # Qdrant Collection
    qdrant_collection = Column(String(128), unique=True)

    # 状态
    status = Column(Enum(KnowledgeBaseStatus), default=KnowledgeBaseStatus.ACTIVE)
    document_count = Column(Integer, default=0)
    chunk_count = Column(Integer, default=0)

    # 时间戳
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # 关联
    documents = relationship("Document", back_populates="knowledge_base", cascade="all, delete-orphan")

    @property
    def is_public(self) -> bool:
        return self.kb_type == KnowledgeBaseType.PUBLIC

    @property
    def is_private(self) -> bool:
        return self.kb_type == KnowledgeBaseType.PRIVATE


class Document(Base):
    """文档"""
    __tablename__ = "documents"

    id = Column(String(36), primary_key=True)
    knowledge_base_id = Column(String(36), ForeignKey("knowledge_bases.id", ondelete="CASCADE"))

    # 文件信息
    filename = Column(String(256), nullable=False)
    file_path = Column(String(512))
    file_type = Column(String(32))  # pdf, docx, xlsx, html, txt, md
    file_size = Column(Integer)

    # 处理状态
    status = Column(Enum(DocumentStatus), default=DocumentStatus.PENDING)
    chunk_count = Column(Integer, default=0)
    error_message = Column(Text)
    retry_count = Column(Integer, default=0)  # 重试次数

    # 元数据
    metadata = Column(JSON, default={})

    # 时间戳
    created_at = Column(DateTime, default=datetime.utcnow)
    processed_at = Column(DateTime)

    # 关联
    knowledge_base = relationship("KnowledgeBase", back_populates="documents")
```

### 3.3 权限检查服务

```python
# backend/app/knowledge_base/permissions.py

from typing import List, Optional
from .models import KnowledgeBase, KnowledgeBaseType

class KnowledgeBasePermissions:
    """知识库权限检查"""

    @staticmethod
    async def get_accessible_knowledge_bases(
        db,
        user_id: Optional[str] = None,
        include_public: bool = True
    ) -> List[KnowledgeBase]:
        """
        获取用户可访问的知识库列表

        规则:
        - 公共知识库: 所有用户可见
        - 个人知识库: 仅创建者可见
        """
        from sqlalchemy import select, or_

        conditions = []

        # 公共知识库
        if include_public:
            conditions.append(KnowledgeBase.kb_type == KnowledgeBaseType.PUBLIC)

        # 个人知识库（需要user_id）
        if user_id:
            conditions.append(
                (KnowledgeBase.kb_type == KnowledgeBaseType.PRIVATE) &
                (KnowledgeBase.owner_id == user_id)
            )

        query = select(KnowledgeBase).where(or_(*conditions))
        result = await db.execute(query)
        return result.scalars().all()

    @staticmethod
    async def can_manage(
        kb: KnowledgeBase,
        user_id: str,
        is_admin: bool = False
    ) -> bool:
        """
        检查用户是否有管理权限

        规则:
        - 公共知识库: 仅管理员可管理
        - 个人知识库: 仅创建者可管理
        """
        if kb.is_public:
            return is_admin
        else:
            return kb.owner_id == user_id

    @staticmethod
    async def can_search(
        kb: KnowledgeBase,
        user_id: Optional[str] = None
    ) -> bool:
        """
        检查用户是否有检索权限

        规则:
        - 公共知识库: 所有人可检索
        - 个人知识库: 仅创建者可检索
        """
        if kb.is_public:
            return True
        else:
            return kb.owner_id == user_id
```

### 3.4 知识库检索工具

```python
# backend/app/tools/knowledge/search_knowledge_base/tool.py

from typing import Dict, Any, List, Optional
from app.tools.base import LLMTool
import structlog

logger = structlog.get_logger()

class SearchKnowledgeBaseTool(LLMTool):
    """
    知识库检索工具

    作为ReAct Agent的工具节点，支持：
    - 多知识库联合检索（公共+个人）
    - 语义相似度搜索 + Reranker精排
    - 元数据过滤
    - 混合检索（向量+关键词）
    """

    name = "search_knowledge_base"
    description = """
    在用户的私有知识库和公共知识库中检索相关信息。

    **何时使用此工具**：
    - 用户询问政策法规、排放标准、技术规范
    - 需要历史案例、分析报告作为参考
    - 涉及企业信息、工艺流程等背景知识
    - 用户明确提到"根据知识库"、"查阅资料"

    **何时不使用**：
    - 实时数据查询（天气、空气质量）→ 使用专用数据工具
    - 计算分析任务（PMF、OBM）→ 使用分析工具

    参数：
    - query: 检索查询（自然语言）
    - knowledge_base_ids: 要检索的知识库ID列表（可选，不指定则检索所有可用知识库）
    - top_k: 返回结果数量（默认5）
    - score_threshold: 相似度阈值（0-1，默认0.5）
    - filters: 元数据过滤条件（可选）

    返回：
    - 相关文档片段列表，包含内容、来源、相似度分数
    """

    parameters = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "检索查询内容"
            },
            "knowledge_base_ids": {
                "type": "array",
                "items": {"type": "string"},
                "description": "知识库ID列表，不指定则检索所有"
            },
            "top_k": {
                "type": "integer",
                "default": 5,
                "description": "返回结果数量"
            },
            "score_threshold": {
                "type": "number",
                "default": 0.5,
                "description": "相似度阈值"
            },
            "filters": {
                "type": "object",
                "description": "元数据过滤条件"
            }
        },
        "required": ["query"]
    }

    async def execute(
        self,
        query: str,
        knowledge_base_ids: Optional[List[str]] = None,
        top_k: int = 5,
        score_threshold: float = 0.5,
        filters: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """执行知识库检索"""

        from app.knowledge_base.service import KnowledgeBaseService

        service = KnowledgeBaseService()

        try:
            # 执行检索
            results = await service.search(
                query=query,
                knowledge_base_ids=knowledge_base_ids,
                top_k=top_k,
                score_threshold=score_threshold,
                filters=filters
            )

            logger.info(
                "knowledge_base_search_completed",
                query=query[:50],
                result_count=len(results),
                knowledge_bases=knowledge_base_ids
            )

            return {
                "status": "success",
                "success": True,
                "data": results,
                "metadata": {
                    "schema_version": "v2.0",
                    "generator": "search_knowledge_base",
                    "query": query,
                    "knowledge_base_ids": knowledge_base_ids,
                    "result_count": len(results)
                },
                "summary": f"从知识库中检索到 {len(results)} 条相关信息"
            }

        except Exception as e:
            logger.error(
                "knowledge_base_search_failed",
                query=query[:50],
                error=str(e)
            )
            return {
                "status": "failed",
                "success": False,
                "error": str(e),
                "metadata": {
                    "schema_version": "v2.0",
                    "generator": "search_knowledge_base"
                }
            }
```

### 3.5 知识库服务

```python
# backend/app/knowledge_base/service.py

from typing import Dict, Any, List, Optional
from uuid import uuid4
import structlog
import asyncio

from .models import KnowledgeBase, Document, KnowledgeBaseStatus, DocumentStatus, KnowledgeBaseType, ChunkingStrategy
from .document_processor import DocumentProcessor
from .vector_store import KnowledgeVectorStore
from .permissions import KnowledgeBasePermissions

logger = structlog.get_logger()

class KnowledgeBaseService:
    """知识库服务"""

    def __init__(self, db=None, vector_store=None):
        self.db = db
        self.processor = DocumentProcessor()
        self.vector_store = vector_store or KnowledgeVectorStore()
        self.reranker = None  # 延迟加载

    def _get_reranker(self):
        """延迟加载Reranker模型"""
        if self.reranker is None:
            from sentence_transformers import CrossEncoder
            self.reranker = CrossEncoder("BAAI/bge-reranker-v2-m3")
        return self.reranker

    # ============ 知识库CRUD ============

    async def create_knowledge_base(
        self,
        name: str,
        description: str = "",
        kb_type: KnowledgeBaseType = KnowledgeBaseType.PRIVATE,
        owner_id: Optional[str] = None,
        chunking_strategy: ChunkingStrategy = ChunkingStrategy.SENTENCE,
        chunk_size: int = 256,
        chunk_overlap: int = 64
    ) -> KnowledgeBase:
        """创建知识库"""
        kb_id = str(uuid4())
        collection_name = f"kb_{kb_id.replace('-', '_')}"

        # 公共知识库不需要owner_id
        if kb_type == KnowledgeBaseType.PUBLIC:
            owner_id = None

        # 创建Qdrant Collection
        await self.vector_store.create_collection(collection_name)

        # 创建数据库记录
        kb = KnowledgeBase(
            id=kb_id,
            name=name,
            description=description,
            kb_type=kb_type,
            owner_id=owner_id,
            chunking_strategy=chunking_strategy,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            qdrant_collection=collection_name
        )

        # 保存到数据库
        self.db.add(kb)
        await self.db.commit()
        await self.db.refresh(kb)

        logger.info("knowledge_base_created", kb_id=kb_id, name=name, kb_type=kb_type.value)
        return kb

    async def list_knowledge_bases(
        self,
        user_id: Optional[str] = None,
        include_public: bool = True,
        status: Optional[KnowledgeBaseStatus] = None
    ) -> List[KnowledgeBase]:
        """
        列出用户可访问的知识库

        - 公共知识库: 所有用户可见
        - 个人知识库: 仅创建者可见
        """
        kbs = await KnowledgeBasePermissions.get_accessible_knowledge_bases(
            self.db, user_id, include_public
        )

        if status:
            kbs = [kb for kb in kbs if kb.status == status]

        return kbs

    async def delete_knowledge_base(self, kb_id: str, user_id: str, is_admin: bool = False):
        """删除知识库（需要权限检查）"""
        kb = await self.get_knowledge_base(kb_id)

        if not await KnowledgeBasePermissions.can_manage(kb, user_id, is_admin):
            raise PermissionError("无权删除此知识库")

        # 删除Qdrant Collection
        await self.vector_store.delete_collection(kb.qdrant_collection)

        # 删除数据库记录
        await self.db.delete(kb)
        await self.db.commit()

        logger.info("knowledge_base_deleted", kb_id=kb_id)

    # ============ 文档处理 ============

    async def upload_document(
        self,
        kb_id: str,
        file_path: str,
        filename: str,
        metadata: Dict[str, Any] = None
    ) -> Document:
        """上传并处理文档"""
        doc_id = str(uuid4())

        # 创建文档记录
        doc = Document(
            id=doc_id,
            knowledge_base_id=kb_id,
            filename=filename,
            file_path=file_path,
            status=DocumentStatus.PROCESSING,
            metadata=metadata or {}
        )

        try:
            # 1. 解析文档
            parsed_content = await self.processor.parse(file_path)

            # 2. 分块
            kb = await self.get_knowledge_base(kb_id)
            chunks = await self.processor.chunk(
                content=parsed_content,
                strategy=kb.chunking_strategy,
                chunk_size=kb.chunk_size,
                chunk_overlap=kb.chunk_overlap
            )

            # 3. 向量化并存储
            await self.vector_store.add_chunks(
                collection_name=kb.qdrant_collection,
                chunks=chunks,
                metadata={
                    "document_id": doc_id,
                    "filename": filename,
                    **metadata
                }
            )

            doc.status = DocumentStatus.COMPLETED
            doc.chunk_count = len(chunks)

            logger.info(
                "document_processed",
                doc_id=doc_id,
                filename=filename,
                chunk_count=len(chunks)
            )

        except Exception as e:
            doc.status = DocumentStatus.FAILED
            doc.error_message = str(e)
            logger.error("document_processing_failed", doc_id=doc_id, error=str(e))

        return doc

    # ============ 检索 ============

    async def search(
        self,
        query: str,
        user_id: Optional[str] = None,
        knowledge_base_ids: Optional[List[str]] = None,
        top_k: int = 5,
        score_threshold: float = 0.5,
        filters: Optional[Dict[str, Any]] = None,
        use_reranker: bool = True
    ) -> List[Dict[str, Any]]:
        """
        检索知识库（支持权限过滤和Reranker精排）

        流程:
        1. 获取用户可访问的知识库
        2. 多路召回（top_k * 3）
        3. Reranker精排重排序
        4. 返回Top-K结果
        """
        results = []

        # 获取要检索的知识库（权限过滤）
        if knowledge_base_ids:
            # 指定知识库ID时，仍需检查权限
            all_accessible = await self.list_knowledge_bases(user_id=user_id)
            accessible_ids = {kb.id for kb in all_accessible}
            kbs = [
                await self.get_knowledge_base(kb_id)
                for kb_id in knowledge_base_ids
                if kb_id in accessible_ids
            ]
        else:
            # 默认检索所有可访问的知识库
            kbs = await self.list_knowledge_bases(
                user_id=user_id,
                status=KnowledgeBaseStatus.ACTIVE
            )

        # 多路召回（召回更多候选）
        recall_k = top_k * 3 if use_reranker else top_k

        # 并行检索所有知识库
        async def search_single_kb(kb):
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
            # 按向量分数排序
            results.sort(key=lambda x: x["score"], reverse=True)
            results = results[:top_k]

        return results

    async def _rerank(
        self,
        query: str,
        candidates: List[Dict[str, Any]],
        top_k: int
    ) -> List[Dict[str, Any]]:
        """使用BGE-Reranker重排序"""
        reranker = self._get_reranker()

        pairs = [(query, c["content"]) for c in candidates]
        scores = reranker.predict(pairs)

        for i, score in enumerate(scores):
            candidates[i]["rerank_score"] = float(score)
            candidates[i]["original_score"] = candidates[i]["score"]
            candidates[i]["score"] = float(score)  # 使用rerank分数作为最终分数

        candidates.sort(key=lambda x: x["rerank_score"], reverse=True)
        return candidates[:top_k]
```

### 3.6 文档处理器

```python
# backend/app/knowledge_base/document_processor.py

from typing import List, Dict, Any
from pathlib import Path
import structlog

logger = structlog.get_logger()

class DocumentProcessor:
    """
    文档处理器

    使用 Unstructured 进行文档解析
    使用 LlamaIndex 进行智能分块
    """

    def __init__(self):
        self._unstructured = None
        self._llama_index = None

    def _get_unstructured(self):
        """延迟加载 Unstructured"""
        if self._unstructured is None:
            from unstructured.partition.auto import partition
            self._unstructured = partition
        return self._unstructured

    async def parse(self, file_path: str) -> str:
        """
        解析文档

        支持格式：PDF, DOCX, XLSX, PPTX, HTML, TXT, MD, CSV, JSON
        """
        partition = self._get_unstructured()

        try:
            # Unstructured 自动检测文件类型并解析
            elements = partition(filename=file_path)

            # 提取文本内容
            content = "\n\n".join([str(el) for el in elements])

            logger.info(
                "document_parsed",
                file_path=file_path,
                element_count=len(elements),
                content_length=len(content)
            )

            return content

        except Exception as e:
            logger.error("document_parse_failed", file_path=file_path, error=str(e))
            raise

    async def chunk(
        self,
        content: str,
        strategy: str = "semantic",
        chunk_size: int = 512,
        chunk_overlap: int = 50
    ) -> List[Dict[str, Any]]:
        """
        文档分块

        策略：
        - semantic: 语义分块（推荐，保持语义完整性）
        - fixed: 固定长度分块
        - sentence: 按句子分块
        """
        from llama_index.core.node_parser import (
            SentenceSplitter,
            SemanticSplitterNodeParser
        )
        from llama_index.core import Document

        doc = Document(text=content)

        if strategy == "semantic":
            # 语义分块（需要embedding模型，较慢但精准）
            from llama_index.embeddings.huggingface import HuggingFaceEmbedding
            embed_model = HuggingFaceEmbedding(model_name="BAAI/bge-m3")
            parser = SemanticSplitterNodeParser(
                embed_model=embed_model,
                buffer_size=1,
                breakpoint_percentile_threshold=95
            )
        elif strategy == "sentence":
            # 句子分块（快速，推荐默认）
            parser = SentenceSplitter(
                chunk_size=chunk_size,
                chunk_overlap=chunk_overlap
            )
        elif strategy == "markdown":
            # Markdown标题分块（适合结构化文档）
            from llama_index.core.node_parser import MarkdownNodeParser
            parser = MarkdownNodeParser()
        elif strategy == "hybrid":
            # 混合分块：先按标题，再按句子
            from llama_index.core.node_parser import HierarchicalNodeParser
            parser = HierarchicalNodeParser.from_defaults(
                chunk_sizes=[1024, 256, 64]
            )
        else:  # fixed
            parser = SentenceSplitter(
                chunk_size=chunk_size,
                chunk_overlap=chunk_overlap,
                paragraph_separator="\n\n"
            )

        nodes = parser.get_nodes_from_documents([doc])

        chunks = []
        for i, node in enumerate(nodes):
            chunks.append({
                "id": f"chunk_{i}",
                "content": node.text,
                "metadata": node.metadata,
                "start_char": node.start_char_idx,
                "end_char": node.end_char_idx
            })

        logger.info(
            "document_chunked",
            strategy=strategy,
            chunk_count=len(chunks),
            avg_chunk_size=sum(len(c["content"]) for c in chunks) / len(chunks) if chunks else 0
        )

        return chunks
```

### 3.7 API路由

```python
# backend/app/api/knowledge_base_routes.py

from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from typing import List, Optional
from pydantic import BaseModel
import structlog

logger = structlog.get_logger()
router = APIRouter(prefix="/knowledge-base", tags=["Knowledge Base"])


class CreateKnowledgeBaseRequest(BaseModel):
    name: str
    description: str = ""
    kb_type: str = "private"  # "public" | "private"
    chunking_strategy: str = "sentence"
    chunk_size: int = 256
    chunk_overlap: int = 64


class KnowledgeBaseResponse(BaseModel):
    id: str
    name: str
    description: str
    kb_type: str  # "public" | "private"
    status: str
    document_count: int
    chunk_count: int
    is_owner: bool  # 当前用户是否是创建者
    created_at: str


class SearchRequest(BaseModel):
    query: str
    knowledge_base_ids: Optional[List[str]] = None
    top_k: int = 5
    score_threshold: float = 0.5
    use_reranker: bool = True


# ============ 知识库管理 ============

@router.post("/", response_model=KnowledgeBaseResponse)
async def create_knowledge_base(request: CreateKnowledgeBaseRequest):
    """创建知识库"""
    from app.knowledge_base.service import KnowledgeBaseService
    service = KnowledgeBaseService()
    kb = await service.create_knowledge_base(**request.dict())
    return kb


@router.get("/", response_model=List[KnowledgeBaseResponse])
async def list_knowledge_bases():
    """列出所有知识库"""
    from app.knowledge_base.service import KnowledgeBaseService
    service = KnowledgeBaseService()
    return await service.list_knowledge_bases()


@router.get("/{kb_id}", response_model=KnowledgeBaseResponse)
async def get_knowledge_base(kb_id: str):
    """获取知识库详情"""
    pass


@router.delete("/{kb_id}")
async def delete_knowledge_base(kb_id: str):
    """删除知识库"""
    pass


# ============ 文档管理 ============

@router.post("/{kb_id}/documents")
async def upload_document(
    kb_id: str,
    file: UploadFile = File(...),
    metadata: str = Form(default="{}")
):
    """上传文档到知识库"""
    import json
    import tempfile
    import shutil

    # 保存上传的文件
    with tempfile.NamedTemporaryFile(delete=False, suffix=file.filename) as tmp:
        shutil.copyfileobj(file.file, tmp)
        tmp_path = tmp.name

    from app.knowledge_base.service import KnowledgeBaseService
    service = KnowledgeBaseService()

    doc = await service.upload_document(
        kb_id=kb_id,
        file_path=tmp_path,
        filename=file.filename,
        metadata=json.loads(metadata)
    )

    return {
        "id": doc.id,
        "filename": doc.filename,
        "status": doc.status.value,
        "chunk_count": doc.chunk_count
    }


@router.get("/{kb_id}/documents")
async def list_documents(kb_id: str):
    """列出知识库中的文档"""
    pass


@router.delete("/{kb_id}/documents/{doc_id}")
async def delete_document(kb_id: str, doc_id: str):
    """删除文档"""
    pass


# ============ 检索 ============

@router.post("/search")
async def search_knowledge_base(request: SearchRequest):
    """检索知识库"""
    from app.knowledge_base.service import KnowledgeBaseService
    service = KnowledgeBaseService()

    results = await service.search(
        query=request.query,
        knowledge_base_ids=request.knowledge_base_ids,
        top_k=request.top_k,
        score_threshold=request.score_threshold
    )

    return {
        "status": "success",
        "results": results,
        "count": len(results)
    }
```

---

## 4. 前端设计

### 4.1 组件结构

```
frontend/src/
├── views/
│   └── KnowledgeBaseView.vue          # 知识库管理页面
├── components/
│   ├── knowledge/
│   │   ├── KnowledgeBaseList.vue      # 知识库列表
│   │   ├── KnowledgeBaseCard.vue      # 知识库卡片
│   │   ├── DocumentUploader.vue       # 文档上传组件
│   │   ├── DocumentList.vue           # 文档列表
│   │   └── KnowledgeBaseSelector.vue  # 知识库选择器（用于分析页面）
│   └── InputBox.vue                   # 修改：添加知识库选择
├── stores/
│   └── knowledgeBaseStore.js          # 知识库状态管理
└── api/
    └── knowledgeBase.js               # 知识库API
```

### 4.2 知识库选择器组件

```vue
<!-- frontend/src/components/knowledge/KnowledgeBaseSelector.vue -->
<template>
  <div class="kb-selector">
    <div class="kb-header" @click="toggleExpand">
      <span class="kb-icon">📚</span>
      <span class="kb-title">知识库</span>
      <span class="kb-count" v-if="selectedCount > 0">{{ selectedCount }}</span>
      <span class="expand-icon" :class="{ expanded: isExpanded }"></span>
    </div>

    <div class="kb-list" v-show="isExpanded">
      <!-- 公共知识库分组 -->
      <div class="kb-group" v-if="publicKnowledgeBases.length > 0">
        <div class="kb-group-header">公共知识库</div>
        <div
          v-for="kb in publicKnowledgeBases"
          :key="kb.id"
          class="kb-item"
          :class="{ selected: isSelected(kb.id) }"
          @click="toggleSelect(kb.id)"
        >
          <input
            type="checkbox"
            :checked="isSelected(kb.id)"
            @click.stop
            @change="toggleSelect(kb.id)"
          />
          <div class="kb-info">
            <span class="kb-name">
              <span class="kb-type-badge public">公共</span>
              {{ kb.name }}
            </span>
            <span class="kb-meta">{{ kb.document_count }} 文档 / {{ kb.chunk_count }} 片段</span>
          </div>
        </div>
      </div>

      <!-- 个人知识库分组 -->
      <div class="kb-group" v-if="privateKnowledgeBases.length > 0">
        <div class="kb-group-header">我的知识库</div>
        <div
          v-for="kb in privateKnowledgeBases"
          :key="kb.id"
          class="kb-item"
          :class="{ selected: isSelected(kb.id) }"
          @click="toggleSelect(kb.id)"
        >
          <input
            type="checkbox"
            :checked="isSelected(kb.id)"
            @click.stop
            @change="toggleSelect(kb.id)"
          />
          <div class="kb-info">
            <span class="kb-name">
              <span class="kb-type-badge private">个人</span>
              {{ kb.name }}
            </span>
            <span class="kb-meta">{{ kb.document_count }} 文档 / {{ kb.chunk_count }} 片段</span>
          </div>
        </div>
      </div>

      <div v-if="knowledgeBases.length === 0" class="kb-empty">
        暂无可用知识库
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { useKnowledgeBaseStore } from '@/stores/knowledgeBaseStore'

const store = useKnowledgeBaseStore()
const isExpanded = ref(false)

const knowledgeBases = computed(() => store.knowledgeBases)
const publicKnowledgeBases = computed(() => 
  knowledgeBases.value.filter(kb => kb.kb_type === 'public')
)
const privateKnowledgeBases = computed(() => 
  knowledgeBases.value.filter(kb => kb.kb_type === 'private')
)
const selectedIds = computed(() => store.selectedIds)
const selectedCount = computed(() => selectedIds.value.length)

const toggleExpand = () => {
  isExpanded.value = !isExpanded.value
}

const isSelected = (id) => selectedIds.value.includes(id)

const toggleSelect = (id) => {
  store.toggleSelection(id)
}
</script>

<style scoped>
.kb-group-header {
  font-size: 12px;
  color: #666;
  padding: 8px 12px 4px;
  font-weight: 500;
}
.kb-type-badge {
  font-size: 10px;
  padding: 2px 6px;
  border-radius: 4px;
  margin-right: 6px;
}
.kb-type-badge.public {
  background: #e6f7ff;
  color: #1890ff;
}
.kb-type-badge.private {
  background: #f6ffed;
  color: #52c41a;
}
</style>
```

### 4.3 知识库管理页面

```vue
<!-- frontend/src/views/KnowledgeBaseView.vue -->
<template>
  <div class="kb-management">
    <header class="page-header">
      <h1>知识库管理</h1>
      <button class="btn-primary" @click="showCreateDialog = true">
        + 新建知识库
      </button>
    </header>

    <div class="kb-grid">
      <KnowledgeBaseCard
        v-for="kb in knowledgeBases"
        :key="kb.id"
        :knowledge-base="kb"
        @click="selectKnowledgeBase(kb)"
        @delete="handleDelete(kb)"
      />
    </div>

    <!-- 知识库详情面板 -->
    <aside class="kb-detail" v-if="selectedKb">
      <header>
        <h2>{{ selectedKb.name }}</h2>
        <p>{{ selectedKb.description }}</p>
      </header>

      <div class="stats">
        <div class="stat-item">
          <span class="stat-value">{{ selectedKb.document_count }}</span>
          <span class="stat-label">文档数</span>
        </div>
        <div class="stat-item">
          <span class="stat-value">{{ selectedKb.chunk_count }}</span>
          <span class="stat-label">片段数</span>
        </div>
      </div>

      <DocumentUploader
        :knowledge-base-id="selectedKb.id"
        @uploaded="refreshDocuments"
      />

      <DocumentList
        :documents="selectedKb.documents"
        @delete="handleDeleteDocument"
      />
    </aside>

    <!-- 创建知识库对话框 -->
    <CreateKnowledgeBaseDialog
      v-model:visible="showCreateDialog"
      @created="handleCreated"
    />
  </div>
</template>
```

### 4.4 InputBox修改

在现有InputBox组件中添加知识库选择功能：

```vue
<!-- 在 InputBox.vue 中添加 -->
<template>
  <div class="input-box">
    <!-- 知识库选择器 -->
    <div class="input-options">
      <KnowledgeBaseSelector v-model="selectedKnowledgeBases" />
    </div>

    <!-- 现有输入区域 -->
    <div class="input-area">
      <textarea
        v-model="message"
        :placeholder="placeholder"
        :disabled="disabled"
        @keydown.enter.exact="handleSend"
      />
      <button
        class="send-btn"
        :disabled="disabled || !message.trim()"
        @click="handleSend"
      >
        发送
      </button>
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { useKnowledgeBaseStore } from '@/stores/knowledgeBaseStore'
import KnowledgeBaseSelector from './knowledge/KnowledgeBaseSelector.vue'

const kbStore = useKnowledgeBaseStore()
const selectedKnowledgeBases = computed(() => kbStore.selectedIds)

const emit = defineEmits(['send'])

const handleSend = () => {
  emit('send', {
    query: message.value,
    knowledgeBaseIds: selectedKnowledgeBases.value
  })
}
</script>
```

### 4.5 路由配置

```javascript
// frontend/src/router/index.js

{
  path: '/knowledge-base',
  name: 'KnowledgeBase',
  component: () => import('@/views/KnowledgeBaseView.vue'),
  meta: { title: '知识库管理' }
}
```

### 4.6 AssistantSidebar修改

在现有侧边栏添加知识库管理入口：

```javascript
// 在 modules 数组中添加
{
  id: 'knowledge-base',
  name: '知识库管理',
  desc: '管理和维护知识库',
  ready: true,
  isManagement: true  // 标记为管理功能，点击跳转页面
}
```

---

## 5. ReAct工作流集成

### 5.1 分析请求参数扩展

```python
# 修改 /api/analyze 接口

class AnalyzeRequest(BaseModel):
    query: str
    session_id: Optional[str] = None
    assistant_mode: Optional[str] = None
    knowledge_base_ids: Optional[List[str]] = None  # 新增：知识库ID列表
    enable_rag: bool = True  # 新增：是否启用RAG增强
```

### 5.2 专家执行器集成

```python
# 修改 ExpertRouterV3，在执行前自动进行知识库检索

class ExpertRouterV3:

    async def execute_pipeline(
        self,
        user_query: str,
        knowledge_base_ids: Optional[List[str]] = None
    ) -> PipelineResult:
        """执行完整的专家流水线"""
        result = PipelineResult()

        # 1. 知识库检索（如果启用）
        rag_context = ""
        if knowledge_base_ids:
            rag_context = await self._retrieve_knowledge(
                query=user_query,
                knowledge_base_ids=knowledge_base_ids
            )
            result.rag_context = rag_context

        # 2. 结构化解析（增强查询）
        enhanced_query = user_query
        if rag_context:
            enhanced_query = f"""
用户查询: {user_query}

相关知识背景:
{rag_context}
"""

        parsed_query = await self.query_parser.parse(enhanced_query)
        # ... 后续流程

    async def _retrieve_knowledge(
        self,
        query: str,
        knowledge_base_ids: List[str]
    ) -> str:
        """检索知识库"""
        from app.tools.knowledge.search_knowledge_base.tool import SearchKnowledgeBaseTool

        tool = SearchKnowledgeBaseTool()
        result = await tool.execute(
            query=query,
            knowledge_base_ids=knowledge_base_ids,
            top_k=3
        )

        if result["success"] and result["data"]:
            contexts = []
            for item in result["data"]:
                contexts.append(f"[来源: {item['knowledge_base']['name']}]\n{item['content']}")
            return "\n\n---\n\n".join(contexts)

        return ""
```

---

## 6. 部署配置

### 6.1 本地资源 (已下载)

| 资源 | 本地路径 | 说明 |
|------|----------|------|
| **Tesseract-OCR** | `D:\溯源\Tesseract-OCR` | OCR引擎 (v5.x)，含英文语言包 |
| **bge-m3模型** | `D:\溯源\models--BAAI--bge-m3` | HuggingFace缓存格式，1024维中英双语Embedding |

### 6.2 依赖安装

```bash
# Python依赖
pip install unstructured[all-docs]>=0.15.0
pip install llama-index>=0.10.0
pip install llama-index-embeddings-huggingface>=0.2.0
pip install sentence-transformers>=2.2.0  # 用于Embedding和Reranker
pip install pytesseract>=0.3.10           # OCR Python接口

# 系统依赖 - 已下载到本地，无需额外安装
# Tesseract-OCR: D:\溯源\Tesseract-OCR\tesseract.exe
```

### 6.3 环境变量

在 `backend/.env` 中添加：

```env
# ========== 知识库本地资源配置 ==========

# Tesseract OCR路径 (Windows本地)
TESSERACT_CMD=D:/溯源/Tesseract-OCR/tesseract.exe
TESSDATA_PREFIX=D:/溯源/Tesseract-OCR/tessdata

# HuggingFace本地模型缓存目录
HF_HOME=D:/溯源
TRANSFORMERS_CACHE=D:/溯源

# bge-m3模型本地路径 (离线加载，无需联网)
BGE_M3_MODEL_PATH=D:/溯源/models--BAAI--bge-m3/snapshots/5617a9f61b028005a4858fdac845db406aefb181

# 知识库存储
KNOWLEDGE_BASE_STORAGE_DIR=D:/溯源/data/knowledge_base
KNOWLEDGE_BASE_MAX_FILE_SIZE=50MB
KNOWLEDGE_BASE_ALLOWED_TYPES=pdf,docx,xlsx,pptx,html,txt,md,csv,json

# Qdrant配置（复用现有）
QDRANT_HOST=localhost
QDRANT_PORT=6333

# Reranker模型（首次使用时自动下载，或手动下载到本地）
RERANKER_MODEL=BAAI/bge-reranker-v2-m3
```

### 6.4 代码中使用本地模型

```python
# backend/app/knowledge_base/vector_store.py

import os
import structlog

logger = structlog.get_logger()

class KnowledgeVectorStore:
    def _init_embedding(self):
        """初始化bge-m3 Embedding模型（优先本地）"""
        from sentence_transformers import SentenceTransformer

        local_path = os.getenv("BGE_M3_MODEL_PATH")
        if local_path and os.path.exists(local_path):
            self.embedding_model = SentenceTransformer(local_path)
            logger.info("bge_m3_loaded_from_local", path=local_path)
        else:
            self.embedding_model = SentenceTransformer("BAAI/bge-m3")
            logger.info("bge_m3_loaded_from_hub")
```

```python
# backend/app/knowledge_base/document_processor.py

import os

class DocumentProcessor:
    def __init__(self):
        # 配置Tesseract本地路径
        tesseract_cmd = os.getenv("TESSERACT_CMD")
        if tesseract_cmd and os.path.exists(tesseract_cmd):
            import pytesseract
            pytesseract.pytesseract.tesseract_cmd = tesseract_cmd

        tessdata = os.getenv("TESSDATA_PREFIX")
        if tessdata:
            os.environ["TESSDATA_PREFIX"] = tessdata
```

### 6.5 中文OCR支持 (可选)

当前tessdata仅含英文(`eng.traineddata`)。如需中文OCR：

```bash
# 下载中文简体语言包
# 文件: chi_sim.traineddata
# 下载地址: https://github.com/tesseract-ocr/tessdata/raw/main/chi_sim.traineddata
# 放置路径: D:\溯源\Tesseract-OCR\tessdata\chi_sim.traineddata
```

### 6.6 数据库迁移

```bash
# 创建知识库相关表
alembic revision --autogenerate -m "add knowledge base tables"
alembic upgrade head
```

---

## 7. 实施计划

### Phase 1: 后端核心（3-4天）

1. 知识库数据模型和数据库迁移
2. 文档处理器（Unstructured + LlamaIndex）
3. 向量存储封装
4. 知识库CRUD API
5. 知识库检索工具

### Phase 2: 前端管理页面（2-3天）

1. 知识库列表和创建
2. 文档上传和管理
3. 知识库状态展示

### Phase 3: ReAct集成（2天）

1. 分析请求参数扩展
2. 知识库选择器组件
3. 专家执行器集成RAG

### Phase 4: 测试和优化（2天）

1. 端到端测试
2. 检索效果调优
3. 性能优化

---

## 8. 扩展考虑

### 8.1 已实现增强

1. **Reranker精排** ✅：使用BGE-Reranker-v2-m3提升召回质量
2. **权限控制** ✅：公共知识库/个人知识库隔离
3. **多分块策略** ✅：语义/句子/Markdown/混合四种策略
4. **中英双语** ✅：使用bge-m3模型支持中英文

### 8.2 未来增强

1. **混合检索**：向量检索 + BM25全文检索（Elasticsearch）
2. **多模态**：支持图片/表格内容解析（OCR增强）
3. **增量更新**：文档变更时增量更新向量
4. **知识库共享**：支持用户间共享个人知识库
5. **检索分析**：查询日志、热门问题、效果评估
6. **缓存优化**：Redis缓存高频查询结果

### 8.3 监控指标

1. 检索延迟（P50/P95/P99）
2. 召回率/准确率（需人工标注评估）
3. 文档处理成功率/失败原因统计
4. 存储使用量（按知识库/用户统计）
5. Reranker调用耗时
6. 知识库使用热度

### 8.4 安全考虑

1. **文件类型白名单**：限制上传文件类型，防止恶意文件
2. **文件大小限制**：前端50MB限制，后端二次校验
3. **权限隔离**：个人知识库严格隔离，防止越权访问
4. **敏感信息检测**：上传文档时检测敏感信息（可选）
5. **审计日志**：记录知识库操作日志
