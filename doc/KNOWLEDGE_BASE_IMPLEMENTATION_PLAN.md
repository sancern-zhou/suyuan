# 知识库集成详细实施计划

## 实施概览

| 阶段 | 内容 | 工时 | 产出物 |
|------|------|------|--------|
| Phase 1 | 后端基础设施 | 4天 | 数据模型、向量存储、文档处理 |
| Phase 2 | 后端API与工具 | 3天 | REST API、ReAct工具 |
| Phase 3 | 前端管理页面 | 3天 | 知识库管理界面 |
| Phase 4 | ReAct集成 | 2天 | 工作流集成、选择器组件 |
| Phase 5 | 测试与优化 | 2天 | 测试用例、性能调优 |

**总计: 14天**

---

## 本地资源配置 (已就绪)

### 已下载资源

| 资源 | 本地路径 | 说明 |
|------|----------|------|
| **Tesseract-OCR** | `D:\溯源\Tesseract-OCR` | OCR引擎，含英文语言包 |
| **bge-m3模型** | `D:\溯源\models--BAAI--bge-m3` | HuggingFace缓存格式 |

### 环境变量配置

在 `backend/.env` 中添加：

```env
# ========== 知识库本地资源配置 ==========

# Tesseract OCR路径 (Windows)
TESSERACT_CMD=D:/溯源/Tesseract-OCR/tesseract.exe
TESSDATA_PREFIX=D:/溯源/Tesseract-OCR/tessdata

# HuggingFace本地模型缓存
HF_HOME=D:/溯源
TRANSFORMERS_CACHE=D:/溯源

# bge-m3模型本地路径 (离线加载)
BGE_M3_MODEL_PATH=D:/溯源/models--BAAI--bge-m3/snapshots/5617a9f61b028005a4858fdac845db406aefb181

# 知识库存储
KNOWLEDGE_BASE_STORAGE_DIR=D:/溯源/data/knowledge_base
KNOWLEDGE_BASE_MAX_FILE_SIZE=50MB

# Qdrant配置
QDRANT_HOST=localhost
QDRANT_PORT=6333
```

### 代码中使用本地模型

```python
# backend/app/knowledge_base/vector_store.py

import os

class KnowledgeVectorStore:
    def _init_embedding(self):
        """初始化bge-m3 Embedding模型（优先本地）"""
        from sentence_transformers import SentenceTransformer

        # 优先使用本地模型路径
        local_path = os.getenv("BGE_M3_MODEL_PATH")
        if local_path and os.path.exists(local_path):
            self.embedding_model = SentenceTransformer(local_path)
            logger.info("bge_m3_loaded_from_local", path=local_path)
        else:
            # 回退到在线下载
            self.embedding_model = SentenceTransformer("BAAI/bge-m3")
            logger.info("bge_m3_loaded_from_hub")
```

```python
# backend/app/knowledge_base/document_processor.py

import os

class DocumentProcessor:
    def __init__(self):
        # 配置Tesseract路径
        tesseract_cmd = os.getenv("TESSERACT_CMD")
        if tesseract_cmd:
            import pytesseract
            pytesseract.pytesseract.tesseract_cmd = tesseract_cmd

        tessdata = os.getenv("TESSDATA_PREFIX")
        if tessdata:
            os.environ["TESSDATA_PREFIX"] = tessdata
```

### 中文OCR支持 (可选)

当前tessdata仅含英文(`eng.traineddata`)。如需中文OCR：

```bash
# 下载中文语言包到 D:\溯源\Tesseract-OCR\tessdata\
# 文件: chi_sim.traineddata (简体中文)
# 下载地址: https://github.com/tesseract-ocr/tessdata/raw/main/chi_sim.traineddata
```

---

## Phase 1: 后端基础设施 (4天)

### Day 1: 数据模型与数据库

#### 1.1 创建数据模型文件

**文件**: `backend/app/knowledge_base/models.py`

```
创建内容:
- KnowledgeBaseStatus 枚举
- KnowledgeBaseType 枚举 (PUBLIC/PRIVATE)
- DocumentStatus 枚举
- ChunkingStrategy 枚举 (SEMANTIC/SENTENCE/MARKDOWN/HYBRID)
- KnowledgeBase 模型
- Document 模型
```

#### 1.2 创建Pydantic模式

