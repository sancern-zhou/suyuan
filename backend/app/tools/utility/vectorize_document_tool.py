"""
文档向量化工具

将PDF、Word、Excel、TXT等文档解析、分块、向量化并存入知识库。
支持智能知识库选择、批量处理、自动归档等场景。

使用场景：
- Agent帮助用户批量处理文档并存入知识库
- 分析报告生成后自动归档到知识库
- 文档预处理预览
"""

import os
import time
from pathlib import Path
from typing import Dict, Any, Optional
from datetime import datetime

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.tools.base.tool_interface import LLMTool, ToolCategory
from app.knowledge_base.models import KnowledgeBase, KnowledgeBaseStatus, KnowledgeBaseType
from app.knowledge_base.service import KnowledgeBaseService
from app.db.database import async_session

logger = structlog.get_logger()


class VectorizeDocumentTool(LLMTool):
    """
    文档向量化工具

    将本地文档文件解析、分块、向量化并存入知识库，支持智能知识库选择。
    """

    def __init__(self):
        # 当前系统无用户登录时使用占位符
        self.agent_user_id = "agent"

        super().__init__(
            name="vectorize_document",
            description=(
                "将文档文件（PDF/Word/Excel/TXT/MD/HTML）向量化并存入知识库。"
                "支持自动创建知识库、智能分块、自定义元数据。"
                "使用场景：批量处理文档、自动归档分析报告、文档预处理。"
            ),
            category=ToolCategory.QUERY,
            requires_context=False,
        )

    def get_function_schema(self) -> Dict[str, Any]:
        """获取函数调用模式"""
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "文档文件路径（支持绝对路径或相对路径）"
                    },
                    "knowledge_base_id": {
                        "type": "string",
                        "description": "指定知识库ID（可选，优先级最高）"
                    },
                    "knowledge_base_name": {
                        "type": "string",
                        "description": "指定知识库名称（可选，不存在则自动创建）"
                    },
                    "filename": {
                        "type": "string",
                        "description": "自定义文件名（可选，默认使用原文件名）"
                    },
                    "chunking_strategy": {
                        "type": "string",
                        "description": "分块策略：llm(智能分块)/sentence(句子)/semantic(语义)/markdown(MD)/hybrid(混合)，默认llm",
                        "enum": ["llm", "sentence", "semantic", "markdown", "hybrid"]
                    },
                    "chunk_size": {
                        "type": "integer",
                        "description": "分块大小（字符数），默认800"
                    },
                    "chunk_overlap": {
                        "type": "integer",
                        "description": "分块重叠（字符数），默认100"
                    },
                    "llm_mode": {
                        "type": "string",
                        "description": "LLM模式：online(线上API，更快)/local(本地模型)，默认online",
                        "enum": ["online", "local"]
                    },
                    "metadata": {
                        "type": "object",
                        "description": "自定义元数据（可选，用于文档标签、分类等）"
                    }
                },
                "required": ["file_path"]
            }
        }

    async def execute(self, **kwargs) -> Dict[str, Any]:
        """
        执行文档向量化

        Args:
            **kwargs: 工具参数
                - file_path: 文件路径（必需）
                - knowledge_base_id: 知识库ID（可选）
                - knowledge_base_name: 知识库名称（可选）
                - filename: 自定义文件名（可选）
                - chunking_strategy: 分块策略（可选）
                - chunk_size: 分块大小（可选）
                - chunk_overlap: 分块重叠（可选）
                - llm_mode: LLM模式（可选）
                - metadata: 自定义元数据（可选）

        Returns:
            Dict: 工具执行结果
                - success: 是否成功
                - data: 详细数据
                - summary: 简短摘要
                - error: 错误信息（失败时）
                - error_code: 错误代码（失败时）
        """
        # 解析参数
        file_path = kwargs.get("file_path")
        knowledge_base_id = kwargs.get("knowledge_base_id")
        knowledge_base_name = kwargs.get("knowledge_base_name")
        filename = kwargs.get("filename")
        chunking_strategy = kwargs.get("chunking_strategy", "llm")
        chunk_size = kwargs.get("chunk_size", 800)
        chunk_overlap = kwargs.get("chunk_overlap", 100)
        llm_mode = kwargs.get("llm_mode", "online")
        metadata = kwargs.get("metadata")

        # 参数验证
        if not file_path:
            return {
                "success": False,
                "error": "缺少必需参数：file_path",
                "summary": "缺少文件路径参数",
                "error_code": 1
            }

        # 文件路径验证
        validation_result = await self._validate_file_path(file_path)
        if not validation_result["valid"]:
            return {
                "success": False,
                "error": validation_result["error"],
                "summary": validation_result["error"],
                "error_code": validation_result["error_code"]
            }

        validated_path = validation_result["path"]
        actual_filename = filename or os.path.basename(validated_path)

        # 检查文件类型是否支持
        file_ext = Path(validated_path).suffix.lower()
        supported_extensions = {".pdf", ".docx", ".doc", ".xlsx", ".xls", ".txt", ".md", ".markdown", ".html", ".htm"}
        if file_ext not in supported_extensions:
            return {
                "success": False,
                "error": f"不支持的文件类型：{file_ext}，支持的类型：{', '.join(sorted(supported_extensions))}",
                "summary": f"不支持的文件类型：{file_ext}",
                "error_code": 3
            }

        # 开始处理
        started_at = time.time()

        try:
            # 使用独立数据库会话
            async with async_session() as db:
                # 创建服务实例
                kb_service = KnowledgeBaseService(db=db)

                # 智能知识库选择
                kb_selection_result = await self._select_or_create_knowledge_base(
                    kb_service=kb_service,
                    user_id=self.agent_user_id,
                    kb_id=knowledge_base_id,
                    kb_name=knowledge_base_name,
                    chunking_strategy=chunking_strategy,
                    chunk_size=chunk_size,
                    chunk_overlap=chunk_overlap
                )

                if not kb_selection_result["success"]:
                    return {
                        "success": False,
                        "error": kb_selection_result["error"],
                        "summary": kb_selection_result["summary"],
                        "error_code": 4
                    }

                kb = kb_selection_result["knowledge_base"]

                # 调用upload_document
                document = await kb_service.upload_document(
                    kb_id=kb.id,
                    file_path=validated_path,
                    filename=actual_filename,
                    user_id=self.agent_user_id,
                    is_admin=False,
                    metadata=metadata,
                    chunking_strategy=chunking_strategy,
                    chunk_size=chunk_size,
                    chunk_overlap=chunk_overlap,
                    llm_mode=llm_mode
                )

                # 计算处理时间
                processing_time = time.time() - started_at

                # 返回成功结果
                return {
                    "success": True,
                    "data": {
                        "document_id": document.id,
                        "filename": document.filename,
                        "file_type": document.file_type,
                        "file_size": document.file_size,
                        "chunk_count": document.chunk_count,
                        "status": document.status.value,
                        "knowledge_base": {
                            "id": kb.id,
                            "name": kb.name,
                            "type": kb.kb_type.value
                        },
                        "processing_time": round(processing_time, 2),
                        "created_at": document.created_at.isoformat() if document.created_at else None
                    },
                    "summary": (
                        f"文档向量化成功：{document.filename}，"
                        f"分块数: {document.chunk_count}，"
                        f"知识库: {kb.name}，"
                        f"耗时: {processing_time:.2f}秒"
                    )
                }

        except ValueError as e:
            # 知识库不存在、权限错误等
            logger.warning("vectorize_document_value_error", file_path=file_path, error=str(e))
            return {
                "success": False,
                "error": str(e),
                "summary": f"知识库错误：{str(e)}",
                "error_code": 4
            }
        except PermissionError as e:
            # 权限错误
            logger.warning("vectorize_document_permission_error", file_path=file_path, error=str(e))
            return {
                "success": False,
                "error": str(e),
                "summary": f"权限错误：{str(e)}",
                "error_code": 5
            }
        except Exception as e:
            # 处理失败
            logger.error("vectorize_document_failed", file_path=file_path, error=str(e), exc_info=True)
            return {
                "success": False,
                "error": f"文档处理失败：{str(e)}",
                "summary": f"文档处理失败：{str(e)[:100]}",
                "error_code": 6
            }

    async def _validate_file_path(self, file_path: str) -> Dict[str, Any]:
        """
        验证文件路径

        Args:
            file_path: 文件路径

        Returns:
            Dict: 验证结果
                - valid: 是否有效
                - path: 验证后的绝对路径
                - error: 错误信息（无效时）
                - error_code: 错误代码（1=路径无效, 2=文件不存在）
        """
        try:
            # 解析路径（支持~和相对路径）
            expanded_path = Path(file_path).expanduser().resolve()

            # 检查文件是否存在
            if not expanded_path.exists():
                return {
                    "valid": False,
                    "error": f"文件不存在：{file_path}",
                    "error_code": 2
                }

            # 检查是否是文件（不能是目录）
            if not expanded_path.is_file():
                return {
                    "valid": False,
                    "error": f"路径不是文件：{file_path}",
                    "error_code": 1
                }

            # 检查文件是否可读
            if not os.access(expanded_path, os.R_OK):
                return {
                    "valid": False,
                    "error": f"文件不可读：{file_path}",
                    "error_code": 1
                }

            return {
                "valid": True,
                "path": str(expanded_path)
            }

        except Exception as e:
            logger.warning("file_path_validation_failed", file_path=file_path, error=str(e))
            return {
                "valid": False,
                "error": f"路径验证失败：{str(e)}",
                "error_code": 1
            }

    async def _select_or_create_knowledge_base(
        self,
        kb_service: KnowledgeBaseService,
        user_id: str,
        kb_id: Optional[str] = None,
        kb_name: Optional[str] = None,
        chunking_strategy: str = "llm",
        chunk_size: int = 800,
        chunk_overlap: int = 100
    ) -> Dict[str, Any]:
        """
        智能选择或创建知识库

        优先级：
        1. 指定知识库ID → 直接使用
        2. 指定知识库名称 → 查找或创建
        3. 查找默认知识库（is_default=True）
        4. 创建新的默认知识库

        Args:
            kb_service: KnowledgeBaseService实例
            user_id: 用户ID
            kb_id: 知识库ID（可选）
            kb_name: 知识库名称（可选）
            chunking_strategy: 分块策略
            chunk_size: 分块大小
            chunk_overlap: 分块重叠

        Returns:
            Dict: 选择结果
                - success: 是否成功
                - knowledge_base: 知识库对象
                - error: 错误信息（失败时）
                - summary: 错误摘要（失败时）
        """
        # 优先级1: 指定知识库ID
        if kb_id:
            kb = await kb_service.get_knowledge_base(kb_id)
            if kb:
                logger.info("using_specified_kb", kb_id=kb_id, name=kb.name)
                return {
                    "success": True,
                    "knowledge_base": kb
                }
            else:
                return {
                    "success": False,
                    "error": f"指定的知识库不存在：{kb_id}",
                    "summary": "知识库不存在"
                }

        # 优先级2: 指定知识库名称
        if kb_name:
            kbs = await kb_service.list_knowledge_bases(user_id=user_id, include_public=True)
            matching_kbs = [kb for kb in kbs if kb.name == kb_name]

            if matching_kbs:
                # 使用第一个匹配的知识库
                kb = matching_kbs[0]
                logger.info("using_named_kb", kb_name=kb_name, kb_id=kb.id)
                return {
                    "success": True,
                    "knowledge_base": kb
                }
            else:
                # 自动创建新知识库
                try:
                    kb = await kb_service.create_knowledge_base(
                        name=kb_name,
                        description=f"由Agent自动创建的知识库：{kb_name}",
                        kb_type="private",
                        owner_id=user_id,
                        chunking_strategy=chunking_strategy,
                        chunk_size=chunk_size,
                        chunk_overlap=chunk_overlap,
                        is_default=False
                    )
                    logger.info("auto_created_kb", kb_name=kb_name, kb_id=kb.id)
                    return {
                        "success": True,
                        "knowledge_base": kb
                    }
                except Exception as e:
                    logger.error("auto_create_kb_failed", kb_name=kb_name, error=str(e))
                    return {
                        "success": False,
                        "error": f"自动创建知识库失败：{str(e)}",
                        "summary": f"创建知识库失败：{str(e)[:100]}"
                    }

        # 优先级3: 查找默认知识库
        kbs = await kb_service.list_knowledge_bases(user_id=user_id, include_public=True)
        default_kbs = [kb for kb in kbs if kb.is_default and kb.status == KnowledgeBaseStatus.ACTIVE]

        if default_kbs:
            # 使用第一个默认知识库
            kb = default_kbs[0]
            logger.info("using_default_kb", kb_name=kb.name, kb_id=kb.id)
            return {
                "success": True,
                "knowledge_base": kb
            }

        # 优先级4: 创建新的默认知识库
        default_kb_name = "Agent默认知识库"
        try:
            kb = await kb_service.create_knowledge_base(
                name=default_kb_name,
                description="Agent自动创建的默认知识库，用于存储向量化的文档",
                kb_type="private",
                owner_id=user_id,
                chunking_strategy=chunking_strategy,
                chunk_size=chunk_size,
                chunk_overlap=chunk_overlap,
                is_default=True
            )
            logger.info("auto_created_default_kb", kb_id=kb.id)
            return {
                "success": True,
                "knowledge_base": kb
            }
        except Exception as e:
            logger.error("auto_create_default_kb_failed", error=str(e))
            return {
                "success": False,
                "error": f"自动创建默认知识库失败：{str(e)}",
                "summary": "创建默认知识库失败"
            }
