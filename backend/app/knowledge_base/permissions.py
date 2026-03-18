"""
知识库权限管理

实现公共/个人知识库的权限检查和访问控制。

当前策略：保留PUBLIC/PRIVATE概念，但允许所有人访问所有知识库。
"""

from typing import List, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from .models import KnowledgeBase, KnowledgeBaseType, KnowledgeBaseStatus

logger = structlog.get_logger()


class KnowledgeBasePermissions:
    """知识库权限管理"""

    @staticmethod
    async def get_accessible_knowledge_bases(
        db: AsyncSession,
        user_id: Optional[str] = None,
        include_public: bool = True,
        status: Optional[KnowledgeBaseStatus] = None
    ) -> List[KnowledgeBase]:
        """
        获取用户可访问的知识库列表

        当前规则（临时措施）:
        - 所有知识库都可访问（PUBLIC + PRIVATE）
        - 不检查user_id
        - 保留PUBLIC/PRIVATE类型标识，仅用于显示区分

        Args:
            db: 数据库会话
            user_id: 用户ID（暂不使用）
            include_public: 是否包含公共知识库
            status: 状态过滤

        Returns:
            可访问的知识库列表
        """
        # 构建查询：获取所有知识库
        query = select(KnowledgeBase)

        # 状态过滤
        if status:
            query = query.where(KnowledgeBase.status == status)

        # 排序：默认在前，然后按创建时间倒序
        query = query.order_by(
            KnowledgeBase.is_default.desc(),
            KnowledgeBase.created_at.desc()
        )

        result = await db.execute(query)
        return list(result.scalars().all())

    @staticmethod
    def can_manage(
        kb: KnowledgeBase,
        user_id: str,
        is_admin: bool = False
    ) -> bool:
        """
        检查用户是否有管理权限

        当前规则（临时措施）: 所有人可管理所有知识库

        Args:
            kb: 知识库对象
            user_id: 用户ID（暂不使用）
            is_admin: 是否为管理员（暂不使用）

        Returns:
            是否有管理权限
        """
        return True  # 所有人可管理（临时措施）

    @staticmethod
    def can_search(
        kb: KnowledgeBase,
        user_id: Optional[str] = None
    ) -> bool:
        """
        检查用户是否有检索权限

        当前规则（临时措施）: 所有人可检索所有知识库

        Args:
            kb: 知识库对象
            user_id: 用户ID（暂不使用）

        Returns:
            是否有检索权限
        """
        return True  # 所有人可检索

    @staticmethod
    def can_upload(
        kb: KnowledgeBase,
        user_id: Optional[str] = None,
        is_admin: bool = False
    ) -> bool:
        """
        检查用户是否有上传文档权限

        当前规则（临时措施）: 所有人可上传到所有知识库

        Args:
            kb: 知识库对象
            user_id: 用户ID（暂不使用）
            is_admin: 是否为管理员（暂不使用）

        Returns:
            是否有上传权限
        """
        return True  # 所有人可上传

    @staticmethod
    async def filter_accessible_ids(
        db: AsyncSession,
        knowledge_base_ids: List[str],
        user_id: Optional[str] = None
    ) -> List[str]:
        """
        过滤出用户可访问的知识库ID

        当前规则（临时措施）: 返回所有传入的知识库ID，不进行过滤

        Args:
            db: 数据库会话
            knowledge_base_ids: 待检查的知识库ID列表
            user_id: 用户ID（暂不使用）

        Returns:
            可访问的知识库ID列表
        """
        if not knowledge_base_ids:
            return []

        # 返回所有传入的ID，不进行过滤
        return knowledge_base_ids[:]