**文件**: `backend/app/knowledge_base/schemas.py`

```python
# 需要创建的Schema:
class KnowledgeBaseCreate(BaseModel):
    name: str
    description: str = ""
    kb_type: str = "private"
    chunking_strategy: str = "sentence"
    chunk_size: int = 256
    chunk_overlap: int = 64

class KnowledgeBaseResponse(BaseModel):
    id: str
    name: str
    description: str
    kb_type: str
    status: str
    document_count: int
    chunk_count: int
    is_owner: bool
    created_at: datetime

class DocumentCreate(BaseModel):
    filename: str
    metadata: Dict[str, Any] = {}

class DocumentResponse(BaseModel):
    id: str
    filename: str
    file_type: str
    file_size: int
    status: str
    chunk_count: int
    error_message: Optional[str]
    created_at: datetime

class SearchRequest(BaseModel):
    query: str
    knowledge_base_ids: Optional[List[str]] = None
    top_k: int = 5
    score_threshold: float = 0.5
    use_reranker: bool = True

class SearchResult(BaseModel):
    content: str
    score: float
    rerank_score: Optional[float]
    document_id: str
    filename: str
    knowledge_base: Dict[str, str]
    metadata: Dict[str, Any]
```

#### 1.3 数据库迁移

```bash
# 命令序列:
cd backend
alembic revision --autogenerate -m "add_knowledge_base_tables"
alembic upgrade head
```

**验证SQL**:
```sql
-- 检查表创建
SELECT table_name FROM information_schema.tables
WHERE table_schema = 'public' AND table_name IN ('knowledge_bases', 'documents');

-- 检查索引
CREATE INDEX idx_kb_owner ON knowledge_bases(owner_id);
CREATE INDEX idx_kb_type ON knowledge_bases(kb_type);
CREATE INDEX idx_doc_kb ON documents(knowledge_base_id);
CREATE INDEX idx_doc_status ON documents(status);
```

---

### Day 2: 向量存储封装

#### 2.1 创建向量存储模块

**文件**: `backend/app/knowledge_base/vector_store.py`

```python
class KnowledgeVectorStore:
    """知识库向量存储封装"""

    def __init__(self):
        self.qdrant_client = None
        self.embedding_model = None
        self._init_client()
        self._init_embedding()

    def _init_client(self):
        """初始化Qdrant客户端"""
        from qdrant_client import QdrantClient
        self.qdrant_client = QdrantClient(
            host=os.getenv("QDRANT_HOST", "localhost"),
            port=int(os.getenv("QDRANT_PORT", 6333))
        )

    def _init_embedding(self):
        """初始化bge-m3 Embedding模型"""
        from sentence_transformers import SentenceTransformer
        self.embedding_model = SentenceTransformer("BAAI/bge-m3")
        # 维度: 1024

    async def create_collection(self, collection_name: str):
        """创建Qdrant Collection"""
        from qdrant_client.models import Distance, VectorParams

        self.qdrant_client.create_collection(
            collection_name=collection_name,
            vectors_config=VectorParams(
                size=1024,  # bge-m3 维度
                distance=Distance.COSINE
            )
        )

    async def delete_collection(self, collection_name: str):
        """删除Collection"""
        self.qdrant_client.delete_collection(collection_name)

    async def add_chunks(
        self,
        collection_name: str,
        chunks: List[Dict[str, Any]],
        metadata: Dict[str, Any]
    ):
        """添加文档分块到向量库"""
        from qdrant_client.models import PointStruct

        # 批量生成embedding
        texts = [chunk["content"] for chunk in chunks]
        embeddings = self.embedding_model.encode(texts, normalize_embeddings=True)

        # 构建点
        points = []
        for i, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
            points.append(PointStruct(
                id=self._generate_point_id(metadata["document_id"], i),
                vector=embedding.tolist(),
                payload={
                    "content": chunk["content"],
                    "chunk_index": i,
                    "start_char": chunk.get("start_char"),
                    "end_char": chunk.get("end_char"),
                    **metadata
                }
            ))

        # 批量插入
        self.qdrant_client.upsert(
            collection_name=collection_name,
            points=points
        )

    async def search(
        self,
        collection_name: str,
        query: str,
        top_k: int = 5,
        score_threshold: float = 0.5,
        filters: Optional[Dict] = None
    ) -> List[Dict[str, Any]]:
        """向量检索"""
        # 生成查询向量
        query_embedding = self.embedding_model.encode(
            query, normalize_embeddings=True
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
        return [
            {
                "content": hit.payload.get("content"),
                "score": hit.score,
                "document_id": hit.payload.get("document_id"),
                "filename": hit.payload.get("filename"),
                "metadata": {
                    k: v for k, v in hit.payload.items()
                    if k not in ["content", "document_id", "filename"]
                }
            }
            for hit in results
        ]

    async def delete_by_document(self, collection_name: str, document_id: str):
        """删除文档的所有向量"""
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
```

