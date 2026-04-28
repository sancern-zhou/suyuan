"""
知识库Pydantic模式

定义API请求和响应的数据模式。
"""

from pydantic import BaseModel, Field, validator
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum


class KnowledgeBaseTypeEnum(str, Enum):
    """知识库类型枚举"""
    PUBLIC = "public"
    PRIVATE = "private"


class ChunkingStrategyEnum(str, Enum):
    """分块策略枚举"""
    SEMANTIC = "semantic"
    SENTENCE = "sentence"
    MARKDOWN = "markdown"
    HYBRID = "hybrid"
    LLM = "llm"


class LLMModeEnum(str, Enum):
    """LLM分块模式枚举"""
    LOCAL = "local"    # 本地千问3（默认，25000字符阈值）
    ONLINE = "online"  # 线上API（60000字符阈值）


class KnowledgeBaseStatusEnum(str, Enum):
    """知识库状态枚举"""
    ACTIVE = "active"
    BUILDING = "building"
    FAILED = "failed"
    ARCHIVED = "archived"


class DocumentStatusEnum(str, Enum):
    """文档状态枚举"""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


# ============ 知识库相关 ============

class KnowledgeBaseCreate(BaseModel):
    """创建知识库请求"""
    name: str = Field(..., min_length=1, max_length=128, description="知识库名称")
    description: str = Field(default="", max_length=1000, description="知识库描述")
    kb_type: KnowledgeBaseTypeEnum = Field(
        default=KnowledgeBaseTypeEnum.PRIVATE,
        description="知识库类型：public(公共) / private(个人)"
    )
    chunking_strategy: ChunkingStrategyEnum = Field(
        default=ChunkingStrategyEnum.SENTENCE,
        description="分块策略"
    )
    chunk_size: int = Field(default=256, ge=64, le=2048, description="分块大小")
    chunk_overlap: int = Field(default=64, ge=0, le=512, description="分块重叠")
    is_default: bool = Field(default=False, description="是否默认启用")

    @validator("chunk_overlap")
    def validate_overlap(cls, v, values):
        chunk_size = values.get("chunk_size", 256)
        if v >= chunk_size:
            raise ValueError("chunk_overlap must be less than chunk_size")
        return v


class KnowledgeBaseUpdate(BaseModel):
    """更新知识库请求"""
    name: Optional[str] = Field(None, min_length=1, max_length=128)
    description: Optional[str] = Field(None, max_length=1000)
    is_default: Optional[bool] = None
    chunking_strategy: Optional[ChunkingStrategyEnum] = None
    chunk_size: Optional[int] = Field(None, ge=64, le=2048)
    chunk_overlap: Optional[int] = Field(None, ge=0, le=512)


class KnowledgeBaseResponse(BaseModel):
    """知识库响应"""
    id: str
    name: str
    description: str
    kb_type: str
    status: str
    document_count: int
    chunk_count: int
    total_size: int = Field(description="总文件大小（字节）")
    is_owner: bool = Field(description="当前用户是否是创建者")
    is_default: bool
    chunking_strategy: str
    chunk_size: int
    chunk_overlap: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class KnowledgeBaseListResponse(BaseModel):
    """知识库列表响应"""
    public: List[KnowledgeBaseResponse] = Field(description="公共知识库列表")
    private: List[KnowledgeBaseResponse] = Field(description="个人知识库列表")
    total: int


# ============ 文档相关 ============

class DocumentCreate(BaseModel):
    """创建文档请求（元数据）"""
    metadata: Dict[str, Any] = Field(default_factory=dict, description="自定义元数据")


class DocumentResponse(BaseModel):
    """文档响应"""
    id: str
    filename: str
    file_type: Optional[str]
    file_size: int
    status: str
    chunk_count: int
    error_message: Optional[str]
    extra_metadata: Dict[str, Any] = Field(default_factory=dict, alias="extra_metadata")
    created_at: datetime
    processed_at: Optional[datetime]
    # 溯源相关字段
    file_storage_type: Optional[str] = Field(default=None, description="存储类型：database/local/oss")
    file_mime_type: Optional[str] = Field(default=None, description="MIME类型")
    has_original_file: bool = Field(default=False, description="是否有原文件可下载")
    preview_text: Optional[str] = Field(default=None, description="文档预览文本")

    class Config:
        from_attributes = True
        populate_by_name = True


