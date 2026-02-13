"""
知识库权限管理

实现公共/个人知识库的权限检查和访问控制。
"""

from typing import List, Optional
from sqlalchemy import select, or_
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

        规则:
        - 公共知识库: 所有用户可见
        - 个人知识库: 仅创建者可见

        Args:
            db: 数据库会话
            user_id: 用户ID（可选）
            include_public: 是否包含公共知识库
            status: 状态过滤

        Returns:
            可访问的知识库列表
        """
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

        if not conditions:
            return []

        # 构建查询
        query = select(KnowledgeBase).where(or_(*conditions))

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

        规则:
        - 公共知识库: 仅管理员可管理
        - 个人知识库: 仅创建者可管理

        Args:
            kb: 知识库对象
            user_id: 用户ID
            is_admin: 是否为管理员

        Returns:
            是否有管理权限
        """
        if kb.is_public:
            return is_admin
        else:
            return kb.owner_id == user_id

    @staticmethod
    def can_search(
        kb: KnowledgeBase,
        user_id: Optional[str] = None
    ) -> bool:
        """
        检查用户是否有检索权限

        规则:
        - 公共知识库: 所有人可检索
        - 个人知识库: 仅创建者可检索

        Args:
            kb: 知识库对象
            user_id: 用户ID

        Returns:
            是否有检索权限
        """
        if kb.is_public:
            return True
        else:
            return kb.owner_id == user_id

    @staticmethod
    def can_upload(
        kb: KnowledgeBase,
        user_id: Optional[str] = None,
        is_admin: bool = False
    ) -> bool:
        """
        检查用户是否有上传文档权限

        规则:
        - 公共知识库: 所有人都可上传（包括匿名用户）
        - 个人知识库: 仅创建者可上传

        Args:
            kb: 知识库对象
            user_id: 用户ID
            is_admin: 是否为管理员

        Returns:
            是否有上传权限
        """
        if kb.is_public:
            return True  # 公共知识库允许匿名上传
        else:
            return kb.owner_id == user_id  # 个人知识库需要是创建者

    @staticmethod
    async def filter_accessible_ids(
        db: AsyncSession,
        knowledge_base_ids: List[str],
        user_id: Optional[str] = None
    ) -> List[str]:
        """
        过滤出用户可访问的知识库ID

        Args:
            db: 数据库会话
            knowledge_base_ids: 待检查的知识库ID列表
            user_id: 用户ID

        Returns:
            可访问的知识库ID列表
        """
        if not knowledge_base_ids:
            return []

        # 获取所有可访问的知识库
        accessible_kbs = await KnowledgeBasePermissions.get_accessible_knowledge_bases(
            db=db,
            user_id=user_id,
            include_public=True
        )
        accessible_ids = {kb.id for kb in accessible_kbs}

        # 过滤
        return [kb_id for kb_id in knowledge_base_ids if kb_id in accessible_ids]