---

### Day 3: 文档处理器

#### 3.1 创建文档处理模块

**文件**: `backend/app/knowledge_base/document_processor.py`

```python
class DocumentProcessor:
    """文档解析和分块处理器"""

    def __init__(self):
        self._unstructured = None

    async def parse(self, file_path: str) -> str:
        """解析文档内容"""
        from unstructured.partition.auto import partition

        elements = partition(filename=file_path)
        content = "\n\n".join([str(el) for el in elements])

        return content

    async def chunk(
        self,
        content: str,
        strategy: str = "sentence",
        chunk_size: int = 256,
        chunk_overlap: int = 64
    ) -> List[Dict[str, Any]]:
        """智能分块"""
        from llama_index.core.node_parser import (
            SentenceSplitter,
            SemanticSplitterNodeParser,
            MarkdownNodeParser,
            HierarchicalNodeParser
        )
        from llama_index.core import Document

        doc = Document(text=content)

        # 选择分块策略
        if strategy == "semantic":
            from llama_index.embeddings.huggingface import HuggingFaceEmbedding
            embed_model = HuggingFaceEmbedding(model_name="BAAI/bge-m3")
            parser = SemanticSplitterNodeParser(
                embed_model=embed_model,
                buffer_size=1,
                breakpoint_percentile_threshold=95
            )
        elif strategy == "markdown":
            parser = MarkdownNodeParser()
        elif strategy == "hybrid":
            parser = HierarchicalNodeParser.from_defaults(
                chunk_sizes=[1024, 256, 64]
            )
        else:  # sentence (默认)
            parser = SentenceSplitter(
                chunk_size=chunk_size,
                chunk_overlap=chunk_overlap
            )

        nodes = parser.get_nodes_from_documents([doc])

        return [
            {
                "id": f"chunk_{i}",
                "content": node.text,
                "metadata": node.metadata,
                "start_char": getattr(node, "start_char_idx", None),
                "end_char": getattr(node, "end_char_idx", None)
            }
            for i, node in enumerate(nodes)
        ]
```

#### 3.2 创建分块策略配置

**文件**: `backend/app/knowledge_base/chunking_strategies.py`

```python
CHUNKING_STRATEGIES = {
    "semantic": {
        "name": "语义分块",
        "description": "基于语义相似度自动分块，保持语义完整性",
        "pros": ["语义完整", "检索精准"],
        "cons": ["速度较慢", "需要embedding模型"],
        "recommended_for": ["技术文档", "研究论文"]
    },
    "sentence": {
        "name": "句子分块",
        "description": "按句子边界切分，固定大小",
        "pros": ["速度快", "简单可靠"],
        "cons": ["可能切断上下文"],
        "recommended_for": ["通用文档", "默认选择"]
    },
    "markdown": {
        "name": "Markdown分块",
        "description": "按Markdown标题层级切分",
        "pros": ["保持文档结构", "层次清晰"],
        "cons": ["仅适用于MD格式"],
        "recommended_for": ["技术文档", "API文档"]
    },
    "hybrid": {
        "name": "混合分块",
        "description": "先按标题，再按句子，支持多层次检索",
        "pros": ["层次丰富", "检索灵活"],
        "cons": ["存储量大"],
        "recommended_for": ["长篇报告", "书籍章节"]
    }
}
```

---

### Day 4: 权限与服务层

#### 4.1 创建权限检查模块

**文件**: `backend/app/knowledge_base/permissions.py`