class DocumentListResponse(BaseModel):
    """文档列表响应"""
    documents: List[DocumentResponse]
    total: int
    processing: int = Field(description="处理中的文档数")
    failed: int = Field(description="处理失败的文档数")


# ============ 检索相关 ============

class SearchRequest(BaseModel):
    """检索请求"""
    query: str = Field(..., min_length=1, max_length=2000, description="检索查询")
    knowledge_base_ids: Optional[List[str]] = Field(
        default=None,
        description="知识库ID列表，不指定则检索所有可访问的知识库"
    )
    top_k: int = Field(default=5, ge=1, le=20, description="返回结果数量")
    score_threshold: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="相似度阈值"
    )
    use_reranker: bool = Field(default=True, description="是否使用Reranker精排")
    filters: Optional[Dict[str, Any]] = Field(
        default=None,
        description="元数据过滤条件"
    )


class SearchResultItem(BaseModel):
    """单个检索结果"""
    content: str = Field(description="匹配内容")
    original_content: Optional[str] = Field(default=None, description="原文分块内容")
    context_prefix: Optional[str] = Field(default=None, description="检索增强上下文前缀")
    embedding_text: Optional[str] = Field(default=None, description="实际用于向量化/精排的文本")
    score: float = Field(description="最终得分")
    rerank_score: Optional[float] = Field(default=None, description="Reranker得分（Reranker可用时）")
    original_score: Optional[float] = Field(default=None, description="向量检索原始得分（Reranker可用时）")
    document_id: str
    filename: str
    knowledge_base: Dict[str, str] = Field(description="知识库信息")
    metadata: Dict[str, Any] = Field(description="文档元数据")
    chunk_index: Optional[int] = Field(default=None, description="分块索引")
    section: Optional[str] = Field(default=None, description="章节")
    topic: Optional[str] = Field(default=None, description="主题")
    # 溯源相关字段
    document: Optional[Dict[str, Any]] = Field(default=None, description="原文档信息")
    download_url: Optional[str] = Field(default=None, description="原文件下载链接")
    preview_url: Optional[str] = Field(default=None, description="文档预览链接")
    has_original_file: bool = Field(default=False, description="是否有原文件可下载")


class SearchResult(BaseModel):
    """检索结果响应"""
    status: str
    results: List[SearchResultItem]
    total: int
    query: str
    knowledge_base_ids: Optional[List[str]]
    elapsed_ms: Optional[float] = Field(description="检索耗时（毫秒）")


# ============ 统计相关 ============

class KnowledgeBaseStats(BaseModel):
    """知识库统计信息"""
    total_knowledge_bases: int
    total_documents: int
    total_chunks: int
    total_size: int
    public_count: int
    private_count: int
    processing_documents: int
    failed_documents: int


# ============ 分块策略信息 ============

class ChunkingStrategyInfo(BaseModel):
    """分块策略信息"""
    id: str
    name: str
    description: str
    pros: List[str]
    cons: List[str]
    recommended_for: List[str]


class ChunkingStrategiesResponse(BaseModel):
    """分块策略列表响应"""
    strategies: List[ChunkingStrategyInfo]


# ============ 文档分段相关 ============

class DocumentChunk(BaseModel):
    """文档分段"""
    chunk_index: int = Field(description="分块索引")
    content: str = Field(description="分块内容")
    original_content: Optional[str] = Field(default=None, description="原文分块内容")
    context_prefix: Optional[str] = Field(default=None, description="检索增强上下文前缀")
    embedding_text: Optional[str] = Field(default=None, description="实际用于向量化/精排的文本")
    chunk_id: Optional[str] = Field(description="分块ID")
    start_char: Optional[int] = Field(description="起始字符位置")
    end_char: Optional[int] = Field(description="结束字符位置")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="分块元数据")


class DocumentChunksResponse(BaseModel):
    """文档分段响应"""
    document_id: str
    filename: str
    chunks: List[DocumentChunk]
    total: int