```python
class KnowledgeBasePermissions:
    """知识库权限管理"""

    @staticmethod
    async def get_accessible_kbs(
        db: AsyncSession,
        user_id: Optional[str] = None,
        include_public: bool = True
    ) -> List[KnowledgeBase]:
        """获取用户可访问的知识库"""
        from sqlalchemy import select, or_

        conditions = []

        if include_public:
            conditions.append(
                KnowledgeBase.kb_type == KnowledgeBaseType.PUBLIC
            )

        if user_id:
            conditions.append(
                (KnowledgeBase.kb_type == KnowledgeBaseType.PRIVATE) &
                (KnowledgeBase.owner_id == user_id)
            )

        if not conditions:
            return []

        query = select(KnowledgeBase).where(
            or_(*conditions),
            KnowledgeBase.status == KnowledgeBaseStatus.ACTIVE
        )

        result = await db.execute(query)
        return result.scalars().all()

    @staticmethod
    def can_manage(
        kb: KnowledgeBase,
        user_id: str,
        is_admin: bool = False
    ) -> bool:
        """检查管理权限"""
        if kb.kb_type == KnowledgeBaseType.PUBLIC:
            return is_admin
        return kb.owner_id == user_id

    @staticmethod
    def can_search(
        kb: KnowledgeBase,
        user_id: Optional[str] = None
    ) -> bool:
        """检查检索权限"""
        if kb.kb_type == KnowledgeBaseType.PUBLIC:
            return True
        return kb.owner_id == user_id
```

#### 4.2 创建服务层

**文件**: `backend/app/knowledge_base/service.py`

```python
class KnowledgeBaseService:
    """知识库核心服务"""

    def __init__(self, db: AsyncSession = None):
        self.db = db
        self.processor = DocumentProcessor()
        self.vector_store = KnowledgeVectorStore()
        self._reranker = None

    def _get_reranker(self):
        """延迟加载Reranker"""
        if self._reranker is None:
            from sentence_transformers import CrossEncoder
            self._reranker = CrossEncoder("BAAI/bge-reranker-v2-m3")
        return self._reranker

    # CRUD方法实现 (见设计文档3.5节)
    # - create_knowledge_base
    # - get_knowledge_base
    # - list_knowledge_bases
    # - update_knowledge_base
    # - delete_knowledge_base
    # - upload_document
    # - delete_document
    # - search
    # - _rerank
```

---

## Phase 2: 后端API与工具 (3天)

### Day 5: REST API实现

#### 5.1 创建API路由

**文件**: `backend/app/api/knowledge_base_routes.py`

```python
router = APIRouter(prefix="/knowledge-base", tags=["Knowledge Base"])

# 知识库CRUD
@router.post("/")                      # 创建知识库
@router.get("/")                       # 列出知识库
@router.get("/{kb_id}")               # 获取详情
@router.put("/{kb_id}")               # 更新配置
@router.delete("/{kb_id}")            # 删除知识库

# 文档管理
@router.post("/{kb_id}/documents")    # 上传文档
@router.get("/{kb_id}/documents")     # 列出文档
@router.delete("/{kb_id}/documents/{doc_id}")  # 删除文档
@router.post("/{kb_id}/documents/{doc_id}/retry")  # 重试处理

# 检索
@router.post("/search")               # 检索知识库
```

#### 5.2 注册路由

**修改文件**: `backend/app/main.py`

```python
from app.api.knowledge_base_routes import router as kb_router

app.include_router(kb_router, prefix="/api")
```

---

### Day 6: ReAct工具实现

#### 6.1 创建知识库检索工具

**文件**: `backend/app/tools/knowledge/search_knowledge_base/__init__.py`

```python
from .tool import SearchKnowledgeBaseTool

__all__ = ["SearchKnowledgeBaseTool"]
```

**文件**: `backend/app/tools/knowledge/search_knowledge_base/tool.py`

```python
class SearchKnowledgeBaseTool(LLMTool):
    """知识库检索工具 (见设计文档3.4节)"""

    name = "search_knowledge_base"
    description = """..."""
    parameters = {...}

    async def execute(self, **kwargs) -> Dict[str, Any]:
        """执行检索"""
        pass
```

#### 6.2 注册工具到Registry

**修改文件**: `backend/app/tools/__init__.py`

```python
# 在 create_global_tool_registry() 中添加:
from app.tools.knowledge.search_knowledge_base import SearchKnowledgeBaseTool

registry.register_tool("search_knowledge_base", SearchKnowledgeBaseTool())
```

---

### Day 7: 异步任务处理

#### 7.1 创建文档处理任务

**文件**: `backend/app/knowledge_base/tasks.py`

```python
import asyncio
from typing import Dict, Any

class DocumentProcessingTask:
    """异步文档处理任务"""

    def __init__(self, service: KnowledgeBaseService):
        self.service = service
        self._processing_queue: asyncio.Queue = asyncio.Queue()
        self._is_running = False

    async def enqueue(self, doc_id: str, kb_id: str, file_path: str):
        """添加到处理队列"""
        await self._processing_queue.put({
            "doc_id": doc_id,
            "kb_id": kb_id,
            "file_path": file_path
        })

    async def start_worker(self):
        """启动后台处理worker"""
        self._is_running = True
        while self._is_running:
            try:
                task = await asyncio.wait_for(
                    self._processing_queue.get(),
                    timeout=1.0
                )
                await self._process_document(task)
            except asyncio.TimeoutError:
                continue

    async def _process_document(self, task: Dict[str, Any]):
        """处理单个文档"""
        try:
            await self.service.process_document(
                doc_id=task["doc_id"],
                kb_id=task["kb_id"],
                file_path=task["file_path"]
            )
        except Exception as e:
            logger.error(
                "document_processing_failed",
                doc_id=task["doc_id"],
                error=str(e)
            )
```

---

## Phase 3: 前端管理页面 (3天)

### Day 8: 基础组件

#### 8.1 创建Store

**文件**: `frontend/src/stores/knowledgeBaseStore.js`

```javascript
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import * as api from '@/api/knowledgeBase'

export const useKnowledgeBaseStore = defineStore('knowledgeBase', () => {
  // 状态
  const knowledgeBases = ref([])
  const selectedIds = ref([])
  const currentKb = ref(null)
  const loading = ref(false)

  // 计算属性
  const publicKbs = computed(() =>
    knowledgeBases.value.filter(kb => kb.kb_type === 'public')
  )
  const privateKbs = computed(() =>
    knowledgeBases.value.filter(kb => kb.kb_type === 'private')
  )

  // Actions
  async function fetchKnowledgeBases() {
    loading.value = true
    try {
      const data = await api.listKnowledgeBases()
      knowledgeBases.value = data
    } finally {
      loading.value = false
    }
  }

  function toggleSelection(id) {
    const index = selectedIds.value.indexOf(id)
    if (index > -1) {
      selectedIds.value.splice(index, 1)
    } else {
      selectedIds.value.push(id)
    }
  }

  return {
    knowledgeBases,
    selectedIds,
    currentKb,
    loading,
    publicKbs,
    privateKbs,
    fetchKnowledgeBases,
    toggleSelection
  }
})
```

#### 8.2 创建API模块

**文件**: `frontend/src/api/knowledgeBase.js`

```javascript
import request from '@/utils/request'

const BASE_URL = '/api/knowledge-base'

export async function listKnowledgeBases() {
  const { data } = await request.get(BASE_URL)
  return data
}

export async function createKnowledgeBase(params) {
  const { data } = await request.post(BASE_URL, params)
  return data
}

export async function deleteKnowledgeBase(id) {
  await request.delete(`${BASE_URL}/${id}`)
}

export async function uploadDocument(kbId, file, metadata = {}) {
  const formData = new FormData()
  formData.append('file', file)
  formData.append('metadata', JSON.stringify(metadata))

  const { data } = await request.post(
    `${BASE_URL}/${kbId}/documents`,
    formData,
    { headers: { 'Content-Type': 'multipart/form-data' } }
  )
  return data
}

export async function searchKnowledgeBase(params) {
  const { data } = await request.post(`${BASE_URL}/search`, params)
  return data
}
```

---

### Day 9: 管理页面组件

#### 9.1 知识库卡片

**文件**: `frontend/src/components/knowledge/KnowledgeBaseCard.vue`

#### 9.2 文档上传器

**文件**: `frontend/src/components/knowledge/DocumentUploader.vue`

#### 9.3 文档列表

**文件**: `frontend/src/components/knowledge/DocumentList.vue`

#### 9.4 创建对话框

**文件**: `frontend/src/components/knowledge/CreateKnowledgeBaseDialog.vue`

---

### Day 10: 管理页面整合

#### 10.1 知识库管理视图

**文件**: `frontend/src/views/KnowledgeBaseView.vue`

(见设计文档4.3节)

#### 10.2 路由配置

**修改文件**: `frontend/src/router/index.js`

```javascript
{
  path: '/knowledge-base',
  name: 'KnowledgeBase',
  component: () => import('@/views/KnowledgeBaseView.vue'),
  meta: { title: '知识库管理' }
}
```

#### 10.3 侧边栏入口

**修改文件**: `frontend/src/components/AssistantSidebar.vue`

```javascript
// 在modules数组中添加
{
  id: 'knowledge-base',
  name: '知识库管理',
  desc: '管理和维护知识库',
  ready: true,
  isManagement: true
}
```

---

## Phase 4: ReAct集成 (2天)

### Day 11: 知识库选择器

#### 11.1 选择器组件

**文件**: `frontend/src/components/knowledge/KnowledgeBaseSelector.vue`

(见设计文档4.2节)

#### 11.2 InputBox集成

**修改文件**: `frontend/src/components/InputBox.vue`

```vue
<template>
  <div class="input-box">
    <!-- 新增：知识库选择器 -->
    <div class="input-options">
      <KnowledgeBaseSelector />
    </div>

    <!-- 现有输入区域 -->
    ...
  </div>
</template>
```

---

### Day 12: 后端工作流集成

#### 12.1 分析请求扩展

**修改文件**: `backend/app/api/analysis_routes.py` (或对应文件)

```python
class AnalyzeRequest(BaseModel):
    query: str
    session_id: Optional[str] = None
    assistant_mode: Optional[str] = None
    knowledge_base_ids: Optional[List[str]] = None  # 新增
    enable_rag: bool = True  # 新增
```

#### 12.2 ExpertRouterV3集成

**修改文件**: `backend/app/agent/experts/expert_router_v3.py`

```python
async def execute_pipeline(
    self,
    user_query: str,
    use_full_chemistry: bool = False,
    knowledge_base_ids: Optional[List[str]] = None  # 新增
) -> PipelineResult:

    # 1. 知识库检索
    rag_context = ""
    if knowledge_base_ids:
        rag_context = await self._retrieve_knowledge(
            query=user_query,
            knowledge_base_ids=knowledge_base_ids
        )

    # 2. 增强查询解析
    enhanced_query = user_query
    if rag_context:
        enhanced_query = f"用户查询: {user_query}\n\n相关知识背景:\n{rag_context}"

    # 后续流程...
```

#### 12.3 ReactAgent参数透传

**修改文件**: `backend/app/agent/react_agent.py`

```python
async def analyze(
    self,
    user_query: str,
    ...
    knowledge_base_ids: Optional[List[str]] = None  # 新增
) -> AsyncGenerator[Dict[str, Any], None]:

    # 传递给专家路由器
    pipeline_task = asyncio.create_task(
        expert_router.execute_pipeline(
            user_query,
            use_full_chemistry=use_full_chemistry,
            knowledge_base_ids=knowledge_base_ids  # 新增
        )
    )
```

---

## Phase 5: 测试与优化 (2天)

### Day 13: 测试用例

#### 13.1 后端单元测试

**文件**: `backend/tests/test_knowledge_base.py`

```python
import pytest
from app.knowledge_base.service import KnowledgeBaseService

class TestKnowledgeBaseService:

    @pytest.fixture
    async def service(self, db_session):
        return KnowledgeBaseService(db=db_session)

    async def test_create_knowledge_base(self, service):
        """测试创建知识库"""
        kb = await service.create_knowledge_base(
            name="测试知识库",
            kb_type="private",
            owner_id="user_123"
        )
        assert kb.id is not None
        assert kb.name == "测试知识库"

    async def test_permission_isolation(self, service):
        """测试权限隔离"""
        # 创建用户A的私有知识库
        kb_a = await service.create_knowledge_base(
            name="用户A的知识库",
            kb_type="private",
            owner_id="user_a"
        )

        # 用户B不应该能看到
        kbs_for_b = await service.list_knowledge_bases(
            user_id="user_b",
            include_public=False
        )
        assert kb_a.id not in [kb.id for kb in kbs_for_b]

    async def test_search_with_reranker(self, service):
        """测试带Reranker的检索"""
        results = await service.search(
            query="大气污染防治",
            top_k=5,
            use_reranker=True
        )
        # 验证rerank_score存在
        for r in results:
            assert "rerank_score" in r
```

#### 13.2 API集成测试

**文件**: `backend/tests/test_knowledge_base_api.py`

```python
import pytest
from httpx import AsyncClient

class TestKnowledgeBaseAPI:

    async def test_create_and_list(self, client: AsyncClient):
        """测试创建和列表API"""
        # 创建
        response = await client.post("/api/knowledge-base/", json={
            "name": "测试知识库",
            "kb_type": "private"
        })
        assert response.status_code == 200
        kb_id = response.json()["id"]

        # 列表
        response = await client.get("/api/knowledge-base/")
        assert response.status_code == 200
        assert any(kb["id"] == kb_id for kb in response.json())

    async def test_document_upload(self, client: AsyncClient, test_pdf):
        """测试文档上传"""
        # 先创建知识库
        kb_response = await client.post("/api/knowledge-base/", json={
            "name": "文档测试库"
        })
        kb_id = kb_response.json()["id"]

        # 上传文档
        with open(test_pdf, "rb") as f:
            response = await client.post(
                f"/api/knowledge-base/{kb_id}/documents",
                files={"file": ("test.pdf", f, "application/pdf")}
            )
        assert response.status_code == 200
        assert response.json()["status"] in ["processing", "completed"]
```

---

### Day 14: 性能优化

#### 14.1 批量处理优化

```python
# vector_store.py 中添加批量插入
async def add_chunks_batch(
    self,
    collection_name: str,
    all_chunks: List[Dict],
    batch_size: int = 100
):
    """批量添加分块"""
    for i in range(0, len(all_chunks), batch_size):
        batch = all_chunks[i:i + batch_size]
        await self.add_chunks(collection_name, batch, ...)
```

#### 14.2 缓存优化

```python
# service.py 中添加embedding缓存
from functools import lru_cache

@lru_cache(maxsize=1000)
def _cached_embed(self, text: str) -> List[float]:
    """缓存常见查询的embedding"""
    return self.vector_store.embedding_model.encode(
        text, normalize_embeddings=True
    ).tolist()
```

#### 14.3 监控指标

```python
# 添加Prometheus指标
from prometheus_client import Counter, Histogram

KB_SEARCH_LATENCY = Histogram(
    'kb_search_latency_seconds',
    'Knowledge base search latency',
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0]
)

KB_SEARCH_COUNT = Counter(
    'kb_search_total',
    'Total knowledge base searches',
    ['status']
)
```

---

## 依赖清单

### Python依赖 (requirements.txt追加)

```txt
# 知识库核心
unstructured[all-docs]>=0.15.0
llama-index>=0.10.0
llama-index-embeddings-huggingface>=0.2.0
sentence-transformers>=2.2.0

# 可选：OCR增强
pytesseract>=0.3.10
pdf2image>=1.16.0
```

### 系统依赖

```bash
# Ubuntu/Debian
apt-get install -y poppler-utils tesseract-ocr tesseract-ocr-chi-sim

# Windows
# 手动安装 poppler 和 tesseract
```

### 前端依赖

```bash
# 无新增npm依赖，使用现有UI组件
```

---

## 验收检查清单

### Phase 1 验收
- [ ] 数据库表创建成功
- [ ] Qdrant Collection创建/删除正常
- [ ] 文档解析支持PDF/Word/Excel
- [ ] 四种分块策略可配置

### Phase 2 验收
- [ ] 知识库CRUD API正常
- [ ] 文档上传异步处理
- [ ] search_knowledge_base工具注册成功
- [ ] 权限隔离生效

### Phase 3 验收
- [ ] 知识库管理页面可访问
- [ ] 文档上传进度显示
- [ ] 公共/个人知识库分组展示

### Phase 4 验收
- [ ] 知识库选择器在InputBox显示
- [ ] 选中知识库参与分析
- [ ] RAG增强效果可验证

### Phase 5 验收
- [ ] 单元测试通过率 > 90%
- [ ] API响应时间 < 2s
- [ ] 检索延迟P95 < 500ms
